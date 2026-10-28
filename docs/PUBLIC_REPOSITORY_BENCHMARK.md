# Public GitHub repository scoring assessment - 20 October 2026

**Historical baseline.** The failures below were addressed in the [21 October fixes and rerun](ACCURACY_FIXES.md). This original assessment and its raw results are preserved for comparison.

**Original verdict: deterministic and bounded, but not yet reliable enough to claim accurate deployment-risk ranking or general microservice discovery.**

The run exposed false API-change alarms, a missed cross-file public-model change, omitted backend source and unsupported topology. Application scoring code and weights were not changed to improve the benchmark.

## Method

- Downloaded immutable public GitHub archives at exact commits. Archive digests and implementation fingerprints are in the result JSON. Public source archives remain only under ignored scratch/public-benchmark/.
- Used a disposable Python 3.11 backend container limited to 2 CPUs and 1 GiB. Downloaded application code, dependencies, manifests and tests were never executed.
- Replaced only GitHub tree/blob transport with bounded archive reads to avoid anonymous API quotas. Production onboarding, evaluate_job, extraction, detectors, scoring and previews ran unchanged. Image fingerprints match the current local backend.
- This is an application-core assessment, not a browser, authenticated HTTP, GitHub REST quota, tracing or public deployment test.
- Tested manually labeled controlled edits to real source, plus a genuine Express revision comparison. Controlled mutations are not upstream commits or observed incidents.
- Python comment controls preserve identical ASTs. Route renames/deletions and ItemBase.title inheritance through ItemCreate/ItemPublic were checked against the actual upstream files.
- Scored cases ran twice, each with a separate no-edit preview check. No live projects, accounts, credentials or database rows were created.

## Pinned repositories

