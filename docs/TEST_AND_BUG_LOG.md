# Tests and bug log — 26 October 2026

## Native Windows acceptance completed — 26 October 2026

The corrected human-operated run passed all four checks: native connection with no token in settings; Cancel without an upload; exactly one approved upload with verified mode-specific source and the actual server result; and disconnect followed by an Analyze command rejected before network access. The server returned a partial result with risk 5/100, and the extension retained that evidence warning. These four native checks are separate from the 477 named automated checks.

The editor exited normally. Backend logs confirm HTTP 204 for deletion of the disposable project and logout; its temporary profile was removed. The native-consent release flag is now true. Previous failures and timeouts remain recorded below and in [the full evidence](benchmarks/release-vscode-interactive-2026-10-26.json). Public services, another OS and deployed vscode.dev still need acceptance.

## Native terminal-state follow-up — 26 October 2026

Native connection and upload cancellation passed. The next approved synthetic upload reached the local API and the extension displayed the actual `partial` result: risk 5/100, insufficient evidence, with the evidence warning retained. The test observer incorrectly recognized only `succeeded`, `failed` and `cancelled`, so it remained waiting after the product had completed. This was another harness defect, not a failed analysis or a reason to relabel coverage.

The observer now uses the shared client's terminal classifier, requires a real result, preserves partial-result flags, and rejects failed/cancelled outcomes. It records dialog choices and request progress immediately, then waits for the view to consume the actual result. Two new regressions pass; the VS Code suite is 18/18 and the combined named inventory is **477**. This incomplete attempt was followed by the successful four-check native run recorded above. [Follow-up evidence](benchmarks/release-vscode-interactive-2026-10-26.json).

## Native VS Code harness correction — 25 October 2026

The first interactive editor attempt exited before producing a report. A retry established native connection, but no upload was observed. That retry's initial cancellation claim is withdrawn: the harness had not verified that a source-upload dialog was actually reached. Later instrumentation recorded cancellation of a project picker instead. Another attempt correctly rejected a revoked token supplied at the native input.

The decisive log error was `DialogService: refused to show dialog in tests`. The installed VS Code source confirms that extension-development mode with an extension-tests location suppresses native modal dialogs. The manual harness now uses a separate disposable development driver without `--extensionTestsPath`. It selects only its own synthetic fixture project, prefills a temporary masked token requiring human submission, observes actual upload-dialog decisions, and separates Cancel and approval checks with an explicit continuation. Partial reports and a zero editor exit code never count as a completed pass. Updates are disabled only in the disposable profile; source is checked before forwarding to its test project. Native acceptance remains pending until all four checks finish.

A later screenshot exposed another harness error: it expected working-tree text when the selected command correctly collected staged text. Assertions now use the actual selected mode, and the run accepts the two required human choices in either order. The failed assertion prevented that attempt from forwarding source. The inactivity deadline now resets at each input/dialog step; an attempt that expired while still waiting for the token is retained as incomplete evidence. Neither issue is counted as a product source-collection failure.

## Browser permission follow-up — 25 October 2026

Fixed a blank pending-permission state, duplicate connection submissions, and stale "Connecting" status after connection failure. The popup now shows the requested host and a Cancel control immediately, explains recovery after 15 seconds, clears the token on cancellation, and ignores a later permission result for a cancelled attempt. Four new regressions pass; browser unit tests now total 14 and the combined named inventory is **475**.

Actual headed Chrome and Edge both passed origin grant/denial and authenticated connection to the local API, with four projects returned. Token input clearing, persistent-storage exclusion, popup reload, actual service-worker restart, server logout revocation (401) and disconnect/reload also pass. Test sessions were revoked and windows closed. An intended Edge denial initially returned grant; a fresh profile verified denial separately. The user confirmed Chrome's prompt eventually appeared, but the earlier invisible-prompt cause is not proven. Pending timeout/cancellation is covered by unit tests, not represented as a completed native manual check.

