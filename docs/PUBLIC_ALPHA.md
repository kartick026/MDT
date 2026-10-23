# MDT academic alpha: implementation and release runbook

Updated 20 October 2026. The detailed report-to-code audit and phased backlog are in [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md). This document describes the implemented alpha, not every future item in that plan. No cloud account, GitHub push, or store publication is performed by these files.

## Delivered architecture

The browser UI, Manifest V3 browser extension, and VS Code desktop/web entries use the same `/v1` API. Each project belongs to one authenticated account. Each queued job contains its own architecture snapshot; the worker uses a task-local registry and cannot reach the shared local Neo4j/Chroma graph. Hosted analysis is deterministic and does not call an LLM or embedding provider.

`RUNTIME_PROFILE=local` retains the full Docker research stack and four runnable example services. `RUNTIME_PROFILE=hosted` exposes only authentication, health, the illustrative demo, and owned project/job routes. Global registry editing, runtime URL probes, legacy analysis and development webhooks are absent from the hosted routing table. GitHub repositories must be public in hosted mode; private source can only be submitted deliberately as bounded before/after snapshots. Per-user GitHub App installation permissions are a later phase.

The default preview copies a versioned snapshot, applies explicit edits and runs the same detector before and after. It reports introduced/resolved/unchanged findings, removed dependencies and raw/normalized debt. Gateway/facade names have no special effect. Stale versions and ambiguous parallel-edge removals fail. An optional local Neo4j transaction adapter exists for rollback experiments; it is not needed for hosting.

## What changed from the report baseline

| Area | Implemented behavior | Interpretation / remaining limit |
| --- | --- | --- |
| Extraction | Exact base/head content; renames, deletions, initial commits, bounded cached GitHub reads; real staged/index/working snapshots | Python AST and bounded JS/TS/TSX Tree-sitter; other languages/frameworks retain explicit coverage limits |
| Onboarding | Reads multiple nested source files per service; preserves Compose edges; records immutable revision and coverage | At most 100 source files / 2 MiB; incomplete coverage stays visible |
| Scoring | Distinct-neighbour topology counts, API contract method/path evidence, evidence-aware results | Risk remains a weighted engineering indicator, not a calibrated probability |
| Retrieval | Revision/provider/dimension isolation, chronology filters, lexical fallback with zero semantic modifier | Optional local research feature; hosted/scoped jobs do not use it |
| Preview | Shared deterministic detector, immutable snapshots, explicit graph edits, real transaction rollback tests | Better debt scores do not prove preserved business functionality |
| Storage | SQLite locally; PostgreSQL remotely; full results, owned projects and leased jobs | Single-instance academic service; no availability SLA |
| Security | Current-account role validation, one-hour tokens, logout/refresh revocation, invitation-only hosted analysts, request/source/job limits | Web tokens remain XSS-readable sessionStorage; no claim of HttpOnly-cookie authentication |
| Clients | Projects/History/Account web UI, measured fixture previews, browser ZIP and dual-entry VS Code VSIX with findings tree | Five desktop and four actual VS Code web-worker checks pass; broader consent/credential testing, Chrome/Edge checks, deployed vscode.dev acceptance and store approval remain pending |

Revise the paper's experiment section after rerunning the final implementation: replace old test counts; distinguish illustrative topology history from observed traffic; publish the actual dataset, labels, failure cases, parser coverage, hardware and latency percentiles. Do not describe current confidence values as validated prediction accuracy. Keep deployment risk and architectural debt as separate quantities. The original Word report is preserved.

## API and operational limits

- `/v1/demo` is public and explicitly illustrative. `frontend/public/demo.json` is a bundled fallback when the API is asleep.
- `/auth/login`, `/auth/refresh`, `/auth/logout` issue/rotate/revoke bearer sessions. `/auth/invite` is administrator-only and provisions an analyst with supplied credentials; it sends no messages.
- `POST /v1/projects` creates an owned project and returns an import `job_id`. Wait for the import job and the project's `ready` flag. GET/DELETE project operations enforce ownership.
- `POST /v1/projects/{id}/analyses` accepts commit/PR input or paired full source snapshots. Patch-only input is rejected. Use `base_ref` for patch inputs, and `comparison_mode=merge_base` for PR comparisons. Optional `pull_request` resolves the immutable GitHub base/head SHAs server-side.
- `GET /v1/jobs/{id}` returns queued/running/succeeded/partial/failed/cancelled plus the full saved result. `DELETE` cancels. `/v1/analyses/{id}` is an alias. `/v1/analyses/{id}/previews` uses the saved analysis snapshot.
- Supply `Idempotency-Key` when retrying submissions. A changed body with the same key returns 409. Deleting a project does not reset daily quotas.
- Defaults: 5 projects/account, 2 active jobs/account, 30 jobs/day/account, 180-second job timeout, 30-day result retention; 5 MiB HTTP body, 2 MiB extracted source and 100 files; preview limits 500 nodes / 5,000 edges / 100 edits, bounded cycle enumeration to 8 nodes.
- The worker renews leases and recovers interrupted jobs with bounded retries. Cancellation/deletion/lease replacement prevents stale workers from publishing. Raw submitted source is removed from the job payload at termination; results retain findings, paths, contracts, topology and provenance. Failed repeated interruptions also erase queued source.
- Anonymous GitHub API quotas are shared by the host's outbound IP. A real public-repository smoke test hit that limit during a multi-file commit analysis: import succeeded and analysis returned explicit partial coverage. Keep beta usage small; do not interpret missing source as a clean result. Per-user GitHub App credentials and bulk source retrieval remain follow-on work.

