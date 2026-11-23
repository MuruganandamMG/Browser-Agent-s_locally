"""Serialized, bounded stdio MCP connection to the locally installed native binary."""

import json
import os
from pathlib import Path
import platform
from queue import Queue, Empty, Full
import subprocess
from threading import RLock, Thread
from time import monotonic


ROOT = Path(__file__).resolve().parent


def desktop_binary():
    override = os.environ.get('CHAT_DESKTOP_BINARY')
    if override:
        path = Path(override)
        if not path.is_absolute() or not path.is_file():
            raise FileNotFoundError('CHAT_DESKTOP_BINARY must name an installed native executable.')
        return str(path)
    extension = '.exe' if platform.system() == 'Windows' else ''
    path = ROOT / f'runtime/agent-desktop/node_modules/agent-desktop/bin/agent-desktop{extension}'
    if not path.is_file():
        raise FileNotFoundError('Agent Desktop is not installed. Run python setup_desktop.py.')
    return str(path)


class DesktopClient:
    def __init__(self, command=None, timeout=20):
        self.command = command
        self.timeout = timeout
        self.process = None
        self.session = None
        self.headed = False
        self.counter = 0
        self.lock = RLock()

    def configure(self, session=None, headed=False):
        with self.lock:
            if (session, headed) != (self.session, self.headed):
                self.close()
                self.session, self.headed = session, headed

    def _start(self):
        if self.process is not None:
            return
        env = {k: v for k, v in os.environ.items() if not k.startswith('AGENT_DESKTOP_')}
        # The native default home has private ACLs; project drives can inherit public access.
        if self.session:
            env['AGENT_DESKTOP_SESSION'] = self.session
        command = self.command or [desktop_binary(), 'mcp']
        self.process = subprocess.Popen([*command, *(['--headed'] if self.headed else [])],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            env=env, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        self.responses = Queue(maxsize=64)
        Thread(target=self._read, args=(self.process.stdout, self.responses), daemon=True).start()
        self._request('initialize', {'protocolVersion': '2025-11-25', 'capabilities': {},
            'clientInfo': {'name': 'local-assistant', 'version': '1.0'}})
        self._send({'jsonrpc': '2.0', 'method': 'notifications/initialized'})

    @staticmethod
    def _read(stream, responses):
        try:
            while True:
                line = stream.readline(4 * 1024 * 1024 + 1)
                if not line:
                    raise OSError('Agent Desktop MCP closed its output.')
                if len(line) > 4 * 1024 * 1024:
                    raise ValueError('Agent Desktop MCP response exceeds 4 MiB.')
                message = json.loads(line)
                if not isinstance(message, dict):
                    raise ValueError('Invalid MCP response.')
                if 'id' in message:
                    responses.put(message, timeout=.1)
        except (OSError, ValueError, Full) as error:
            try:
                responses.put(error, timeout=.1)
            except Full:
                pass

    def _send(self, message, timeout=None):
        raw = json.dumps(message).encode('utf-8') + b'\n'
        if len(raw) > 4 * 1024 * 1024:
            raise ValueError('MCP request exceeds 4 MiB.')
        process = self.process
        written = Queue(maxsize=1)
        def write():
            try:
                process.stdin.write(raw)
                process.stdin.flush()
                written.put(None)
            except (OSError, ValueError) as error:
                written.put(error)
        Thread(target=write, daemon=True).start()
        try:
            error = written.get(timeout=self.timeout if timeout is None else timeout)
        except Empty:
            raise TimeoutError('Agent Desktop stopped reading MCP input; delivery is uncertain.') from None
        if error:
            raise error

    def _request(self, method, params):
        self.counter += 1
        request_id = self.counter
        deadline = monotonic() + self.timeout
        self._send({'jsonrpc': '2.0', 'id': request_id, 'method': method, 'params': params})
        while True:
            try:
                if monotonic() >= deadline:
                    raise Empty
                result = self.responses.get(timeout=max(0, deadline - monotonic()))
            except Empty:
                try:
                    self._send({'jsonrpc': '2.0', 'method': 'notifications/cancelled',
                                'params': {'requestId': request_id, 'reason': 'Local timeout'}}, timeout=.1)
                except (OSError, TimeoutError):
                    pass
                raise TimeoutError('Agent Desktop timed out; delivery may be uncertain.') from None
            if isinstance(result, Exception):
                raise result
            if result.get('id') == request_id:
                if 'error' in result:
                    raise ValueError('Agent Desktop MCP rejected the request: ' + str(result['error'])[:500])
                return result['result']

    def request(self, method, params=None):
        with self.lock:
            try:
                self._start()
                return self._request(method, params or {})
            except Exception:
                # Never reconnect and replay a call: its input may already have landed.
                self.close()
                raise

    def call(self, name, arguments):
        result = self.request('tools/call', {'name': name, 'arguments': arguments})
        envelope = result.get('structuredContent')
        if not isinstance(envelope, dict):
            envelope = next((json.loads(item['text']) for item in result.get('content', [])
                             if item.get('type') == 'text'), None)
        if not isinstance(envelope, dict) or type(envelope.get('ok')) is not bool:
            raise ValueError('Agent Desktop returned no valid command envelope.')
        return envelope

    def close(self):
        with self.lock:
            process, self.process = self.process, None
            if process:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=3)
                for stream in (process.stdin, process.stdout):
                    try:
                        stream.close()
                    except OSError:
                        pass

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
