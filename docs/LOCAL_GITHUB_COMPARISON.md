# Local folder versus GitHub

Checked: 2026-10-20 20:50:05 +05:30. Remote refs refreshed with git fetch origin --prune.

Repository: https://github.com/kartick026/MDT

This inventories repository-visible files, including this generated report. Ignored credentials, installed dependencies, caches, databases, Docker volumes and generated dist/ZIP/VSIX outputs are excluded. Their contents were not read.

## Branch comparison

| Reference | Commit |
| --- | --- |
| Local HEAD: feat/live-docker-integration | 0b6dd744fb7acc25c433d5331a60fc76b10cb23c |
| GitHub: feat/live-docker-integration | 0b6dd744fb7acc25c433d5331a60fc76b10cb23c |
| GitHub: main | 0f1c4204c2f22d97d27b7a847b2fe057f36afd42 |

Local HEAD and its GitHub branch are identical: zero commits ahead and zero behind. All newer implementation/UI work below is uncommitted locally and absent from that branch.

The feature branch is 23 commits ahead of GitHub main, with zero behind. These commits are already on GitHub, separate from the uncommitted changes.

## Complete local file inventory against the matching GitHub branch

| Category | Files |
| --- | ---: |
| Modified tracked files | 63 |
| New implementation, configuration, tests and documentation | 85 |
| New screenshots and browser traces | 93 |
| Total new untracked files | 178 |
| Total differing repository-visible files | 241 |

No tracked files are added/deleted/renamed relative to the matching branch. New files are untracked. This combines the user's UI edits and implementation work; Git cannot reliably attribute uncommitted lines to an author.

### Modified tracked files

- M  .gitignore
- M  README.md
- M  backend/.env.example
- M  backend/Dockerfile
- M  backend/api/analysis.py
- M  backend/api/auth.py
- M  backend/api/health.py
- M  backend/api/webhook.py
- M  backend/app.py
- M  backend/core/auth.py
- M  backend/core/config.py
- M  backend/core/database.py
- M  backend/core/history.py
- M  backend/core/middleware.py
- M  backend/core/registry.py
- M  backend/requirements.txt
- M  backend/schemas/analysis.py
- M  backend/services/dependency_graph.py
- M  backend/services/git_analyzer.py
- M  backend/services/impact_engine.py
- M  backend/services/llm_explainer.py
- M  backend/services/remediation_simulator.py
- M  backend/services/repo_onboarding.py
- M  backend/services/retrieval.py
- M  backend/services/smell_detector.py
- M  docker-compose.yml
- M  docs/API.md
- M  docs/ARCHITECTURE.md
- M  docs/deployment.md
- M  docs/features.md
- M  docs/github_app.md
- M  frontend/.env.example
- M  frontend/Dockerfile
- M  frontend/README.md
- M  frontend/nginx.conf
- M  frontend/package-lock.json
- M  frontend/package.json
- M  frontend/src/App.css
- M  frontend/src/App.jsx
- M  frontend/src/api.js
- M  frontend/src/components/AnalysisHistory.jsx
- M  frontend/src/components/AuthPage.jsx
- M  frontend/src/components/DependencyGraph.jsx
- M  frontend/src/components/ErrorBoundary.jsx
- M  frontend/src/components/ImpactForm.jsx
- M  frontend/src/components/LoginModal.jsx
- M  frontend/src/components/ServiceGrid.jsx
- M  frontend/src/components/Toast.jsx
- M  frontend/src/context/AuthContext.jsx
- M  frontend/vite.config.ts
- M  mdt-hook/mdt_check.py
- M  pytest.ini
- M  tests/conftest.py
- M  tests/test_api_integration.py
- M  tests/test_api_type_safety.py
- M  tests/test_audit_and_parity.py
- M  tests/test_git_analyzer.py
- M  tests/test_llm_explainer.py
- M  tests/test_observability.py
- M  tests/test_remediation_simulator.py
- M  tests/test_retrieval.py
- M  tests/test_smell_detector.py
- M  tests/test_webhook_security.py

### New implementation, configuration, tests and documentation

