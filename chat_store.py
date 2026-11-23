"""Durable local conversations and an atomic backup snapshot."""
from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from threading import RLock
from uuid import uuid4


class ChatStore:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / 'chats.sqlite3'
        self.lock = RLock()
        backup_path = self.directory / 'chats-backup.sqlite3'
        if not self.path.exists() and backup_path.exists():
            with closing(sqlite3.connect(backup_path)) as source, closing(sqlite3.connect(self.path)) as target:
                if source.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise sqlite3.DatabaseError('Backup integrity check failed.')
                source.backup(target)
        with closing(sqlite3.connect(self.path)) as db:
            db.executescript('CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, document TEXT NOT NULL);'
                             'CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);')
            db.commit()

    def _write(self, sql, values):
        with closing(sqlite3.connect(self.path)) as db:
            db.execute(sql, values)
            db.commit()
            target = self.directory / 'backup.tmp'
            with closing(sqlite3.connect(target)) as backup:
                db.backup(backup)
            target.replace(self.directory / 'chats-backup.sqlite3')

    def save(self, session):
        with self.lock:
            session['updated'] = datetime.now(timezone.utc).isoformat()
            self._write('INSERT OR REPLACE INTO sessions VALUES (?, ?)',
                        (session['id'], json.dumps(session)))
        return session

    def create(self):
        return self.save({'id': str(uuid4()), 'title': 'New conversation', 'messages': [],
                          'draft': '', 'summary': '', 'summary_count': 0})

    def update(self, session_id, **changes):
        with self.lock:
            session = self.get(session_id)
            session.update(changes)
            return self.save(session)

    def get(self, session_id):
        with self.lock, closing(sqlite3.connect(self.path)) as db:
            row = db.execute('SELECT document FROM sessions WHERE id=?', (session_id,)).fetchone()
            if not row:
                raise KeyError('Conversation not found.')
            return json.loads(row[0])

    def delete(self, session_id):
        with self.lock:
            session = self.get(session_id)
            if any(message.get('state') == 'pending' for message in session['messages']):
                raise ValueError('Wait for the reply to finish before deleting this chat.')
            self._write('DELETE FROM sessions WHERE id=?', (session_id,))

    def all(self):
        with self.lock, closing(sqlite3.connect(self.path)) as db:
            return sorted((json.loads(row[0]) for row in db.execute('SELECT document FROM sessions')),
                          key=lambda item: item['updated'], reverse=True)

    def memory(self, value=None):
        with self.lock:
            if value is not None:
                self._write('INSERT OR REPLACE INTO settings VALUES (?, ?)', ('memory', value))
            with closing(sqlite3.connect(self.path)) as db:
                row = db.execute('SELECT value FROM settings WHERE key=?', ('memory',)).fetchone()
            return row[0] if row else ''

    def begin(self, session_id, content, thinking, request_id):
        with self.lock:
            session = self.get(session_id)
            for message in session['messages']:
                if message.get('request_id') == request_id and message['role'] == 'user':
                    if message['content'] != content:
                        raise ValueError('Request ID already belongs to another message.')
                    if message['state'] == 'complete':
                        return session, next(m['result'] for m in session['messages']
                                             if m['role'] == 'assistant' and m.get('request_id') == request_id)
                    if message['state'] == 'pending':
                        raise ValueError('This message is already running. Reopen this chat to see its reply.')
                    message.update(state='pending', error='', thinking=thinking)
                    return self.save(session), None
            if any(m.get('state') == 'pending' for m in session['messages']):
                raise ValueError('A reply is still running in this conversation.')
            session['messages'].append({'role': 'user', 'content': content, 'request_id': request_id,
                                        'state': 'pending', 'thinking': thinking})
            if len(session['messages']) == 1:
                session['title'] = content[:64]
            session['draft'] = ''
            return self.save(session), None

    def finish(self, session_id, request_id, result=None, error=None, tools=None):
        with self.lock:
            session = self.get(session_id)
            user = next(m for m in session['messages'] if m.get('request_id') == request_id and m['role'] == 'user')
            if tools is not None:
                user['tool_calls'] = tools
            elif error:
                if not any(m['role'] == 'assistant' and m.get('request_id') == request_id for m in session['messages']):
                    user.update(state='failed', error=error)
            else:
                user['state'] = 'complete'
                session['messages'].append({'role': 'assistant', 'content': result['reply'],
                                            'request_id': request_id, 'result': result})
            return self.save(session)

    def recover(self):
        for session in self.all():
            changed = False
            for message in session['messages']:
                if message['role'] == 'user' and message.get('state') == 'failed' and any(
                    m['role'] == 'assistant' and m.get('request_id') == message.get('request_id') for m in session['messages']):
                    message.update(state='complete', error='')
                    changed = True
                if message.get('state') == 'pending':
                    message.update(state='failed', error='Server restarted before this reply finished. You can retry it.')
                    changed = True
            if changed:
                self.save(session)
