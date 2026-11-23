# Local model chatbot

## Autonomous task behavior

New Browser and Computer tasks run automatically after validation, including desktop actions and project commands. The request and final success/failure report appear as normal saved chat messages. Recoverable errors are replanned up to eight consecutive failures within the execution budget; exhausted or genuinely blocked tasks end with an explanation instead of requesting Resume. Login/CAPTCHA and protected browser operations remain enforced. Uncertain mutations are never replayed. Commands still run with your full user permissions. Legacy saved tasks retain their prior controls.

## Windows computer agent

Agent Desktop **1.2.0** is integrated alongside BrowserOS Neo. Install its optional native engine once with `python setup_desktop.py` (Node.js 18+ and npm required), then restart with `python start.py`. Installation stays under `runtime/agent-desktop`; no global npm or additional Python dependency is needed.

Choose **Computer: On** beside the composer and describe a desktop, browser or coding task. The same saved task controller chooses between BrowserOS Neo, native Windows applications, and a separate project directory at `data/projects/<task-id>`. **Browser: On** retains the original website-only behavior. Ordinary chat and voice cannot control the desktop.

- Desktop: list apps/windows, read accessibility snapshots, launch Notepad/Calculator/Explorer/VS Code, click qualified element refs, set text semantically, type or press scoped keys, and move the physical mouse when explicitly requested.
- Cursor: the upstream overlay shows semantic actions with animation, highlights, click feedback and a label. It is a visual pointer, not another independent hardware cursor. The monitor reports when rendering is unavailable. Physical input shares your mouse/keyboard focus and never becomes a fallback after semantic failure.
- Coding: create/read/list UTF-8 files up to 64 KB in the task project; approve existing-file replacement and every process command. Commands use an argument array, project working directory, bounded output, and a 60-second limit. Processes run with **your full user permissions, not an OS sandbox**. There is no delete tool or permanent server manager. Browser private/local-network destinations remain blocked.

Legacy tasks can pause at **Review operation**. Inspect the exact arguments and target, then choose **Approve once** or **Reject**. Approval expires after five minutes; altered arguments/targets need a new approval. Pending raw arguments live only in memory so redaction cannot corrupt code or commands; stored/exported evidence stays redacted. Restart invalidates approvals and never replays interrupted operations. Stop prevents subsequent actions; an operation already in flight may finish.

The native engine uses its private home, normally `%USERPROFILE%/.agent-desktop`, for session/ref state. Automatic traces and screenshots are disabled. UI snapshots can contain private text, and redaction is heuristic. Keep this state and `data/` private. Conversation deletion does not delete generated project files.

Live Windows smoke checks verified Notepad snapshots, semantic click/text entry, text readback, and `cursor-overlay` reporting `rendered=true`. UAC secure desktop, locked/sign-in screens and other users' sessions are unsupported; some apps/editors require physical input. More details: [desktop integration report](docs/DESKTOP_INTEGRATION.md).

## Autonomous Browser agent

Restart with `python start.py` after updating the source, open `http://127.0.0.1:3000`, keep BrowserOS neo open, and select **Browser: On** beside the composer. Describe the whole task and send it once. The agent plans bounded actions, observes the actual website, and saves its report and execution history. Ordinary chat and optimized voice remain separate; they cannot execute browser scripts.

The monitor shows the task state, current website/action, step evidence, and **Stop task**. Stop prevents the next operation; a browser operation already dispatched may finish. Refreshing or reopening the conversation restores the task. One model job runs at a time, across all conversations.

Website navigation, form filling, submissions and other ordinary interactions run automatically without approval prompts. The executor still checks current page/form state before acting. Uncertain outcomes trigger fresh snapshots and replanning, without blindly repeating the action. There is no “I checked the site” acknowledgement checkbox. Credentials, payments, destructive operations, uploads and recognizable private values retain their security protections; complete those directly in the browser. Model-written JavaScript and the old parallel tool are not exposed.

Parallel mode supports up to five task-owned tabs for independent opening, reading and snapshots. Dependent interactions remain sequential and use current observed refs. Colored pointers are animated webpage overlays, not Windows mouse cursors.

