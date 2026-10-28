# Credential exposure remediation

The tracked `scripts/test_neon_db.py` contained a literal database connection string. The literal was introduced in commit `240074b` and that commit was confirmed on the remote feature branch. Neither the connection string nor password is reproduced here.

## Completed local remediation

- The script now reads `DATABASE_URL` from the process environment or ignored `.env` files. Root `.env` takes precedence over `backend/.env`; the process environment takes precedence over both.
- Database-driver failures are reported without echoing connection details.
- The owner supplied an updated connection URL in root `.env`. Its password differs from the exposed value. The backend environment was synchronized without changing its other settings.
- A real connection using the replacement credential succeeded. A separate connection using the exposed credential was rejected by password authentication. The backend is ready and reports healthy durable storage.
- All 13 projects and 45 history entries were present during the check. No database records were deleted or rewritten for this incident.
- Exact-value scans found neither the exposed password nor its replacement in current tracked source or built frontend/client artifacts. Pattern-based credential scanning also passed.
- Environment-file variants are now ignored while explicit example/template files remain allowed.
- `scripts/check_secrets.py` provides location-only, redacted findings. `--staged` can be used before a commit. A CI job runs the check before the other validation jobs.
- Six focused secret-handling tests passed; the earlier combined secret-handling/authentication run passed 23 tests.

## Remaining publication boundary

The scan of 38 reachable commits found the exposed value in `240074b`, in `scripts/test_neon_db.py`. Local source changes do not change that published GitHub commit. Replacing the leaked tip commit requires an explicitly approved Git history rewrite and guarded force-push. The repository owner's standing instruction requires explicit authorization for each push.

Revocation prevents the exposed password from authenticating even while historical copies exist. GitHub caches, forks and previously downloaded copies cannot be assumed erased by a branch rewrite. This check does not establish whether the previously valid credential was accessed by anyone.

Neon documents password reset/rotation in its [role-management guide](https://neon.com/docs/manage/roles#reset-a-password).
