# Professional readiness: candidate scope and evidence

MDT remains an academic alpha. Local validation supports a controlled advisory trial; it does not establish professional readiness, calibrated risk probabilities, complete runtime topology or a service availability guarantee. Professional clearance is deliberately blocked until the evidence below exists for the actual release candidate.

## Candidate scope

| Capability | Intended first professional scope | Explicit limit |
| --- | --- | --- |
| Change review | Python AST and supported JavaScript/TypeScript syntax; literal HTTP routes; bounded Python model changes with supplied context | Generated routes, reflection, arbitrary frameworks and unsupported languages can abstain. No execution of uploaded code. |
| Architecture | Declared Compose and plain Kubernetes topology, configuration references, supported entrypoint discovery | Startup order is not observed runtime communication. Missing services/edges and incomplete scanning stay visible. |
| Findings and scores | Reproducible heuristic indicators with inspectable evidence | Risk/debt scores are not incident probabilities or an automatic approval to deploy. Static findings still require developer review. |
| Clients | Web, Chrome/Edge and VS Code desktop/web using the same API and source snapshots | Local acceptance does not prove HTTPS, CORS, actual deployment permissions or cross-OS behavior. |
| Deployment | Small invited pilot; initially one API process and bounded jobs | The in-process request limiter is not shared between processes. A shared ingress limiter is required before multiple API processes or public abuse exposure. Durable account job quotas are separately transactional. |

The initial accuracy gate covers four **candidate** families: semantic changes, breaking literal routes, Python model schema changes and deployment configuration changes. It does not certify architecture-smell precision/recall, all parser languages or numerical score calibration. Expand the corpus and gate before advertising those additional capabilities as professionally validated.

## Implemented locally on 26 October 2026

- Fixed concurrent request admission: a forced 12-request login race previously admitted all 12 against a limit of three; the regression now admits exactly three.
- Reject conflicting `local_changes` and `before_files`/`after_files` in one patch request. Previously one representation silently overrode the other.
- Added an actual-parser accuracy runner with per-family confusion counts, precision, recall, prediction coverage, abstentions and Wilson intervals. Abstention on a labeled positive counts against recall. Empty denominators remain unknown.
- Added 20 clearly labeled development controls. They are assistant-authored synthetic regressions, **not** independent human ground truth. No scoring weights or result values were tuned to make them pass.
- Added isolated concurrent queue and backup/restore exercises using the actual store. The disposable fixture never reads production data or executes repository source.
- Added an evidence gate tied to current source bytes, report hashes, timestamps, dataset identity, release artifact hashes, target deployment and required review records. It rejects old-source reports, missing files, altered reports, path escapes, insufficient accuracy samples and local evidence substituted for deployed checks.
- Added the accuracy and recovery runners to CI, with evidence artifacts retained. Editing CI locally does not mean remote CI ran.

See [the implementation validation record](PROFESSIONAL_VALIDATION_2026-10-26.md) and [27 October runtime activation and package refresh](RUNTIME_VALIDATION_2026-10-27.md) for executed results and limitations.

## Ordered release gates

Targets in `readiness-policy.json` are proposed starting criteria, not measured guarantees or industry mandates. Agree them with pilot users before the holdout evaluation; changing them afterward requires renewed review.

| Order | Gate | Required evidence |
| --- | --- | --- |
| 1 | Accuracy | At least 10 previously unused repositories pinned to revisions; two independent label reviewers; adjudicated, frozen holdout; at least 50 positive and 50 negative cases per family; precision ≥90%, recall ≥80%, prediction coverage ≥90%. Report intervals and repository clustering; these point thresholds are not confidence guarantees. |
| 2 | Application security | Independent review of account isolation, untrusted source/repository handling, credentials, retention/deletion, upload consent and abuse; refreshed dependency scan; no unresolved high/critical findings. Use the [security review brief](SECURITY_REVIEW_SCOPE.md). |
| 3 | Operations | Actual chosen deployment: 10 concurrent clients (2× the proposed five-user pilot concurrency), ≥1,000 requests over ≥10 minutes, ≥99% expected-request success, API admission/status p95 ≤1 second. Demonstrate worker/database failure, saturation, alerts, backup restore and rollback. Proposed restore ≤1 hour and data loss ≤24 hours. Analysis completion latency must also be measured and agreed by repository size; no current guarantee. |
| 4 | Clients | All five clients against that deployment; identical input/snapshot yields equivalent graph/findings/scores; real grant/denial, cancellation, revocation and Restricted Mode checks; desktop VS Code on at least two operating systems. |
| 5 | Pilot | At least five external developers over 30 actual days, with reviewed findings, support and incident records; no unresolved high/critical defects. Record unsuccessful and abandoned runs, not only successful users. |
| 6 | Approval | Contributor-approved license, publisher, support contact, public privacy notice, HTTPS URLs, named release/rollback owner and human approval of the exact packaged artifacts and preceding evidence. |