- .dockerignore
- .github/workflows/ci.yml
- backend/.dockerignore
- backend/api/projects.py
- backend/core/store.py
- backend/Dockerfile.hosted
- backend/domain/__init__.py
- backend/domain/architecture.py
- backend/domain/drift.py
- backend/domain/policies.py
- backend/requirements-hosted.txt
- backend/services/source_parser.py
- docs/IMPLEMENTATION_PLAN.md
- docs/IMPLEMENTATION_STATUS.md
- docs/LOCAL_GITHUB_COMPARISON.md
- docs/OPERATIONS.md
- docs/PUBLIC_ALPHA.md
- docs/VALIDATION.md
- extensions/browser/.gitignore
- extensions/browser/background.js
- extensions/browser/build.js
- extensions/browser/manifest.json
- extensions/browser/package.json
- extensions/browser/popup.css
- extensions/browser/popup.html
- extensions/browser/popup.js
- extensions/browser/PRIVACY.md
- extensions/browser/README.md
- extensions/browser/tests/manifest.test.js
- extensions/browser/tests/popup.test.js
- extensions/browser/tests/worker.test.js
- extensions/README.md
- extensions/vscode/.gitignore
- extensions/vscode/.vscodeignore
- extensions/vscode/build.js
- extensions/vscode/package-lock.json
- extensions/vscode/package.json
- extensions/vscode/README.md
- extensions/vscode/src/extension.js
- extensions/vscode/src/git.js
- extensions/vscode/src/results.js
- extensions/vscode/src/web-extension.js
- extensions/vscode/tests/git.test.js
- extensions/vscode/tests/host/index.js
- extensions/vscode/tests/host/run.js
- extensions/vscode/tests/host/web.js
- extensions/vscode/tests/results.test.js
- extensions/vscode/tests/web.test.js
- frontend/.dockerignore
- frontend/public/demo.json
- frontend/src/components/AnalysisResult.jsx
- frontend/src/components/Diagnostics.jsx
- frontend/src/components/EvidenceDetails.jsx
- frontend/src/components/EvidenceSummary.jsx
- frontend/src/components/FindingReview.jsx
- frontend/src/components/ProjectDrift.jsx
- frontend/src/components/ProjectHistory.jsx
- frontend/src/components/ProjectPolicies.jsx
- frontend/src/components/Workspace.jsx
- frontend/src/context/useAuth.js
- frontend/src/context/useToast.js
- frontend/src/utils/analysis.js
- frontend/src/utils/session.js
- frontend/tests/analysis.test.js
- mdt-hook/README.md
- packages/client/index.js
- packages/client/package.json
- packages/client/tests/client.test.js
- render.yaml
- requirements-test.txt
- scripts/api_smoke.py
- scripts/hosted_smoke.py
- scripts/test_isolated.py
- scripts/verify_postgres_backup.py
- tests/test_change_extraction_regressions.py
- tests/test_demo_previews.py
- tests/test_finding_reviews.py
- tests/test_history_and_drift.py
- tests/test_hook_v1.py
- tests/test_preview_neo4j_integration.py
- tests/test_project_policies.py
- tests/test_projects_jobs.py
- tests/test_source_parser_and_cache.py
- tests/test_store_postgres.py
- tests/test_store_security.py

### New screenshots and browser traces

Review artifacts, not application features. They have not been deleted or prepared for publication.

