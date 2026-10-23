# MDT alpha validation record

> Latest local completion (23 October): [graph connections, evidence labels, import findings and refreshed release artifacts](ALPHA_COMPLETION_2026-10-23.md). Current client tests: 19 frontend, 7 shared client, 10 browser, 9 VS Code; 20 targeted backend checks rerun. The unchanged backend retains its 355-pass full run. The [inventory](TEST_INVENTORY.md) lists 400 checks. Publication requirements are listed separately in the new report.


> Latest verification (22 October, detector 2.1.0): [backend evidence and graph hover fixes](BACKEND_EVIDENCE_FIXES.md). **355 backend + 14 frontend tests passed**; all ten pinned repository imports were replayed, eight with partial topology and two abstentions. Eleven demo links stayed stable under stationary-pointer sampling; a measured 390px viewport also passed. The [inventory](TEST_INVENTORY.md) now lists 393 named checks, with client/extension results retained from the earlier pass. Older scores and counts below are historical. Existing saved jobs require a fresh import/analysis for updated results.


## Accuracy repair validation — 21 October 2026

- Complete isolated Python 3.11 suite: **320 passed, 57.03 seconds**, including 9 PostgreSQL and 3 Neo4j integration tests. Disposable PostgreSQL removed; live Neo4j preview transactions verified rollback and unchanged graph.
- Frontend: **8 tests passed**, lint clean, production and normal Docker builds passed. Existing design retained; evidence completeness and provisional-score labels added.
- Pinned public source rerun: **15/15 scored cases repeatable**, **14/14 selected diagnostic API labels correct** (original 11/11 plus three new controls). Eight imported-project no-edit previews unchanged; seven source-only library previews/debt explicitly not applicable. The full 115-file Express comparison remains correctly rejected by the 100-file bound.
- Comment-only cases now risk 0, including the 254 KiB file and 100-file/1.36 MiB batch. Cross-file model type change is 45 instead of 5. Template reads backend40/frontend60 files; Google discovers all11 workloads. Express/FastAPI libraries abstain.
- All seven benchmark implementation fingerprints match source; original public archive digests and original results preserved. Benchmark registry unchanged. Process peak RSS177.398MiB under 1GiB/twoCPU limits is a single-run observation, not a capacity guarantee.

See [fix details, before/after measurements and limits](ACCURACY_FIXES.md), [raw JSON](benchmarks/public-repositories-2026-10-21-fixed.json) and [CSV](benchmarks/public-repositories-2026-10-21-fixed.csv). Scores remain uncalibrated and source coverage stays explicit. These diagnostic controls are not an independent incident dataset.

Local backend source was layered onto its previously validated runtime dependencies; a fresh upstream Python-base download was cancelled. Frontend used its normal Docker build. Backend/frontend containers were recreated with existing volumes; the four-service fleet remains running. No commit, GitHub push or publication occurred.

Final live API smoke passed: authentication, owned patch jobs, measured evidence fields, comment-only risk0, history/snapshot/baseline/drift/reviews, unchanged no-edit preview, logout revocation and disposable-project cleanup. The route-change control scored60 in the four-service demo topology; the comment-only control scored0. Live backend, benchmark and host source match on all seven recorded SHA-256 fingerprints. Frontend HTML/assets and proxied API readiness passed. The live registry hash stayed `62d9fa65357611e73aebbf67ecb10cc9c6aef98d4d4b997821abcf32b216658e` across container replacement and smoke checks. All normal eight Compose containers are running. Final whitespace and script compilation checks passed.

## Historical public-repository assessment: 20 October 2026

An opt-in benchmark ran the unchanged local application core on pinned GitHub sources from Google Online Boutique, the FastAPI full-stack template, Express and FastAPI. Twelve scored cases reproduced identical results in two runs; twelve no-edit previews were unchanged. A real 115-file Express comparison was rejected by the configured limit; its separate 12-file core subset scored 55.

Accuracy controls exposed material limits: comment-only edits scored 30, 65 and 70; a cross-file public model type change scored 5; the template import read zero backend source files; Online Boutique discovery failed; and framework example/tutorial directories were modeled as isolated services. Six of eleven selected API-change controls matched their labels. This small, correlated set does not establish overall accuracy or calibrated incident probability.

