# Implementation status — 21 October 2026

> Latest local completion (23 October): [graph connections, evidence labels, import findings and refreshed release artifacts](ALPHA_COMPLETION_2026-10-23.md). Current client tests: 19 frontend, 7 shared client, 10 browser, 9 VS Code; 20 targeted backend checks rerun. The unchanged backend retains its 355-pass full run. The [inventory](TEST_INVENTORY.md) lists 400 checks. Publication requirements are listed separately in the new report.


> Latest verification (22 October, detector 2.1.0): [backend evidence and graph hover fixes](BACKEND_EVIDENCE_FIXES.md). **355 backend + 14 frontend tests passed**; all ten pinned repository imports were replayed, eight with partial topology and two abstentions. Eleven demo links stayed stable under stationary-pointer sampling; a measured 390px viewport also passed. The [inventory](TEST_INVENTORY.md) now lists 393 named checks, with client/extension results retained from the earlier pass. Older scores and counts below are historical. Existing saved jobs require a fresh import/analysis for updated results.


This is the current local delivery checklist. [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) remains the original report audit and research roadmap. No GitHub push, cloud deployment or extension-store publication has been performed.

## Graph layout and test inventory — 22 October 2026

Replaced sample-grid curves with worker-based ELK layered/orthogonal layout, reserved endpoint-label space, fit/actual-size controls, direction switching and an expanded native dialog. Fixed the stretched project-directory search and legacy 680px mobile SVG minimum. Sixteen saved graph/direction combinations pass node, route and label separation assertions; dense graphs can still have perpendicular crossings. Demo provenance and parallel endpoint relations are explicit. See [TEST_AND_BUG_LOG.md](TEST_AND_BUG_LOG.md) and the [373 named check inventory](TEST_INVENTORY.md). Current JS rerun: frontend 13, client 6, browser 10, VS Code 8; backend last full run 336 remains recorded separately. Final lint/build, Nginx and npm audit passed.

## Live website checks — 21 October 2026

Ten real public repositories were tested through Browser. Seven produced graphs and provisional commit scores; Ponytail, Express and .NET eShop abstained for insufficient/unsupported architecture evidence. Fixed anonymous GitHub quota fallback, invented service risk/ports, missing infrastructure, duplicate undeclared nodes, sample-specific graph geometry and a Findings link incorrectly pointing to the demo. See [LIVE_WEBSITE_AUDIT.md](LIVE_WEBSITE_AUDIT.md) for all scores and coverage limits. Final checks: 336 backend tests including PostgreSQL/Neo4j, 10 frontend tests, lint/build. An extra API smoke was blocked by the observed daily quota; it was not bypassed. No calibrated accuracy claim is made.

## Accuracy fixes — 21 October 2026

The benchmark failures are fixed and rerun: parser-proven comments/formatting score zero; breaking Python model contracts are detected across supplied file context; Compose source mappings and fair sampling include backend code; plain Kubernetes discovery finds all 11 Online Boutique workloads; framework libraries abstain. Scores carry measured evidence completeness and provisional/insufficient-evidence status. The original numeric weights remain unchanged. See [ACCURACY_FIXES.md](ACCURACY_FIXES.md) for implementation, before/after scores and limits.

Validation: 320 backend tests including PostgreSQL/Neo4j, 8 frontend tests, lint/build, 14 selected diagnostic API labels and 15 repeatable scored cases. These checks do not establish calibrated deployment probabilities or independent held-out accuracy.

## Earlier implementation — 20 October 2026

