"""Allowlisted models and the single llama.cpp process owned by this app."""
import json
from pathlib import Path
import socket
import subprocess
from threading import Lock
from time import monotonic, sleep
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent
MODELS = {
    'qwen9b': dict(name='Qwen3.5 9B · Q4_K_M', alias='qwen3.5-9b', file='Qwen3.5-9B-Q4_K_M.gguf', context=16384, layers='all'),
    'qwen4b': dict(name='Qwen3.5 4B Uncensored · Q4_K_M', alias='qwen3.5-4b-uncensored-hauhaucs-aggressive', file='Qwen3.5-4B-Uncensored-HauhauCS-Aggressive-Q4_K_M.gguf', context=65536, layers='all'),
    'wizard7b': dict(name='WizardLM 7B Uncensored · Q4_K_M', alias='wizardlm-7b-uncensored', file='WizardLM-7B-uncensored.Q4_K_M.gguf', context=2048, layers='all'),
    'qwen30b': dict(name='Qwen3 30B A3B Abliterated Erotic · IQ3_XS', alias='qwen3-30b-a3b-erotic-iq3-xs', file='Qwen3-30B-A3B-abliterated-erotic.i1-IQ3_XS.gguf', context=4096, layers='18'),
}


class ModelRuntime:
    def __init__(self):
        self.process = None
        self.model = None
        self.lock = Lock()

    def catalog(self):
        return [dict(id=key, name=value['name'], context=value['context'], installed=(ROOT / 'models' / value['file']).is_file(),
                     active=self.model == value['alias'] and self.process is not None and self.process.poll() is None)
                for key, value in MODELS.items()]

    def close(self):
        if self.process is not None:
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=15)
            self.process = None
        self.model = None

    def load(self, key):
        if not isinstance(key, str) or key not in MODELS:
            raise ValueError('Choose a model from the list.')
        model = MODELS[key]
        path = ROOT / 'models' / model['file']
        executable = ROOT / 'runtime/llama/llama-server.exe'
        if not path.is_file() or not executable.is_file():
            raise FileNotFoundError('Model or runtime is missing. Run setup_local.py with --qwen30b or --extra-models.')
        if self.model == model['alias'] and self.process is not None and self.process.poll() is None:
            return
        self.close()
        try:
            with socket.create_connection(('127.0.0.1', 8080), timeout=1):
                raise RuntimeError('Port 8080 is used by another runtime. Stop its launcher first.')
        except OSError:
            pass
        args = [str(executable), '-m', str(path), '--alias', model['alias'], '--host', '127.0.0.1',
                '--port', '8080', '-ngl', model['layers'], '-c', str(model['context']), '-np', '1',
                '--jinja', '--reasoning-format', 'deepseek', '--no-webui',
                '--cors-origins', 'http://127.0.0.1:3000,http://localhost:3000', '--no-cors-credentials']
        if key == 'wizard7b':
            args += ['--chat-template-file', str(ROOT / 'templates/vicuna.jinja')]
        try:
            with (ROOT / 'runtime/llama.log').open('w') as out, (ROOT / 'runtime/llama-error.log').open('w') as err:
                self.process = subprocess.Popen(args, stdout=out, stderr=err, creationflags=subprocess.CREATE_NO_WINDOW)
            deadline = monotonic() + 300
            while monotonic() < deadline:
                if self.process.poll() is not None:
                    raise RuntimeError('Model runtime exited. See runtime/llama-error.log. Try a smaller model.')
                try:
                    with urlopen('http://127.0.0.1:8080/v1/models', timeout=2) as response:
                        data = json.loads(response.read())
                    if any(item.get('id') == model['alias'] for item in data['data']):
                        self.model = model['alias']
                        return
                except (OSError, ValueError, KeyError):
                    pass
                sleep(1)
            raise RuntimeError('Model loading timed out. See runtime/llama-error.log; try a smaller model.')
        except Exception:
            self.close()
            raise