**Resume** observes the saved tabs before replanning and needs no acknowledgement. Uncertain operations remain in a separate do-not-repeat ledger. Actual connection failures, login/CAPTCHA and repeated errors can still pause a task. Server restarts pause incomplete tasks. If Neo restarts and tab ownership is lost, recovery pauses rather than claiming someone else's tabs; cancel/start a new scoped task if ownership cannot be restored. Reconnection never automatically retries a failed action.

Tasks, step intents, outcomes, approvals and ordered events are saved in `agent_tasks` JSON records inside the existing chat SQLite database and its automatic backup. Export includes tasks. Deleting a conversation requires cancelling unfinished tasks and also removes its task records. Recognizable private values are redacted from agent evidence before persistence; this is not a general secret detector, and normal conversation storage is unchanged.

Limits: at most 60 planning steps or 30 minutes per run, up to two recovery retries before pausing, 30 seconds per Neo SDK batch, and 180 seconds per model request. Small-context models require shorter task instructions; requests are rejected instead of silently dropping their ending. Task planning disables thinking and uses compact observations.

URL/DNS checks reject explicit private/local/metadata destinations, unsafe schemes and nonstandard web ports. These checks **are not a browser network firewall**: redirects, subresources, webpage JavaScript and DNS rebinding require external egress controls for isolation. Action classification and completion reasoning remain heuristic/model-dependent. A verified observation is evidence, not a guarantee that the whole task was interpreted correctly.

API: `POST /api/agent/tasks`, `GET /api/agent/tasks?session_id=...`, `GET /api/agent/tasks/{id}`, `GET /api/agent/tasks/{id}/events?after=N`, and `POST /api/agent/tasks/{id}/{cancel|resume}` with body `{}`. Old approve/reject routes remain for saved-task compatibility; new tasks do not request approval. `GET /api/agent/neo/status` checks MCP connectivity. The UI uses nonoverlapping one-second polling rather than SSE.

Implementation and test evidence: [autonomous browser implementation report](docs/AUTONOMOUS_BROWSER_IMPLEMENTATION.md).

Runs local models with llama.cpp CUDA. The Python launcher defaults to Qwen3.5 4B HauhauCS Aggressive Q4_K_M. LM Studio is not required.

## Run and stop

Open a terminal in this folder and run:

```powershell
cd D:\projeect\test-shit
python start.py
```

Open **http://127.0.0.1:3000**. Keep the terminal open. Press **Ctrl+C** in that terminal to stop both this app and its model runtime. BrowserOS neo should be open when using browser tools; it is a separate application.

Below the message box, the footer shows the loaded model and its configured context window in tokens. The model picker lists the context limit for every model. Selecting an option does not change the active-model footer until that model is loaded. These are the local runtime limits, rather than the model's advertised maximum or a live counter of remaining tokens.

To start WizardLM instead, run `python start.py --model wizard7b`. Use `--model qwen9b` for Qwen 9B, or choose an installed model from the app's model picker.

**Chats and memory survive closing and restarting the app.** Reopen a conversation from the sidebar to continue it. Use **Memory across chats** for facts or preferences that should apply to every conversation. Saved history and shared memory are stored in `data/chats.sqlite3`, with the automatic snapshot in `data/chats-backup.sqlite3`. Keep the entire `data/` folder; the models do not learn these memories by changing their weights. Use **Export all conversations** for a copy on another drive. Memory is local to this project.

The `start.py` file can also be run from another folder using its full path: `python D:\projeect\test-shit\start.py`.

## First-time setup

Requires Windows, Python 3.11+, curl.exe, and an NVIDIA GPU with a CUDA 12.4-compatible driver. This computer's RTX 4060 8 GB is supported.

Install browser automation once:

```powershell
python -m pip install -r requirements.txt
python -m playwright install chromium
```

```powershell
python setup_local.py
python setup_local.py --extra-models
python start.py
```

The downloads and dependencies are already installed on this computer; normal restarts only need `python start.py`. The server owns its model runtime and closes it on Ctrl+C.

## Additional models