- .playwright-mcp/page-2026-10-20T04-53-38-470Z.yml
- .playwright-mcp/page-2026-10-20T05-18-27-864Z.yml
- .playwright-mcp/page-2026-10-20T05-18-47-821Z.yml
- .playwright-mcp/page-2026-10-20T05-18-57-195Z.yml
- .playwright-mcp/page-2026-10-20T05-23-18-673Z.yml
- .playwright-mcp/page-2026-10-20T05-23-38-644Z.yml
- .playwright-mcp/page-2026-10-20T05-25-09-981Z.yml
- .playwright-mcp/page-2026-10-20T05-25-15-885Z.yml
- .playwright-mcp/page-2026-10-20T05-25-32-848Z.yml
- .playwright-mcp/page-2026-10-20T05-25-51-571Z.yml
- .playwright-mcp/page-2026-10-20T05-26-10-336Z.yml
- .playwright-mcp/page-2026-10-20T05-26-24-349Z.yml
- .playwright-mcp/page-2026-10-20T05-26-37-808Z.yml
- .playwright-mcp/page-2026-10-20T05-55-43-051Z.yml
- .playwright-mcp/page-2026-10-20T05-55-59-511Z.yml
- .playwright-mcp/page-2026-10-20T05-56-20-718Z.yml
- .playwright-mcp/page-2026-10-20T05-57-09-925Z.yml
- .playwright-mcp/page-2026-10-20T05-57-25-245Z.yml
- .playwright-mcp/page-2026-10-20T05-57-49-849Z.yml
- .playwright-mcp/page-2026-10-20T05-58-15-761Z.yml
- .playwright-mcp/page-2026-10-20T05-58-57-982Z.yml
- .playwright-mcp/page-2026-10-20T09-04-33-913Z.yml
- .playwright-mcp/page-2026-10-20T09-05-02-164Z.yml
- .playwright-mcp/page-2026-10-20T09-05-25-767Z.png
- .playwright-mcp/page-2026-10-20T09-14-48-281Z.yml
- .playwright-mcp/page-2026-10-20T09-15-47-914Z.yml
- .playwright-mcp/page-2026-10-20T09-15-57-827Z.png
- .playwright-mcp/page-2026-10-20T09-16-09-566Z.yml
- .playwright-mcp/page-2026-10-20T09-16-20-604Z.png
- .playwright-mcp/page-2026-10-20T09-16-39-395Z.yml
- .playwright-mcp/page-2026-10-20T09-16-53-603Z.png
- .playwright-mcp/page-2026-10-20T09-17-10-846Z.png
- .playwright-mcp/page-2026-10-20T09-18-15-124Z.yml
- .playwright-mcp/page-2026-10-20T09-18-25-590Z.png
- .playwright-mcp/page-2026-10-20T09-18-42-210Z.yml
- .playwright-mcp/page-2026-10-20T09-19-35-260Z.yml
- .playwright-mcp/page-2026-10-20T09-19-49-525Z.png
- .playwright-mcp/page-2026-10-20T09-20-10-674Z.yml
- .playwright-mcp/page-2026-10-20T09-20-37-901Z.png
- .playwright-mcp/page-2026-10-20T09-30-24-359Z.png
- .playwright-mcp/page-2026-10-20T09-30-36-419Z.yml
- .playwright-mcp/page-2026-10-20T09-31-11-465Z.png
- .playwright-mcp/page-2026-10-20T09-31-35-105Z.png
- .playwright-mcp/page-2026-10-20T09-31-50-198Z.yml
- .playwright-mcp/page-2026-10-20T09-32-00-443Z.png
- .playwright-mcp/page-2026-10-20T09-32-11-170Z.yml
- .playwright-mcp/page-2026-10-20T09-32-22-225Z.png
- .playwright-mcp/page-2026-10-20T09-32-34-513Z.yml
- .playwright-mcp/page-2026-10-20T09-32-49-646Z.yml
- .playwright-mcp/page-2026-10-20T09-33-05-731Z.yml
- .playwright-mcp/page-2026-10-20T09-33-17-572Z.png
- .playwright-mcp/page-2026-10-20T09-33-30-793Z.yml
- .playwright-mcp/page-2026-10-20T09-33-40-682Z.png
- .playwright-mcp/page-2026-10-20T09-33-51-471Z.yml
- .playwright-mcp/page-2026-10-20T09-34-00-682Z.yml
- .playwright-mcp/page-2026-10-20T09-34-12-496Z.png
- .playwright-mcp/page-2026-10-20T09-34-35-827Z.png
- .playwright-mcp/page-2026-10-20T09-34-50-494Z.yml
- .playwright-mcp/page-2026-10-20T09-35-12-293Z.png
- .playwright-mcp/page-2026-10-20T09-35-35-176Z.yml
- .playwright-mcp/page-2026-10-20T09-36-09-808Z.png
- .playwright-mcp/page-2026-10-20T09-36-41-864Z.yml
- .playwright-mcp/page-2026-10-20T09-36-54-232Z.png
- .playwright-mcp/page-2026-10-20T09-37-05-277Z.yml
- .playwright-mcp/page-2026-10-20T09-37-14-252Z.png
- .playwright-mcp/page-2026-10-20T09-37-38-704Z.png
- .playwright-mcp/page-2026-10-20T09-39-48-884Z.yml
- .playwright-mcp/page-2026-10-20T09-40-58-830Z.yml
- .playwright-mcp/page-2026-10-20T09-41-11-097Z.png
- .playwright-mcp/page-2026-10-20T09-41-23-265Z.yml
- .playwright-mcp/page-2026-10-20T09-41-32-379Z.png
- .playwright-mcp/page-2026-10-20T09-41-43-914Z.yml
- .playwright-mcp/page-2026-10-20T09-42-07-727Z.yml
- .playwright-mcp/page-2026-10-20T09-42-28-195Z.png
- fresh_screenshot_home.png
- screenshot_analyze_view.png
- screenshot_authenticated_projects.png
- screenshot_demo.png
- screenshot_drift.png
- screenshot_expanded_finding.png
- screenshot_findings.png
- screenshot_graph.png
- screenshot_history_authenticated.png
- screenshot_main.png
- screenshot_mdt_graph.png
- screenshot_new_account.png
- screenshot_new_demo_summary.png
- screenshot_new_findings.png
- screenshot_new_graph.png
- screenshot_new_history.png
- screenshot_project_mdt.png
- screenshot_saved_analysis_findings.png
- screenshot_saved_analysis_summary.png

