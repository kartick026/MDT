# MDT Git hook

The default hook uses project-scoped `/v1` jobs, the same path as the web and editor clients. Import a project first, then copy its ID from Project settings. Set `MDT_API_URL`, `MDT_API_TOKEN` and `MDT_PROJECT_ID` in your process environment. Keep tokens out of Git configuration, tracked files and shell history. Tokens expire with the web session.

The hook verifies that the selected project's repository matches the Git remote, submits actual before/after contents, and polls within `MDT_WAIT_SECONDS` (default 120 seconds). On timeout or interruption it attempts to cancel its job. A server outage, authentication error, failed job or partial result blocks by default; errors include actionable configuration guidance.

`MDT_API_MODE=legacy` is an explicit local compatibility option for the old `/analysis/analyze` endpoint. It is not the default and is unavailable in the hosted profile. `MDT_ON_ERROR=warn`, `MDT_FORCE` and `MDT_SKIP` are deliberate developer overrides; inspect `mdt_check.py` before opting out of a check. The hook never executes repository source, commits or pushes.

The server receives the selected source snapshots. Use only a trusted MDT endpoint; HTTPS is required except for loopback addresses. For a free sleeping host, use a larger bounded wait or review in the web app before invoking the hook.
