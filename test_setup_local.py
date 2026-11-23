import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import setup_local


class DownloadTests(unittest.TestCase):
    def test_verified_download_and_corrupt_file_rejected(self):
        content = b'fixture model bytes'
        digest = hashlib.sha256(content).hexdigest()
        with tempfile.TemporaryDirectory() as directory, patch.object(setup_local, 'ROOT', Path(directory)):
            def transfer(command, **kwargs):
                Path(command[command.index('--output') + 1]).write_bytes(content)

            with patch('setup_local.subprocess.run', side_effect=transfer) as curl:
                target = setup_local.download(('https://example.com/model', 'models/test.gguf', digest))
                self.assertEqual(target.read_bytes(), content)
                self.assertFalse(target.with_suffix('.gguf.part').exists())
                setup_local.download(('https://example.com/model', 'models/test.gguf', digest))
                curl.assert_called_once()
                target.write_bytes(b'corrupt')
                with self.assertRaisesRegex(ValueError, 'Checksum mismatch'):
                    setup_local.download(('https://example.com/model', 'models/test.gguf', digest))
