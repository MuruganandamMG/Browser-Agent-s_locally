"""Download checksum-verified CUDA binaries and local GGUF models."""

from concurrent.futures import ThreadPoolExecutor
import argparse
import hashlib
from pathlib import Path
import subprocess
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parent
RELEASE = 'https://github.com/ggml-org/llama.cpp/releases/download/b12199/'
FILES = [
    (RELEASE + 'llama-b12199-bin-win-cuda-12.4-x64.zip',
     'runtime/llama.zip', '3c80120dc7763d67d0e882dda1545fbf626b2db471270030731cca4913cfc228'),
    (RELEASE + 'cudart-llama-bin-win-cuda-12.4-x64.zip',
     'runtime/cudart.zip', '8c79a9b226de4b3cacfd1f83d24f962d0773be79f1e7b75c6af4ded7e32ae1d6'),
    ('https://huggingface.co/lmstudio-community/Qwen3.5-9B-GGUF/resolve/'
     '1379f25c6b505a3fc737bd7818cb09389cf807c1/Qwen3.5-9B-Q4_K_M.gguf',
     'models/Qwen3.5-9B-Q4_K_M.gguf',
     'cd76ec205963b3b33350093e6904d9de16c4e666fd104e1f632d25c7f15f2a13'),
]
EXTRA_MODELS = [
    ('https://huggingface.co/HauhauCS/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive/resolve/'
     'c09cdbcdb1fefad6d335809d445621b5f5ba0c6e/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive-Q4_K_M.gguf',
     'models/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive-Q4_K_M.gguf',
     '79e28ecacf84e75b6056cf4059636d435aa9eb67795780f7b7dbc7d32a962741'),
    ('https://huggingface.co/TheBloke/WizardLM-7B-uncensored-GGUF/resolve/'
     'db690b5e11897e4bcbfb5193bb24fd531ab5cd2f/WizardLM-7B-uncensored.Q4_K_M.gguf',
     'models/WizardLM-7B-uncensored.Q4_K_M.gguf',
     '4280add7a95263033bfe6344f67eb96d78a2b265c20bd96f0445e0f5f1dc6baf'),
]
QWEN30B = (
    'https://huggingface.co/mradermacher/Qwen3-30B-A3B-abliterated-erotic-i1-GGUF/resolve/'
    '0de9ed4efb67e979c7c378d5afe040f1fe15ec20/Qwen3-30B-A3B-abliterated-erotic.i1-IQ3_XS.gguf',
    'models/Qwen3-30B-A3B-abliterated-erotic.i1-IQ3_XS.gguf',
    '7ace3361d440bdfda771bbd808dae25a547098662e4d957de8ca35f415106449',
)



def download(item):
    url, name, expected = item
    target = ROOT / name
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        partial = target.with_suffix(target.suffix + '.part')
        print(f'Downloading {name}', flush=True)
        subprocess.run(['curl.exe', '--fail', '--location', '--retry', '5',
                        '--retry-all-errors', '--connect-timeout', '20',
                        '--speed-time', '30', '--speed-limit', '1024',
                        '--silent', '--show-error', '--continue-at', '-',
                        '--output', str(partial), url], check=True)
        candidate = partial
    else:
        candidate = target
    with candidate.open('rb') as source:
        actual = hashlib.file_digest(source, 'sha256').hexdigest()
    if actual != expected:
        raise ValueError(f'Checksum mismatch for {candidate}; remove it and retry setup.')
    if candidate != target:
        candidate.replace(target)
    print(f'Verified {name}', flush=True)
    return target


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--extra-models', action='store_true', help='Download Qwen 4B and WizardLM 7B without changing the runtime.')
    parser.add_argument('--qwen30b', action='store_true', help='Download Qwen3 30B IQ3_XS only (12.6 GB).')
    args = parser.parse_args()
    selected = [QWEN30B] if args.qwen30b else EXTRA_MODELS if args.extra_models else FILES
    with ThreadPoolExecutor(max_workers=3) as pool:
        paths = list(pool.map(download, selected))
    for archive in ([] if args.extra_models or args.qwen30b else paths[:2]):
        with ZipFile(archive) as bundle:
            bundle.extractall(ROOT / 'runtime' / 'llama')
    print('Models verified. Use the model picker in the chat UI to load one.'
          if args.extra_models or args.qwen30b else
          'Local runtime installed. Run powershell -ExecutionPolicy Bypass -File start.ps1', flush=True)
