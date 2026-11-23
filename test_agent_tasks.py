import tempfile
import time
import unittest
from threading import Lock, Event
from types import SimpleNamespace

from chat_store import ChatStore
from agent.task_manager import TaskManager


class Browser:
    def __init__(self):
        self.calls = []

    def run(self, action, tabs, approved_fingerprint=None):
        self.calls.append((action, approved_fingerprint))
        if action['action'] == 'click' and approved_fingerprint != 'exact':
            return {'ok': False, 'status': 'approval_required', 'approval': {
                'fingerprint': 'exact', 'action': action, 'url': 'https://example.com',
                'target': 'Send', 'reason': 'External submission'}}
        tabs['1'] = {'url': 'https://example.com', 'text': 'Example Domain'}
        return {'ok': True, 'status': 'ok', 'page': 1, 'url': 'https://example.com',
                'observation': 'Example Domain', 'verified': True}


def wait_state(manager, task, states):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        result = manager.get(task['id'])
        if result['state'] in states and task['id'] not in manager.workers:
            return result
        time.sleep(.01)
    raise AssertionError(manager.get(task['id']))


class TaskTests(unittest.TestCase):
    def test_uncertain_action_observes_and_continues_without_acknowledgement(self):
        original = self.browser.run
        def uncertain(action, tabs, approved_fingerprint=None):
            if action['action'] == 'click':
                self.browser.calls.append((action, approved_fingerprint))
                tabs['1'] = {'url': 'https://example.com', 'text': 'Saved'}
                return {'ok': False, 'status': 'uncertain', 'page': 1, 'url': 'https://example.com'}
            return original(action, tabs, approved_fingerprint)
        self.browser.run = uncertain
        self.responses = [('browser_action', {'action': 'click', 'page': 1, 'ref': 'e1'}),
                          ('finish_task', {'summary': 'Observed the current page after the action.'})]
        done = wait_state(self.manager, self.create(), {'completed', 'paused'})
        self.assertEqual(done['state'], 'completed', done)
        self.assertEqual([c[0]['action'] for c in self.browser.calls], ['click', 'snapshot'])
        self.assertEqual(done['steps'][0]['state'], 'uncertain')

    def test_resume_uncertain_task_needs_no_acknowledgement(self):
        self.responses = [('request_human', {'reason': 'Browser connection needs attention.'})]
        paused = wait_state(self.manager, self.create(), {'paused'})
        paused['steps'] = [{'number': 1, 'action': {'action': 'click', 'page': 1, 'ref': 'e1'}, 'state': 'uncertain'}]
        paused['tabs'] = {'1': {'url': 'https://example.com'}}
        self.manager._save(paused)
        self.responses = [('finish_task', {'summary': 'Current state observed.'})]
        self.manager.control(paused['id'], 'resume', {})
        done = wait_state(self.manager, paused, {'completed', 'paused'})
        self.assertEqual(done['state'], 'completed', done)

    def test_uncertain_submission_is_not_dispatched_twice(self):
        original = self.browser.run
        def uncertain(action, tabs, approved_fingerprint=None):
            if action['action'] == 'click':
                self.browser.calls.append((action, approved_fingerprint))
                tabs['1'] = {'url': 'https://example.com'}
                return {'ok': False, 'status': 'uncertain', 'page': 1}
            return original(action, tabs, approved_fingerprint)
        self.browser.run = uncertain
        click = {'action': 'click', 'page': 1, 'ref': 'e1'}
        self.responses = [('browser_action', click), ('browser_action', dict(click, expected_text='Saved')),
                          ('finish_task', {'summary': 'Observed current state.'})]
        wait_state(self.manager, self.create(), {'completed', 'paused'})
        self.assertEqual(sum(c[0]['action'] == 'click' for c in self.browser.calls), 1)

    def test_failed_recovery_snapshot_cannot_claim_completion(self):
        original = self.browser.run
        def interrupted(action, tabs, approved_fingerprint=None):
            if action['action'] in ('click', 'snapshot'):
                self.browser.calls.append((action, approved_fingerprint))
                return {'ok': False, 'status': 'uncertain' if action['action'] == 'click' else 'error'}
            return original(action, tabs, approved_fingerprint)
        self.browser.run = interrupted
        self.responses = [('browser_action', {'action': 'new_tab', 'url': 'https://example.com'}),
                          ('browser_action', {'action': 'click', 'page': 1, 'ref': 'e1'}),
                          ('finish_task', {'summary': 'Done'})]
        done = wait_state(self.manager, self.create(), {'completed', 'paused'})
        self.assertEqual(done['state'], 'paused')
        self.assertEqual(done['result'], '')

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ChatStore(self.tmp.name)
        self.session = self.store.create()
        self.runtime = SimpleNamespace(lock=Lock())
        self.browser = Browser()
        self.responses = []
        self.manager = TaskManager(self.store, self.runtime, self.request, lambda: 'qwen3.5-4b', self.browser)

    def tearDown(self):
        self.manager.close()
        self.tmp.cleanup()

    def request(self, path, payload):
        name, args = self.responses.pop(0)
        import json
        return {'choices': [{'message': {'tool_calls': [{'id': 'call', 'function': {
            'name': name, 'arguments': json.dumps(args)}}]}}]}

    def create(self):
        return self.manager.create(self.session['id'], 'Read example.com', autonomous=False)

    def test_completion_and_backup_persistence(self):
        self.responses = [('browser_action', {'action': 'new_tab', 'url': 'https://example.com'}),
                          ('finish_task', {'summary': 'Example Domain https://example.com'})]
        task = wait_state(self.manager, self.create(), {'completed', 'failed'})
        self.assertEqual(task['state'], 'completed', task)
        self.assertEqual(len(task['steps']), 1)
        self.assertIn('Example Domain', task['result'])
        self.assertTrue(task['steps'][0]['result']['verified'])
        self.assertTrue((self.store.directory / 'chats-backup.sqlite3').exists())
        other = TaskManager(self.store, self.runtime, self.request, lambda: 'qwen3.5-4b', self.browser)
        self.assertEqual(other.get(task['id'])['state'], 'completed')
        other.close()

    def test_exact_approval_required_and_single_use(self):
        self.responses = [('browser_action', {'action': 'click', 'page': 1, 'ref': 'e1'}),
                          ('finish_task', {'summary': 'Sent and verified'})]
        task = wait_state(self.manager, self.create(), {'awaiting_approval', 'failed'})
        self.assertEqual(task['state'], 'awaiting_approval', task)
        self.assertFalse(self.runtime.lock.locked())
        with self.assertRaises(ValueError):
            self.manager.control(task['id'], 'approve', {'fingerprint': 'wrong'})
        self.manager.control(task['id'], 'approve', {'fingerprint': 'exact'})
        done = wait_state(self.manager, task, {'completed', 'failed'})
        self.assertEqual(done['state'], 'completed', done)
        self.assertEqual(len([c for c in self.browser.calls if c[1] == 'exact']), 1)
        with self.assertRaises(ValueError):
            self.manager.control(task['id'], 'approve', {'fingerprint': 'exact'})

    def test_restart_invalidates_approval_and_never_replays(self):
        self.responses = [('browser_action', {'action': 'click', 'page': 1, 'ref': 'e1'})]
        task = wait_state(self.manager, self.create(), {'awaiting_approval'})
        self.manager.recover()
        recovered = self.manager.get(task['id'])
        self.assertEqual(recovered['state'], 'paused')
        self.assertIsNone(recovered['approval'])
        self.assertEqual(len(self.browser.calls), 1)

    def test_cancel_during_inference_stops_next_browser_action(self):
        entered, release = Event(), Event()
        def slow(path, payload):
            entered.set()
            release.wait(2)
            return self.request(path, payload)
        self.manager.model_request = slow
        self.responses = [('browser_action', {'action': 'new_tab', 'url': 'https://example.com'})]
        task = self.create()
        self.assertTrue(entered.wait(1))
        self.manager.control(task['id'], 'cancel', {})
        release.set()
        self.manager.close()
        self.assertEqual(self.manager.get(task['id'])['state'], 'cancelled')
        self.assertEqual(self.browser.calls, [])

    def test_model_cannot_finish_without_browser_evidence(self):
        self.responses = [('finish_task', {'summary': 'I did it'})] * 3
        done = wait_state(self.manager, self.create(), {'paused', 'failed'})
        self.assertNotEqual(done['state'], 'completed')

    def test_validation_and_busy_runtime(self):
        with self.assertRaises(ValueError):
            self.manager.create(self.session['id'], '')
        self.runtime.lock.acquire()
        try:
            with self.assertRaises(ValueError):
                self.create()
        finally:
            self.runtime.lock.release()

    def test_planner_preserves_request_and_serializes_compact_observations(self):
        import json
        captured = []
        def request(path, payload):
            captured.append(json.loads(payload['messages'][1]['content']))
            return {'choices': [{'message': {'tool_calls': [{'function': {
                'name': 'finish_task', 'arguments': '{"summary":"done"}'}}]}}]}
        self.manager.model_request = request
        task = {'request': 'x' * 5500 + ' Do not submit the form.', 'tabs': {
            '1': {'url': 'https://example.com', 'snapshot': {'text': 'a' * 16000, 'refs': []}}},
            'steps': [{'action': {'action': 'read', 'page': 1}, 'state': 'complete', 'result': {
                'ok': True, 'snapshot': {'text': 'a' * 16000}}}],
            'events': [{'type': 'recovering', 'message': 'Choose a valid reference.'}]}
        self.manager._next(task)
        self.assertEqual(captured[0]['request'], task['request'])
        self.assertIn('Choose a valid reference.', json.dumps(captured[0]))

    def test_resume_observations_do_not_erase_uncertain_action_ledger(self):
        import json
        captured = []
        def request(path, payload):
            captured.append(json.loads(payload['messages'][1]['content']))
            return {'choices': [{'message': {'tool_calls': [{'function': {
                'name': 'finish_task', 'arguments': '{"summary":"done"}'}}]}}]}
        self.manager.model_request = request
        task = {'request': 'Submit a record once.', 'tabs': {}, 'events': [], 'steps': [
            {'number': 1, 'action': {'action': 'click', 'page': 1, 'ref': 'e2'},
             'state': 'uncertain', 'result': {'status': 'uncertain'}}] + [
            {'number': n, 'action': {'action': 'snapshot', 'page': n}, 'state': 'complete',
             'result': {'ok': True}} for n in range(2, 7)]}
        self.manager._next(task)
        self.assertEqual(captured[0]['do_not_repeat'][0]['action']['ref'], 'e2')

    def test_private_browser_evidence_never_reaches_primary_or_backup(self):
        secret = 'sk-proj-' + 'private1234567890' * 2
        key_body = 'SAMPLEPRIVATEKEYBODY'
        private_key = '-----BEGIN PRIVATE KEY-----\n' + key_body + '\n-----END PRIVATE KEY-----'
        original = self.browser.run
        def private_read(action, tabs, approved_fingerprint=None):
            result = original(action, tabs, approved_fingerprint)
            tabs['1']['text'] = 'Visible token: ' + secret + '\n' + private_key
            result['observation'] = 'Visible token: ' + secret + '\n' + private_key
            return result
        self.browser.run = private_read
        self.responses = [('browser_action', {'action': 'new_tab', 'url': 'https://example.com'}),
                          ('finish_task', {'summary': 'The token is ' + secret})]
        done = wait_state(self.manager, self.create(), {'completed'})
        for path in (self.store.path, self.store.directory / 'chats-backup.sqlite3'):
            self.assertFalse(secret.encode() in path.read_bytes(), 'Private browser evidence reached ' + path.name)
            self.assertFalse(key_body.encode() in path.read_bytes(), 'Private key body reached ' + path.name)
        self.assertNotIn(secret, str(self.manager.get(done['id'])))

    def test_cancel_cannot_be_overwritten_by_final_model_response(self):
        self.responses = [('browser_action', {'action': 'new_tab', 'url': 'https://example.com'}),
                          ('finish_task', {'summary': 'Done'})]
        original = self.manager._live
        cancelled = []
        def racing_live(task_id):
            result = original(task_id)
            if result and self.browser.calls and not self.responses and not cancelled:
                cancelled.append(True)
                self.manager.control(task_id, 'cancel', {})
            return result
        self.manager._live = racing_live
        done = wait_state(self.manager, self.create(), {'cancelled', 'completed'})
        self.manager.close()
        self.assertEqual(self.manager.get(done['id'])['state'], 'cancelled')


if __name__ == '__main__':
    unittest.main()