## Zero-cost hosting choice

Use Cloudflare Pages Free for the UI, Render Free for the single API process, and Supabase Free PostgreSQL for durable state. Keep paid model providers disabled. This is a limited academic alpha, not an always-on production commitment.

1. Create a Supabase Free project. Use the IPv4-compatible session pooler connection string when required by your host, with TLS (`sslmode=require`). Set it only in the API's `DATABASE_URL`. The store creates its own `mdt` schema; do not add that schema to the Data API's exposed schemas. Never put database passwords, service-role keys, JWT secrets or GitHub tokens in `VITE_*` variables. Export the `mdt` schema periodically; free-tier backup guarantees are insufficient for important research data.
2. Create the Render API from [../render.yaml](../render.yaml) using the **Free** plan. It uses `backend/Dockerfile.hosted`, a non-root runtime, `$PORT`, one API worker and `/health/ready`. Set a strong admin password, persistent generated signing secret, database URL, and exact frontend origin in `ALLOWED_ORIGINS` (JSON list is supported). Signup and default auditor must remain disabled. Auto-deploy is off.
3. Build the frontend with root directory `frontend`, command `npm ci && npm run build`, output `dist`, Node 22.12 or newer within Node 22. Set `VITE_API_URL` to the HTTPS API URL, `VITE_ENABLE_LOCAL_DASHBOARD=false` and `VITE_ALLOW_SIGNUP=false`. Publish the static result to Cloudflare Pages; use its free subdomain initially. Rebuild after changing Vite variables because they are build-time values. A static host does not use the Docker Nginx `/api` proxy automatically.
4. Log in as administrator, provision a small number of analysts using `/auth/invite`, and hand credentials to each tester through your chosen private channel. Confirm one user cannot read another user's project/job/preview. Do not post administrator credentials publicly.
5. Run release smoke tests: anonymous demo, login, public-repo import, exact revision analysis, saved-job reopen after API restart, preview, cancellation, data deletion, logout rejection, offline-demo fallback and CORS. Inspect the service's memory and outbound usage before increasing quotas.
6. After the extension-host checks below pass, distribute the browser ZIP for extraction and Load unpacked, plus the installable VSIX. Replace the VSIX's local placeholder publisher ID only after choosing an actual publisher. Add the verified support contact/privacy URL and resolve code licensing with all project owners before a store submission. The packaged extensions contain no database/model credentials.

