import unittest
import test_agent_tasks as fixtures
from test_agent_tasks import wait_state


class AutonomousTests(unittest.TestCase):
    setUp = fixtures.TaskTests.setUp
    tearDown = fixtures.TaskTests.tearDown
    request = fixtures.TaskTests.request

    def test_recovers_from_more_than_three_errors_without_resume(self):
        self.responses = [('bad_tool', {})] * 4 + [('browser_action', {'action': 'new_tab', 'url': 'https://example.com'}),
                          ('finish_task', {'summary': 'Done'})]
        task = self.manager.create(self.session['id'], 'Read example.com')
        done = wait_state(self.manager, task, {'completed', 'failed', 'paused'})
        self.assertEqual(done['state'], 'completed')
        messages = self.store.get(self.session['id'])['messages']
        self.assertEqual([m['role'] for m in messages], ['user', 'assistant'])
        self.assertEqual(messages[-1]['content'], 'Done')

    def test_unrecoverable_errors_end_with_chat_report_instead_of_resume(self):
        self.responses = [('bad_tool', {})] * 10
        task = self.manager.create(self.session['id'], 'Read example.com')
        done = wait_state(self.manager, task, {'failed', 'paused'})
        self.assertEqual(done['state'], 'failed')
        self.assertTrue(self.store.get(self.session['id'])['messages'][-1]['content'])

    def test_user_authorized_actions_execute_without_approval_pause(self):
        self.responses = [('browser_action', {'action': 'click', 'page': 1, 'ref': 'e1'}),
                          ('finish_task', {'summary': 'Done'})]
        task = self.manager.create(self.session['id'], 'Click the requested control')
        done = wait_state(self.manager, task, {'completed', 'awaiting_approval', 'failed'})
        self.assertEqual(done['state'], 'completed')
        self.assertEqual(self.browser.calls[-1][1], 'exact')

    def test_same_tab_batch_is_sequential_and_does_not_get_stuck(self):
        self.responses = [('browser_action', {'action': 'parallel', 'tasks': [
            {'action': 'read', 'page': 1}, {'action': 'snapshot', 'page': 1}]}),
            ('finish_task', {'summary': 'Observed'})]
        task = self.manager.create(self.session['id'], 'Read the page')
        done = wait_state(self.manager, task, {'completed', 'failed'})
        self.assertEqual(done['state'], 'completed')
        self.assertEqual([a['action'] for a, _ in self.browser.calls], ['read', 'snapshot'])


if __name__ == '__main__': unittest.main()
