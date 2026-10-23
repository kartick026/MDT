# MDT web workspace

The entrypoint is `/#/projects`; existing `/#/workspace` links still resolve. Three main destinations provide Projects, History and Account. Each owned project has Summary, Analyze, Graph, Findings and Drift views. Anonymous users can open an explicitly labeled illustrative reference snapshot with Summary, Graph and Findings. Analysis links retain project/job IDs; the server checks ownership when reopened.

Signed-in users create owned projects, follow architecture-import jobs, analyze revisions, search history, compare captured snapshots, pin a baseline, export JSON/Markdown/HTML and preview structured graph edits. Finding reviews and dependency rules retain their reasons separately from calculated scores. Each job captures the rules used at submission.

## Local development

Run `npm.cmd ci` and `npm.cmd run dev`. With `VITE_API_URL=/api`, Vite proxies API calls to `http://127.0.0.1:8000`. Run `npm.cmd run build`, `npm.cmd test`, and `npm.cmd run lint` for verification. The Docker frontend proxies `/api/` to the backend service. A separate static host needs an HTTPS API URL configured at build time or an equivalent same-origin proxy.

Copy `.env.example` for local configuration. `VITE_ENABLE_LOCAL_DASHBOARD=true` adds an authenticated Local diagnostics dialog; hosted builds leave it false. `VITE_ALLOW_SIGNUP=false` keeps the public alpha invite-only. These switches change the interface, not server authorization.

Graph, History, Drift, account, project-rule settings and diagnostics JavaScript load on demand. Pending reads are aborted when their views unmount, job polling pauses in hidden documents, and diagnostics fetch only on open or explicit refresh. Lazy-import failures offer a reload while preserving the saved link.

## Sessions and evidence

Short-lived bearer credentials are stored in sessionStorage, cleared on logout, and revoked through `/auth/logout`. Previous localStorage sessions are removed. Analysis caches are in component state, remounted on account changes, and discarded on project changes. Session storage remains readable to injected JavaScript; an HttpOnly BFF session is a future hardening step, not an implemented claim.

Scores retain up to three decimals. Commit risk and architecture debt are separate. Evidence provenance, partial coverage, warnings and raw results remain visible/exportable. Text recommendations never turn into guessed graph edits; only structured server edits can be previewed.

The updated finding cards, filters and inline preview panels retain the project's custom UI. Findings paginate in groups of 15. Preview panels display the measured signed debt change, introduced/resolved findings and detector warnings; a lower score does not establish runtime reliability or preserved functionality. The development admin shortcut appears only when the local dashboard is enabled on a loopback hostname.

## Public snapshot fallback

`getDemo` first requests `/v1/demo`, then falls back to `/demo.json` when the API is unavailable. From the repository root, run `python scripts/export_demo.py` with backend dependencies installed, then `python scripts/export_demo.py --check`. This recalculates the canonical fixture and previews in an isolated copy without local credentials or runtime data. CI rejects a stale asset. The UI labels a fallback as a bundled recorded example; the payload records detector and snapshot versions rather than pretending to be a runtime capture.

The fixture includes three structured recommendations with previews recomputed by the canonical detector on immutable copies. The UI displays these recorded results only when the snapshot version and recomputation provenance match. It does not invent score reductions or simulate a network delay. Owned-analysis previews continue to call the authenticated saved-analysis endpoint.

The graph defaults to directed service connections. Select a connection to inspect all captured relations, including methods, endpoints and provenance; Individual relations draws each record separately. Counts distinguish connections from relations. These are presentation choices and do not alter detector inputs. Partial/insufficient architectural evidence is shown neutrally in results and exports; zero does not imply safety.
## Validation scope

Node tests verify precision, export integrity, evidence defaults, route round trips and session cleanup. Build/lint validation does not replace browser acceptance testing. Check sign-in, two-account isolation, project creation/import, analysis completion/cancellation, snapshot browsing, exported evidence, logout, and narrow-screen keyboard navigation against the actual backend before release.
