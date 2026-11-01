# Public alpha release preparation — 25–26 October 2026

The local implementation and review bundles are updated. **The project is not cleared for public release yet.** Both current container candidates have zero package-scanner findings, and 477 named checks pass. Chrome/Edge permission/session checks and all four native VS Code credential, upload-consent, result and disconnect checks pass locally. Hosting/publisher/license details are undecided, and deployed acceptance plus another desktop operating system remain open. No commit, push, cloud deployment, account creation or marketplace submission was performed.

## Work completed in the requested order

| Item | Completed | Remaining gate |
| --- | --- | --- |
| 1. Parser fixes | Fixed the two observed valid-source failures; bounded minified-file exclusions have reason counts and regression tests | Other unsupported language/framework and grammar cases remain disclosed; no full architecture/runtime coverage claim |
| 2. Validation | 414 backend tests passed on the new Alpine runtime, including all 12 PostgreSQL/Neo4j integration checks; 63 client tests passed; ten pinned repositories replayed; source-tree stress, accessibility, dependency/container scans and PostgreSQL restore exercised | Automated accessibility checks are not full screen-reader acceptance; a clean package scan is not a penetration test |
| 3. Extension acceptance | Actual Chrome/Edge permission grant/denial, authenticated connection, session recovery and logout passed locally. Pending permission now has waiting/recovery status and cancellation. Actual VS Code desktop, web-worker and Restricted Mode hosts passed 5, 4 and 4 checks. The native Windows follow-up passed all 4 credential, Cancel/Send, actual-result and disconnect checks | Deployed browser analysis/result parity, another OS and deployed vscode.dev remain acceptance work |
| 4. Packages | Browser ZIP, desktop/web VSIX and public-profile web ZIP rebuilt; contents and SHA-256 recorded | Review/sideload bundles only; actual URLs and publisher/license must be finalized before distribution |
| 5. Hosting | Hosted Docker image built and import-smoked; private test PostgreSQL dump restored and matched by streamed hashes; environment template and read-only preflight prepared | No chosen accounts, public URLs or secrets. Public HTTPS/CORS, cold-start/restart and managed-host restore checks are pending |
| 6. Metadata/docs | Current runbook limits, inventory and status links updated; privacy notice draft and metadata configuration template prepared | Publisher identity, support contact, contributor-approved license and final privacy URL are explicitly undecided |

## Parser and scanner changes

The FastAPI template's `backend/app/api/deps.py` uses unparenthesized multi-exception headers valid in Python 3.14. A bounded token-aware bridge permits only simple comma-separated names without an `as` clause on older runtimes, reparses the equivalent parenthesized header, and restores AST columns. Original snapshots and line numbers remain unchanged; unrelated syntax failures stay failures. See [PEP 758](https://peps.python.org/pep-0758/).

The TSX grammar misparses a bare ampersand inside a quoted JSX attribute. The parser now accepts that recovery only within an intact quoted attribute boundary. Attribute text is not traversed as executable call evidence. Unclosed attributes, errors outside the literal, and cases where the grammar loses the boundary remain failed. Byte and syntax-node limits remain enforced.

Files named `*.min.js`, `*.min.mjs` and `*.min.cjs` are explicitly excluded from eligible source sampling. Counts and `excluded_source_reasons.minified_bundle` expose the omission; limits were not raised to force a passing parse. Direct submitted changes still retain parser bounds.

The ten pinned public archives were replayed offline through current imports; source was not executed and commit-risk analysis was not rerun. All topology counts and architectural-debt scores stayed unchanged. Notable current outcomes:

- FastAPI template: 40/40 files read and AST-parsed, zero parse failures.
- OpenTelemetry: 161/161 read; 116 syntax-parsed, 45 heuristic, zero parse failures.
- Voting: 7/7 eligible read; 6 syntax-parsed, 1 heuristic; one minified bundle explicitly excluded.
- eShop: 275/275 eligible read; 13 syntax-parsed, 262 heuristic; one minified bundle excluded.
- Image-only/unmapped source, unsupported contracts and unmeasured runtime still limit conclusions.

