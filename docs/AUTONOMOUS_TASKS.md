# Autonomous tasks ? 11 November 2026

New tasks default to autonomous execution. Validated desktop/workspace operations no longer pause for exact-action approval. Recoverable errors replan up to eight consecutive failures; unrecoverable problems, policy denials and execution limits produce a final chat report instead of Resume. Uncertain mutations remain protected against replay. Login/CAPTCHA cannot be bypassed.

Requests and final reports are stored as ordinary conversation messages, keyed by task ID to avoid duplicate insertion. The monitor refreshes chat on task creation/completion and hides its duplicate terminal report. Legacy explicitly supervised test/task records remain compatible.

Same-page parallel reads now serialize, and nested batch errors reach the planner. Image-element refs are converted to a real download link on direct image pages.

Verification: Python regression suite and Node monitor/voice tests; live BrowserOS inspection confirmed the terminal report appears in normal chat without Resume controls. The live image download hit a BrowserOS timeout and was stopped; successful image saving was not verified.

Deployment: the first restart loaded autonomous execution and normal chat reports. Automatic approval review rejected the follow-up restart with ?blocked by policy?; the final image-download correction and subsequent small refinements are saved but were not reloaded. No alternate process-termination method was attempted.