See [full assessment and required fixes](PUBLIC_REPOSITORY_BENCHMARK.md), [raw result JSON](benchmarks/public-repositories-2026-10-20.json) and [CSV](benchmarks/public-repositories-2026-10-20.csv). The disposable container was removed, implementation fingerprints matched current local source, and the live registry/store/fleet were preserved. Scoring weights and application code were not changed. The existing unit/integration suite below was not rerun because this task added only an opt-in benchmark and documentation.

## Current pass: 20 October 2026

Validated locally on `feat/live-docker-integration`, with base commit `0b6dd744fb7acc25c433d5331a60fc76b10cb23c` plus uncommitted changes. The user's new frontend design was retained. No commit, push, public deployment or store submission occurred.

| Check | Current result |
| --- | --- |
| Complete Python 3.11 Docker suite | **276 passed in 58.94 seconds** |
| PostgreSQL / Neo4j integrations | **9 / 3 passed**, included above |
| Frontend / shared client / browser / VS Code unit checks | **8 / 6 / 10 / 8 passed** |
| Actual VS Code 1.141.0 desktop host | **5 checks passed**: activation, commands, findings view, configuration and real staged/working Git collection |
| Actual VS Code 1.141.0 web-worker host | **4 checks passed**: browser entry without Node, initial view state, commands and findings view |
| Frontend lint, production and Docker builds | Passed |
| Local SQLite API smoke | Passed: auth, patch job, captured rules, history, snapshot, baseline, drift, review labels, preview, cleanup and logout revocation |
| VS Code packaging dependency audit | **0 known vulnerabilities**, including dev dependencies after updating VSCE; not an OS/container scan |
| Extension artifacts | Browser ZIP and desktop/web VSIX rebuilt and structurally inspected |

The public demo now includes three previews generated by the same detector used for owned analyses. A regression test reapplies each exact edit, verifies before/after scores, snapshot identity, provenance and finding references, and confirms that the shared registry is unchanged. Browser inspection confirmed the cycle preview **90.662 → 89.89**, a **−0.772 point** change with one resolved finding and the functional-contract warning. The panel no longer substitutes invented score reductions. Tests also cover worsening/unchanged preview scores and missing history measurements remaining unavailable rather than becoming zero.

The new findings UI rendered 15 of 18 findings on page one and the remaining three on page two. Searching `payment` from page two reset pagination and showed one matching finding. Summary, measured inline previews and the dedicated graph with the user's caller/callee legend rendered correctly. No graph is mounted in Summary. Clipboard failures are visible, and the default-admin shortcut is limited to the explicitly enabled local dashboard on loopback hosts.

Browser extension tests exercise permission denial, repository matching, restart/resume, disconnect during connection validation, changes during storage writes, late job submissions and stale popup responses. Tokens and destinations remain in the same session-only connection record. Legacy separate-token state requires reconnecting. These are simulated Chrome popup/worker checks, not real Chrome installation acceptance.

The new VS Code web entry is bundled without Node dependencies and submits only explicitly confirmed repository/revision identifiers. Its unit tests cover confirmation denial, wrong repositories, disconnect during submission and configuration changes while reading secrets. The real web-worker check uses VS Code's `--extensionDevelopmentKind=web`; it does **not** establish hosted `vscode.dev` installation, deployed CORS, interactive credentials or end-to-end network acceptance.

The final Docker frontend entry is **258.87 kB** (85.12 kB gzip estimate), with **47.67 kB** (11.87 kB gzip estimate) in the Projects chunk. Graph (19.13 kB), History (9.91 kB) and Drift (6.76 kB) load separately; CSS is 69.28 kB. These sizes include the user's expanded UI. The historical 19 October size reduction below describes that earlier build, not this build or measured loading latency.

The disposable PostgreSQL test container and API-smoke project were removed. The normal eight-container Compose stack, existing project data and four runnable services remain. The final backend/frontend images are running locally. The 19 October hosted-image/backup-restore results below remain historical; that restore exercise was not repeated in this pass.

Current package SHA-256 values:

- Browser ZIP: `11E430455EE9143D7FDA40B01A2ECE7148AFA2A6794814C2AEB174288AE7E2CA`.
- VSIX: `B95053666C40A1BA7C93A5579FC3A6F2C9273D70ED3C307A5C33E8A268148AB5`.

Public hosting, real Chrome/Edge acceptance, deployed `vscode.dev` HTTPS/CORS, editor consent/credentials, other operating systems, publisher/licensing decisions and independent accuracy/load evaluation remain open. See [implementation status](IMPLEMENTATION_STATUS.md) for the full remaining scope.

## Historical pass: 19 October 2026

Validated locally on `feat/live-docker-integration`, with base commit `0b6dd744fb7acc25c433d5331a60fc76b10cb23c` plus uncommitted changes. No commit, push, public deployment or store submission occurred. The sections dated 18 October below are retained as historical evidence.

| Check | Current result |
| --- | --- |
| Complete Python 3.11 Docker suite | **275 passed in 54.81 seconds** |
| PostgreSQL 17 integration | **9 passed**, included in that total |
| Neo4j rollback integration | **3 passed**, included in that total |
| Frontend / shared client / browser / VS Code unit checks | **6 / 6 / 3 / 4 passed** |
| Actual VS Code 1.141.0 extension host | **5 checks passed**: activation, command registration, findings view, configuration defaults, real staged/working Git collection |
| Frontend lint and builds | Clean; local frontend/backend and minimal hosted Docker images build |
| Hosted Python dependency audit | No known vulnerabilities found in the final image's frozen runtime packages, including transitive dependencies and the new parsers |
| Local SQLite and hosted PostgreSQL API smoke | Passed: auth, patch job, captured rules, history, snapshot, baseline, drift, review labels, preview, cleanup and logout revocation |
| PostgreSQL backup/restore | Separate database restored; all 7 records, 1 job and 1 schema-version row matched by streamed SHA-256 values |

The parser/cache regressions cover real JavaScript/TypeScript/TSX syntax, ignored comment/string decoys, dynamic-route warnings, changed Python same-path contracts, immutable-SHA caching, credential/repository isolation, eviction and rate-limit cooldown. History tests cover literal wildcard search, pagination, projection privacy, ownership, baseline persistence, actual import revision selection and deletion races. Reviews and dependency policies are tested separately from scores.

The browser showed exactly three main destinations, zero graph SVGs in Summary, a dedicated graph, findings filtering (18 findings narrowed to one for `payment`), a saved result reopened through sign-in and History, and truthful same-snapshot drift. An accepted-risk review persisted after reload; a forbidden self-dependency saved through project settings was correctly marked violated. On-demand diagnostics showed healthy application services, and sign-out returned to the anonymous interface. During a live rebuild, a stale tab exposed a missing lazy-import failure; the corrected error boundary kept the app visible, offered Refresh Application and preserved the deep link.

The disposable browser project and the separate hosted-validation/PostgreSQL containers were removed after validation. The existing project data and normal eight-container Compose stack remain. The static demo JSON was refreshed from the public illustrative endpoint and included in the rebuilt frontend.

Measured local-build JavaScript: the prior eager entry was 363.49 kB (109.31 kB gzip estimate). The new initial entry plus Projects chunk totals **279.39 kB** (257.99 + 21.40), approximately **23% less**, with **91.16 kB** combined gzip estimate. Graph (18.81 kB), History (6.18 kB), Drift (3.95 kB), policy settings (2.62 kB), account and diagnostics load separately. CSS is 49.08 kB. These are build artifacts, not measured loading-time or production-capacity improvements. Nginx's actual JavaScript response was verified to carry `Content-Encoding: gzip`, immutable caching and security headers.

The minimal hosted image ran within a 384 MiB container limit; a point-in-time post-smoke reading was **57.24 MiB**. This is not peak memory or a load-test guarantee. Real Chrome/Edge extension installation, editor consent/credential UI, cross-platform acceptance, public hosting and independent accuracy/load evaluation remain incomplete.

Updated package SHA-256 values:

- Browser ZIP: `EAF976EB894F6E16B82FC9EBA5C87B7B2F73603C226466289BB35D1877502F40`.
- VSIX: `CDB5CB81F8C0B6EC869F499196E56CB1BBBF07EFA85347A5D9D5F7A6CEC760AA`.

