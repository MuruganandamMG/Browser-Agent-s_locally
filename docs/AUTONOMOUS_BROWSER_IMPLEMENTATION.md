# Autonomous browser implementation

## Verified image-download repair

The running service was gracefully stopped and restarted with current code after a mixed frontend/backend deployment left the old acknowledgement requirement active. The browser tool now exposes `download`: use an observed download-button ref, or omit ref on a direct image page. A trusted same-origin download link is created only for image content, and Neo's actual download tool saves the file. The backend verifies local file existence, nonzero size (up to 50 MB), and SHA-256 before returning download success. Saved-file evidence is included in planner context.

Live chat verification on 9 November 2026: the prompt requested a random image from `https://picsum.photos/800/600`, actual saving, and path/size/hash verification. Qwen 9B executed navigation (redirect), fresh snapshot, `download`, and completion without any approval/acknowledgement prompt. The app saved `C:\Users\Muruganandam\Downloads\405-800x600.jpg`, **99,189 bytes**, SHA-256 `cbd2a54f6e55b27772d35dc9bcf754e79629dd4106cabc1d512aa8d50ca040e4`. File size, JPEG signature and hash were independently checked, and the chat monitor showed `completed`. This was the application's own tool execution, not a manual download substituted for the test. **64 Python tests and 19 JavaScript tests passed.**

## Automatic interaction update

The user subsequently requested no routine confirmations. Ordinary website actions now run automatically. Approval UI and the uncertainty acknowledgement checkbox have been removed. An uncertain result triggers fresh page snapshots and replanning while retaining the do-not-repeat ledger. A dispatch guard rejects repeat uncertain operations, and recovery requires verified fresh observations before the planner continues. Resume requires only a click, with no acknowledgement payload. Stop, action/ref/ownership validation, private-network checks, sensitive-data protections, restart recovery and bounded error handling remain. The original implementation record below describes the earlier approval-based delivery and is retained for history.

Automatic-mode verification: **63 Python tests and 19 JavaScript tests passed**, with syntax/compilation checks passing. Deployment restart was attempted after checking that no browser jobs or chat replies were running, but automatic approval review rejected termination/restart of the running Python/model processes with “blocked by policy.” A normal app restart is required to activate this backend change; no live automatic submission was executed.

Implemented 9 November 2026 from [the approved blueprint](../use-case/BrowserOS_Neo_High_Autonomy_Implementation_Blueprint.md).

## Use it

1. Stop the existing app with Ctrl+C in its launcher terminal, then run `python start.py`.
2. Keep BrowserOS neo open. Open `http://127.0.0.1:3000`.
3. Select **Browser: On** beside the composer and send a complete browser task.
4. Follow the monitor. Routine actions proceed automatically; review exact protected actions before approving.
5. Use Stop to stop subsequent operations. Use Resume after checking any uncertain website outcome.

Suggested first request: “Open https://example.com, read its title and explanation, and summarize with the source URL.”

Ordinary chat retains writing, calculator and clock functions. The existing optimized voice path is preserved and does not perform browser actions. Dictation can supply text for a manually submitted Browser-mode task.

## What changed

| Area | Implementation |
| --- | --- |
| Planner | Local model selects exactly one validated JSON action per iteration; tool output and webpage text are untrusted evidence |
| Actions | New tab, navigate, back, snapshot, read, click, fill, press, select and scroll |
| Executor | Trusted SDK templates; installed `run` schema discovery; task-owned tabs; current URL/ref/DOM/form checks before dispatch |
| Policy | Public URL/DNS checks, sensitive-target restrictions, protected/uncertain operation approvals |
| Verification | Post-action observations; final URL, field value, navigation or newly appearing expected-text checks; uncertain effects pause |
| Visuals | Existing pointer reused with pulse/glow and action/direction labels; no OS cursor movement |
| Parallel work | Up to five task-owned tabs; independent opening/reading/snapshots; isolated child results |
| Lifecycle | Queued, planning, executing, verifying, recovering, awaiting approval, paused, completed, cancelled, blocked states |
| Persistence | Task request, model, steps/intents, observations, tabs, approval and ordered events in one JSON task record per SQLite row |
| Approval | Exact action + current page/target/form fingerprint; five-minute expiry; consumed before execution; fresh state rechecked |
| Cancellation | Cooperatively checks boundaries, including after inference; no later completion can overwrite cancelled state |
| Recovery | Bounded replan attempts; fresh snapshots on resume; uncertain-action ledger retained separately from recent observations |
| Restart | Incomplete tasks pause, executing intents become uncertain, approvals invalidated; no automatic replay |
| Monitor | Nonoverlapping one-second polling, session restoration, exact approval/reject, Stop, resume/uncertainty acknowledgement, reconnect, sanitized Markdown result |
| Privacy | Recognizable private strings and sensitive field values redacted from agent persistence/export; normal chat storage unchanged |
| API | Task create/list/get/events, approve/reject/cancel/resume, neo connectivity status |
| Chat safety boundary | Removed model-facing raw JavaScript and old parallel action tool; explicit Browser mode uses the controller |

No dependency was added. The existing Python HTTP server, llama.cpp runtime, SQLite backup mechanism, browser connection and frontend styling remain.

## Source map

