# Windows desktop integration

Implemented from `use-case/Vercel_Agent_Desktop_Integration_Analysis.md`, using the existing Python/local-Qwen task loop. BrowserOS Neo remains the website executor. TaskManager provides planning, durable task memory, budgets, approvals, cancellation, recovery and SQLite backups for both modes.

## Components

| File | Role |
|---|---|
| `desktop_client.py` | Standard-library stdio MCP handshake, bounded read/write deadlines, native envelopes, cleanup, no transport replay |
| `agent/desktop_policy.py` | Closed action fields, qualified refs, launch allowlist, scoped keyboard/explicit physical input, fingerprints |
| `agent/desktop_executor.py` | Native snapshots, exact approval, semantic/physical dispatch, upstream cursor overlay |
| `agent/workspace_executor.py` | Project-scoped files, approved replacement and process execution |
| `agent/task_manager.py` | Shared orchestration, opt-in tools, exact pending arguments, bounded model evidence and outcome checks |
| `server.py`, `public/agent-monitor.js` | Status/API routes and saved-task approval UI |
| `setup_desktop.py` | Pinned local npm installation and Windows executable alias for the renderer |

No duplicate planner/memory database, custom cursor engine, arbitrary desktop MCP tool passthrough, shell-string tool, or additional Python dependency was added.

## Installation / use

```powershell
python setup_desktop.py
python start.py
```

Select **Computer: On**, then try: “Inspect Notepad and write Hello in a new blank document.” Review each proposed desktop change. For coding, try: “Create a Python program in the task workspace and run its self-check.” New files are written directly; overwrites and process execution need exact approval.

The optional `CHAT_DESKTOP_BINARY` environment variable must name an absolute native executable. On Windows its filename must be `agent-desktop.exe` for the upstream renderer to start. The npm platform-suffixed executable otherwise works for observation but cannot start the overlay. Setup copies the installer's verified binary to the required name in the package's `bin` directory.

Agent Desktop's native private home is used rather than `runtime/desktop`: on this installation the project drive inherits ACL entries that the upstream session store correctly refuses. Native state can contain unredacted accessibility content even with tracing disabled.

## API

`POST /api/agent/tasks` accepts `{ "session_id": "UUID", "request": "...", "mode": "computer" }`. Omit `mode` for backward-compatible browser tasks. The model gets `desktop_action` and `workspace_action` only in computer mode. Runtime dispatch independently enforces this boundary.

`GET /api/agent/desktop/status` checks the installed engine. Existing task get/list/events/control routes remain. `approve` accepts only the displayed fingerprint; callers cannot substitute arguments. `reject`, `cancel` and `resume` keep the original task lifecycle. `GET /api/export` uses redacted stored records. Task get/list used by the local UI overlays exact pending arguments from memory for review; those raw arguments are discarded on approval, rejection, cancellation or recovery.

## Verification and limits

Tests cover stdio initialization/notifications, blocked writes/timeouts, native delivery semantics, qualified refs, opt-in routing, exact arguments through redaction, approval controls, oversized model evidence, file containment/device names/ADS/links, bounded editing, command output, cancellation and old browser-task regressions.

Final runs: **86 Python tests and 21 Node tests passed**, with both frontend JavaScript files also passing syntax checks. The idle app was restarted on its existing Qwen 4B model; live model status, desktop status and UI requests returned 200. BrowserOS Neo was offline during final verification, so live web workflows and visual browser UI inspection were not checked.

Live Notepad checks used the installed engine: snapshot; semantic click of Add New Tab; snapshot of the blank editor; set-value; fresh snapshot confirming the exact text. No existing document was edited. The native overlay acknowledged rendering. The demonstration used a separate unsaved Notepad tab. Session/overlay teardown was confirmed. A live Qwen 4B computer task also selected `desktop_action list_apps`, received the inventory and completed with an accurate report. Raw diagnostic snapshots live only under ignored `runtime/`; do not share them publicly.

The 60-second process tool is for installs, scripts and tests, not persistent app servers. Its working directory and the direct file tools are scoped; approved programs have the signed-in user's full permissions. It is not a security sandbox. BrowserOS Neo remains required for web actions and localhost navigation remains blocked by the existing browser policy. No CAPTCHA/UAC bypass or credential entry was added.

Small local models can still misinterpret goals. Completion requires verified evidence; after a desktop mutation it additionally requires a fresh snapshot of the affected application/window. This is a guard against unsupported claims, not a proof that arbitrary workflows are correct. Large observations are shortened for the model, while full bounded evidence remains in task history.

## Upstream references

- [MCP interface and command envelopes](https://github.com/vercel-labs/agent-desktop/blob/main/apps/docs/content/docs/guides/mcp.mdx)
- [Headed-mode policy and delivery semantics](https://github.com/vercel-labs/agent-desktop/blob/main/apps/docs/content/docs/guides/headed-mode.mdx)
- [Cursor/session commands](https://github.com/vercel-labs/agent-desktop/blob/main/apps/docs/content/docs/commands/system.mdx)
- [Windows renderer executable-name guard](https://github.com/vercel-labs/agent-desktop/blob/main/crates/windows/src/system/cursor_overlay/image_identity.rs)
