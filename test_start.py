import os
import unittest
from unittest.mock import patch

import start


class LauncherTests(unittest.TestCase):
    def test_default_and_explicit_model_use_existing_server(self):
        for arguments, expected in (([], 'qwen4b'), (['--model', 'wizard7b'], 'wizard7b')):
            with self.subTest(model=expected), patch('sys.argv', ['start.py', *arguments]), \
                    patch.dict(os.environ, {}, clear=True), patch('start.os.chdir') as change_directory, \
                    patch('start.runpy.run_path') as run_server:
                start.main()
                self.assertEqual(os.environ['CHAT_MODEL_KEY'], expected)
                change_directory.assert_called_once_with(start.ROOT)
                run_server.assert_called_once_with(str(start.ROOT / 'server.py'), run_name='__main__')

    def test_invalid_model_does_not_start_server(self):
        with patch('sys.argv', ['start.py', '--model', '../bad']), \
                patch('start.runpy.run_path') as run_server, patch('sys.stderr'):
            with self.assertRaises(SystemExit) as result:
                start.main()
            self.assertEqual(result.exception.code, 2)
            run_server.assert_not_called()
