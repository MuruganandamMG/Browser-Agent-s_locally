import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from unittest.mock import patch

import server
from chat_store import ChatStore
from agent.task_manager import TaskManager
from test_agent_tasks import Browser, wait_state


class AgentApiTests(unittest.TestCase):
    def test_routes_security_and_lifecycle(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ChatStore(directory)
            session = store.create()
            manager = TaskManager(store, server.RUNTIME, lambda *_: {}, lambda: 'qwen3.5-4b', Browser())
            from functools import partial
            manager.create = partial(manager.create, autonomous=False)
            app = ThreadingHTTPServer(('127.0.0.1', 0), server.ChatHandler)
            threading.Thread(target=app.serve_forever, daemon=True).start()
            def request(path, data=None, host='127.0.0.1:3000'):
                c = HTTPConnection(*app.server_address, timeout=5)
                c.request('GET' if data is None else 'POST', path,
                          None if data is None else json.dumps(data),
                          {'Host': host, 'Content-Type': 'application/json'})
                r = c.getresponse()
                result = r.status, json.loads(r.read())
                c.close()
                return result
            try:
                with patch('server.STORE', store), patch('server.AGENT', manager):
                    self.assertEqual(request('/api/agent/tasks', {}, 'evil.test')[0], 403)
                    self.assertEqual(request('/api/agent/tasks', {'session_id': session['id'], 'request': ''})[0], 400)
                    code, task = request('/api/agent/tasks', {'session_id': session['id'], 'request': 'Read example.com'})
                    self.assertEqual(code, 202)
                    prefix = '/api/agent/tasks/' + task['id']
                    self.assertEqual(request(prefix)[0], 200)
                    self.assertEqual(request('/api/agent/tasks?session_id=' + session['id'])[1]['tasks'][0]['id'], task['id'])
                    self.assertEqual(request(prefix + '/events?after=0')[0], 200)
                    wait_state(manager, task, {'paused'})
                    self.assertEqual(request(prefix + '/approve', {'fingerprint': 'fake'})[0], 409)
                    self.assertEqual(request('/api/sessions/delete', {'session_id': session['id']})[0], 409)
                    self.assertEqual(request(prefix + '/cancel', {})[1]['state'], 'cancelled')
                    with patch('desktop_client.DesktopClient') as client:
                        client.return_value.__enter__.return_value.call.return_value = {'ok': True, 'data': {'platform': 'windows'}}
                        self.assertTrue(request('/api/agent/desktop/status')[1]['connected'])
                    self.assertEqual(request('/api/agent/tasks', {'session_id': session['id'], 'request': 'Test', 'mode': 'unsafe'})[0], 409)
                    self.assertEqual(request('/api/export')[1]['agent_tasks'][0]['id'], task['id'])
                    self.assertEqual(request('/api/sessions/delete', {'session_id': session['id']})[0], 200)
                    self.assertEqual(request(prefix)[0], 404)
                    self.assertEqual(request('/api/agent/tasks/not-a-uuid')[0], 400)
                    new_session = store.create()
                    code, computer = request('/api/agent/tasks', {'session_id': new_session['id'], 'request': 'Inspect Notepad', 'mode': 'computer'})
                    self.assertEqual(code, 202)
                    self.assertEqual(computer['mode'], 'computer')
                    wait_state(manager, computer, {'paused'})
                    self.assertEqual(request('/api/agent/tasks/' + computer['id'] + '/cancel', {})[1]['state'], 'cancelled')
            finally:
                app.shutdown()
                app.server_close()
                manager.close()

    def test_no_model_facing_javascript_or_parallel_bypass(self):
        from chat_tools import TOOLS, execute_tool
        names = [t['function']['name'] for t in TOOLS]
        self.assertNotIn('browser', names)
        self.assertNotIn('browser_parallel', names)
        self.assertIn('error', execute_tool('browser', '{"code":"return 1"}'))
        self.assertIn('error', execute_tool('browser_parallel', '{"tasks":[]}'))


if __name__ == '__main__':
    unittest.main()
