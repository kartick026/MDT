# Render + Neon publication preparation

Updated 29 October 2026. These are local preparations, not a deployment or a claim that all possible vulnerabilities have been eliminated. No commit or GitHub push is authorized by this document.

## Architecture and preserved data

`Dockerfile.render` builds the React site and the deterministic hosted API into one non-root web service. The browser calls the same origin, so no separately deployed frontend proxy or cross-origin API URL is needed. The application binds Render's `PORT`. `render.yaml` selects Singapore to match the existing Neon branch's region and keeps automatic deploys off.

Use the existing Neon PostgreSQL database for both application records (`mdt`) and managed identities (`neon_auth`). The backend verifies the Neon signature, issuer, expiry and subject, then checks the trusted Google account linkage and verified email. It does not trust a client-supplied email/provider. Keep both schemas on this database; an unrelated empty Render Postgres database does not contain the Neon identities.

Password login/registration/invitation and seeded admin/viewer accounts are disabled by default. Published configuration rejects enabling password authentication. Old application tokens without a Google authentication claim must sign in again. Existing account records, roles, project owners and saved history remain unchanged. New verified Google users receive the analyst role for their own projects; the client cannot choose administrator privileges.

## Render setup

1. After explicitly approving the GitHub publication yourself, create a Render Blueprint from the repository's `render.yaml`. Use the root Docker context and `Dockerfile.render`.
2. Supply `DATABASE_URL`, `NEON_AUTH_URL` and `NEON_JWKS_URL` in Render's private environment settings. Copy them from the existing Neon branch privately; never paste credentials in code, logs or frontend variables. The blueprint generates independent JWT and webhook secrets. Preserve the JWT value across deploys.
3. Leave `ALLOWED_ORIGINS` empty to derive the validated HTTPS origin from Render's `RENDER_EXTERNAL_URL`. If using a custom domain, set the explicit HTTPS origin instead. Wildcard, HTTP, credential-bearing and malformed production origins are rejected.
4. In Neon Console → project Settings → Better Auth, add the final `https://...onrender.com` or custom origin to trusted domains. Keep only Google as an OAuth provider. Email sign-up and email sign-in are already disabled on the current branch; magic links and phone sign-in were also verified off. Users were not deleted.
5. Replace **Google — Shared keys** with your own Google OAuth client in Neon before public launch. The Google redirect is the Neon Auth base URL followed by `/callback/google`; use the exact URL shown by Neon. Enter the client secret privately in Neon, not in this repository. Shared keys are development credentials, per [Neon's production checklist](https://neon.com/docs/auth/production-checklist).
6. Once local validation is complete and the public origin is registered, disable Allow Localhost on the production Neon branch. Keep development on a separate branch if local Google sign-in is still needed. The current branch retains localhost during local verification; do not disable it prematurely and lock out the local app.
7. Open the public site and verify Google sign-in, project import/analysis, saved-history reopen, account isolation, token refresh and sign-out. Confirm data survives a Render restart. Public deployment and remote checks remain outstanding until these actions occur.

The Docker fields and private environment values follow the [Render Blueprint reference](https://render.com/docs/blueprint-spec). The API's hosted profile does not require publicly exposing Neo4j, ChromaDB or the four local research services.

## Script commands

Run from the project folder:

```powershell
python scripts/test_isolated.py -q --disable-warnings
python scripts/run_microservices.py --check --base-port 18101
python scripts/test_neon_db.py
python scripts/inspect_db.py
python scripts/api_smoke.py --base-url http://localhost:8000
```

The launcher uses an existing suitable project Python, checks port ownership, waits for all four health endpoints, verifies user/order/payment/notification calls and terminates only the processes it started. Install native dependencies with `python -m pip install -r services/requirements-local.txt` inside a virtual environment if needed.

Database diagnostics use read-only connections and never initialize tables. `verify_neon_e2e.py` requires a separate explicit `TEST_DATABASE_URL` and uses generated test schemas. API smoke defaults to read-only checks; mutating checks require an explicitly supplied test bearer token plus `--allow-write`. Hosted persistence checks are opt-in for disposable validation instances. Ownership migration requires named users and selected project IDs and previews changes by default.

Each script supports `--help` or is an inert helper module. Test-only password credentials are supplied only by the isolated runner/CI; they are not deployment defaults. Evaluation, source replay and benchmarks operate on disposable backend copies and never execute downloaded repository code.

## Security changes and remaining scope

- Google-only authentication is enforced in both browser and API; stored password hashes are retained but cannot authenticate in normal mode.
- Production configuration fails closed for insecure secrets, absent provider settings and invalid CORS origins. Public interactive API docs are disabled.
- Sensitive API responses are not cached. CSP, frame protection, MIME protection, referrer/permissions policies and popup-compatible COOP protect the served frontend. Production responses include HSTS.
- Detailed health requires authentication. Unexpected database/client errors no longer return raw exception text or connection details to the browser.
- Local Compose ports bind to `127.0.0.1`. Compose remains a local research stack; its legacy database settings are not the public deployment blueprint.
- Docker contexts exclude environment variants, signing keys, local databases, virtual environments, screenshots, private backups and generated artifacts. No credentials are compiled into the frontend.
- Dependency review found no moderate/high/critical frontend npm findings, but seven low findings remain in Neon's optional UI dependency chain through `deepmerge` (GHSA-gcqx-w48m-w2h4). The registry's current latest version is still affected. No forced major upgrade or unreviewed patch was applied. Recheck before launch and track the upstream fix.

The existing release preflight also tracks licensing, public support/privacy metadata and native extension acceptance evidence. This work does not certify those separate publication gates.

## Local validation on 29 October 2026

| Check | Observed result |
| --- | --- |
| Isolated Python suite | 512 passed; 14 optional integration checks skipped in this run |
| Frontend tests, lint and production build | 43 tests passed; lint/build passed |
| Script entry points | All 27 Python files parsed/help/imported successfully |
| Native service launcher | Four temporary processes passed user/order/payment/notification calls on 18101–18104, then stopped |
| Offline evaluation and durability controls | 20 development controls passed; local reliability checks passed; bundled demo is current |
| Public-source benchmark/replay | Four repositories and 16 experiments completed without errors and left the registry unchanged; pinned topology replay recorded ten repositories |
| Render image | Built successfully, non-root runtime; same-origin frontend/API served correctly |
| Render vulnerability scan | Trivy with refreshed database: zero HIGH/CRITICAL findings for the built image; this is a point-in-time scan |
| Isolated Render API smoke | Ownership, patch analysis, comment-only control, previews, policies, history, immutable snapshots, baseline/drift, reviews and logout revocation passed |
| Hosted import/restart smoke | Public MDT import and exact commit analysis returned partial evidence as expected; saved project/result/preview reopened after API restart |
| PostgreSQL restore check | Read-only fingerprints matched a separate disposable restored database |
| Live browser | Google sign-out/sign-in, session renewal, retained history, saved graph and endpoint toggle passed; no observed CSP violations |
| Existing application data | Before/after hashes matched for 13 projects, 19 snapshots and all 45 original history rows; one additional account-owned analysis appeared during validation and was retained (46 current rows) |
| Local running stack | Eight services running; API, frontend and four demo health endpoints returned 200; all published ports bound to loopback |
| Credential checks | Git-managed source and script/frontend build scans found no credential literals; environment files remain ignored |

No GitHub commit/push or Render deployment was performed. The private preservation manifests and full scan results remain in ignored `scratch/`. Browser proof: [Google-only site](benchmarks/google-only-site-2026-10-29.png), [Neon provider settings](benchmarks/google-only-neon-settings-2026-10-28.png).

## Cache-only cleanup

The reviewed plan identified about 141 MiB of generated browser caches, Python bytecode and pytest cache. It excludes installed dependencies, reusable source archives, skills, screenshots, runtime databases, signing keys and preservation backups. Both virtual environments are useful: one supplies native service/full-stack dependencies, the other tests/PostgreSQL.

Automatic approval review rejected deletion of even an explicitly named generated cache file with the reason **blocked by policy**. No real cleanup deletion was executed; reclaimed bytes remain zero.

The reusable command is reviewable and defaults to a dry run. The latest reviewed plan contains 135 targets totaling 148,033,646 bytes (about 141.2 MiB); generated cache sizes can change between runs:

```powershell
python scripts/clean_generated_cache.py
# Run manually only after reviewing its generated private manifest:
python scripts/clean_generated_cache.py --apply
```

The command checks containment, symlinks/reparse points, tracked files, cache allowlists, source/data hashes and changed targets. It refuses a cache folder containing databases or reusable files. The build context was independently reduced by `.dockerignore` without deleting project files.