- `agent/policy.py`: closed schemas, URL validation, classifications, fingerprints and action redaction.
- `agent/browser_executor.py`: trusted SDK templates, observations, interaction checks, verification, pointers and parallel reads.
- `agent/task_manager.py`: persistence, context budgeting, local model planner, worker lifecycle, approval/cancel/resume/recovery.
- `server.py`: task API, export/deletion integration and shutdown.
- `neo_client.py`: invalidate failed transport sessions without retrying dispatched actions.
- `chat_tools.py`: ordinary chat calculator and clock; browser execution is not exposed here.
- `public/agent-monitor.js` and `.css`: browser-task controller/view and responsive styles.
- `public/app.js` and `index.html`: explicit mode, session restoration and composer integration.

The blueprint's seven proposed engine modules are combined into three focused modules. Logical steps, approvals, events and tab ownership are kept within each task record instead of separate tables. Existing chat backup snapshots cover the task table too. There is no destructive migration.

## Execution bounds

- One shared runtime lock prevents concurrent inference/model changes. Approval/paused jobs release compute for ordinary chat.
- At most 60 iterations or 30 minutes per run; three consecutive planning/action errors pause the task.
- Neo batches remain subject to the installed 30-second cap. An already running operation cannot be instantly cancelled.
- Each model HTTP request has a 180-second timeout. Planner output is capped at 512 tokens, with thinking disabled.
- Compact per-tab observations and recent results are serialized structurally. User request endings are preserved; overly long requests for the selected model are rejected.
- Default application model, model picker and original conversation/voice controls are preserved.

## Evidence from this implementation session

Automated checks cover schema/URL/ref/ownership rules, sensitive and ambiguous actions, stale approval fingerprints, malicious code as data, transport failures, parallel isolation, task completion, approval replay/expiry handling, cancellation races, restart recovery, evidence redaction in primary/backup, compact context, uncertain-action history, API Host validation, export/deletion and UI lifecycle.

Final automated result: **58 Python tests and 19 JavaScript tests passed**, with JavaScript syntax and Python compilation checks passing. Full PEM private-key evidence redaction is covered in addition to recognizable-token redaction.

The live test used a temporary chat database and preview server on port 3001, with the existing Qwen 4B inference service and real BrowserOS neo. It did not switch models or modify the user's saved conversations.

Observed live results:

- Backend/model task completed `new_tab → read → finish_task` on example.com and saved a source-linked summary.
- Browser UI submitted a second task, showed planning/progress, polled completion and restored its report after refresh.
- Stop was clicked during another task; persisted state remained cancelled and no subsequent operation ran. One already-dispatched new-tab operation finished, matching the UI's cooperative-stop notice.
- Adapter smoke checks exercised example.com navigation, an IANA link click, page read, back navigation, a Google search-field fill, and parallel public reads. Navigation/fill readback reported verification and pointer feedback.
- Desktop and 390px-wide monitor layouts were inspected. The narrow viewport had no document-level horizontal overflow.
- Exact approval/reject and uncertain/restart paths were exercised against deterministic fake browser/model boundaries in automated tests; no real message, payment, deletion or account change was submitted.

Fresh review caught and fixed tool-name mismatch, cancelled-state overwrite, malformed/truncated planner context, native browser timer receiver errors, stale MCP-session recovery, stale uncertainty acknowledgements, lost uncertain-action history, and sensitive observation persistence.

Run the checks:

```powershell
python -m unittest discover -v
node --test test_voice.cjs test_agent_monitor.cjs
node --check public/app.js
node --check public/agent-monitor.js
python -m compileall -q agent server.py neo_client.py chat_tools.py
```

## Boundaries and remaining limitations

1. **Browser network isolation:** public URL/DNS checks are not a firewall. Redirects, subresources, webpage scripts and DNS rebinding can perform requests before final-URL inspection. Use external egress controls if full local-network isolation is required.
2. **Heuristic policy:** unknown interactions require approval, but arbitrary website JavaScript can hide side effects. No general website classifier can guarantee that every navigation or search is harmless. Keep consequential work supervised.
3. **Verification:** the executor verifies concrete observable facts. The model still interprets whether those facts satisfy the whole user request; it is not a formal proof of task completion.
4. **Neo restart/ownership:** a new MCP connection can lose ownership labels. Resume then pauses safely rather than taking over another connection's tabs. Inspect the browser and cancel/start a new scoped task if ownership cannot be restored.
5. **Redaction:** recognizable tokens, email/card-like strings and known sensitive fields are handled conservatively. This is not exhaustive detection of arbitrary secrets or personal information. Existing chat history remains local plaintext SQLite data.
6. **Budgeting:** context is conservatively character-budgeted rather than exactly tokenized; small-context models may still encounter context errors. These pause rather than silently discarding task constraints.
7. **Scope choices:** parallel browser mutations are sequential policy-checked operations; raw-code escape hatches are removed. Browser mode is explicit, and voice remains optimized conversation rather than autonomous control. Neo must already be open.
8. **Unmeasured:** no broad model reliability benchmark, no forced live Neo restart, and no live signed-in consequential-operation test was performed. Automated test doubles cover those lifecycle states.

Only code and documentation were updated. The existing launcher/service needs a normal restart to load the new backend. QA services/tabs are temporary and do not replace the user's running app.