| Repository | Exact commit | Archive files | Import outcome | Debt index |
| --- | --- | ---: | --- | ---: |
| [Google Online Boutique](https://github.com/GoogleCloudPlatform/microservices-demo/tree/38e7348eb289eb5b87c0c6e8cb19ced0449dc389) | 38e7348eb289eb5b87c0c6e8cb19ced0449dc389 | 364 | Failed discovery | Unavailable |
| [FastAPI full-stack template](https://github.com/fastapi/full-stack-fastapi-template/tree/b1125d8839482cb7bbae603ddc6d0081bf87532e) | b1125d8839482cb7bbae603ddc6d0081bf87532e | 248 | 5 inferred nodes / 3 edges; partial | 21.429 |
| [Express](https://github.com/expressjs/express/tree/0dee2c52c7c873498f8ed7d8ee4ddd0a04d3ada8) | 0dee2c52c7c873498f8ed7d8ee4ddd0a04d3ada8 | 214 | One examples node / 0 edges; partial | 12 |
| [FastAPI](https://github.com/fastapi/fastapi/tree/8ee0e7e96baf68a02212199d0d64153945b701ba) | 8ee0e7e96baf68a02212199d0d64153945b701ba | 3,193 | One docs_src node / 0 edges; partial | 12 |

Express comparison base: release 4.21.2, commit 1faf228935aa0a13111f92c28ee795be64ce3f0f, with 234 archive files.

Debt reflects the captured import. Ordinary change analysis reuses that topology, so these edits do not produce a new imported graph. Low debt is not trustworthy with incomplete topology or library/tutorial inputs.

## Actual scores

| Change | Changed paths | Paired source bytes | Risk / 100 | Assessment |
| --- | ---: | ---: | ---: | --- |
| Identical FastAPI template source | 0 | 6,892 | 0 | Correct no-change result |
| FastAPI template: comment only | 1 | 6,921 | 30 | False API-change alarm |
| FastAPI template: rename HTTP route | 1 | 6,909 | 30 | API change detected |
| FastAPI template: delete route module | 1 | 3,446 | 30 | API change detected |
| FastAPI template: cross-file public model type change | 1 | 6,954 | 5 | API change missed |
| Express example: comment only | 1 | 568 | 5 | No API-change flag; base file penalty |
| Express example: rename HTTP route | 1 | 555 | 30 | API change detected |
| Express example: delete route module | 1 | 269 | 30 | API change detected |
| Actual Express 4.21.2 to pinned HEAD, all supported changed files | 115 | 1,302,658 | Rejected | Correct 100-file limit |
| Actual Express upgrade, core subset only | 12 | 159,588 | 55 | Real comparison; no incident label |
| FastAPI routing.py: comment only | 1 | 520,815 | 30 | False API-change alarm |
| 100 real small Python files: comments only | 100 | 37,972 | 65 | False API-change alarm / high score |
| 100 real larger Python files: comments only | 100 | 1,426,664 | 70 | False API-change alarm / high score |

The full Express comparison was rejected; no whole-release score was obtained. The separate 12-file lib/, index.js and package.json subset scored 55 and must not be presented as the complete upgrade. Express documents compatibility breaks in its [official v5 migration guide](https://expressjs.com/en/guide/migrating-5/); that does not establish a true numeric incident probability for this subset.

## Accuracy findings and causes

1. **Comment-only false positives.** backend/app/api/routes/items.py and fastapi/routing.py score 30 despite unchanged contracts and identical ASTs. Filename/path heuristics add 25 API points without a contract change. The 100-file comment controls score 65 and 70 because file-count, API-path and schema/config-path factors accumulate. See [API heuristic](../backend/services/impact_engine.py:317) and [risk weights](../backend/services/impact_engine.py:538).
2. **Missed cross-file public contract.** Changing ItemBase.title from str to int in backend/app/models.py scores 5, with zero detected contract changes. The real routes import ItemCreate/ItemPublic, which inherit this field across files. This exceeds the current [same-file schema extraction](../backend/services/source_parser.py:40). [Pinned models](https://github.com/fastapi/full-stack-fastapi-template/blob/b1125d8839482cb7bbae603ddc6d0081bf87532e/backend/app/models.py) and [route imports](https://github.com/fastapi/full-stack-fastapi-template/blob/b1125d8839482cb7bbae603ddc6d0081bf87532e/backend/app/api/routes/items.py) establish the relationship.
3. **Backend source omitted.** The template has a backend node but zero backend files read. Its Compose build uses context=. and dockerfile=backend/Dockerfile. Empty normalized context is discarded; directory inference then skips the already registered backend name. All 100 read source files belong to frontend. This is a mapping failure, not a GitHub outage. See [Compose mapping](../backend/services/repo_onboarding.py:504), [directory discovery](../backend/services/repo_onboarding.py:711) and [upstream Compose](https://github.com/fastapi/full-stack-fastapi-template/blob/b1125d8839482cb7bbae603ddc6d0081bf87532e/compose.yml).
4. **Kubernetes/gRPC discovery gap.** Online Boutique documents 11 application services under src/. The importer fails to discover services and returns no score. Kubernetes and src/<service> support are required. See the [pinned upstream architecture reference](https://github.com/GoogleCloudPlatform/microservices-demo/blob/38e7348eb289eb5b87c0c6e8cb19ced0449dc389/README.md#architecture). A failure here was not converted to a falsely clean zero.
5. **Examples mistaken for deployed architecture.** Express becomes an examples node; FastAPI becomes a docs_src node. Both receive 12 debt points for an isolated service. Example/tutorial folders do not establish a deployed service graph. These scores do not describe the frameworks' architecture quality.
6. **Confidence is not calibrated.** All scored results disclose partial coverage, but every nonempty case reports confidence=0.70. This constant does not quantify reliability when backend files or public schemas are missing.
7. **Unchanged debt is expected.** Debt remains 21.429 for the template and 12 for the example/tutorial nodes because the jobs reuse the import. Risk differences do not prove a new topology was captured.

## What passed

- 12/12 scored cases repeated identical scores, snapshots, findings, coverage and affected-file evidence: 24 core evaluations.
- 12/12 no-edit previews preserved before/after results.
- Identical source scored zero. Literal Python and JavaScript route renames/deletions were detected.
- The 100-file boundary was accepted; 115 files were rejected rather than silently truncated.
- Heavy single file: actual fastapi/routing.py, approximately 254 KiB per snapshot. Heavy batch: 100 actual files and approximately 1.36 MiB of paired source.
- Measured peak Python-process RSS was 149.578 MiB, including archive ingestion. This excludes other container processes and does not establish concurrent API capacity.
- The global registry, user data and existing Docker fleet were preserved.

## Selected API-change control metrics

11 manually labeled controls: TP=4, TN=2, FP=4, FN=1; 6/11 correct flags. Precision=0.500; recall=0.800.

These are diagnostic metrics for a small, deliberately adversarial and correlated set. They are not overall product accuracy, incident-prediction accuracy or calibration. No ground-truth numeric incident probability or accuracy rate for all architectural smells was established.

## Required fixes, in order

1. Separate semantic/contract changes from file location; suppress API/schema/config penalties caused solely by comments and unchanged syntax.
2. Repair Compose context/Dockerfile mapping and allocate source coverage across services.
3. Resolve cross-file request/response schemas and inheritance; distinguish compatible additions from breaking type, requiredness and removal changes.
4. Recognize library/tutorial-only projects and abstain from microservice grading without a supported service definition; add Kubernetes/gRPC and src/<service> discovery.
5. Mark missing topology/contracts as insufficient evidence and calibrate confidence against labels.
6. Add these controls as regressions when fixing the implementation, then use an independently labeled, held-out dataset of actual upstream compatibility changes and operational outcomes. Do not fit weights only to these cases.

## Reproduce

Harness: [scripts/benchmark_public_repositories.py](../scripts/benchmark_public_repositories.py). Run from the repository root. The image must match current backend source; output records code fingerprints. This opt-in script performs public network reads and never publishes. Cached provenance pins later runs to the same commits.

~~~powershell
New-Item -ItemType Directory -Path scratch/public-benchmark -Force | Out-Null
docker build -t mdt-benchmark-backend backend
docker run --rm --memory 1g --cpus 2 --mount 'type=bind,source=D:\projects\project 1\scripts,target=/benchmark-scripts,readonly' --mount 'type=bind,source=D:\projects\project 1\scratch\public-benchmark,target=/benchmark-output' --entrypoint python mdt-benchmark-backend /benchmark-scripts/benchmark_public_repositories.py
~~~

[Full JSON](benchmarks/public-repositories-2026-10-20.json) includes provenance, code hashes, findings, coverage and each affected-file contract. [Score CSV](benchmarks/public-repositories-2026-10-20.csv) contains the matrix. The seconds_two_runs field includes diagnostic parsing/invariant checks as well as two evaluations; it is not a single-request API latency measurement.

No scoring code, weights, database contents, Git commits, GitHub state or publication settings were changed.