## Functional differences in the local version

GitHub already contains earlier authentication, graph, history, scoring and simulation features. The local work extends or replaces the behavior below; those whole areas were not absent remotely.

| Area | Local changes relative to the matching GitHub branch |
| --- | --- |
| Interface | User-updated design; Projects/History/Account; project Summary/Analyze/Graph/Findings/Drift; dedicated graph, filters, sorting, pagination and inline previews |
| UI lifecycle | Lazy views, cancelled reads, paused hidden-tab polling, on-demand diagnostics, stale-chunk recovery, accessible labels and visible clipboard failures |
| Project API | Owned /v1 projects; bounded import/analysis jobs, readiness, cancellation, idempotency and saved links |
| Persistence | SQLite/PostgreSQL store, job leases/recovery, retention, ownership and concurrency checks |
| Authentication/security | Live account/role checks, session revocation, invite-only hosted access, request/source/job limits and credential isolation |
| Hosted runtime | Minimal deterministic backend without mandatory Neo4j/Chroma/LLM; local research stack retained |
| Extraction | Exact base/head source, deletion/rename handling, immutable revision evidence and explicit partial coverage |
| Parsers | Bounded JS/TS/TSX Tree-sitter and expanded same-file Python contracts; unsupported dynamic prefixes remain warnings |
| Retrieval/cache | Bounded per-client immutable-source cache, credential/repository separation, cooldown evidence and chronology/provider isolation |
| Scoring | Canonical snapshot detectors shared across adapters; distinct commit risk and architectural debt with evidence/coverage limits |
| Simulation | Immutable explicit graph edits, stale/ambiguous-edit rejection, introduced/resolved findings and measured signed debt changes |
| Public demo | Bundled outage fallback and three detector-recomputed fixture previews; invented score reductions removed |
| History/drift | Owned searchable history, two-result comparison, immutable snapshots, baselines, node/edge/contract/finding drift and missing-score handling |
| Governance | Finding review labels with reasons/expiry; project require/forbid dependency rules captured at job submission |
| Exports | JSON/Markdown/HTML with escaped repository-controlled markup |
| Browser extension | New Manifest V3 client, explicit origin permission, identifier-only submissions, session-only connection record and stale-response guards |
| VS Code extension | New desktop staged/working Git analysis with trust/consent, findings tree/status and browser-worker analysis without workspace reads |
| Git hook | Authenticated project-scoped jobs, matching repository, bounded polling/cancellation and explicit legacy opt-in |
| Operations | Hosted Dockerfile, Render template, Nginx cache/gzip, CI definition, smoke checks, backup/restore verifier and runbooks |
| Documentation/evaluation | Report implementation plan, current status/validation and corrected unsupported production, accuracy and licensing claims |