[Repository replay](benchmarks/release-replay-2026-10-25.json)

## Checks and findings

- **477 named automated checks passed:** 414 backend, 23 frontend, 8 shared client, 14 browser-extension and 18 VS Code unit checks (including two native-harness regressions). The four new browser cases cover pending permission and duplicate submits, cancellation followed by a late grant, successful credential clearing, and rejected permission API recovery. The new Alpine backend run took 91.87 seconds with no skips; its single warning is Starlette's existing TestClient/httpx deprecation. The previous Debian run took 68.91 seconds. The earlier 89 targeted parser checks overlap the full run. [Named CSV](benchmarks/test-inventory-2026-10-25.csv).
- Frontend lint/build, both extension builds, VSIX packaging, canonical demo parity, Nginx syntax and Git whitespace checks passed.
- Real Chrome 155.0.8059.85 and Edge 155.0.4283.62 loaded the unmodified extension in disposable development profiles. The earlier headless run only established loading and session boundaries ([historical host evidence](benchmarks/release-browser-hosts-2026-10-25.json)). The headed follow-up now verifies permission grant and denial in each browser, authenticated connection to the actual local API with four projects, token input clearing, no credential in persistent local storage, popup reload, actual worker stop/restart, server logout rejected with HTTP 401, and disconnect remaining effective after reload. Temporary test tokens were revoked and disposable browser windows closed. These checks do not certify store installation, deployed HTTPS/CORS or complete analysis/result parity. [Current permission/session evidence](benchmarks/release-permission-workflows-2026-10-25.json).
- Actual VS Code 1.141.0 desktop host passed activation/view/command/configuration and staged-versus-working-source checks. Its real browser worker passed no-Node-global, activation, command and findings-view checks. These are local host tests, not deployed vscode.dev acceptance.
- A separate fresh VS Code profile keeps Workspace Trust enabled and asserts `isTrusted === false`. The limited extension activates, findings remain accessible, and both source commands make no Git or network calls. [Restricted Mode evidence](benchmarks/release-vscode-restricted-2026-10-25.json). The six new desktop unit tests exercise actual command/client code with controlled UI choices and HTTP transport; they do not certify native credential/consent dialogs.
- Twelve WCAG A/AA automated page/viewport combinations passed at 320px and 1440px: demo Summary/Graph/Findings, History, Account and a saved Drift view. Fixed keyboard access to the graph's scrollable connection-details region. Screenshot review also found the focused skip link used low-contrast browser-default blue; it now uses the cyan text token. The focused-link audit and Enter-to-main-content check pass. No page JavaScript errors were collected. [Measurements](benchmarks/release-accessibility-2026-10-25.json), [mobile image](benchmarks/release-accessibility-mobile-2026-10-25.png).
- A synthetic 100-service tree with 1,000 / 10,000 / 50,000 candidate paths read exactly 500 files, five per service, within the configured budget. At one CPU and 512 MiB container limit, measured scanner times were 0.744 / 0.593 / 2.749 seconds; peak process RSS reached approximately 116 MiB. These are local bounded-scanner measurements, not GitHub latency or production capacity. [Load evidence](benchmarks/release-load-2026-10-25.json).
- A fresh disposable PostgreSQL 17 dump restored into a different empty database. Streamed hashes matched all four record rows, one queued job and one schema-version row. This verifies local data recovery, not a selected cloud provider or post-restore UI login.
- Local frontend/backend were refreshed after confirming zero active jobs. Readiness passed and the global registry SHA-256 remained `62d9fa65357611e73aebbf67ecb10cc9c6aef98d4d4b997821abcf32b216658e`. Existing saved analyses retain their original captured evidence; a new import is required for new parser counts.

## Security review

