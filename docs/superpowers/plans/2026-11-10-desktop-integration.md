# Agent Desktop Integration Implementation Plan

**Goal:** Add Windows application control and a visible agent cursor to the existing local assistant, alongside BrowserOS Neo.

**Architecture:** Keep TaskManager as the planner, durable memory, approval ledger and cancellation controller. Add a standard-library stdio MCP client and a closed desktop executor. Reuse the monitor and its approval routes. Add project-scoped file operations and explicitly approved process execution for coding tasks.

**Tech stack:** Python standard library, existing HTML/JS, agent-desktop 1.2.0 (local npm installation).

**Spec:** `use-case/Vercel_Agent_Desktop_Integration_Analysis.md`

## Constraints and decisions

- Browser tasks and ordinary chat retain their current behavior. Computer tasks explicitly opt in to desktop/workspace tools.
- Work in this directory: it is not a Git repository, so worktrees/commits do not apply.
- No second planner, database, memory system, custom cursor, or Python dependency.
- Desktop observations use bounded app/window snapshots and qualified refs. Ref actions must belong to the latest task observation.
- All desktop mutations require a single-use approval tied to exact arguments and observed target. Physical input is explicitly labelled and enabled only for that approved action.
- Headless failures never trigger automatic physical input. Unknown delivery is never replayed.
- Workspace file operations stay beneath `data/projects/<task-id>`; no delete tool. Processes require approval and run with the user's permissions, not an OS sandbox.
- No trace/screenshots by default. Existing redaction applies before storage/export.

## Tasks

- [x] 1. Tests first: MCP lifecycle, bounded transport, native error envelopes, qualified refs, approvals, physical input and no replay. Implement `desktop_client.py`, `agent/desktop_executor.py` and desktop policy.
- [x] 2. Tests first: workspace containment/overwrite/commands and mixed browser/desktop routing, approvals, recovery and cancellation. Implement `agent/workspace_executor.py`; extend `agent/task_manager.py`, `server.py` and API tests.
- [x] 3. Tests first: computer opt-in, approval view and connection status. Extend existing composer/monitor; document installation and limits; run Python/Node regressions and a live Notepad MCP check.

## Review focus

- Missing binary/offline MCP, timeout after delivery, malformed/oversized replies: clear failure and no replay.
- Stale refs, target changes, approval expiration/restart: no unintended mutation.
- Headed action authorization cannot be smuggled into a read or a different action.
- Paths through traversal, symlinks/junctions, ADS or Windows device names cannot escape the workspace.
- Old browser-only tasks, export and backups remain compatible; pending approvals survive refresh but are invalidated on server restart.

## Evidence / ledger

- Upstream MCP and headed-mode docs verified through the GitHub connector. Installed 1.2.0 locally under ignored `runtime/agent-desktop`; native `status` reports Windows accessibility granted.
- Initial tool schemas captured from the installed MCP server in `runtime/desktop-tools.json`.
- Final review by a fresh read-only reviewer found blocked-stdin timeout, unrelated-app completion, unbounded planner context, large-file hashing and pending-argument redaction defects. Each now has a regression test observed failing before its fix; focused and full suites passed afterward.
- Native state uses the upstream private user home after the project drive's inherited ACLs were rejected. The renderer requires `agent-desktop.exe`; setup creates that alias and skips rewriting an identical running executable.
- Live Notepad: semantic click in a new tab, set-value, exact readback and cursor rendered=true. Live Qwen 4B: selected desktop inventory tool, observed results and completed its report. Evidence: `runtime/desktop-smoke-result.json`, `runtime/desktop-model-smoke.json`.
- Final checks: `python -m unittest discover -q` = 86 passing; `node --test test_agent_monitor.cjs test_voice.cjs` = 21 passing; both changed JavaScript files passed `node --check`. `python setup_desktop.py` passed, including native status.
- Idle service restarted on the existing Qwen 4B model. Live `/api/status`, `/api/agent/desktop/status` and `/` returned 200, model available=true, desktop connected=true/accessibility granted, and Computer mode present.
- BrowserOS Neo's local MCP endpoint was offline, so no live web workflow or visual browser UI check was performed. Existing browser/API/monitor regressions passed; no fallback browser was used.
