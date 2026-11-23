"""Task-scoped UTF-8 files and explicitly approved, bounded local processes."""

import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import tempfile
from threading import Thread
from uuid import UUID

from .desktop_policy import fingerprint


ACTION_TOOL = {'type': 'function', 'function': {
    'name': 'workspace_action',
    'description': 'Work inside this task\'s project directory. list lists files, read reads UTF-8, write creates a file (overwrite needs approval), run executes argv with cwd at the project root and a 60-second limit. Every run needs explicit user approval: processes run with the user\'s full permissions, not a sandbox. No shell interpolation. Use direct file writes for code, then run tests. No deletion tool.',
    'parameters': {'type': 'object', 'properties': {
        'action': {'type': 'string', 'enum': ['list', 'read', 'write', 'run']},
        'path': {'type': 'string'}, 'value': {'type': 'string'},
        'argv': {'type': 'array', 'items': {'type': 'string'}, 'minItems': 1, 'maxItems': 40},
    }, 'required': ['action'], 'additionalProperties': False}}}


class WorkspaceExecutor:
    def __init__(self, base=None):
        self.base = Path(base or Path(__file__).resolve().parents[1] / 'data/projects').absolute()

    def root(self, task_id):
        root = self.base / str(UUID(task_id))
        for path in [root, self.base, *self.base.parents]:
            if path.is_symlink() or (path.exists() and os.name == 'nt' and path.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT):
                raise ValueError('Workspace paths cannot contain symlinks or junctions.')
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _path(self, root, value):
        if not isinstance(value, str) or not 0 < len(value) <= 240 or '\\' in value:
            raise ValueError('Use a short relative path with forward slashes.')
        parts = value.split('/')
        for part in parts:
            if not re.fullmatch(r'[A-Za-z0-9_. -]+', part) or part in ('.', '..') or part.endswith(('.', ' ')) or part.startswith('.') or re.fullmatch(r'(?:con|prn|aux|nul|com[0-9]|lpt[0-9])(?:\..*)?', part, re.I):
                raise ValueError('Unsafe workspace path component.')
        path = root.joinpath(*parts)
        for item in [path, *path.parents]:
            if item == root:
                break
            if item.is_symlink() or (item.exists() and os.name == 'nt' and item.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT):
                raise ValueError('Workspace paths cannot follow symlinks or junctions.')
        if not path.resolve().is_relative_to(root.resolve()):
            raise ValueError('Path escapes the task workspace.')
        return path

    def run(self, action, task_id, approved_fingerprint=None):
        fields = {'list': {'action'}, 'read': {'action', 'path'}, 'write': {'action', 'path', 'value'}, 'run': {'action', 'argv'}}
        if not isinstance(action, dict) or action.get('action') not in fields or set(action) != fields[action['action']]:
            raise ValueError('Missing or unexpected workspace fields.')
        root = self.root(task_id)
        kind = action['action']
        result = {'workspace': str(root)}
        if kind == 'run':
            argv = action['argv']
            if not isinstance(argv, list) or not 1 <= len(argv) <= 40 or any(not isinstance(a, str) or not a or len(a) > 8000 or '\x00' in a for a in argv):
                raise ValueError('argv must contain 1–40 bounded strings.')
            if Path(argv[0]).suffix.lower() in ('.cmd', '.bat', '.ps1'):
                raise ValueError('Use a native executable, such as python, node, or powershell.exe, with explicit arguments.')
            target = {'workspace': str(root), 'argv': argv}
        elif kind != 'list':
            path = self._path(root, action['path'])
            if kind == 'write':
                if not isinstance(action['value'], str) or len(action['value'].encode('utf-8')) > 64000:
                    raise ValueError('File content must be UTF-8 text under 64 KB.')
                if path.is_file() and path.stat().st_size > 64000:
                    raise ValueError('Existing file exceeds the 64 KB edit limit.')
                target = {'path': str(path), 'previous_sha256': hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None}
        needs_approval = kind == 'run' or (kind == 'write' and path.exists())
        if needs_approval and approved_fingerprint != fingerprint(action, target):
            return {**result, 'ok': False, 'status': 'approval_required', 'approval': {
                'fingerprint': fingerprint(action, target), 'target': target,
                'reason': 'Run this command with your full user permissions (not sandboxed).' if kind == 'run' else 'Replace this existing file with the proposed content.'}}
        try:
            if kind == 'list':
                # Do not traverse links or unbounded dependency trees.
                result['files'] = []
                for folder, dirs, files in os.walk(root, followlinks=False):
                    dirs[:] = [d for d in dirs if d not in ('node_modules', '__pycache__', '.venv', '.git') and not (Path(folder) / d).is_symlink()
                               and not (os.name == 'nt' and (Path(folder) / d).lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)]
                    for name in files:
                        relative = (Path(folder) / name).relative_to(root).as_posix()
                        result['files'].append(relative)
                        if len(result['files']) >= 200:
                            return {**result, 'ok': True, 'status': 'ok', 'verified': True, 'truncated': True}
            elif kind == 'read':
                with path.open('rb') as file:
                    data = file.read(64001)
                if len(data) > 64000:
                    raise ValueError('File exceeds the 64 KB read limit.')
                result['text'] = data.decode('utf-8')
            elif kind == 'write':
                path.parent.mkdir(parents=True, exist_ok=True)
                self._path(root, action['path'])
                data = action['value'].encode('utf-8')
                with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as file:
                    temporary = Path(file.name)
                    file.write(data)
                try:
                    if needs_approval:
                        if hashlib.sha256(path.read_bytes()).hexdigest() != target['previous_sha256']:
                            raise ValueError('File changed since approval; observe and review again.')
                        os.replace(temporary, path)
                    else:
                        os.link(temporary, path)  # Fails if a file appeared since the initial check.
                finally:
                    temporary.unlink(missing_ok=True)
                result.update(path=str(path), bytes=len(data), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            else:
                return {**result, **self._process(action['argv'], root)}
            return {**result, 'ok': True, 'status': 'ok', 'verified': True}
        except (OSError, ValueError) as error:
            return {**result, 'ok': False, 'status': 'error', 'verified': False, 'error': str(error)[:1000]}

    @staticmethod
    def _process(argv, root):
        process = subprocess.Popen(argv, cwd=root, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, shell=False, start_new_session=os.name != 'nt',
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        output = {'stdout': bytearray(), 'stderr': bytearray()}
        def read(stream, key):
            try:
                while chunk := stream.read(4096):
                    output[key].extend(chunk[:max(0, 8000 - len(output[key]))])
            finally:
                stream.close()
        readers = [Thread(target=read, args=(getattr(process, key), key), daemon=True) for key in output]
        for reader in readers:
            reader.start()
        timed_out = False
        try:
            process.wait(timeout=60)
        except subprocess.TimeoutExpired:
            timed_out = True
            if os.name == 'nt':
                subprocess.run(['taskkill.exe', '/PID', str(process.pid), '/T', '/F'], capture_output=True, timeout=5,
                               creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                os.killpg(process.pid, signal.SIGKILL)
            process.kill()
            process.wait(timeout=5)
        for reader in readers:
            reader.join(timeout=1)
        return {'ok': not timed_out and process.returncode == 0, 'status': 'uncertain' if timed_out else 'ok' if process.returncode == 0 else 'error',
                'verified': not timed_out, 'exit_code': process.returncode, 'timed_out': timed_out,
                **{key: bytes(value).decode('utf-8', errors='replace') for key, value in output.items()}}