See [implementation status](IMPLEMENTATION_STATUS.md) and [recovery procedure](OPERATIONS.md) for the exact remaining scope.

## Historical baseline: 18 October 2026

The following results describe the earlier checkout state, not the current test count or current package hashes.

## Automated checks

| Check | Result | Scope |
| --- | --- | --- |
| Python suite in a Python 3.11 Docker runtime | **230 passed**, 41.65 seconds | Isolated source copy; real credentials and runtime registry excluded |
| PostgreSQL integration | **7 passed**, included above | Disposable PostgreSQL 17; each test owns a random private schema; persistence, rollback, owner isolation, quotas, leases and concurrency |
| Neo4j integration | **3 passed**, included above | Live local database; success, injected failure and concurrent preview transactions; full graph fingerprint unchanged |
| Frontend | **5 passed** | Precision/export, evidence labeling, deep links, session cleanup and old-session response race |
| Shared API client | **4 passed** | HTTPS/origin checks, GitHub context, auth/idempotency, precise results/errors |
| Browser extension | **3 passed** | Permissions, worker restart/resume and repository mismatch guard |
| VS Code extension | **2 passed** | Real Git-index versus working-file content and path containment |
| Frontend lint | Clean | No warnings or errors |
| Production builds | Passed | Local backend/frontend, minimal hosted image, shared extension bundles; ZIP and VSIX produced |
| Dependency audit | No known vulnerabilities found | Frontend npm audit; actual hosted image's frozen Python runtime packages, including transitive packages, audited with pip-audit; VS Code production dependency audit |
| Git whitespace | Passed | `git diff --check`; Windows line-ending notices are informational |

The security regressions include cross-owner access denial, live role/account checks, refresh/logout revocation, quota concurrency, idempotency conflicts, stale lease/cancel handling, deletion racing with submission, input/body limits, and isolation from the global graph and provider clients. Passing tests does not establish production security or calibrated predictive accuracy.

The full Python run used `scripts/test_isolated.py` inside the built full backend image, with test requirements installed in a disposable container. Explicit test database variables enabled the ten integration tests. A minimal-dependency run without optional integration settings skips those tests; it should not be described as the full integration run.

## Runtime and browser evidence

