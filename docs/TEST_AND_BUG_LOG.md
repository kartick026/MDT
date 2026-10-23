# Tests and bug log — 22 October 2026

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
