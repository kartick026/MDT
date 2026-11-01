# Benchmark accuracy fixes — 21 October 2026

The failures exposed by the 20 October assessment have been corrected locally and rerun against the same pinned public source archives. This is a regression assessment, not calibration against real deployment incidents. Numeric weights were not tuned to the benchmark.

## Observed before and after

| Control | Before | After |
| --- | --- | --- |
| FastAPI template route-module comment | Risk 30 | Risk 0 |
| Express example comment | Risk 5 | Source-only risk 0; architecture import abstains |
| 254 KiB FastAPI Python file, comment only | Risk 30 | Source-only risk 0 |
| 100 real Python files, comment only | Risk 65 | Source-only risk 0 |
| 100 larger Python files, 1.36 MiB paired source, comments only | Risk 70 | Source-only risk 0 |
| Template model field `str` → `int` | Risk 5; contract missed | Risk 45; breaking schema detected |
| Template route renamed / deleted | Risk 30 / 30 | Risk 30 / 30 |
| Template optional / required field addition with consumer context | Not assessed | Risk 20 / 45; compatibility evidence retained |
| Template backend source coverage | 0 files | 40 read, 39 parsed; frontend 60 read and parsed |
| Online Boutique discovery | Import failed | All 11 application workloads; 15 declared environment references |
| Framework architecture inference | Examples/tutorials became isolated services | Express and FastAPI imports explicitly abstain |
| Confidence | Fixed 0.70 for nonempty cases | Evidence completeness, explicit missing evidence and partial status |

The original 11 API-change controls now agree with their diagnostic labels. With three additional model controls, **14/14 selected labels** agree. **15/15 scored cases** repeat exactly. The 115-file full Express release comparison still correctly exceeds the 100-file input limit; its 12-file source-only subset scores 30. These correlated controls were used to repair the implementation and must not be advertised as held-out product accuracy.

Library source-only controls call the application core with an explicitly empty topology, bypassing the ready-project admission requirement for diagnostic purposes. Their debt and architecture previews are **not applicable**. They do not imply that the normal product accepts these libraries as deployed architectures. Eight imported-project no-edit previews were unchanged; seven source-only previews were not attempted.

## Implementation

- Python AST and JavaScript/TypeScript syntax comparisons distinguish comments/formatting from meaningful changes. JSON, YAML and TOML use format-aware comparisons. Missing, invalid, oversized and unsupported changed source remains unknown. Known equivalent files do not accrue file-count, API, schema, core-service, depth or historical semantic risk points.
- API flags require extracted contract evidence. Breaking and additive changes are distinguished; compatible additions no longer receive the breaking-API penalty. Model schema changes remain visible even when no endpoint consumer was supplied. Endpoint linkage is claimed only when supported by supplied context.
- Bounded Python model resolution handles imports, aliases and inherited fields in supplied before/after snapshots without importing or executing repository code. Unchanged supplied consumers can expose a changed model contract. Context contributes to the snapshot fingerprint. Response compatibility is directional; adding a response field retains uncertainty rather than promising compatibility.
- Compose root build contexts use nested Dockerfile locations to map source. Sampling distributes the 100-file budget across services and records per-service candidate, read and parsed counts. Empty source is distinguished from failed HTTP retrieval. Fabricated routes, API counts and name-only frontend/backend links were removed.
- Plain Kubernetes workloads, selector aliases and literal endpoint configuration references are discovered within bounded manifest reads. Canonical deployment manifests take precedence over optional, undeployed source directories. References retain their declaration provenance.
- The legacy numeric `confidence` field now measures the weakest observed dimension of changed-source semantic coverage, service mapping and affected-service parsed-source coverage. `confidence_evidence` supplies counts, reasons and the explicit `calibrated: false` marker. `assessment_status` distinguishes unsupported evidence, partial coverage, supported static analysis, no changes and equivalent changes. Graph depth no longer increases confidence. The web UI and exports label evidence completeness and provisional scores.

## Verification

- Complete isolated Python 3.11 suite: **320 passed in 57.03 seconds**, including **9 PostgreSQL** and **3 Neo4j** integration checks. The PostgreSQL container was disposable; Neo4j preview tests verify rollback and graph invariance.
- Frontend: **8 tests**, lint and production build passed. The user's layout and visual design are retained.
- Benchmark: **15 scored cases**, each evaluated twice; original archive SHA-256 values and all seven recorded production-file fingerprints match the tested implementation. Global benchmark registry unchanged. Peak benchmark-process RSS: **177.398 MiB**, under a container limit of 1 GiB and two CPUs; this is not a concurrency or capacity guarantee.
- Results: [JSON](benchmarks/public-repositories-2026-10-21-fixed.json), [CSV](benchmarks/public-repositories-2026-10-21-fixed.csv). The [original assessment](PUBLIC_REPOSITORY_BENCHMARK.md) and original raw results are preserved.

The backend image was rebuilt from the previously validated local runtime with updated application source, preserving its installed dependencies. A fresh upstream Python-base rebuild was cancelled during download; this pass does not claim a fresh OS/dependency audit. The frontend used its normal Docker build. Local runtime smoke results are recorded in [VALIDATION.md](VALIDATION.md).

## Limits that remain explicit

The scores remain heuristic engineering indicators. Independent operational outcome labels, predictive calibration and realistic concurrent-load testing remain future evaluation work.

The template has 141 candidate files and a 100-file budget. Its Python 3.12 syntax in `app/api/deps.py` is unsupported by the Python 3.11 runtime, so the result stays partial. Effective template changes report evidence completeness 0.975 and partial status. Source-only library edits lack service topology and report insufficient architecture evidence. Equivalent-source controls can report complete syntax evidence without claiming deployment safety.

Online Boutique dependencies are configuration declarations, not measured calls. gRPC contracts and Go/Java/C# contracts remain unsupported and disclosed. There is no Helm rendering, generated-route evaluation, full cross-file OpenAPI resolution, middleware execution or runtime tracing. A patch reuses the captured topology; importing a revision remains necessary to measure structural drift. Optional model additions are not certified safe.

No commit, GitHub push, public deployment or extension-store publication was performed.