The diagnostic harness now distinguishes pending permission from denial and handles HTTP 204 logout without attempting JSON parsing. Browser ZIP, package hash and named inventory were refreshed. [Current evidence and remaining gates](RELEASE_READINESS_2026-10-25.md), [native permission/session outcomes](benchmarks/release-permission-workflows-2026-10-25.json).

## Release completion follow-up — 25 October 2026

Replaced the hosted Debian runtime with a multi-stage Python 3.11/Alpine 3.24 image. Current backend and frontend scans have zero package findings; prior Debian findings are retained in the evidence. Native-library imports and all 414 backend tests passed on Alpine, including the 12 external database checks (91.87s, no skips, one existing TestClient/httpx deprecation warning).

Added six desktop regression cases covering Restricted Mode, denied/approved source consent, connection changes during confirmation, credential expiry and cancellation. VS Code unit tests now total 16; the combined named inventory is 471. A separate actual VS Code Restricted Mode profile also passes four checks. The first native browser permission attempt hit a test-harness 30-second timeout; it was corrected to five minutes. A failed/incomplete interactive attempt is not a passing permission check.

CI now provisions both test databases and builds/scans both release images. Its configuration parses locally; remote CI remains unrun without an authorized push. Native credential/consent and deployed service acceptance, plus undecided release metadata, remain explicit gates. See [current evidence](RELEASE_READINESS_2026-10-25.md).

## Release preparation — 25 October 2026

Fixed valid Python 3.14 multi-exception syntax rejected by the older runtime, a bounded quoted-JSX-attribute parser failure, and minified bundles being included in eligible source sampling. Ten pinned repository imports were replayed: parser failures cleared in the affected fixtures while topology/debt stayed unchanged. Unsupported evidence remains disclosed.

Fixed keyboard access to the scrollable graph connection-details region and contrast of the focused skip link. Twelve automated accessibility page/viewport combinations pass. Updated vulnerable VS Code packaging dependencies and frontend OS packages; hosted backend build tools were removed. The backend still has 49 high, 85 medium, 126 low and 5 unknown package findings with no fixed versions listed, so security clearance remains pending.

All **465 named checks passed**, including the previously skipped 12 database tests. Real Chrome/Edge loaded the extension; VS Code desktop/web hosts passed 5/4 checks. Native permission, consent and deployed workflows remain acceptance work. Scanner load and fresh PostgreSQL restore checks passed. Local ZIP/VSIX/web bundles and their hashes were refreshed. The extra hosted-mode container smoke was rejected by automatic approval review with only “blocked by policy”; it did not run.

See [full evidence, initial failures and remaining gates](RELEASE_READINESS_2026-10-25.md) and the [named inventory](benchmarks/test-inventory-2026-10-25.csv). Nothing was pushed or published.

## Separate coverage indicators and scanning — 24 October 2026

[Implementation, measured results, regressions and remaining limits](COVERAGE_IMPROVEMENTS_2026-10-24.md). Source scan, parser support and runtime verification are now distinct in the website, reports and extension summaries. The ten pinned repositories were replayed: OpenTelemetry source reads increased from 100 to 161 and eShop from 100 to 276. Four valid TypeScript generic-template failures were fixed; unsupported evidence remains explicit. A fresh website import verified the counts, and old saved analysis/export counts stayed unchanged after re-import.

389 backend tests passed with 12 external database tests skipped; the final scanner refinement passed 39 relevant tests (overlapping the full run). Frontend/shared-client/browser/VS Code suites passed 23/8/10/10. Builds, lint, demo consistency, backend readiness, Nginx, and responsive coverage-card checks passed. The detailed report records the initial test-fixture failure, Windows async-test stall, and remaining parser/language limitations. Local services are updated; nothing was pushed or published.

## Shared layout follow-up — 23 October 2026

The wider audit found additional narrow-screen overflow beyond the drift cards:

- Evidence-warning identifiers and source paths escaped their list containers in Summary and Findings.
- Finding titles were squeezed between severity badges and Copy/Expand controls; headers now wrap, with a separate title row on mobile.
- Recommendation edit pills and preview actions exceeded their cards; shared wrapping and button sizing now keep the content inside.
- Findings pagination and the graph relation guide needed wrapping at narrow widths.

