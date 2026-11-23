import json
from pathlib import Path
import sys
import tempfile
from time import monotonic
import unittest
from unittest.mock import Mock, patch


class DesktopClientTests(unittest.TestCase):
    def test_windows_binary_uses_the_name_required_by_the_native_overlay(self):
        from desktop_client import desktop_binary
        with patch.dict('os.environ', {}, clear=True), patch('platform.system', return_value='Windows'), patch('pathlib.Path.is_file', return_value=True):
            self.assertEqual(Path(desktop_binary()).stem, 'agent-desktop')

    def test_stdio_handshake_notifications_and_error_envelopes(self):
        from desktop_client import DesktopClient
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / 'mcp.py'
            script.write_text('''import json,sys,os
for line in sys.stdin:
 m=json.loads(line)
 if 'id' not in m: continue
 result={'protocolVersion':'2025-11-25'} if m['method']=='initialize' else {'structuredContent':{'ok':False,'data':{'home_override':os.environ.get('AGENT_DESKTOP_HOME')},'error':{'code':'STALE_REF','disposition':{'delivery':'not_delivered','retry':'safe'}}},'isError':True}
 print(json.dumps({'jsonrpc':'2.0','method':'notifications/message','params':{}}),flush=True)
 print(json.dumps({'jsonrpc':'2.0','id':m['id'],'result':result}),flush=True)
''', encoding='utf-8')
            with DesktopClient(command=[sys.executable, str(script)], timeout=2) as client:
                result = client.call('desktop_click', {'ref_id': '@s1:e1'})
                self.assertEqual(result['error']['code'], 'STALE_REF')
                self.assertIsNone(result['data']['home_override'], 'Use the native private home, not inherited project ACLs.')
                process = client.process
            self.assertIsNotNone(process.poll())

    def test_timeout_closes_transport_without_replay(self):
        from desktop_client import DesktopClient
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / 'mcp.py'
            script.write_text('import time\ntime.sleep(10)', encoding='utf-8')
            client = DesktopClient(command=[sys.executable, str(script)], timeout=.05)
            with self.assertRaises(TimeoutError):
                client.call('desktop_status', {})
            self.assertIsNone(client.process)

    def test_timeout_also_bounds_writing_to_a_server_that_stopped_reading(self):
        from desktop_client import DesktopClient
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / 'mcp.py'
            script.write_text('import json,sys,time\nm=json.loads(sys.stdin.readline())\nprint(json.dumps({"jsonrpc":"2.0","id":m["id"],"result":{}}),flush=True)\ntime.sleep(2)', encoding='utf-8')
            client = DesktopClient(command=[sys.executable, str(script)], timeout=.1)
            start = monotonic()
            try:
                client.call('desktop_set_value', {'value': 'x' * 8000})
            except (OSError, TimeoutError):
                pass
            finally:
                client.close()
            self.assertLess(monotonic() - start, 1)