- Preserved the user's updated project, findings, graph, history and drift layouts. Connected inline recommendation panels to measured detector results and canonical edit fields; removed invented score reductions and unsupported runtime guarantees. Public examples carry three reproducible fixture previews, including warnings and signed score changes. Clipboard failures now surface visibly, search controls have accessible labels, and the default-admin shortcut is restricted to local development.
- Three main destinations: **Projects, History, Account**. Project views provide Summary, Analyze, Graph, Findings and Drift. The public example exposes only Summary, Graph and Findings. Overview and the parallel legacy workflows are removed from the main interface. Existing extension `#/workspace` links still resolve.
- A single graph view per project. Its JavaScript loads only when requested; no graph is mounted in Summary or Findings. Account, History, Drift, dependency-rule settings and local Diagnostics also load on demand.
- Inactive views unmount, pending read requests are aborted, job polling stops while the document is hidden, and local health requests occur only when Diagnostics opens or refreshes. Findings render in pages of 15 and raw evidence is formatted on expansion. Keyboard focus, input labels, narrow layouts and reduced-motion support are retained.
- Owned searchable analysis history with project/status filters, pagination, deep links and a two-result score comparison. Comparisons explicitly identify reused topology and do not imply that risk differences establish runtime improvements.
- Immutable captured snapshots, saved baselines and drift comparison of nodes, edges, captured API declarations, findings and debt. Importing an explicit revision captures fresh topology. Ordinary change analysis states that it reuses the current capture. API contracts now participate in snapshot identity.
- JSON, Markdown and standalone HTML exports. Repository-controlled markup is escaped in readable reports.
- Finding review labels (confirmed, false positive, accepted risk, unreviewed), required reasons and 7–90 day review expiry. Original evidence and scores are unchanged. Ownership and input validation are tested.
- Up to 50 per-project require/forbid dependency rules, with reasons and unresolved-node handling. Jobs retain the rules captured at submission time. These are static topology checks, not runtime policy enforcement or inferred patch topology.
- JavaScript/TypeScript/TSX syntax parsing with bounded Tree-sitter trees, literal route extraction and explicit warnings for dynamic paths/mount prefixes. Python route contracts compare local and bounded supplied cross-file model fields/inheritance, parameters, required/default metadata, return models and status codes. Unseen imports remain unresolved. This is not full OpenAPI compatibility analysis.
- A bounded per-client immutable-source cache and rate-limit cooldown evidence. Moving refs are not cached as immutable; credentials and repositories are isolated. Cross-job cache persistence and bulk retrieval are not implemented.
- The Git hook now defaults to authenticated project-scoped `/v1` jobs, verifies repository matching, polls with a bounded deadline and attempts cancellation on timeout. Legacy mode requires explicit opt-in.
- Browser extension credentials, authenticated destinations and recent job now share a session-only connection record. Reconnect/disconnect invalidates pending responses; denied permission never submits the token, and old popup results cannot reappear after disconnect. Ten worker/popup/manifest tests pass.
- VS Code findings tree, evidence/source navigation, status indicator and clearer connection errors. The new browser entry submits explicitly confirmed repository/revision identifiers without Node, Git or workspace-file access. Desktop source analysis remains available in trusted filesystem workspaces. Five desktop checks and four web-worker checks pass in actual VS Code hosts. The browser ZIP and dual-entry VSIX are rebuilt locally.
- Nginx gzip and hashed-asset caching, lazy-import failure recovery, expanded local/hosted smoke checks and a read-only PostgreSQL restore verifier. The backup/restore procedure was exercised on disposable data.

## Remaining before a public alpha release

The [original public-repository assessment](PUBLIC_REPOSITORY_BENCHMARK.md) exposed accuracy failures that are now corrected in the [21 October rerun](ACCURACY_FIXES.md). Retain the disclosed limits: partial source coverage, unsupported gRPC/polyglot contracts, static topology and uncalibrated risk. Broader independently labeled evaluation remains required before predictive-accuracy claims.

1. Choose the actual free hosting accounts, API/web URLs and administrator secrets; apply the prepared deployment configuration; verify public HTTPS, CORS, cold starts and the final live build. Keep quotas small. No cloud accounts or public endpoints have been created here.
2. Confirm licensing with all project owners, publisher identity, support contact and a hosted privacy policy. The VSIX publisher is still a local placeholder and its license remains `UNLICENSED`.
3. Complete real Chrome/Edge extension-host acceptance: permission denial, session/token expiry, popup/worker restart, cancellation and saved web links. Chrome worker/popup tests are simulated. Actual editor host tests cover desktop Git collection and browser-worker activation/views/commands; upload consent, credential entry, Restricted Mode and another OS still require interaction testing. Validate the browser entry on deployed `vscode.dev`, including the actual worker origin's HTTPS/CORS configuration.
4. Run the final end-to-end scenarios against the selected public services, verify backup recovery there, and then distribute signed/store packages where chosen. Local packages are available for review and sideloading.
5. Update the academic paper's evaluation with a disclosed dataset, independent labels, actual hardware, latency percentiles and failure cases. The original Word file is preserved; [VALIDATION.md](VALIDATION.md) contains measured implementation evidence, not claimed predictive accuracy.

## Further engineering from the original roadmap

- GitHub App installation and private-repository authorization, per-user quotas, PR checks and review links; this needs an actual app registration and account consent.
- Cross-job/bulk GitHub source retrieval and broader language/framework support, including cross-file OpenAPI schemas, router prefixes, middleware and generated routes.
- A consent-based local companion and observed tracing. Static source edges must remain distinct from measured runtime traffic.
- Team roles, shared projects, multi-repository relationships and their isolation/audit model.
- Dedicated extension authorization that replaces manual short-lived token copying. The browser editor entry is implemented; its public distribution and deployed-host acceptance remain release gates above.
- Independent quality/accuracy evaluation, realistic large-repository load tests, full mobile/screen-reader acceptance and operating-system/container vulnerability scans. Current checks do not establish production capacity or calibrated deployment safety.

These items remain explicit scope rather than being represented as completed features.