Download Qwen 4B and WizardLM with `python setup_local.py --extra-models`. Download the requested Qwen3 30B A3B IQ3_XS with `python setup_local.py --qwen30b` (12,598,442,624 bytes). Existing Qwen 9B and Gemma files are preserved. Use the **Model** dropdown and **Load model** button above the conversation to switch. One model runs at a time; loading and replies prevent switching. Missing models stay listed as “not downloaded.” Chats and drafts remain saved.

You can also choose a model at startup:

```powershell
python start.py --model qwen4b
python start.py --model wizard7b
python start.py --model qwen30b
```

`--model qwen9b` runs the original Qwen 9B configuration. The older `start.ps1` launcher remains available and keeps its Qwen 9B default.

| Choice | Model source | Context | Browser tools |
| --- | --- | --- | --- |
| `qwen4b` | [HauhauCS/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive](https://huggingface.co/HauhauCS/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive) | 65,536 | Enabled through the existing neo integration |
| `wizard7b` | [TheBloke/WizardLM-7B-uncensored-GGUF](https://huggingface.co/TheBloke/WizardLM-7B-uncensored-GGUF) | 2,048 | Disabled; use for supplied text extraction and summaries |
| `qwen30b` | [mradermacher/Qwen3-30B-A3B-abliterated-erotic-i1-GGUF](https://huggingface.co/mradermacher/Qwen3-30B-A3B-abliterated-erotic-i1-GGUF) · IQ3_XS | 4,096 | Qwen native tools; variant quality needs evaluation |

The 30B IQ3_XS configuration uses partial GPU offload (18 layers) because the 12.6 GB weights exceed this GPU's 8 GB VRAM. It also uses system RAM; loading and generation may be slower than the smaller models. Pinned revision: `0de9ed4efb67e979c7c378d5afe040f1fe15ec20`; SHA-256: `7ace3361d440bdfda771bbd808dae25a547098662e4d957de8ca35f415106449`. Setup verifies the checksum before making the model available in the picker.

Installation verified on this PC: the IQ3_XS download passed SHA-256 verification and loaded successfully through the UI with the configuration above. Generation speed and answer quality have not been benchmarked.

WizardLM uses its documented Vicuna prompt format through `templates/vicuna.jinja`; `USER:` ends the assistant's reply. It does not support the app's native browser-tool or thinking interface; the Thinking button is hidden for this model. The Qwen 4B setup uses text/DOM observations, without the optional vision projector. The model names identify the requested variants; the screenshots did not identify their quantization, so Q4_K_M was chosen to fit this GPU.

The extra downloads are pinned and checksum verified:

- Qwen 4B: revision `c09cdbcdb1fefad6d335809d445621b5f5ba0c6e`, `Qwen3.5-4B-Uncensored-HauhauCS-Aggressive-Q4_K_M.gguf`, 2,707,513,696 bytes, SHA-256 `79e28ecacf84e75b6056cf4059636d435aa9eb67795780f7b7dbc7d32a962741`.
- WizardLM 7B: revision `db690b5e11897e4bcbfb5193bb24fd531ab5cd2f`, `WizardLM-7B-uncensored.Q4_K_M.gguf`, 4,081,009,920 bytes, SHA-256 `4280add7a95263033bfe6344f67eb96d78a2b265c20bd96f0445e0f5f1dc6baf`.

Functional checks loaded each model in a temporary llama.cpp process with partial GPU offload while the existing service stayed running. Qwen 4B issued a BrowserOS neo call and read a live webpage; WizardLM extracted a product name and price from supplied HTML. These are basic checks, not a broad scraping-quality benchmark. Tab reuse was inconsistent in the Qwen test, so longer browser workflows may need retries.

Setup downloads about 6 GB, resumes interrupted downloads, and verifies SHA-256 checksums. Files are pinned to:

- Model: [lmstudio-community/Qwen3.5-9B-GGUF](https://huggingface.co/lmstudio-community/Qwen3.5-9B-GGUF), revision `1379f25c6b505a3fc737bd7818cb09389cf807c1`, file `Qwen3.5-9B-Q4_K_M.gguf` (5,627,044,256 bytes), SHA-256 `cd76ec205963b3b33350093e6904d9de16c4e666fd104e1f632d25c7f15f2a13`. The Gemma model file is preserved. This installation uses text and browser DOM observations; the vision projector is not installed.
- Runtime: [llama.cpp b12199](https://github.com/ggml-org/llama.cpp/releases/tag/b12199), Windows x64 CUDA 12.4 binaries and runtime DLLs.

Model files live in `models/`; binaries and logs live in `runtime/`. These folders are excluded from version control. The original LM Studio installation and its model files are preserved.

The app connects to `http://127.0.0.1:8080/v1` with model alias `qwen3.5-9b`. The runtime uses GPU offload, one generation slot, and a 16,384-token context to fit the 8 GB GPU. Long conversations may exceed that context; start a new chat when needed.

Run `python -m unittest -v` for request validation, reasoning toggle translation, metrics, and download integrity checks. These tests mock inference; a live request verifies the installed model and GPU runtime.

Each reply shows elapsed request time and token counts supplied by llama.cpp, including thinking tokens when available. **avg tok/s** is output tokens divided by backend request time (including prompt processing), not pure generation speed. Metrics appear after generation finishes; unavailable counts are omitted.

Use **Thinking: On / Off** above the message box to control Qwen's reasoning for the next message. It defaults to Off, stays selected across New chat, and resets on refresh. The backend sends `chat_template_kwargs: {"enable_thinking": true | false}` to llama.cpp. Only the final answer is displayed; thinking may take longer.

The web backend uses Python with a local MCP connection to BrowserOS neo; the chat interface uses HTML, CSS, and JavaScript. After setup, no API keys or cloud inference are needed. Both servers bind to loopback only. Conversations, drafts, tool results, and reply metrics are stored in SQLite under `data/` and survive refreshes and restarts. New chat creates a separate saved conversation. Runtime logs remain on disk.

Replies appear after generation finishes. Requests time out after three minutes and replies are capped at 2,048 tokens including thinking. Each incoming request is limited to 256 KB and each message to 20,000 characters. Saved sessions are not limited to 100 messages. Older context is summarized when needed; original messages remain stored.

Ordinary chat can call `calculate` and `current_time`. Its existing ten-round tool limit and metrics remain. Use **Browser: On** for website work; browser tasks have their own saved progress, approval flow and execution budget described above.

The browser tool now controls **BrowserOS neo over MCP**. Keep BrowserOS neo open. The connector reads its actual proxy port from `%LOCALAPPDATA%/BrowserClaw/User Data/.browseros/config.json` (9010 on this installation), falling back to 9200 when that config is absent. It automatically initializes and names a browser session. It never falls back to the old headless browser when neo is offline; the tool returns a connection error instead.

The model supplies validated JSON actions. The trusted executor translates them into bounded neo SDK scripts and checks current page state before acting. Browser tabs/logins belong to neo's persistent profile; task ownership is checked within the shared connection. New chat does not close existing browser tabs. CAPTCHA and login screens require human interaction; consequential actions follow the approval policy above.

Connection verified with Qwen3.5-9B: the chat called neo, opened the Python documentation, and read a topic from the page. CUDA runtime reported approximately 10?11 generated tokens/sec during this test; the UI's end-to-end average includes model retries and browser work. This is a single functional test, not a broad benchmark.

## Saved conversations and memory

The sidebar lists saved sessions; reopening one resumes its stored conversation. The last selected session is restored on refresh. Drafts are saved in the browser immediately and synced to the server after a short debounce. Sent messages are committed before inference; tool results are saved as they arrive and completed replies before they are returned. Refreshing during generation reconnects to the saved session. A server restart marks unfinished replies for manual retry; it never automatically repeats browser actions.

`data/chats.sqlite3` contains the primary chat database. Every committed write creates an atomic local snapshot at `data/chats-backup.sqlite3`. If the primary is missing, startup restores the snapshot after an integrity check. These copies are on the same computer; use **Export all conversations** or copy `data/` to another drive for protection against disk failure. The export includes session transcripts, drafts, metrics, tool records, summaries, and shared memory. Keep backups private: chats and browser results may contain personal information.

**Memory across chats** is editable user context injected into every saved session. It is separate from each session's history; saving it does not alter earlier messages. Long conversations use cached model-generated summaries for older context, while retaining the complete transcript. Summaries can omit details; reopen the original transcript when exact wording matters. No Obsidian integration is needed.

Run `python -m unittest test_chat_store test_server test_neo_client test_chat_tools test_setup_local -v` for storage recovery, backup restoration, idempotent retries, context continuation, memory injection, summary retention, and existing API checks.

## Chat interface

The interface follows the familiar ChatGPT layout while remaining a local application: neutral dark surfaces, a collapsible history sidebar with title search, right-aligned user messages, formatted assistant replies, and a fixed bottom composer. Model selection and loading remain available in the top-left menu. Memory and export remain in the sidebar; thinking, tool information, tool execution records, and token metrics are preserved.

Replies render sanitized Markdown, including lists, headings, links, tables, inline code, and scrollable code blocks. Copy-response and copy-code buttons use the browser clipboard; if unavailable, the UI explains how to copy manually. Starter prompts fill the composer without sending. Enter sends, Shift+Enter adds a line, and the composer expands up to a bounded height.

Markdown dependencies are vendored locally: marked 18.1.3 and DOMPurify 3.4.17. Versions, registry sources, and SHA-256 hashes are in `public/vendor/versions.json`; upstream license files are alongside the scripts. No CDN or Node.js server is required. This app does not claim the hosted ChatGPT service's voice, image generation, or subscription features.

Voice: **STT · Dictate** puts recognized speech into the composer for review. **TTS + STT · Voice chat** opens a dedicated voice screen with a live transcript, listening/thinking/speaking states, mute, interrupt reply, and end controls. It waits 1.4 seconds after finalized speech before sending, speaks the completed reply, then listens again. Click **End conversation** or press Escape to stop. Interrupt stops playback and resumes listening. Listening pauses during model replies and playback; switching chats, hiding the tab, or loading a model stops voice. Voice chat stays active through silence until you end it. Automatic interruption by speaking over playback is not supported; use Interrupt reply. Code blocks and tables are omitted from spoken replies. Set Speech language to match your speech (for example `en-IN`, `en-US`, or `ta-IN`). Use localhost or HTTPS and allow microphone access. Recognition and installed voices depend on browser/OS support; browser recognition may send audio to an online speech service, even though chat runs locally. Accuracy is not guaranteed; dictation lets you correct words before sending. No additional speech model or API key is installed. Voice lifecycle checks: `node --test test_voice.cjs`.

## Parallel tab pointers

The browser agent can request a validated `parallel` batch of 1–5 independent tasks. They run concurrently through BrowserOS neo using `Promise.all`, with results and failures isolated per task. Sequential interactions display a colored virtual pointer with click, typing and scroll feedback. These are page overlays, not additional Windows mouse cursors. The physical mouse is not moved.

Agent parallel batches support new tabs, reading and snapshots. Click, fill, key press, select and scroll run sequentially through the policy-checked executor using observed eN refs. Batches reject duplicate existing page IDs and enforce task ownership.

Overlays use trusted page code and may be unavailable on restricted pages; the operation can proceed with `cursor: false`. Batches retain neo's 30-second cap. Browser internals and focus-sensitive sites may serialize parts of an interaction. Live public parallel reads and sequential form filling were checked; protected parallel mutations are intentionally unavailable. This feature controls browser pages, not the Windows desktop.

## Increasing the context window

The context window includes input, browser tool observations, conversation history, and the generated answer. Qwen 4B is configured for 65,536 tokens. To change a model's limit, edit its `context` value in the `MODELS` table in `model_runtime.py`, stop the app with Ctrl+C, and restart with `python start.py`. Reload the page to see the new configured limit. More context uses more GPU memory; a limit that is too high can prevent the model from loading. Saved chats and shared memory are not deleted when changing this setting.

Voice replies prioritize latency: reasoning is disabled, answers are capped at 160 tokens, and only the last eight messages (dropping older turns above 8,000 characters) are used. Full transcripts remain saved. Voice does not run browser tools or create blocking history summaries; use typed chat for research and long-context work. Speech starts before the chat-history refresh.
"# Browser-Agent-s_locally" 
