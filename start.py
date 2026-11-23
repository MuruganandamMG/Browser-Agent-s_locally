"""Start the local chat app; Ctrl+C stops the app and its model runtime."""

import argparse
import os
import runpy

from model_runtime import MODELS, ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', choices=MODELS, default='qwen4b',
                        help='Model to load at startup (default: qwen4b).')
    args = parser.parse_args()
    os.chdir(ROOT)
    os.environ['CHAT_MODEL_KEY'] = args.model
    runpy.run_path(str(ROOT / 'server.py'), run_name='__main__')


if __name__ == '__main__':
    main()
