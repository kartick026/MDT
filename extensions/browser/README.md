# MDT browser extension alpha

Run `npm.cmd run build` in this directory, then open Chrome or Edge's extensions page, enable Developer mode and choose **Load unpacked**, selecting `dist`. All executable code is bundled locally; no remote scripts are loaded.

1. Start MDT and sign in. Create a project and wait for its architecture import.
2. In My Account, copy the short-lived MDT session token.
3. Open the extension, enter the API URL (local `http://localhost:8000`, or an HTTPS deployment) and web URL (local `http://localhost:5173`). Paste the MDT token and connect. Permission is requested only for that API origin.
4. Open a matching GitHub repository, commit, compare, or pull request. Select the project and choose Analyze.
5. Open the full result in the web workspace. Closing the popup does not cancel the server job; reopening restores it during this browser session.

The extension sends revision identifiers, never page contents. PR base/head resolution is performed by MDT. Source execution and automatic GitHub comments are not part of this client. See PRIVACY.md.

The token, API/web destinations and recent job share one session-only connection record. Reconnecting or disconnecting invalidates pending popup/worker responses, so an old request cannot restore findings or attach its job to another server. An upgrade from the earlier separate-token storage format requires reconnecting. API URLs saved locally are form defaults only and are never paired with a session token to choose an authenticated destination.

`npm.cmd test` runs ten manifest, popup and worker checks, including denied origin permission, restart/resume, repository matching, late responses and connection changes during storage writes. These are simulated host checks; real Chrome/Edge installation, expiry and consent acceptance remain release gates.

At a zero budget, use unpacked Chrome builds or submit to Edge Add-ons after the release checklist is complete. Chrome Web Store developer registration has a one-time fee. Nothing in this build script submits or publishes an extension.