Use the [OWASP ASVS](https://asvs.owasp.org/) as the security review reference. This repository does not claim ASVS certification. The operational targets follow the principle of agreed, measurable user-facing objectives described in [Google's SLO guidance](https://sre.google/workbook/implementing-slos/); the specific numbers above are MDT proposals.

## Reproduce local checks

Run from the repository root with the backend test dependencies installed:

```powershell
python scripts/test_isolated.py -q
python scripts/evaluate_accuracy.py --output scratch/readiness/accuracy-development.json
python scripts/check_local_reliability.py --output scratch/readiness/local-reliability.json
python scripts/release_preflight.py --profile professional --config release-config.local.json --evidence release-evidence.example.json
```

The final command currently exits **2**, as intended. It cannot clear a professional release using alpha Boolean flags alone. For an actual held-out evaluation, follow [the evaluation protocol](../evaluation/README.md), then use `--dataset evaluation/holdout.json` with the accuracy runner. Do not overwrite the development control labels to make tests pass.

## Supply evidence without fabricating completion

Copy `release-evidence.example.json` to a private working manifest. Each `evidence` entry is keyed by `accuracy`, `security`, `operations`, `clients`, `pilot` or `approval` and contains a checkout-relative `path` and actual `sha256`. Example structure, using a digest calculated from a real report:

```json
{"schema_version":1,"evidence":{"security":{"path":"scratch/readiness/security-review.json","sha256":"ACTUAL_SHA256"}}}
```

Every report needs `schema_version:1`, matching `kind`, truthful `status`, UTC `created_at`, and the current `source.sha256`. `scripts.readiness_common.evidence()` supplies common fields; it does not supply review results. Evidence expires after 14 days and becomes invalid after relevant source/config/test changes. A frozen candidate can undergo the pilot; review which checks must repeat after fixes.

Additional gate fields are enforced in `scripts/professional_readiness.py`:

- **Accuracy:** the evaluator emits `dataset`, `dataset_sha256`, `split`, `provenance`, individual `cases` and metrics. The gate recomputes metrics and matches labels to the hashed dataset, rather than trusting a summary flag.
- **Security:** `review_type:"independent"`, named `reviewer`, integer `open_high_critical:0`, and `checks` entries `{name,passed}` for every scenario named in the security brief.
- **Operations:** `environment:"deployed"`, exact `api_url`, all measured fields from the operations row, and checks `worker-crash`, `database-outage`, `queue-saturation`, `backup-restore`, `rollback`, `https-cors`, `alerts`.
- **Clients:** deployed environment/API URL; `runs` with `client`, `version`, `os`, `passed`, `parity_verified`; checks `grant-denial`, `token-revocation`, `upload-cancel-send`, `restricted-mode`.
- **Pilot:** deployed environment/API URL, UTC `started_at`/`ended_at`, integer `external_users`, integer `open_high_critical`, checks `finding-review`, `support-response`, `incident-review`.
- **Approval:** named `reviewer`, `approved:true`, checks `license`, `privacy`, `support`, `scope`, `rollback-owner`; `artifacts` entries for `web`, `browser`, `vscode`, each with actual relative path and SHA-256.

Hashes and schema checks provide traceability and catch accidental substitution. They cannot authenticate a reviewer, prove that someone actually ran a test, or replace review of raw evidence. Retain raw logs/review notes privately; keep credentials, customer source and personal data out of public reports. Human approval must inspect these records before setting acceptance flags.

Hosting/account/URL, publisher/contact and license decisions are still pending. Independent reviewers and pilot participants have not been appointed. Those are real remaining steps, not items that can be completed by editing this checklist.
