# Alpha operations and recovery

Keep the application and database in the same region where possible. The deployment configuration remains local until an owner chooses the actual hosting accounts, URLs and secrets. Use the release steps in [PUBLIC_ALPHA.md](PUBLIC_ALPHA.md); do not treat a successful local container as a public deployment.

## Health and smoke checks

Use `/health/ready` for readiness and the authenticated `/health/detailed` route for diagnostics. A free API may sleep. The public demo can fall back to its bundled recorded fixture while it wakes. Job results, policies, reviews and baselines live in PostgreSQL in hosted mode; do not put them on an ephemeral web-server filesystem.

`scripts/api_smoke.py`, run inside the API container, creates a named disposable project, submits real before/after source, checks policy evaluation, history, snapshots, baseline comparison, review annotations, immutable previews and logout revocation, then deletes its project. `--keep-for-browser` deliberately retains that one project for UI checks and prints its link; delete it after validation. Run smoke checks against a validation deployment before releasing a new image.

## PostgreSQL backup and restore

Use PostgreSQL client utilities compatible with the server. Set connection credentials privately in process environment variables or a protected service file; never put passwords in a tracked command file. A backup contains private source snapshots, account password hashes and project records. Keep it outside the repository in a restricted, encrypted storage location.

1. Export the private `mdt` schema with `pg_dump --dbname=<source connection> --schema=mdt --format=custom --file=<new backup file>`. Use a new timestamped filename and keep the last known good backup.
2. Restore first into a **new empty database**, using `pg_restore --dbname=<new restore connection> --no-owner --no-privileges <backup file>`. Do not use `--clean` against an existing application database.
3. Quiesce writes while comparing source and restore. Set `MDT_BACKUP_SOURCE_URL` and `MDT_BACKUP_RESTORE_URL`, then run `python scripts/verify_postgres_backup.py`. It uses read-only repeatable-read transactions and streamed SHA-256 comparisons of records, jobs and schema versions. It never prints source contents or URLs.
4. Point an isolated API instance at the restored database. Verify login, owned project access, an existing result, baseline and review labels. Running jobs can be recovered by the lease mechanism; never run two independently configured applications against the same restored queue accidentally.
5. Switch the actual deployment only after that check. Preserve the original database until the restoration is accepted.

On 19 October 2026, a PostgreSQL 17 dump of the disposable hosted test database restored into a separate database. All rows and values in `records` (7), `jobs` (1) and `schema_versions` (1) matched by streamed hashes. This verifies the local recovery procedure, not a managed host's backup service.

For local SQLite, use Python's `sqlite3.Connection.backup()` API or stop the application before copying the database; copying a live database file alone can miss pending journal/WAL data. Restore to a new local file and start a validation instance before replacing any working database.

## Rollback and retention

Retain the previous container image and its deployment configuration before a release. Revert the application image first when the schema remains compatible. The current store migration is additive; future destructive migrations need a separate recovery plan and a verified backup.

Jobs expire after `JOB_RETENTION_DAYS` (30 by default). Old captured snapshots expire on the same schedule except the current project snapshot and the pinned baseline. Finding review annotations follow their analysis retention; expiry labels remind reviewers to reconsider a classification and never change the original risk/debt score. Deleting a project removes its owned analyses, captures, rules and reviews. Quota receipts deliberately survive deletion for their short anti-abuse retention.

The app catches failed lazy-view imports and offers a refresh after a deployment or lost connection. Preserve hashed static assets across deployments where the chosen host supports it. Nginx serves JavaScript/CSS/JSON with gzip and hashed assets with immutable caching; the entry document is not cached.
