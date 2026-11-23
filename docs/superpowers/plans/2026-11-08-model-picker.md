# Local model picker implementation plan

Goal: download the requested Qwen3 30B A3B IQ3_XS and load any of the four configured models from the existing UI.

Design: preserve the current UI and chats. Add a labeled dropdown, Load button, installed/active status, and errors. Python owns one llama.cpp subprocess, using an allowlisted catalog shared with setup and the launcher. A lock prevents switching during replies. Unknown or missing models fail before stopping the current one. Use partial GPU offload and a smaller context for 30B on this 8 GB GPU. No dependencies.

Alternatives: keeping PowerShell as process owner prevents reliable UI switching; running multiple models exceeds available memory. Use Python ownership and one loaded model.

1. Add failing tests for catalog, invalid/missing model preservation, process arguments, startup failure and shutdown.
2. Implement model catalog/process lifecycle; extend checksum-verified setup with --qwen30b. Download IQ3_XS.
3. Integrate allowlisted model API, serializing chat and load requests. Simplify start.ps1 to launch the Python owner.
4. Add dropdown and Load button, loading/error states, and disable switching during replies. Preserve existing styling and mobile layout.
5. Run Python tests, JavaScript syntax check, browser checks, checksum verification and actual model load/reply/switch smoke tests. Document measured limits.

Review focus: unknown IDs, missing downloads, concurrent load/chat, startup failure, external runtime port conflict. Leave unrelated processes and existing model files intact.

Completed: IQ3_XS downloaded (12,598,442,624 bytes) and SHA-256 verified. Model picker exercised in desktop and mobile layouts; Qwen 4B, WizardLM, and Qwen3 30B loaded successfully. The 30B loaded at 18 GPU layers and 4,096 context, with about 4.8 GB total GPU memory in use. All 22 Python tests and JavaScript syntax check passed. The running UI was independently redesigned during this work; those concurrent changes were preserved. A competing request prevented the 30B reply smoke test, and the active selection subsequently changed back to Qwen 4B; no 30B generation speed or quality claim is made.