## Implementations still to do

### Before public academic alpha

1. Configure the selected zero-cost hosting accounts, public frontend/API URLs, database and secrets; deploy when explicitly authorized.
2. Verify actual public HTTPS/CORS, cold starts, persistence/restart, quotas and backup recovery.
3. Complete real Chrome/Edge acceptance: permission denial, expiry, restart/resume, cancellation, wrong-project handling and saved links.
4. Complete deployed vscode.dev acceptance using the actual worker origin; test editor credentials/consent, Restricted Mode and another operating system.
5. Confirm owner licensing, real publisher identity, support contact and public privacy policy; choose sideloading/store distribution.
6. Run final cross-client end-to-end/parity scenarios against the deployed API and distribute the chosen alpha packages.
7. Run a disclosed labeled research benchmark with hardware, latency percentiles, failures and parser coverage; update the paper from measured evidence.

### Further engineering from the original plan

8. Dedicated scoped extension pairing instead of manually copying a shared short-lived session.
9. GitHub App per-user installations, private-repository access, installation-routed webhooks, PR checks and review links.
10. Cross-job/bulk source retrieval/cache to reduce GitHub quota pressure.
11. More languages/frameworks, router/mount prefixes, cross-file OpenAPI schemas, middleware and generated routes.
12. Consent-based local companion and observed tracing, kept distinct from static source edges.
13. Teams/roles/shared projects and multi-repository relationships with isolation/audit controls.
14. BFF/HttpOnly-cookie session hardening, realistic load tests, full mobile/screen-reader acceptance and OS/container vulnerability scans.

Scope: [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md). Prior test evidence: [VALIDATION.md](VALIDATION.md). Tests were not rerun for this comparison.

## Additional differences from GitHub main

The tracked differences below also include the 23 feature-branch commits already published. Add the complete new-file inventory above for the current local folder. A = added relative to main, M = modified, D = deleted, R = renamed. These statuses do not imply new actions in this comparison.

- M  .gitignore
- M  .kiro/steering/context-graph.md
- M  README.md
- M  backend/.env.example
- M  backend/Dockerfile
- M  backend/api/analysis.py
- A  backend/api/auth.py
- M  backend/api/health.py
- M  backend/api/registry.py
- M  backend/api/services.py
- M  backend/api/webhook.py
- M  backend/app.py
- A  backend/core/auth.py
- M  backend/core/config.py
- M  backend/core/database.py
- A  backend/core/history.py
- A  backend/core/middleware.py
- M  backend/core/registry.py
- A  backend/core/utils.py
- A  backend/requirements-test.txt
- M  backend/requirements.txt
- M  backend/schemas/analysis.py
- A  backend/schemas/auth.py
- A  backend/schemas/common.py
- A  backend/schemas/service.py
- A  backend/services/connection_validator.py
- M  backend/services/dependency_graph.py
- M  backend/services/git_analyzer.py
- M  backend/services/github_app.py
- M  backend/services/impact_engine.py
- M  backend/services/llm_explainer.py
- A  backend/services/remediation_simulator.py
- A  backend/services/repo_onboarding.py
- M  backend/services/retrieval.py
- M  backend/services/smell_detector.py
- M  docker-compose.yml
- A  docs/API.md
- A  docs/ARCHITECTURE.md
- M  docs/deployment.md
- A  docs/features.md
- M  docs/github_app.md
- R100  Microservice Drift Tracker.pdf  docs/references/Microservice_Drift_Tracker_Design.pdf
- R100  Microservice Drift Tracker ayush demand.docx  docs/references/Microservice_Drift_Tracker_Requirements.docx
- D  frontend/.env
- A  frontend/.env.example
- M  frontend/.gitignore
- M  frontend/Dockerfile
- M  frontend/README.md
- M  frontend/index.html
- A  frontend/nginx.conf
- M  frontend/package-lock.json
- M  frontend/package.json
- M  frontend/src/App.css
- M  frontend/src/App.jsx
- M  frontend/src/api.js
- D  frontend/src/assets/react.svg
- D  frontend/src/assets/vite.svg
- M  frontend/src/components/AnalysisHistory.jsx
- M  frontend/src/components/ArchitecturalSmells.jsx
- A  frontend/src/components/AuthPage.jsx
- M  frontend/src/components/DependencyGraph.jsx
- A  frontend/src/components/ErrorBoundary.jsx
- M  frontend/src/components/ImpactForm.jsx
- A  frontend/src/components/LoginModal.jsx
- M  frontend/src/components/ServiceGrid.jsx
- A  frontend/src/components/SystemHealthModal.jsx
- A  frontend/src/components/Toast.jsx
- A  frontend/src/context/AuthContext.jsx
- M  frontend/src/index.css
- M  frontend/tsconfig.app.json
- D  frontend/vite.config.js
- M  frontend/vite.config.ts
- D  git_push.bat
- M  mdt-hook/mdt_check.py
- A  pyrightconfig.json
- A  pytest.ini
- A  scripts/run_microservices.py
- A  services/README.md
- M  services/order_service/main.py
- A  tests/conftest.py
- A  tests/test_api_integration.py
- A  tests/test_api_type_safety.py
- A  tests/test_audit_and_parity.py
- A  tests/test_auth.py
- A  tests/test_connection_validator_and_onboarding.py
- A  tests/test_database_and_registry.py
- M  tests/test_dependency_graph.py
- M  tests/test_git_analyzer.py
- M  tests/test_impact_engine.py
- M  tests/test_llm_explainer.py
- A  tests/test_observability.py
- A  tests/test_remediation_simulator.py
- A  tests/test_retrieval.py
- M  tests/test_smell_detector.py
- A  tests/test_webhook_security.py

