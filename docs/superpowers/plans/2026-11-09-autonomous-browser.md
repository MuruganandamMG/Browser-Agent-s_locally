# Autonomous browser implementation plan

> **For agentic workers:** Use superpowers:subagent-driven-development or superpowers:executing-plans. Keep tests and responsibilities isolated; do not overwrite unrelated voice changes.

**Goal:** Implement the approved BrowserOS high-autonomy blueprint end to end.
**Architecture:** Existing Python HTTP server and SQLite remain. A bounded background task controller calls the local model for structured next actions, dispatches only validated browser operations, persists intent/outcome and exact approvals, and exposes polling to an accessible monitor. Existing chat uses this same controlled browser path; raw SDK code is no longer model-facing.
**Tech stack:** Python standard library, installed neo MCP/SDK, plain JavaScript/CSS.
**Spec:** `use-case/BrowserOS_Neo_High_Autonomy_Implementation_Blueprint.md`.

## Global constraints and decisions

- No new dependencies; dict validation replaces illustrative Pydantic schemas.
- Preserve automatic neo port discovery, optionally accept validated loopback NEO_MCP_URL.
- Preserve existing voice optimization and chat history. One shared inference/runtime lock.
- Protected/uncertain website changes require exact expiring approval; credential/security/payment/destructive actions blocked by default. Read/search/navigation automatic where identifiable.
- No raw JavaScript route exposed to the model. Parallel agent operations initially restricted to independent reads/snapshots/new tabs, max five; no policy bypass through old parallel tool.
- Bounded polling rather than SSE. Stop is cooperative at operation boundaries; no claim of immediate cancellation of an already executing operation.
- Recover after restart by pausing, invalidating approvals and observing before replanning, never replay an uncertain mutation.
- Existing directory is not a Git repository. Work in place, maintain this ledger, no fabricated commits/worktrees.

## Interfaces

`agent.browser_executor.BrowserExecutor.run(action, tabs, approved_fingerprint=None)` mutates a task-owned `tabs` dict (string page IDs to observations) and returns JSON `{ok,status,...}`. Status: `ok`, `approval_required`, `denied`, `error`, `uncertain`, `human_required`. Approval result includes `approval: {fingerprint, action, url, target, reason}`. Successful results include page, url, observation/snapshot, verified. `ACTION_TOOL` is the JSON function schema. `run_parallel(tasks,tabs)` supports independent safe reads with errors isolated.

`agent.task_manager.TaskManager(store, runtime, model_request, model_name, executor=None)` owns asynchronous task lifecycle. `create(session_id,request)`, `get(id)`, `list(session_id)`, `control(id,operation,data)`, `recover()`, `close()`. `model_name` callable. Tasks include id, session_id, request, state, steps, events, tabs, approval, result, error, created, updated. API exposes sanitized JSON without hidden prompts.

## Review focus

1. Raw browser JavaScript/legacy parallel must not bypass policy.
2. Stop/approval/restart races must not replay external mutations.
3. Local/private URLs, redirects and untrusted page contents must not silently gain trust.
4. Busy model locks and model switching must not corrupt task state.
5. UI refresh/chat switching must recover task state and never execute from rendering.

## Tasks

### 1. Validated browser adapter and policy
- [x] Add failing executor/policy tests: schema/URL/ref/ownership/approval/uncertain errors and parallel isolation.
- [x] Implement `agent/browser_executor.py`, `agent/policy.py`; reuse neo transport/pointers with bounded trusted scripts and installed-schema discovery.
- [x] Verify tests and a live public read, document network policy limits honestly.

### 2. Durable task lifecycle and model planner
- [x] Add failing task tests with fake inference/browser for completion, approval fingerprint/expiry, cancel, restart, invalid actions, bounded recovery, no duplicate effects.
- [x] Add task persistence through existing ChatStore backup writes, worker/controller, model planner and verification records.
- [x] Verify small-context history budgeting, one runtime slot, and error states.

### 3. API and controlled chat tools
- [x] Test routes, local validation, invalid IDs, approval/cancel, busy model, export/deletion interaction.
- [x] Wire task APIs and lifecycle to server; replace raw browser schemas/dispatch, preserve ordinary/voice chat.
- [x] Verify legacy regression suite and safe error responses.

### 4. Live monitor and integration
- [x] Add browser mode toggle, progress monitor, exact approval/reject/Stop/resume and reconnect behavior using existing interface styles.
- [x] Test JavaScript lifecycle and UI in neo at narrow/wide sizes.
- [x] Run full regression and deterministic end-to-end fixture; exercise live model/neo where available.
- [x] Final fresh-context review, fix findings, update README and blueprint implementation record with limitations and evidence.

## Progress / rulings

- Design authorized by user: “Implement it end to end”. No new design approval loop.
- Installed neo tools/list responded; run, tabs, snapshot, act, navigate available. Config proxy remains 9010.
- Ruling: reuse compact modules rather than seven empty architecture layers; enforce behavior in executor and controller.

- Task 1: complete ? 21 policy/executor tests; live public navigation/click/read/back/fill/parallel checked.
- Task 2: complete ? durable controller, exact approvals, bounded model planning, cancellation/restart/uncertain-action and privacy regressions.
- Task 3: complete ? API, export/deletion, shutdown, raw tool removal and MCP transport reset.
- Task 4: complete ? 12 monitor + 7 voice tests; desktop/390px QA, real local model task completion and UI Stop checked.
- Fresh final checks: 58 Python tests + 19 JavaScript tests passed; syntax/compile checks passed.
- Ruling: Browser mode is explicit and voice stays ordinary optimized conversation; this removes the legacy policy bypass while preserving recent voice behavior.
- Ruling: no egress-firewall claim; installed browser SDK cannot prevent all redirect/subresource/DNS-rebinding requests.
- Ruling: lost Neo tab ownership pauses for inspection rather than silently claiming another connection's tabs or replaying submissions.
- Ruling: existing non-Git workspace retained; no worktree/commits manufactured.
- Final review: cancellation overwrite, tool name, context loss, native timers, transport reset, uncertainty acknowledgement/history, private evidence and full PEM redaction fixed with regressions.
- Not checked: broad model benchmarks, forced live Neo restart, signed-in consequential operations. All temporary QA tabs and service stopped; original app service left running for normal user restart.