Summary with an open counterfactual preview and expanded Findings passed at 320, 390, 768 and 1440px. Raw finding evidence, review controls, Analyze and History comparison passed at 320px; Drift and Graph controls passed at 320px and 1440px. The geometry audit found no remaining visible overflow or sibling collisions in these checked states. SVG internals and deliberately scrollable areas are excluded from this UI audit. The normal viewport was restored. No review or baseline changes were saved.

Lint, production build, Nginx configuration and whitespace checks passed. The updated frontend is running locally. No backend changes, backend test rerun or GitHub push occurred. One expired local session was signed back in during verification.

[Before/after measurements](benchmarks/shared-layout-2026-10-23.json) · [Findings screenshot](benchmarks/shared-layout-findings-2026-10-23.png) · [Mobile screenshot](benchmarks/shared-layout-mobile-2026-10-23.png)

## Drift card overlap repair — 23 October 2026

Long service JSON pills exceeded their grid cells (634px content inside a 254px card), covering neighboring dependencies and contracts. Scoped card sizing and wrapping now contain all values; headings and counts use separate rows, and empty cards keep their natural height. No comparison data or scores changed.

Verified the reported OpenTelemetry comparison at 1440px, the normal 897px viewport, 390px and 320px: all 10 service and 55 dependency pills stay inside their cards, with no header or page overflow. Expanded raw service JSON also stays contained. Frontend lint, production build and Nginx checks passed; no browser console errors were captured. The local frontend container serves the fix. Backend tests were not rerun for this layout-only repair.

[Measurements](benchmarks/drift-layout-2026-10-23.json) · [Screenshot](benchmarks/drift-layout-2026-10-23.png)

> Latest local completion (23 October): [graph connections, evidence labels, import findings and refreshed release artifacts](ALPHA_COMPLETION_2026-10-23.md). Current client tests: 19 frontend, 7 shared client, 10 browser, 9 VS Code; 20 targeted backend checks rerun. The unchanged backend retains its 355-pass full run. The [inventory](TEST_INVENTORY.md) lists 400 checks. Publication requirements are listed separately in the new report.


> Latest verification (22 October, detector 2.1.0): [backend evidence and graph hover fixes](BACKEND_EVIDENCE_FIXES.md). **355 backend + 14 frontend tests passed**; all ten pinned repository imports were replayed, eight with partial topology and two abstentions. Eleven demo links stayed stable under stationary-pointer sampling; a measured 390px viewport also passed. The [inventory](TEST_INVENTORY.md) now lists 393 named checks, with client/extension results retained from the earlier pass. Older scores and counts below are historical. Existing saved jobs require a fresh import/analysis for updated results.


This is the consolidated test record and defect list for the local MDT work. It distinguishes tests rerun for the graph/UI repair from previously recorded backend, benchmark and host checks. Passing checks do not establish prediction accuracy or production readiness.

The [named test inventory](TEST_INVENTORY.md) lists **373 individual automated checks**, with one record per check in [CSV](benchmarks/test-inventory-2026-10-22.csv).

## Automated checks and execution status

| Suite / check | Last recorded result | Execution scope |
| --- | --- | --- |
| Backend Python | 336 passed in 80.46 seconds | Full isolated run on 21 October, including disposable PostgreSQL and transactional Neo4j checks. Backend unchanged by the graph/UI repair; names recollected on 22 October. |
| Frontend | 13 passed | Rerun on 22 October: precision, evidence labels, routing, export escaping, session isolation and five graph layout/fit groups. |
| Shared API client | 6 passed | Rerun: credential destinations, repository matching, partial results, cancellation, error handling and score precision. |
| Browser extension popup/worker/manifest | 10 passed | Rerun simulated checks: no passive browsing, permission denial, session restart, disconnect/reconnect races and stale-response isolation. |
| VS Code unit checks | 8 passed | Rerun: real staged Git content, path confinement, findings provenance, status, browser bundle, consent and credential races. |
| Actual VS Code desktop / browser-worker hosts | 5 / 4 passed previously | Historical 20 October host run. Not rerun for this UI repair; this is separate from the eight unit checks. |
| Frontend lint / production build / Nginx syntax | Passed | Final source compiled and served by the rebuilt local frontend container. Only the frontend container was replaced for this repair. |
| npm dependency audit | 0 reported vulnerabilities after compatible updates | Audit initially found two vulnerable packages, Vite and follow-redirects. Lockfile updates within declared compatible ranges cleared them. Not an OS/container vulnerability scan. |
| Whitespace / patch checks | Passed | `git diff --check`; no commit or push. |

