from pathlib import Path
import sys
import tempfile
import unittest


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        from agent.workspace_executor import WorkspaceExecutor
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.executor = WorkspaceExecutor(Path(self.tmp.name))
        self.task_id = 'c1f91da8-47ee-42eb-91c5-cc419ddcf880'

    def run_action(self, action, approval=None):
        return self.executor.run(action, self.task_id, approved_fingerprint=approval)

    def test_create_read_and_approved_overwrite_with_content_binding(self):
        action = {'action': 'write', 'path': 'demo/main.py', 'value': 'print(1)'}
        self.assertTrue(self.run_action(action)['verified'])
        self.assertEqual(self.run_action({'action': 'read', 'path': 'demo/main.py'})['text'], 'print(1)')
        change = dict(action, value='print(2)')
        approval = self.run_action(change)['approval']['fingerprint']
        self.assertEqual(self.run_action(change, 'wrong')['status'], 'approval_required')
        self.assertTrue(self.run_action(change, approval)['ok'])
        self.assertEqual(self.run_action(action, approval)['status'], 'approval_required')

    def test_rejects_path_escapes_streams_devices_and_reparse_points(self):
        for name in ['../escape', 'D:/escape', '/escape', 'x:secret', 'CON', 'aux.txt', 'a/../b', 'a./b', 'a /b', 'a\\b', '.env']:
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.run_action({'action': 'write', 'path': name, 'value': 'bad'})
        root = Path(self.tmp.name) / self.task_id
        root.mkdir(exist_ok=True)
        try:
            (root / 'link').symlink_to(Path(self.tmp.name), target_is_directory=True)
        except OSError:
            return  # Symlink creation needs Developer Mode on some Windows installations.
        with self.assertRaises(ValueError):
            self.run_action({'action': 'write', 'path': 'link/escape.txt', 'value': 'bad'})

    def test_process_is_explicitly_approved_and_output_exit_code_are_evidence(self):
        action = {'action': 'run', 'argv': [sys.executable, '-c', 'print("verified")']}
        pending = self.run_action(action)
        self.assertEqual(pending['status'], 'approval_required')
        self.assertIn('permissions', pending['approval']['reason'])
        result = self.run_action(action, pending['approval']['fingerprint'])
        self.assertTrue(result['verified'])
        self.assertIn('verified', result['stdout'])
        self.assertEqual(result['exit_code'], 0)

    def test_oversized_existing_files_cannot_be_loaded_for_an_overwrite(self):
        root = self.executor.root(self.task_id)
        with (root / 'large.txt').open('wb') as file:
            file.truncate(1000000)
        with self.assertRaises(ValueError):
            self.run_action({'action': 'write', 'path': 'large.txt', 'value': 'small'})


if __name__ == '__main__':
    unittest.main()
