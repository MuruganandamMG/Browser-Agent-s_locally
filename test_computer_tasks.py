import json
from unittest.mock import Mock

import test_agent_tasks as fixtures
from test_agent_tasks import wait_state
import unittest


class ComputerTaskTests(unittest.TestCase):
    setUp = fixtures.TaskTests.setUp
    tearDown = fixtures.TaskTests.tearDown
    request = fixtures.TaskTests.request

    def test_private_pending_arguments_are_not_modified_by_storage_redaction(self):
        from agent.workspace_executor import WorkspaceExecutor
        from pathlib import Path
        self.manager.workspace = WorkspaceExecutor(Path(self.tmp.name) / 'projects')
        initial = {'action': 'write', 'path': 'config.py', 'value': 'owner = "dev@example.com"'}
        updated = dict(initial, value='owner = "new@example.com"')
        self.responses = [('workspace_action', initial), ('workspace_action', updated), ('finish_task', {'summary': 'Updated file'})]
        task = self.manager.create(self.session['id'], 'Create and update config', mode='computer', autonomous=False)
        pending = wait_state(self.manager, task, {'awaiting_approval', 'paused'})
        self.assertEqual(pending['state'], 'awaiting_approval', pending)
        self.assertEqual(pending['approval']['action']['value'], updated['value'])
        self.assertEqual(self.manager.list(self.session['id'], include_pending=True)[0]['approval']['action']['value'], updated['value'])
        self.assertNotIn('new@example.com', json.dumps(self.manager.list()))
        for path in (self.store.path, self.store.directory / 'chats-backup.sqlite3'):
            self.assertNotIn(b'new@example.com', path.read_bytes())
        self.manager.control(task['id'], 'approve', {'fingerprint': pending['approval']['fingerprint']})
        done = wait_state(self.manager, task, {'completed', 'paused', 'awaiting_approval'})
        self.assertEqual(done['state'], 'completed', done)
        self.assertEqual((self.manager.workspace.root(task['id']) / 'config.py').read_text(), updated['value'])

    def test_computer_tools_are_opt_in_and_route_with_saved_evidence(self):
        self.manager.desktop = Mock()
        def observe(action, state, approved_fingerprint=None):
            state['inventory'] = 'Notepad'
            return {'ok': True, 'status': 'ok', 'verified': True, 'app': 'notepad.exe'}
        self.manager.desktop.run.side_effect = observe
        self.responses = [('desktop_action', {'action': 'list_apps'}), ('finish_task', {'summary': 'Found Notepad'})]
        task = self.manager.create(self.session['id'], 'Find Notepad', mode='computer', autonomous=False)
        done = wait_state(self.manager, task, {'completed', 'paused'})
        self.assertEqual(done['state'], 'completed', done)
        self.assertEqual(done['steps'][0]['action']['tool'], 'desktop_action')
        self.assertEqual(done['desktop']['inventory'], 'Notepad')
        self.assertFalse(self.browser.calls)

    def test_browser_task_cannot_dispatch_a_desktop_action(self):
        self.manager.desktop = Mock()
        self.responses = [('desktop_action', {'action': 'list_apps'})] * 3
        task = self.manager.create(self.session['id'], 'Find Notepad', autonomous=False)
        done = wait_state(self.manager, task, {'paused', 'completed'})
        self.assertEqual(done['state'], 'paused')
        self.manager.desktop.run.assert_not_called()

    def test_planner_sees_desktop_observations_and_only_opted_in_tools(self):
        captured = []
        def model(path, payload):
            captured.append(payload)
            return {'choices': [{'message': {'tool_calls': [{'function': {'name': 'request_human', 'arguments': '{"reason":"help"}'}}]}}]}
        self.manager.model_request = model
        task = {'request': 'Read Notepad', 'mode': 'computer', 'tabs': {}, 'steps': [], 'events': [],
                'desktop': {'apps': {'notepad.exe': {'tree': {'name': 'hello'}}}}, 'id': self.session['id']}
        self.manager._next(task)
        self.assertIn('hello', captured[0]['messages'][1]['content'])
        names = [t['function']['name'] for t in captured[0]['tools']]
        self.assertIn('desktop_action', names)
        self.assertIn('workspace_action', names)
        task['mode'] = 'browser'
        self.manager._next(task)
        self.assertNotIn('desktop_action', [t['function']['name'] for t in captured[1]['tools']])

    def test_planner_bounds_large_desktop_and_workspace_evidence(self):
        captured = []
        def model(path, payload):
            captured.append(payload)
            return {'choices': [{'message': {'tool_calls': [{'function': {'name': 'request_human', 'arguments': '{"reason":"help"}'}}]}}]}
        self.manager.model_request = model
        task = {'id': self.session['id'], 'request': 'Test the app', 'mode': 'computer', 'tabs': {}, 'events': [],
                'desktop': {'apps': {f'app{i}.exe': {'tree': {'value': 'x' * 18000}} for i in range(10)}},
                'steps': [{'action': {'action': 'write', 'value': 'x' * 64000}, 'state': 'complete',
                           'result': {'ok': True, 'text': 'y' * 64000}}] * 4}
        self.manager._next(task)
        payload = captured[0]
        self.assertLess(len(json.dumps(payload)), self.manager._context_budget())

    def test_unrelated_app_snapshot_cannot_verify_a_desktop_mutation(self):
        self.manager.desktop = Mock()
        def run(action, state, approved_fingerprint=None):
            return {'ok': True, 'status': 'ok', 'verified': action['action'] == 'snapshot', 'app': action.get('app')}
        self.manager.desktop.run.side_effect = run
        self.responses = [('desktop_action', {'action': 'launch', 'app': 'notepad'}),
                          ('desktop_action', {'action': 'snapshot', 'app': 'calc.exe'}),
                          ('finish_task', {'summary': 'Done'})] + [('request_human', {'reason': 'Inspect Notepad'})]
        task = self.manager.create(self.session['id'], 'Open Notepad', mode='computer', autonomous=False)
        done = wait_state(self.manager, task, {'paused', 'completed'})
        self.assertEqual(done['state'], 'paused', done)


if __name__ == '__main__':
    unittest.main()
