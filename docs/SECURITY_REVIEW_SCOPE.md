# Independent application-security review brief

Status: local controls and regressions exist; **independent review pending**. This is a review brief, not an ASVS compliance certificate. Review the web/API, extension trust boundaries and deployment configuration using the current [OWASP ASVS](https://asvs.owasp.org/), pinning requirement identifiers to the version actually reviewed.

## Data and trust boundaries

Untrusted repository URLs, refs, manifests and submitted source enter authenticated API jobs. Jobs retain immutable inputs while running, pass source to bounded parsers without executing repository code, and store results under the submitting account. Queued/running source, result-derived excerpts, local SQLite/PostgreSQL records, browser storage and VS Code secret storage have different lifetimes. Review deletion, backups and logs as well as terminal-job cleanup.

The shared API trusts the authenticated server-side account role, not a client JWT role claim. Worker leases fence stale writers. Browser host access and VS Code full-source upload require native consent. Static analysis is advisory and potentially incomplete; false confidence is a product-security concern too.

## Required scenarios and existing evidence entry points

| Evidence check name | Review task | Existing automated entry points |
| --- | --- | --- |
| `account-isolation` | Cross-account reads/writes/deletion/cancellation for projects, jobs, snapshots, reviews and previews; inactive accounts; forged roles | `tests/test_projects_jobs.py`, `tests/test_store_security.py`, `tests/test_finding_reviews.py`, `tests/test_history_and_drift.py` |
| `source-upload` | Cancel sends no source; Send uses exactly the reviewed before/after snapshots; Restricted Mode; conflicting payload representations; source/log retention | Native acceptance report in `docs/benchmarks/release-vscode-interactive-2026-10-26.json`; `tests/test_request_admission.py`; extension host tests |
| `untrusted-repository` | URL/ref/path validation, traversal, malformed/binary/oversized syntax, time/memory bounds, no code execution, archive limits and GitHub failure/abstention | `tests/test_source_parser_and_cache.py`, `tests/test_public_github_source.py`, `tests/test_git_analyzer.py` |
| `credentials` | Password handling, expiry/refresh/logout, real role re-resolution, protected endpoints, no tokens in URLs/settings/logs; production CORS/TLS and secrets | `tests/test_auth.py`, `tests/test_projects_jobs.py`; Chrome/Edge and VS Code native acceptance records |
| `deletion` | Account/project isolation, running-job deletion race, terminal input removal, expiry, backups and external telemetry retention | `tests/test_store_security.py`, `tests/test_projects_jobs.py`; isolated recovery runner |
| `abuse` | Concurrent authentication limits, signup, job quotas, idempotency conflicts, payload limits, queue saturation, process/replica scaling | `tests/test_request_admission.py`, `tests/test_store_security.py`, `tests/test_webhook_security.py` |
| `dependency-scan` | Scan exact runtime images/artifacts; review reachable findings and refresh before release | Existing CI image scan and `docs/benchmarks/release-security-2026-10-25.json`; old clean scan is not a new-image attestation |

## Confirmed fixes from this pass

The original limiter performed read/filter/replace/append without a lock. A forced concurrent schedule admitted 12 requests against a limit of three. The fixed critical section serializes admission and reset; the same regression now admits exactly three. This is per-process protection. It does not solve distributed abuse, active-client memory growth or proxy identity configuration. Evaluate the actual ingress limiter and trusted forwarding configuration before public exposure.

Patch input accepted both `local_changes` and complete or partial file maps, then preferred `local_changes` and silently discarded the maps. Admission now rejects this ambiguity. Existing VS Code submissions use file maps and remain valid; local-change clients can submit that representation alone.

## Remaining review obligations

Independently reproduce attacks on a disposable deployment; do not exercise destructive cases against user data. Review actual HTTPS/CORS, origin handling, ingress limits, secrets, account provisioning, least-privilege database access, backups and their retention. Record severity, impact, reproduction, fix and retest evidence for each issue. Zero dependency-scanner findings does not clear these application controls.

Populate a security evidence report only after that review. Record the reviewer, review scope/version, raw evidence references and any accepted lower-severity residual risks. High/critical issues must be fixed and independently retested before the professional gate can pass.