The earlier backend progression (276, 320, then 336 tests) represents different repository states, not separate accuracy datasets. Relevant earlier runs and smoke checks remain in [VALIDATION.md](VALIDATION.md).

## Graph tests added and strengthened

The earlier graph tests checked finite coordinates and node-box separation. They did **not** check routes crossing nodes, endpoint-label collisions, fit behavior or mobile minimum widths; that allowed the visual defects in the supplied screenshots to remain.

The replacement tests verify:

1. Renamed services retain the same geometry, including reverse edges, self-loops and parallel endpoint relations. No production layout is tied to the sample service names.
2. Sixty nodes with cycles, disconnected components and long names remain separate; every routed edge stays outside node interiors.
3. Empty/isolated graphs and dangling references remain finite without invented edges. Internal layout IDs are separate from repository-controlled names.
4. Fit uses both viewport dimensions and does not upscale small graphs.
5. Seven saved live-repository graphs plus the six-node recorded demo are each checked top-to-bottom and left-to-right: **16 combinations**. Assertions cover node separation, orthogonal routing, route bounds, edges crossing node interiors, badge/node and badge/badge collisions, and shared overlapping edge segments.

All 16 combinations passed with **zero node overlaps, zero edge/node intersections, zero label/node collisions and zero overlapping edge segments**. [Raw geometry checks](benchmarks/graph-layout-2026-10-22.json) include measured layout time, dimensions and remaining edge crossings. Dense graphs can still have perpendicular crossings: OpenTelemetry has 44 in either direction. Crossings are separated visually and are not claimed to be eliminated. The recorded demo has zero crossings in both directions.