class DesktopExecutorTests(unittest.TestCase):
    def setUp(self):
        from agent.desktop_executor import DesktopExecutor
        self.client = Mock()
        self.client.call.side_effect = self.call
        self.executor = DesktopExecutor(client=self.client)
        self.state = {}
        self.calls = []
        self.node = {'ref_id': '@s1:e1', 'role': 'edit', 'name': 'Text editor', 'value': '', 'available_actions': ['SetValue']}

    def call(self, name, args):
        self.calls.append((name, args))
        if name == 'desktop_session_start':
            return {'ok': True, 'data': {'session_id': 'test-session'}}
        if name == 'desktop_snapshot':
            return {'ok': True, 'data': {'app': 'notepad.exe', 'snapshot_id': 's1', 'complete': True, 'window': {'id': 'w1'},
                                       'tree': {'role': 'window', 'name': 'Untitled', 'children': [dict(self.node)]}}}
        if name == 'desktop_get':
            return {'ok': True, 'data': {'value': self.node.get('value', '')}}
        return {'ok': True, 'data': {'disposition': {'delivery': 'delivered_unverified', 'retry': 'unsafe'}}}

    def observe(self):
        return self.executor.run({'action': 'snapshot', 'app': 'notepad.exe'}, self.state)

    def test_mutation_requires_exact_approval_and_new_snapshot(self):
        self.assertTrue(self.observe()['verified'])
        action = {'action': 'set_value', 'app': 'notepad.exe', 'ref': '@s1:e1', 'value': 'hello'}
        pending = self.executor.run(action, self.state)
        self.assertEqual(pending['status'], 'approval_required')
        self.assertNotIn('desktop_set_value', [c[0] for c in self.calls])
        self.assertEqual(self.executor.run(dict(action, value='other'), self.state,
                         pending['approval']['fingerprint'])['status'], 'approval_required')
        result = self.executor.run(action, self.state, pending['approval']['fingerprint'])
        self.assertTrue(result['ok'])
        self.assertEqual(sum(name == 'desktop_set_value' for name, _ in self.calls), 1)
        self.assertFalse(result['verified'], 'Input delivery alone is not outcome verification')

    def test_refs_are_scoped_to_latest_task_observation(self):
        self.observe()
        self.assertEqual(self.state['apps']['notepad.exe']['window_id'], 'w1')
        result = self.executor.run({'action': 'click', 'app': 'notepad.exe', 'ref': '@other:e1'}, self.state)
        self.assertEqual(result['status'], 'denied')

    def test_semantic_text_can_clear_a_field(self):
        self.observe()
        action = {'action': 'set_value', 'app': 'notepad.exe', 'ref': '@s1:e1', 'value': ''}
        pending = self.executor.run(action, self.state)
        self.assertEqual(pending['status'], 'approval_required')

    def test_approved_text_replacement_does_not_overwrite_intervening_user_edits(self):
        self.observe()
        action = {'action': 'set_value', 'app': 'notepad.exe', 'ref': '@s1:e1', 'value': 'replace'}
        pending = self.executor.run(action, self.state)
        self.node['value'] = 'User changed this while approval was pending'
        result = self.executor.run(action, self.state, pending['approval']['fingerprint'])
        self.assertFalse(result['ok'])
        self.assertNotIn('desktop_set_value', [c[0] for c in self.calls])

    def test_physical_input_is_explicit_and_never_automatic(self):
        self.observe()
        action = {'action': 'type', 'app': 'notepad.exe', 'ref': '@s1:e1', 'value': 'hello', 'headed': True}
        pending = self.executor.run(action, self.state)
        self.assertIn('physical', pending['approval']['reason'].lower())
        self.executor.run(action, self.state, pending['approval']['fingerprint'])
        self.assertTrue(self.client.configure.call_args.kwargs['headed'])

    def test_native_uncertain_failure_is_not_reported_as_safe_error(self):
        self.observe()
        action = {'action': 'click', 'app': 'notepad.exe', 'ref': '@s1:e1'}
        pending = self.executor.run(action, self.state)
        original = self.client.call.side_effect
        def uncertain(name, args):
            if name == 'desktop_click':
                return {'ok': False, 'error': {'code': 'ACTION_FAILED', 'disposition': {'delivery': 'delivery_uncertain', 'retry': 'unsafe'}}}
            return original(name, args)
        self.client.call.side_effect = uncertain
        result = self.executor.run(action, self.state, pending['approval']['fingerprint'])
        self.assertEqual(result['status'], 'uncertain')
        self.assertEqual(sum(name == 'desktop_click' for name, _ in self.calls), 0)

    def test_rejects_unknown_fields_global_flags_and_unscoped_keys(self):
        from agent.desktop_policy import validate_action
        for action in [
            {'action': 'launch', 'app': 'powershell.exe', 'args': ['-Command', 'bad']},
            {'action': 'snapshot', 'app': 'notepad.exe', 'headed': True},
            {'action': 'press', 'combo': 'win+r'},
            {'action': 'press', 'app': 'notepad.exe', 'combo': 'win+r', 'force': True},
        ]:
            with self.subTest(action=action), self.assertRaises(ValueError):
                validate_action(action)


if __name__ == '__main__':
    unittest.main()
