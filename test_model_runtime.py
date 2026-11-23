import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from model_runtime import ModelRuntime, MODELS


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        (root / 'runtime').mkdir()
        root_patch = patch('model_runtime.ROOT', root)
        root_patch.start()
        self.addCleanup(root_patch.stop)

    def test_invalid_or_missing_keeps_current_process(self):
        runtime = ModelRuntime()
        process = runtime.process = Mock()
        with self.assertRaises(ValueError):
            runtime.load('../bad')
        with patch('model_runtime.ROOT', Path(tempfile.gettempdir()) / 'missing-model-test'):
            with self.assertRaises(FileNotFoundError):
                runtime.load('qwen30b')
        process.terminate.assert_not_called()

    def test_load_and_shutdown(self):
        runtime = ModelRuntime()
        process = Mock()
        process.poll.return_value = None
        with patch('model_runtime.Path.is_file', return_value=True), patch('model_runtime.socket.create_connection', side_effect=OSError), patch('model_runtime.subprocess.Popen', return_value=process) as spawn, patch('model_runtime.urlopen') as request:
            request.return_value.__enter__.return_value.read.return_value = b'{"data":[{"id":"qwen3-30b-a3b-erotic-iq3-xs"}]}'
            runtime.load('qwen30b')
            args = spawn.call_args.args[0]
            self.assertEqual(args[args.index('-ngl') + 1], '18')
            self.assertEqual(runtime.model, MODELS['qwen30b']['alias'])
            runtime.close()
            process.terminate.assert_called_once()

    def test_failed_start_has_no_active_model(self):
        runtime = ModelRuntime()
        process = Mock()
        process.poll.return_value = 1
        with patch('model_runtime.Path.is_file', return_value=True), patch('model_runtime.socket.create_connection', side_effect=OSError), patch('model_runtime.subprocess.Popen', return_value=process):
            with self.assertRaises(RuntimeError):
                runtime.load('qwen30b')
        self.assertIsNone(runtime.model)

    def test_external_runtime_is_not_stopped(self):
        runtime = ModelRuntime()
        with patch('model_runtime.Path.is_file', return_value=True), patch('model_runtime.socket.create_connection'), patch('model_runtime.subprocess.Popen') as spawn:
            with self.assertRaisesRegex(RuntimeError, 'Port 8080'):
                runtime.load('qwen9b')
            spawn.assert_not_called()


if __name__ == '__main__':
    unittest.main()
