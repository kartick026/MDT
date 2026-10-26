# Runtime activation and release-image validation — 27 October 2026

The verified admission fixes are now active in the local Docker backend. The existing four saved projects have identical before/after record hashes. The API and website proxy are healthy. This completes local activation; professional clearance and public hosting remain pending.

## Executed verification

| Check | Result |
| --- | --- |
| Rebuilt local runtime, isolated full suite | **444 passed**, zero failures/skips, 54.93 s; includes PostgreSQL and Neo4j integration checks |
| Patched hosted runtime, isolated full suite as the non-root `mdt` user | **444 passed**, zero failures/skips, 41.34 s; one existing Starlette/httpx deprecation warning |
| Running API: ambiguous source inputs | All three conflicting combinations returned **422** |
| Running API: valid source representations | Both reached project authorization and returned **404** for the deliberately nonexistent test project |
| Running API: invalid-login burst | Of 12 concurrent requests, **4 returned 401 and 8 returned 429**. The configured five-per-minute budget also included the test's valid login. |
| Running API: normal analysis workflow | Route-change fixture completed with explicit `partial` status, computed risk **70**, and **18** static smells. Comment-only fixture risk **0**. These are fixture outputs, not accuracy guarantees. |
| History, saved snapshot, baseline, drift, review and no-edit preview | Passed; reviewing a finding did not change the saved risk score |
| Session revocation and disposable project cleanup | Passed |
| Existing user project preservation | Four projects before and after; identical SHA-256 digest of their records |
| Website, `/api/health/ready`, `/api/v1/demo` | HTTP **200** through `localhost:5173` |
| Actual browser rendering | **Not verified in this pass.** The existing Codex Browser runtime returned no connected browsers. BrowserAct CLI and `uv` were unavailable; neither was installed. |
| Development accuracy controls and local recovery | Refreshed: **20 controls** and **15 recovery invariants** passed. These remain development/store-level evidence. |

These are 444 distinct backend cases run on two runtime variants, not 888 distinct tests. Test-only dependencies were added to derivative validation images; the shipped hosted candidate retains its non-root user and excludes pip/build tooling. The disposable database containers/network were removed after validation. The original application stack remains running.

## New security issue found and fixed

The first hosted rebuild reused the cached Alpine package-install layer. A current Trivy 0.76.1 database reported **24 libcurl vulnerabilities** in `8.22.0-r0`: **1 high, 1 medium and 22 low**. This demonstrates why the previous clean scan cannot be reused indefinitely.

The runtime stage now has an explicit name. Rebuilding that stage with `--pull --no-cache-filter runtime` installed `libcurl 8.23.0-r0`. The subsequent scan reported **zero known OS/Python package vulnerabilities** for the new candidate. CI now forces this runtime-stage refresh for backend releases and disables build caching for the frontend release build. The Python wheel stage remains reusable.

The zero finding count applies to hosted candidate image `sha256:218809d4c24d415b63259dda183c4c35e1cead6ba26a3a44a13c468fd4a337d2` at scan time. It is not a penetration-test result, a scan of the larger local research image, or a professional-readiness certificate.

To build the hosted candidate locally:

```powershell
docker build --pull --no-cache-filter runtime -t mdt-release-hosted:review -f backend/Dockerfile.hosted backend
```

Use the resulting exact image for scanning and acceptance; a different builder's cached rebuild is a different artifact requiring validation. The hosted image was built and tested locally, not deployed publicly. Remote CI was not triggered.

## Evidence and current limits

- [Runtime, source hashes, project preservation, test results and before/after scanner findings](benchmarks/runtime-activation-2026-10-27.json)
- [Refreshed development accuracy metrics](benchmarks/professional-accuracy-development-2026-10-27.json)
- [Refreshed local recovery measurements](benchmarks/professional-local-reliability-2026-10-27.json)
- [Current professional gate decisions](benchmarks/professional-gates-2026-10-27.json)

The current source fingerprint is `b4d1987948124158c412ff97eeb837a7832c8a3a16382577f5a5c3ad90445e8d`. The local-runtime suite was run before the subsequent hosted Dockerfile/CI cache fix and records its earlier fingerprint separately. The patched hosted-runtime suite and refreshed readiness reports match the current fingerprint. Both running backend admission files match the workspace hashes.

Remaining requirements are unchanged: independently reviewed holdout labels and application security, actual HTTPS deployment and client acceptance (including another desktop OS and deployed VS Code web), hosting/publisher/support/privacy/license decisions, and a real external pilot. See [the ordered readiness gates](PROFESSIONAL_READINESS.md). No approval flags were fabricated, and no commit, push or public publication was performed.