### Feature-branch commits already on GitHub but absent from main

- 0b6dd74 fix(scoring, smells): increase score precision to 3dp and cap hub-and-spoke threshold at 0.85
- 5993b57 fix(engine): resolve dead variable in _get_core_services with variance-aware adaptive threshold
- cac58b6 feat: complete codebase audit, commit diff detection fixes, and operations documentation
- b3524ca fix(smells): fix smell detection parity and clean up hardcoded entries
- 5b54c79 fix(smells): enable all 10 architectural smells detection and proportional what-if score reduction
- 58c08b5 feat: fix after-score calculation, in-memory smell fallbacks, core service centrality, and test isolation
- 400acae feat: dynamic mathematical smell thresholds, what-if preview fix, and analyzing status badge
- b7f5681 chore: clean repo clutter, untrack frontend env, reorganize docs, and update context graph
- 57ecf17 docs: document elementary cycle deduplication, decoupled dials, and pre-push hook override
- c181cda fix(smell-detection): eliminate duplicate composite cycles and decouple commit risk in What-If preview
- 75513a9 chore(types): resolve Pyright type issues in test_remediation_simulator.py
- c33a263 test: align remediation simulator test with verified evidence-based scenario
- c13aea9 fix(security & test): harden default secrets, pin httpx in test requirements, validate analysis input, and remove facade heuristic guess
- be4a96f docs: update documentation with live demo fleet baselines, smell hygiene, and false-positive filtering
- 97cf377 fix(services): preserve individual service risk scores in graph, provide demo fleet baseline, and filter self-loops in smell detectors
- 4f879cd fix(validator): filter dynamic template ports to prevent prober false positives
- 5b7fb73 fix: resolve false positive connection bugs, extract real service endpoints, eliminate isolated services, and align history severity
- 81eaaa4 feat: complete live docker integration, resilient ingestion, dynamic topology layout, and type safety fixes
- 7e9e03b feat: implement 24 codebase improvements, auth & security hardening, and test suites
- b720e2f fix(validator): filter CORS whitelists and restrict What-If preview to genuine graph smell remediations
- f5ae9cb fix(simulator): eliminate fabricated results, fix fallback logger, add localhost networking check, and align docs
- dabe612 feat: comprehensive feature docs, what-if remediation simulator, connection validator, and UI polish
- fd851cb fix: resolve backend startup ImportError, LLM provider config, and dynamic graph node layout

No application code, user data, staging, commits, pushes or remote GitHub state were changed. Fetch refreshed local remote-tracking refs; this report is a new local documentation file.