The layout uses [ELK's layered orthogonal routing and crossing minimization](https://eclipse.dev/elk/reference/algorithms/org-eclipse-elk-layered.html), with its [supported worker interface](https://github.com/kieler/elkjs). Calculation runs outside the main UI thread and is terminated on unmount, topology/direction change or deadline. Line and badge rendering share the computed route. Only highlighted/hovered relations animate. The worker loads when Graph opens; it adds about 1.60 MB before compression, measured at 470,617 transferred bytes with local Nginx gzip. This tradeoff is disclosed; no load/FPS guarantee is claimed. ELK's notice/license ships in `frontend/public/third-party-notices.txt`.

## Website checks

The [ten-repository live run](LIVE_WEBSITE_AUDIT.md) used visible Browser forms, actual HTTP jobs and real public GitHub retrieval at pinned revisions. Final scores and source coverage are in its [JSON](benchmarks/live-website-2026-10-21.json).

| Live repository | Graph result | Commit analysis |
| --- | --- | --- |
| DietrichGebert/ponytail | No supported deployable topology; no fabricated graph | Unavailable |
| GoogleCloudPlatform/microservices-demo | 12 nodes / 16 relations | Risk 40; debt 80.769; provisional |
| fastapi/full-stack-fastapi-template | 5 / 2 | Risk 5; debt 45; provisional |
| dockersamples/example-voting-app | 6 / 5 | Risk 40; debt 52.174; provisional |
| microservices-demo/microservices-demo | 17 / 1; explicitly incomplete | Risk 5; debt 60; provisional |
| spring-petclinic/spring-petclinic-microservices | 11 / 13 | Risk 5; debt 72.152; provisional |
| open-telemetry/opentelemetry-demo | 20 / 47 | Risk 40; debt 88.004; provisional |
| dotnet/eShop | Aspire definitions unsupported | Unavailable |
| saleor/saleor-platform | 7 / 5 | Risk 15; debt 54.545; provisional |
| expressjs/express | Library architecture abstention | Unavailable |

The 22 October graph repair additionally checks the rebuilt website's demo and retained Spring, Voting and OpenTelemetry captures: worker loading, finite SVG geometry, node counts, Fit, 1:1, scrolling, direction changes, expanded-view close/Escape, node selection and endpoint display. The earlier live check verified project-specific Findings navigation. Final [Browser measurements](benchmarks/graph-ui-browser-2026-10-22.json) show no node overlaps, nonfinite paths or fitted-canvas scroll overflow on these four graphs. Geometry for the other four supported repositories is checked from their saved captures, without spending more analysis quota.

Project-directory search was checked for correct filtering/clearing and its measured **44px** container / **42px** input height. Narrow browser checks used observed CSS widths 780px and 480px; the Browser viewport override clamped/scaled smaller requests, so a true 390px check is **not claimed**. At 480px the page and fitted graph no longer overflow horizontally. Temporary viewport overrides were reset.

Screenshots: [project directory](benchmarks/project-directory-2026-10-22.png), [recorded demo](benchmarks/graph-demo-2026-10-22.png), [OpenTelemetry](benchmarks/graph-otel-2026-10-22.png).

Earlier API smokes passed authentication, project isolation, patch analysis, evidence fields, comments-only risk zero, history, snapshots, baseline/drift/reviews, unchanged no-edit preview, cleanup and token revocation. Additional live-run smoke attempts hit the five-project then 30-job quota and did not complete; limits were not bypassed. The job quota is a rolling 24-hour window, not a midnight reset.

## Controlled source-accuracy benchmark

The [21 October regression benchmark](ACCURACY_FIXES.md) evaluated 15 cases twice against pinned public sources. Fourteen selected diagnostic API-change labels agreed after fixes, and eight applicable no-edit previews were unchanged. Seven library/source-only cases had no applicable architecture preview. These repair controls are correlated and do not form an independently held-out incident dataset. The full 115-file Express comparison was correctly rejected at the 100-file limit; a 12-file subset was evaluated separately.

The individual benchmark scenarios, expectations, scores and warnings are retained in [raw results](benchmarks/public-repositories-2026-10-21-fixed.json). They cover identical snapshots, comments/formatting, route rename/deletion, breaking model types, optional/required model additions, supplied cross-file consumers, large source files and batches, real upstream comparisons, source budgets and no-edit previews.

## Errors and bugs found, and what changed

| Finding | Fix / result | Verification / limit |
| --- | --- | --- |
| Project filter stretched to roughly a card's height | Removed inherited 280px flex basis from the directory field; kept the findings filter's separate flex layout | Browser measured 44px container and 42px input; filtering/clear passed |
| Curves passed through service cards and other curves | Replaced hand-positioned grid and direct curves with layered, port-aware orthogonal routes | 16 graph/direction checks; no card/route collisions or shared route segments |
| Labels obscured nodes or each other | Reserved label rectangles in layout; line and badge reuse the same geometry | Badge/node and badge/badge assertions on demo and saved graphs |
| Zoom produced clipped content and phantom scroll space | SVG dimensions now match the scaled drawing; Fit observes viewport width and height | Browser Fit / 1:1 / scroll checks; no forced initial fake viewport dimensions |
| Mobile SVG forced to at least 680px | Removed the inherited minimum for the new graph renderer | Actual 480px browser check; true 390px not available in this Browser override |
| Small embedded graph difficult to inspect | Added expanded native dialog, Fit, 1:1 and direction controls | Demo/large graph expansion; direction relayout keeps dialog working; Escape/close checked |
| All paths animated and route geometry computed twice | One computed route per relation; worker layout; shared animation only for active relations | Build confirms separate worker asset; geometry and Browser checks |
| First worker integration failed in Browser despite Node tests passing | Replaced nested fake-worker bundling with ELK's supported native worker protocol | Rebuilt website renders demo and retained live captures |
| Hovering one endpoint also highlighted every parallel endpoint | Match the exact relation object, not just the service pair | Separate routes/labels preserved; no pair-based grouping or data deletion |
| Duplicate-looking order → user lines | Confirmed two distinct illustrative endpoint records; clarified parallel relations and demo provenance in UI | `/users/{user_id}` and `/users/{user_id}/profile`; see explanation below |
| Graph Findings link opened the public demo | Preserve actual project/job in the target link | Browser navigated from OpenTelemetry into its saved Findings |
| Unknown health shown as green / ONLINE / guessed port 8000 | Neutral unobserved state and no invented port | Browser checked neutral node indicators; missing-value API regressions |
| Missing endpoint shown as `/` | Display endpoint-not-observed evidence instead | Startup relations retain their type; no fake HTTP route |
| Imported service risk assigned baseline values / broken node 90 / stale graph fallback | Imports leave risk unassessed; missing and measured-zero values survive legacy API routes | Missing/zero/broken/stale-risk regression tests |
| Anonymous GitHub REST quota exhausted during real imports | Bounded exact-SHA public archive fallback only after anonymous rate limiting | Ten live imports; private/authenticated errors do not use public fallback |
| Unchanged oversized files falsely counted as changes | Stream hashes without admitting oversized source to parser | Oversized-source regression and corrected actual comparison |
| Infrastructure dropped and undeclared source folders duplicated services | Retain identifiable declared resources; deployment declarations control service membership | Google 12 nodes; Spring 12→11; OpenTelemetry 28→20 |
| Startup order presented as HTTP calls | Preserve startup type/provenance and absent endpoint | Compose parser tests and Browser relation details |
| Unknown ownership marked every service affected | Leave ownership unresolved and lower evidence completeness | Ownership/evidence regressions |
| Failed imports stayed pending / showed an apparently valid empty graph | Persist failed import state and gate graph display for failed/cancelled jobs | Store lease/status tests; UI gate; earlier unsupported-import website checks |
| Revision fields had ambiguous accessible labels / assumed main branch | Explicit labels and HEAD default | Browser exact-SHA submissions and frontend build |
| Comments/formatting accumulated risk | Parser-proven equivalent changes excluded from meaningful change scores | Comment controls now zero, including large single-file and 100-file batches |
| Breaking cross-file Python model changes missed | Resolve bounded supplied model context, inheritance and direction of compatibility | Type change 5→45 in diagnostic control; selected model labels verified |
| Backend source omitted by sampling / workload discovery incomplete | Fair per-service source sampling and supported plain K8s discovery | Template backend40/frontend60 source reads in recorded benchmark; Google workload capture |
| Library tutorial/example directories became services | Require supported deployment/application evidence; abstain otherwise | Express/FastAPI library controls and live unsupported cases |
| Fixed confidence implied reliability | Measured evidence completeness with missing-evidence reasons and provisional labels | Evidence tests and all seven live score cards |
| Dependency audit reported two high-severity packages | Compatible Vite/follow-redirects lockfile updates; no forced major upgrade | Final npm audit reports zero; build/tests passed |

## Why the demo has two order-service → user-service relations

The registry deliberately defines `/users/{user_id}` and `/users/{user_id}/profile` as separate illustrative relations. `frontend/public/demo.json` records both. They are not duplicate records with the same endpoint, so removing one would change the teaching example and detector inputs. The actual runnable `services/order_service/main.py` currently calls only `/users/{user_id}`; the profile relation is not verified runtime behavior. The graph now states that this is an illustrative recorded topology and explains parallel lines. “Relations” counts endpoint/evidence records, not unique service pairs.

## Remaining work and limits

- Dense topologies can retain edge crossings; no claim of a crossing-free graph for arbitrary inputs. Fit can make large graph labels small; 1:1, selection and expanded view are provided.
- Broader framework/language coverage, runtime traffic, independent risk labels, performance/load profiling and calibration remain open. Static partial scores are not repository-quality rankings.
- Public HTTPS hosting, store publication, installed Chrome/Edge acceptance and deployed vscode.dev consent/CORS checks remain release gates. No deployment or GitHub push occurred.
- Some older test-created projects were exported and removed to respect quotas; their pinned evidence is retained. The user's original MDT project, four runnable services and global registry remain intact.
