# Remediation simulation clarity and validation

The reported OpenTelemetry preview is a real zero-change result: the bottleneck finding disappears on `flagd` and appears on `flagd_facade`. Each carries weight 20, so the total stays at 315 and the displayed score remains 89.573. Adding an intermediary does not, by itself, reduce the responsibility concentrated in that route.

## Changes

- Replaced the blanket “high-impact recommendations” wording with possible changes to test. A simulation leads with lower debt, no modeled improvement, higher debt, or unavailable evidence.
- Show the affected services for findings that disappear and appear, explain equal-weight replacements, and give a next action. Zero change has neutral styling instead of the former green success treatment.
- Explain `A → B` as A depending on B. Expandable details retain protocols and endpoints, distinguish startup ordering from calls, and group repeated service pairs for readability without changing submitted edits.
- Provide implementation steps: design the intermediary's responsibilities, update callers and configuration, test contracts and failure behavior, and analyze the actual new revision. Graph edits do not modify source code.
- Link recommendations that use the backend's singular `finding_id` to their findings. Previously the UI recognized only `finding_ids` or legacy keyword matches.
- Exclude startup-order declarations from newly generated topology-remediation plans. The replayed `flagd` proposal now needs 24 edits instead of 44. Saved analyses keep their original 44-edit proposal; rerunning analysis generates the revised plan.
- Return an explicit outcome and a per-finding weighted explanation from the API. A replacement finding no longer receives a contradictory “no measurable change” message.
- Regenerate the bundled public demo from the detector. No score or benchmark outcome was manually substituted.

## Verification

| Check | Result |
| --- | --- |
| Frontend unit, graph and actual React server-render checks | 31 passed |
| Relevant backend simulation, demo, LLM fallback, detector, parity and project/job checks in the isolated Python 3.11 validation image | 107 passed |
| Lint, production frontend build, local backend/frontend Docker builds, whitespace checks | Passed |
| Offline replay of the earlier ten-repository inventory | Eight usable captured graphs; two had no captured topology. 36 previews: 17 improved, 13 unchanged, six worse; no execution or reconciliation errors |
| Exact saved analysis via the rebuilt live API | Original 44-edit `flagd` proposal reproduced 89.573 → 89.573, one finding removed and one introduced; outcome and weight explanation correct |
| Persistence check around the live preview | Saved analysis and all four project records unchanged |
| Public API demo | Three recomputed previews include the new score explanation |
| Browser visual interaction | Not completed: Browser runtime returned no available connection, including after opening the site |

The first native Python attempt lacked the async pytest plugin and reported 14 async test failures; demo export also lacked dependencies in its sanitized child environment. Those environment failures were resolved by running the checks and export in the existing isolated validation image. They are not counted as product failures or as passing native-environment tests.

See [the complete replay results](benchmarks/remediation-replay-2026-10-27.json). This replay uses previously captured graphs and is not a fresh GitHub scan, held-out accuracy validation, or an independent security review. Prior release evidence remains bound to its original source fingerprint; this UI change does not clear the professional-release gates.

## Using the result

For the reported `flagd` proposal, revise the design before adopting it solely to reduce debt. Confirm whether that concentration is intentional for the shared configuration service, inspect actual call volume and failure behavior, and consider caching, responsibility separation or replication only when those measurements support the design. This static model cannot choose those tradeoffs from an arrow alone.

The changed website is served by the local Docker stack at `http://localhost:5173`. Refresh the page to load the new frontend; signing in again may be necessary after the backend restart. Nothing was pushed or publicly deployed.
