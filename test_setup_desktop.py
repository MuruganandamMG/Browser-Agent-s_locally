import unittest
from unittest.mock import patch

import setup_desktop


class SetupDesktopTests(unittest.TestCase):
    def test_repeat_install_does_not_replace_an_identical_running_executable(self):
        with patch('setup_desktop.subprocess.run'), patch('setup_desktop.shutil.which', return_value='node'), \
             patch('setup_desktop.shutil.copy2') as copy, patch('pathlib.Path.is_file', return_value=True), \
             patch('filecmp.cmp', return_value=True), patch('desktop_client.DesktopClient') as client, patch('builtins.print'):
            client.return_value.__enter__.return_value.call.return_value = {'ok': True}
            setup_desktop.main()
            copy.assert_not_called()


if __name__ == '__main__':
    unittest.main()