Free service limitations verified against primary documentation: [Render Free](https://render.com/docs/free) sleeps after 15 minutes idle, has an ephemeral filesystem and 750 shared free instance-hours/month; free Render Postgres expires after 30 days, so it is not this plan's durable database. [Cloudflare Pages limits](https://developers.cloudflare.com/pages/platform/limits/) and [Supabase billing](https://supabase.com/docs/guides/platform/billing-on-supabase) apply independently. Check current quotas when creating the accounts; keep spending controls at zero and accept suspension/cold starts. Do not use synthetic keep-alive traffic to evade free-tier limits.

## Run and verify locally

```powershell
docker compose up -d --build backend frontend
```

Open `http://localhost:5173`. The frontend proxies `/api` to the backend. The four runnable service ports remain 8001–8004. Local development credentials are configured by `backend/.env` or documented development defaults; they are rejected by hosted configuration.

For isolated tests with Python 3.11 preferred:

```powershell
python -m venv .venv-alpha
.\.venv-alpha\Scripts\python.exe -m pip install -r backend/requirements-hosted.txt -r requirements-test.txt
.\.venv-alpha\Scripts\python.exe scripts/test_isolated.py -q
```

The runner copies only source/test files into a temporary directory and excludes real environment files and runtime data. PostgreSQL tests use `TEST_DATABASE_URL` and create/drop only their own generated schema. Neo4j rollback integration tests require explicit `MDT_LIVE_NEO4J_URI` and `MDT_LIVE_NEO4J_PASSWORD` (see the test file). The CI workflow is configured to run backend tests and client tests/builds; it does not run real browser/editor extension hosts, package the VSIX, or certify cross-client parity. Adding it locally does not run GitHub Actions until a user-authorized push.

## Build and install the clients locally

Use Node 22.12+ within Node 22, npm and Git. Run the following PowerShell commands from the repository root. The browser client and shared SDK have no install dependencies. The VS Code packaging tool is installed locally from its lockfile; no global install or publisher login is required.

```powershell
Push-Location frontend
npm.cmd ci
npm.cmd test
npm.cmd run lint
npm.cmd run build
Pop-Location

Push-Location packages/client
npm.cmd test
Pop-Location

Push-Location extensions/browser
npm.cmd test
npm.cmd run build
Compress-Archive -Path 'dist\*' -DestinationPath 'mdt-browser-alpha-0.1.0.zip' -Force
Pop-Location

Push-Location extensions/vscode
npm.cmd ci --ignore-scripts
npm.cmd test
npm.cmd run package
Pop-Location
```

Stop on any failed command. `npm.cmd run package` invokes the VS Code prepublish build hook locally; its name does not mean publication. Outputs are ignored build artifacts:

- [Browser ZIP](../extensions/browser/mdt-browser-alpha-0.1.0.zip): extract it and use Chrome/Edge **Load unpacked** on the folder containing `manifest.json`, or select `extensions/browser/dist` directly after building. Enable Developer mode on the browser's extensions page. A ZIP is not a store-installed extension.
- [VS Code VSIX](../extensions/vscode/mdt-architecture-review-0.1.0.vsix): run **Extensions: Install from VSIX** in desktop VS Code 1.95+ and choose this file. `mdt-local-alpha` is a packaging placeholder, not a registered publisher claim.

For either client, sign in to MDT, create a matching project and wait for its import to become ready. Copy the short-lived token from **My Account**, then connect with the API and dashboard URLs. Local defaults are `http://localhost:8000` and `http://localhost:5173`; deployed URLs require HTTPS. The alpha manually reuses the MDT bearer session; a dedicated scoped extension pairing flow is future work. The browser keeps the token only in `chrome.storage.session`; VS Code uses SecretStorage. Disconnect removes local state; sign out in the web app to revoke that session on the server.

The browser sends GitHub repository/revision/PR identifiers only, after an explicit popup action. It has no content script and requests access to the configured API origin on connection. Its token, authenticated destinations and recent job share a session-only record; old responses cannot restore a disconnected session. The VS Code commands **MDT: Analyze Staged Changes** and **MDT: Analyze Saved Working Changes** require Workspace Trust and explicit confirmation before sending full before/after source. The desktop client limits combined before/after content to 1 MiB and 100 changed paths, with a separate 2 MiB patch limit. New files must be staged; unsaved buffers and untracked files are excluded. Binary, non-UTF-8, symlink and submodule changes are rejected. Remote workspaces run Git on their extension host, so `localhost` refers to that host.

The VS Code browser entry provides **MDT: Analyze Repository Revision (Browser)** with an explicit confirmation and matching-project check. It reads no workspace files and sends repository/revision identifiers to the server. Local Git commands are unavailable there. Both API/web URLs require HTTPS, and the API must allow the actual deployed extension worker's origin through its exact CORS configuration. Actual web-worker activation passed locally; public `vscode.dev` installation and deployed API acceptance remain incomplete. See [browser setup/privacy](../extensions/browser/README.md) and [VS Code boundaries](../extensions/vscode/README.md).

## Client validation status and remaining gates

On 20 October 2026, local validation passed: frontend 8 tests, shared SDK 6 tests, browser 10 tests and VS Code 8 tests, plus 5 desktop and 4 web-worker checks inside VS Code 1.141.0. The full backend suite passed 276 tests, including nine PostgreSQL and three Neo4j integrations. Frontend lint and production builds pass. Chrome popup/worker tests use simulated hosts; the actual editor checks cover activation, commands, findings views, configuration and desktop staged/working source collection. Updated packages and detailed scope are recorded in [VALIDATION.md](VALIDATION.md).

**Interactive Chrome/Edge acceptance and broader VS Code consent/credential workflows remain pending.** Before distributing to testers, use clean browser profiles and a trusted editor workspace to verify connection and permission denial, wrong-project rejection, import readiness, upload consent, cancellation, popup/worker/editor restart, expired-token recovery, logout revocation and links to the saved web analysis. Confirm Restricted Mode prevents source collection. Repeat desktop verification on Windows and at least one other platform. Compare full findings and scores across clients for identical immutable input, snapshot and engine configuration. A successful web workflow does not certify the extensions. See [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) and [OPERATIONS.md](OPERATIONS.md) for current features and the tested recovery procedure.

JSON/Markdown/HTML export, evidence labels, project/job links, session isolation, recorded fixture previews, finding review labels and the editor findings tree/status bar are implemented. Dedicated extension credentials, store listings and deployed browser-editor acceptance remain release work.

## Follow-on research and release work

The full plan also covers labelled benchmark evaluation, tracing-derived dependencies, language parser expansion, organization sharing/RBAC, GitHub App per-user installations, signed webhook installation routing, private-repository access, BFF/HttpOnly-cookie authentication and public extension-store listings. These remain explicit later milestones. Do not advertise them as delivered in the academic alpha.
