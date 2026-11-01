# Professional-readiness implementation and validation — 26–27 October 2026

The local implementation and validation are complete for this pass. **MDT is not professionally cleared.** The new evidence gate correctly reports `professional_ready: false`; external review, deployment and pilot evidence remain required. Artifact filenames use the UTC validation date, 26 October. The [27 October continuation](RUNTIME_VALIDATION_2026-10-27.md) subsequently activated the fixes in Docker and refreshed the release-image security checks.

## Changes and verified outcomes

| Change | Why | Verified result |
| --- | --- | --- |
| Atomic request-limit admission/reset | Concurrent requests could replace each other's counters | The forced race reproduced **12 admitted against a limit of three** before the fix. The same test now admits exactly three. |
| One source representation per patch request | A request containing both `local_changes` and file maps silently ignored the maps | Complete maps and either partial map alongside `local_changes` are rejected. Existing single-representation submissions remain covered by the backend suite. |
| Accuracy evaluator and development corpus | Pass counts did not measure precision, recall or abstention | **20/20 development controls passed** across four families, including two unknown-source controls. Per-family minimum sample requirements correctly fail; these controls cannot certify accuracy. |
| Isolated reliability runner | Queue/recovery behavior needed reproducible concurrency and failure evidence | **15 invariant checks passed**, including quota admission, idempotency, lease fencing, cancellation, bounded crash recovery, terminal source removal and backup restoration. |
| Professional evidence gate | Alpha checklist flags alone were insufficient | Rejects missing, altered, stale, wrong-build or wrong-environment evidence, missing finding families, tuning repositories, changed labels, duplicate cases, invented summary metrics and a short pilot. |
| CI and isolated test runner | New evaluators must remain repeatable | Accuracy and recovery commands are wired into CI; isolated copies include their source and fixtures. Remote CI was not triggered. |

The backup exercise initially left SQLite connections open after committing, causing a Windows temporary-directory cleanup error. The runner now explicitly closes both backup connections; the successful rerun is recorded. This was a defect in the new test utility, not evidence of lost application data.

## Executed tests

| Run | Result | Scope |
| --- | --- | --- |
| Full backend suite in disposable Python 3.11 Alpine copy | **432 passed, 12 skipped**, 40.48 s | The runner had no network; opt-in database checks were intentionally skipped. One Starlette/httpx deprecation warning remains. |
| PostgreSQL and Neo4j integration suite | **12 passed**, 9.19 s | All previously skipped cases ran against fresh disposable databases. No production database or graph was used. |
| Combined unique backend tests | **444 passed** | Includes **30 new regression/evidence tests**. No current backend test remains skipped after combining the two runs. |
| Accuracy development corpus | **20 passed** | Actual parser and finding predicates, offline source pairs; not independent held-out accuracy. |
| Queue and recovery experiment | **40 jobs, concurrency 10; 15 checks passed** | Local SQLite synthetic store workload. 1.630 s complete queue cycle; enqueue p95 371.52 ms; backup/restore equality verified in 0.0095 s. These timings do not establish deployed HTTP latency or production recovery objectives. |
| Professional preflight | **Exit 2, expected blocked** | Publication metadata and all six professional evidence gates remain incomplete. |
| Patch hygiene | **Passed** | `git diff --check`. |

Full passing test identifiers, raw JUnit file hashes, the source fingerprint and fixes are recorded in [the validation JSON](benchmarks/professional-validation-2026-10-26.json). Other evidence:

- [Accuracy metrics and every control prediction](benchmarks/professional-accuracy-development-2026-10-26.json)
- [Queue/recovery checks and measured timings](benchmarks/professional-local-reliability-2026-10-26.json)
- [Current professional gate decisions](benchmarks/professional-gates-2026-10-26.json)

All records refer to source fingerprint `f4e59d23d325de29160e728575f0d501bf2a74e245885110ea6aa95c28f4c5cb` (213 relevant files). The fingerprint includes uncommitted and untracked implementation/test files, not just the existing Git commit. Subsequent relevant edits invalidate this evidence.

## Remaining work, in order

1. Agree the limited advisory scope and proposed acceptance targets in [the readiness policy](PROFESSIONAL_READINESS.md).
2. Have two independent reviewers prepare and adjudicate a fresh holdout from at least ten unused repositories, following [the evaluation protocol](../evaluation/README.md). No holdout labels or accuracy claims were fabricated in this pass.
3. Complete the independent application-security review and fix/retest its findings. [Review scope and existing test entry points](SECURITY_REVIEW_SCOPE.md) are prepared.
4. Select hosting/accounts and actual HTTPS URLs, publisher/support identity and contributor-approved license. Then validate the actual deployment's ingress limits, HTTPS/CORS, load, alerting, worker/database failures, backup restore and rollback.
5. Run all clients against that deployment, including deployed VS Code web and desktop checks on a second operating system. Prior local native permission results remain local evidence; they were not relabeled as deployed checks.
6. Run the real 30-day external pilot, review findings and incidents, and obtain approval of the exact release artifacts.

At the end of this pass, changes were local source changes and application containers had not yet been rebuilt. The [27 October continuation](RUNTIME_VALIDATION_2026-10-27.md) then rebuilt the backend, activated both fixes, and refreshed the hosted candidate and its scans. The disposable validation containers/network from this pass were removed after their checks. No Git commit, push or public deployment was performed.

Cleanup exception: automatic approval review rejected deletion of the earlier failed runner's synthetic fixture directory `C:\Users\DELL\AppData\Local\Temp\mdt-readiness-95zcrtj5`, reporting only “blocked by policy.” That small temporary directory remains; the rejected deletion was not retried through another tool.