- Both **local SQLite** and **hosted PostgreSQL** APIs passed `scripts/api_smoke.py`: readiness, public demo, anonymous project rejection, authenticated project creation, queued source analysis, saved-result lookup, unchanged no-edit preview, project deletion and rejected revoked token. The synthetic route change returned risk 60/100 and 18 illustrative topology findings.
- The final hosted image also passed that smoke after the deletion-race fix. It ran with a 512 MiB memory limit as UID/GID 10001. A point-in-time idle reading was approximately 59 MiB; this is not a load-test result or peak-memory guarantee.
- The hosted OpenAPI schema contained only root, authentication, health and `/v1` routes. Neo4j, ChromaDB and OpenAI modules were absent. PostgreSQL contained `mdt.jobs`, `mdt.records` and `mdt.schema_versions`; no application tables were created in `public`.
- `scripts/hosted_smoke.py prepare` imported the real public `kartick026/MDT` repository, resolved main to `0f1c4204c2f22d97d27b7a847b2fe057f36afd42`, and analyzed that exact revision. Import succeeded. Commit analysis explicitly returned **partial** when GitHub's anonymous shared-IP quota was exhausted. After restarting the API container, `verify` reopened the owned project, full analysis and unchanged immutable preview, then deleted the test project.
- In the in-app browser, the Docker-served web UI passed public-demo display, development login, repository creation/import, readiness polling, revision analysis, preview, saved-link reload and logout. The local checkout revision `0b6dd744fb7acc25c433d5331a60fc76b10cb23c` produced risk **15/100**, debt **84.104/100**, and a graph-edit preview of **81.728/100**. These are reproducible example outputs, not accuracy metrics.
- A separate static-only server, with no API, showed the bundled demo and the explicit **“API unavailable”** label. The public example therefore remains useful during an API cold start or outage.
- Browser inspection at the available approximately 757-pixel viewport exposed a wrapped navbar that overlapped content. Its height now grows with its rows. Long repository hashes wrap within cards. This was not a comprehensive device/browser compatibility run.
- Frontend Nginx configuration passed `nginx -t`. The runtime was updated from 1.27 to 1.30.6, the stable version listed in the [official Nginx downloads](https://nginx.org/en/download.html) during validation. OS/container vulnerability scanning was not performed; the dependency audit above covers application packages.

Temporary validation projects and containers were removed. The normal local Compose stack and its four runnable reference services remain running. The public example is available at http://localhost:5173.

## Package artifacts

| Artifact | SHA-256 |
| --- | --- |
| `extensions/browser/mdt-browser-alpha-0.1.0.zip` | `5E33AF5B72C0497783F87871DB96FBA514C575CE44C2B1B66EDDA3A7589ABCAF` |
| `extensions/vscode/mdt-architecture-review-0.1.0.vsix` | `085D680352E8E389B0926C8837DFB60A412D4697096106FE0E64BF16C3A296E3` |

Archives were structurally inspected and package tests passed. They have **not** completed an interactive Chrome/Edge extension-host or VS Code extension-host installation test. Browser-only VS Code support is not implemented. Follow the installation and consent instructions in [extensions/README.md](../extensions/README.md).

## Docker Desktop recovery

Docker initially failed before application startup because its log reported an inaccessible `dockerInference` runtime socket. Recovery stopped Docker Desktop, preserved the two affected socket directories by renaming them, recreated the empty runtime directories and started Docker again. No Docker factory reset or project-volume deletion was performed.

Preserved runtime directory backups:

- `%LOCALAPPDATA%/Docker/run.mdt-backup-20261018085411`
- `%LOCALAPPDATA%/docker-secrets-engine.mdt-backup-20261018085412`

The database volumes, images and existing application containers remained available after recovery. These backups contain old runtime socket state, not application database backups.

## Remaining release gates

1. Choose and configure the free hosting accounts, secrets and exact CORS origins; validate the actual public HTTPS URLs. Local validation does not prove those services are deployed.
2. Complete real browser/VS Code extension-host installation and user-consent testing; select the publisher identity and support/privacy URLs before any store submission.
3. Confirm repository licensing with its owners. A root license has not been supplied; previous unsupported MIT/enterprise/accuracy claims were corrected in the README.
4. Keep the private beta small. Anonymous GitHub quotas, sleeping free instances and incomplete language coverage are observed limitations. Per-user GitHub App access and broader parsers are later milestones.
5. Rerun and document a labeled research benchmark before updating the paper's evaluation claims. The original Word report was preserved, not silently rewritten.

No commit, GitHub push, cloud deployment, extension-store publication or external message was performed. See [PUBLIC_ALPHA.md](PUBLIC_ALPHA.md) for the concrete release sequence and [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) for the remaining research backlog.


## Live ten-repository website audit — 21 October 2026

See [LIVE_WEBSITE_AUDIT.md](LIVE_WEBSITE_AUDIT.md) for pinned inputs, scores, graph checks, fixes and explicit limitations. Seven supported graphs were inspected in Browser; three unsupported imports received no score. Final automated checks: 336 backend tests including PostgreSQL/Neo4j, 10 frontend tests, lint/build. A separate extra smoke reached the configured daily job quota and did not complete. Existing user data and reference services were preserved; no GitHub writes or public deployment occurred.


## Graph/UI verification — 22 October 2026

See [TEST_AND_BUG_LOG.md](TEST_AND_BUG_LOG.md) for the complete defect/fix record and [TEST_INVENTORY.md](TEST_INVENTORY.md) for all 373 named automated checks. Frontend 13, shared client 6, browser extension 10 and VS Code unit 8 were rerun; the unchanged backend retains its prior 336-pass full integration result. Geometry checks cover seven pinned imported snapshots plus the demo in both directions. Browser checks cover saved live graphs, fit/actual-size/expanded controls, endpoint provenance and the 44px project search. Tests at observed 780px and 480px widths do not establish 390px support; the Browser override clamped smaller requests. npm audit reports 0 known vulnerabilities after compatible Vite/follow-redirects updates. No backend data, GitHub state or external publication changed.
