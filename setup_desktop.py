"""Install the pinned optional desktop engine inside this project."""
from pathlib import Path
import filecmp
import os
import platform
import shutil
import subprocess


def main():
    root = Path(__file__).resolve().parent
    npm = shutil.which('npm.cmd') or shutil.which('npm')
    if not npm:
        raise SystemExit('Install Node.js 18+ and npm, then run this command again.')
    subprocess.run([npm, 'install', '--prefix', str(root / 'runtime/agent-desktop'),
                    '--save-exact', 'agent-desktop@1.2.0'], check=True, cwd=root)
    # Some npm versions block lifecycle scripts; run the reviewed package installer explicitly.
    subprocess.run([shutil.which('node'), str(root / 'runtime/agent-desktop/node_modules/agent-desktop/scripts/postinstall.js')], check=True, cwd=root)
    if os.name == 'nt':
        arch = 'arm64' if platform.machine().lower() in ('arm64', 'aarch64') else 'x64'
        directory = root / 'runtime/agent-desktop/node_modules/agent-desktop/bin'
        # The Windows overlay trusts only an executable named agent-desktop.exe.
        source, alias = directory / f'agent-desktop-win32-{arch}.exe', directory / 'agent-desktop.exe'
        if not alias.is_file() or not filecmp.cmp(source, alias, shallow=False):
            shutil.copy2(source, alias)
    from desktop_client import DesktopClient
    with DesktopClient() as client:
        status = client.call('desktop_status', {})
        print(status)
        if not status['ok']:
            raise SystemExit('Agent Desktop installed, but its native status check failed.')


if __name__ == '__main__':
    main()
