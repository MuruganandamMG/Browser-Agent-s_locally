import json
from contextlib import closing
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import patch
from uuid import uuid4

from chat_store import ChatStore
import server


class PersistenceTests(unittest.TestCase):
    def test_delete_updates_backup_and_preserves_other_chats(self):
        with TemporaryDirectory() as directory:
            store = ChatStore(directory)
            deleted = store.create()['id']
            kept = store.create()['id']
            store.memory('Keep this memory')
            store.delete(deleted)
            with self.assertRaises(KeyError):
                store.get(deleted)
            store.path.unlink()
            restored = ChatStore(directory)
            self.assertEqual([s['id'] for s in restored.all()], [kept])
            self.assertEqual(restored.memory(), 'Keep this memory')

    def test_delete_rejects_pending_reply(self):
        with TemporaryDirectory() as directory:
            store = ChatStore(directory)
            sid = store.create()['id']
            store.begin(sid, 'Hello', False, str(uuid4()))
            with self.assertRaises(ValueError):
                store.delete(sid)
            self.assertEqual(len(store.get(sid)['messages']), 1)

    def test_reopen_backup_retry_and_recovery(self):
        with TemporaryDirectory() as directory:
            store = ChatStore(directory)
            session = store.create()
            sid, rid = session['id'], str(uuid4())
            store.begin(sid, 'Remember blue', False, rid)
            with self.assertRaises(ValueError): store.begin(sid, 'Remember blue', False, rid)
            store.recover()
            self.assertEqual(store.get(sid)['messages'][0]['state'], 'failed')
            store.begin(sid, 'Remember blue', False, rid)
            result = {'reply': 'Blue remembered', 'metrics': {'output_tokens': 4}, 'tool_calls': []}
            store.finish(sid, rid, result=result)
            store.finish(sid, rid, error='Browser disconnected')
            self.assertEqual(store.get(sid)['messages'][0]['state'], 'complete')
            self.assertEqual(store.begin(sid, 'Remember blue', False, rid)[1], result)
            reopened = ChatStore(directory)
            self.assertEqual(len(reopened.get(sid)['messages']), 2)
            reopened.memory('Prefer concise answers')
            self.assertEqual(ChatStore(directory).memory(), 'Prefer concise answers')
            with closing(sqlite3.connect(Path(directory) / 'chats-backup.sqlite3')) as backup:
                data = json.loads(backup.execute('SELECT document FROM sessions WHERE id=?', (sid,)).fetchone()[0])
                self.assertEqual(data['messages'][1]['result'], result)
            store.path.unlink()
            self.assertEqual(ChatStore(directory).get(sid)['messages'][1]['result'], result)

    def test_session_api_continuation_and_idempotency(self):
        with TemporaryDirectory() as directory:
            store = ChatStore(directory)
            http = ThreadingHTTPServer(('127.0.0.1', 0), server.ChatHandler)
            threading.Thread(target=http.serve_forever, daemon=True).start()
            def request(path, payload=None):
                connection = HTTPConnection(*http.server_address)
                try:
                    connection.request('GET' if payload is None else 'POST', path,
                        body=None if payload is None else json.dumps(payload),
                        headers={'Host': '127.0.0.1:3000', 'Content-Type': 'application/json'})
                    response = connection.getresponse()
                    return response.status, json.loads(response.read())
                finally: connection.close()
            try:
                with patch('server.STORE', store), patch('server.lm_request') as model:
                    model.return_value = {'choices': [{'message': {'content': 'I remember blue.'}, 'finish_reason': 'stop'}]}
                    code, session = request('/api/sessions', {})
                    self.assertEqual(code, 201)
                    sid = session['id']
                    request('/api/memory', {'memory': 'Answer in English.'})
                    request('/api/draft', {'session_id': sid, 'draft': 'Unfinished thought'})
                    self.assertEqual(request('/api/session?id=' + sid)[1]['draft'], 'Unfinished thought')
                    payload = {'session_id': sid, 'request_id': str(uuid4()), 'message': 'My favorite color is blue.', 'thinking': False}
                    self.assertEqual(request('/api/chat', payload)[0], 200)
                    calls = model.call_count
                    self.assertEqual(request('/api/chat', payload)[0], 200)
                    self.assertEqual(model.call_count, calls)
                    payload.update(request_id=str(uuid4()), message='What is my favorite color?')
                    self.assertEqual(request('/api/chat', payload)[0], 200)
                    history = model.call_args.args[1]['messages']
                    self.assertIn('Answer in English.', history[0]['content'])
                    self.assertEqual(history[1]['content'], 'My favorite color is blue.')
                    self.assertEqual(history[2]['content'], 'I remember blue.')
                    self.assertEqual(len(request('/api/export')[1]['sessions'][0]['messages']), 4)
                    model.side_effect = TimeoutError()
                    payload.update(request_id=str(uuid4()), message='One more')
                    self.assertEqual(request('/api/chat', payload)[0], 502)
                    self.assertEqual(store.get(sid)['messages'][-1]['state'], 'failed')
                    with server.RUNTIME.lock:
                        self.assertEqual(request('/api/sessions/delete', {'session_id': sid})[0], 409)
                    self.assertEqual(request('/api/sessions/delete', {'session_id': '../bad'})[0], 409)
                    self.assertEqual(request('/api/sessions/delete', {'session_id': sid})[0], 200)
                    self.assertEqual(request('/api/session?id=' + sid)[0], 404)
                    self.assertEqual(request('/api/export')[1]['sessions'], [])
            finally:
                http.shutdown()
                http.server_close()

    def test_long_chat_summary_preserves_originals(self):
        with TemporaryDirectory() as directory:
            store = ChatStore(directory)
            session = store.create()
            session['messages'] = [{'role': 'user', 'content': 'x' * 13000},
                {'role': 'assistant', 'content': 'y' * 13000}, {'role': 'user', 'content': 'Continue'}]
            store.save(session)
            with patch('server.STORE', store), patch('server.lm_request', return_value={
                'choices': [{'message': {'content': 'Earlier context summary'}}]}) as model:
                context = server.session_context(session)
                self.assertEqual(context[-1]['content'], 'Continue')
                self.assertTrue(session['summary'])
                self.assertEqual(len(store.get(session['id'])['messages']), 3)
                server.session_context(session)
                self.assertEqual(model.call_count, 1)
