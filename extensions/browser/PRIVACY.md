# MDT browser alpha privacy

The extension runs only when you open it. It does not inject content scripts, collect browsing history, read page contents, or send telemetry.

When you choose Analyze, it sends the selected GitHub repository and revision or pull request number to the MDT API server you configured. That server retrieves source under its own access and retention policy. Review the server's policy before connecting. The public alpha supports public repositories.

Your MDT bearer token, connection identity, authenticated API/dashboard destinations and recent job identifier are held together in extension session storage. They are not synchronized and are cleared by Disconnect or browser shutdown. API/dashboard URLs are also saved locally as form defaults, without a token. Reopening the popup can resume a job only for the same connection. Responses arriving after a connection change cannot restore the previous session's findings. An upgrade from the older storage format clears its separate token and requires reconnecting. Signing out in the web app revokes the shared session.

Only the configured API origin is requested at connection time. HTTPS is required except for an explicitly configured localhost development server. No GitHub, database, or model-provider secret belongs in the extension.

This is an unpublished academic alpha. Distribution from a store requires a publicly reachable privacy policy, support contact, and verified publisher identity before submission.