Frontend npm audit reports zero findings. The VS Code packaging tool initially pulled an affected MSAL Node dependency ([advisory](https://github.com/advisories/GHSA-xcx6-jx8p-x3h5)). A packaging-only override pins `@azure/identity` 4.13.0 to its unaffected MSAL major and pins that dependency's `uuid` to 11.1.1. The used UUID v4 API, extension tests and actual VSIX build pass. Final npm audit is zero; these development dependencies are excluded from the VSIX. Revisit the overrides when upstream packaging dependencies resolve both advisories.

Trivy 0.76.1 scanned the container OS and installed language packages. Refreshing Alpine security packages removed the frontend image's 11 reported package findings; its final scan is zero. Removing unused pip/setuptools/wheel build tools from the hosted runtime removed ten backend package findings; application imports still pass.

The earlier Debian candidate reported **49 high, 85 medium, 126 low and 5 unknown package findings** with no fixed versions listed. It is superseded by the tested Alpine 3.24 candidate, which reports **zero findings**. Historical Debian scans remain in the evidence file; no CVEs were hidden or waived. The new multi-stage Dockerfile builds parser wheels separately and installs only runtime dependencies into the non-root image. Native parser libraries, PostgreSQL driver, bcrypt, OpenSSL, Git and application imports pass, followed by the full 414-test run on this image with separate disposable PostgreSQL and Neo4j databases. The Docker-reported runtime size is 48,882,225 bytes versus 101,591,007 for the prior Debian image.

Alpine uses musl instead of glibc, so compatibility was verified rather than assumed; see the [official Python image guidance](https://hub.docker.com/_/python). A zero scanner result covers known package findings at scan time, not application, infrastructure or future vulnerabilities. The full local research stack was not security-certified by this hosted-image scan.

CI now provisions disposable PostgreSQL and Neo4j services, supplies their integration-test variables, and builds/scans both release Dockerfiles. Its image gate fails on high or critical package findings using the pinned scanner digest. The YAML parses locally; GitHub Actions itself has not run because nothing was pushed.

[Before/after security evidence](benchmarks/release-security-2026-10-25.json)

Docker Scout required a Docker login, so Trivy supplied the successful scans. One initial JSX regression fixture exceeded the deliberately narrow recovery boundary; it was retained as an explicit unsupported case, and a valid intact-attribute fixture passes. Automatic approval review rejected creation of an additional hosted-mode validation container with only “blocked by policy”; that application-level hosted smoke did not run. Existing local services and isolated database tests were validated separately.

The user agreed to handle native browser permission prompts. The first Chrome attempt timed out after 30 seconds because of a harness option error; a second waited five minutes without observing denial. The user confirmed no prompt was visible at that point. Those attempts remain [incomplete historical evidence](benchmarks/release-interactive-browser-2026-10-25.json), not failed user actions or permission denial.

Investigation found a definite product issue: the popup did not explain that it was waiting for browser permission. It now shows waiting status immediately, suppresses duplicate submissions, offers a Cancel button, and adds recovery instructions after 15 seconds. Cancellation clears the token input and invalidates any later permission response before it can connect. Connection failures also replace stale "Connecting" status. Four regression tests pass; actual hosts showed waiting controls and the corrected failure status. The timeout hint and cancellation/late-grant path are verified in unit tests; real-host permission decisions completed before those checks could be exercised manually.

The subsequent headed Chrome prompt appeared and the user confirmed Allow, then Cancel in a fresh profile. Edge returned grant, then denial in a separate fresh profile. An earlier intended Edge denial returned grant and was repeated; it was not counted as denial. Both browsers passed the local session checks listed above. The original missing-prompt cause is not proven. The harness now waits for readiness, distinguishes pending permission from denial, records permission/session state without credentials, and handles logout's HTTP 204 response instead of parsing an empty JSON body. No permission API was mocked, auto-approved or bypassed.

The native VS Code follow-up found that `--extensionTestsPath` suppresses modal dialogs: the installed `DialogService` explicitly reports "refused to show dialog in tests". A dedicated manual harness now launches a normal disposable development window, selects only its own fixture project, and requires human input for the masked temporary credential and real upload decisions. Earlier picker cancellation is not counted as source consent, and a revoked token was correctly rejected. A staged/working expectation mismatch and an incomplete token wait remain recorded in the [historical attempts](benchmarks/release-vscode-interactive-2026-10-25.json).

On 26 October, an early approved synthetic upload produced a `partial` analysis with risk 5/100 and insufficient evidence, displayed correctly by the extension. The harness omitted `partial` from its terminal states and kept waiting. It now shares the client's terminal classifier, preserves limited-evidence results, records intermediate progress and rejects failed/cancelled outcomes. Two regression checks pass (18 VS Code checks, 477 combined).

The corrected native run passed all four checks in actual VS Code 1.141.0: human-submitted credential fields authenticated without putting the token in settings; Cancel sent no analysis; Send forwarded the exact saved-working before/after fixture once and displayed the actual server result; disconnect cleared the view and credential, and another Analyze command made no network call. The approved job again returned `partial` with risk 5/100; that result was not relabeled. The expected Connect-first message after disconnect is a passing rejection check. The runner exited normally, its project deletion and logout returned HTTP 204, and its temporary profile was removed. The native-consent release flag is now true. [Current evidence and retained earlier failures](benchmarks/release-vscode-interactive-2026-10-26.json). These four host checks are separate from the 477 named automated checks and do not certify deployed services, another OS or marketplace installation.

## Concrete release handoff

[Package manifest and hashes](benchmarks/release-artifacts-2026-10-25.json) records:

- `extensions/browser/mdt-browser-alpha-0.1.0.zip`
- `extensions/vscode/mdt-architecture-review-0.1.0.vsix`
- `scratch/release-2026-10-25/mdt-web-alpha.zip`

The web review build disables local Diagnostics and signup. It uses `/api`; standalone static hosting requires rebuilding with the actual HTTPS API URL or configuring a same-origin proxy. Packaging neither installs nor publishes an extension. Publisher `mdt-local-alpha` and `UNLICENSED` remain honest local placeholders.

1. Decide the hosting accounts/URLs, registered publisher, support contact and contributor-approved license. The user explicitly said these are not decided yet.
2. Complete the local `release-config.local.json` checkpoint using [the metadata template](../release-config.example.json) and set actual secrets privately from [the hosted environment template](../backend/hosted.env.example). The checkpoint records the verified container scan, Restricted Mode, local Chrome/Edge permission workflows and native VS Code upload consent; undecided metadata and unperformed checks remain empty/false. Publish the completed [privacy draft](PRIVACY_RELEASE_TEMPLATE.md), never its placeholders.
3. Deploy the tested container candidate only after the hosting decisions, then perform the acceptance checks listed in the table against actual public services. Re-scan at release time and record evidence before setting the corresponding checklist flags.
4. Run `python scripts/release_preflight.py --config release-config.local.json`. Exit 2 means incomplete. It reads metadata and recorded acceptance flags only; it does not independently verify the network, upload, push or publish anything.
5. Rebuild for the actual API URL and approved metadata. Follow [PUBLIC_ALPHA.md](PUBLIC_ALPHA.md). GitHub push and marketplace/cloud publication remain separate user-controlled actions.

The existing zero-budget hosting option remains Cloudflare Pages, Render Free and Supabase Free, subject to account eligibility. Current official constraints checked on 25 October: [Cloudflare Pages free limits](https://developers.cloudflare.com/pages/platform/limits/), [Render idle spin-down and ephemeral disk](https://render.com/docs/free), and [Supabase low-activity project pausing](https://supabase.com/docs/guides/platform/free-project-pausing). These limitations must be included in the published alpha's availability expectations.
