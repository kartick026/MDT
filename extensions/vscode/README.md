# MDT Architecture Review — desktop and web alpha

This extension uses the same MDT API as the web app. The desktop entry reads actual Git index contents for staged analysis, or saved tracked working files for working analysis. Full before/after source and an immutable base SHA are sent only after an explicit upload confirmation. The separate browser entry submits repository/revision identifiers and never reads workspace files.

## Build and install locally

Run `npm.cmd install`, `npm.cmd test`, `npm.cmd run build`, then `npm.cmd run package` in this directory. In VS Code choose **Extensions: Install from VSIX** and select the generated `.vsix`. The `mdt-local-alpha` publisher ID is a local packaging placeholder, not a registered publisher claim. This script does not publish.

## Desktop workflow

1. Start MDT, sign in, and create/import a project matching the workspace's Git remote.
2. Copy a short-lived MDT session token from the web app's My Account page.
3. Run **MDT: Connect to Server**. Enter the API and web URLs and MDT token. Credentials are stored in VS Code SecretStorage and never in workspace settings.
4. Run **MDT: Analyze Staged Changes** or **MDT: Analyze Saved Working Changes**, review the file list, and confirm sending it to your chosen server.
5. Open **MDT Findings** in Explorer or select the MDT status bar item. The tree shows scores, revision/coverage evidence, findings and changed-file contracts. Source links open captured paths without inventing line numbers. The output channel retains the full result. Use **MDT: Open Last Analysis** for web evidence, or **MDT: Refresh Last Analysis** after restarting VS Code.

Local defaults are `http://localhost:8000` and `http://localhost:5173`. Remote endpoints require HTTPS. In a remote extension host, localhost means that host, not the desktop UI machine.

## Browser workflow

The manifest's `browser` entry is a single bundled web-worker module with no Node, Git or filesystem dependency. This follows the [VS Code web extension model](https://code.visualstudio.com/api/extension-guides/web-extensions).

1. Import a public repository in the MDT web app and wait for the project to become ready.
2. Run **MDT: Connect to Server** with HTTPS API/web URLs and a short-lived MDT token.
3. Run **MDT: Analyze Repository Revision (Browser)**, select the matching project, and enter a GitHub repository, commit, compare or pull-request URL.
4. Confirm the destination and revision before submitting. View findings in Explorer, refresh a saved job or open its evidence in the web app.

This workflow also works without reading a trusted or local workspace. Staged/working source commands are disabled in the web host. The browser entry keeps the token and endpoint together in SecretStorage, binds saved jobs to that connection, and ignores responses after disconnect or configuration changes. A late submission is cancelled on its original server when possible.

Public `vscode.dev` distribution and end-to-end use against a deployed API still require validation. The API must permit the actual extension worker's HTTPS origin in its exact CORS allowlist; inspect the deployed request origin rather than assuming it equals the editor page origin. Do not replace the allowlist with `*`. This package has not been uploaded to the Marketplace.

## Verification

`npm.cmd test` exercises desktop Git collection and the compiled browser module, including denied confirmation, repository matching and connection races. `npm.cmd run test:host` starts an isolated VS Code profile and checks activation, commands, the findings view, configuration and real staged/working Git snapshots. Set `VSCODE_EXECUTABLE` if VS Code is installed elsewhere.

For the actual browser worker, use `$env:MDT_HOST_KIND='web'; npm.cmd run test:host` in PowerShell, then `Remove-Item Env:MDT_HOST_KIND`. This runs VS Code with `--extensionDevelopmentKind=web` and verifies that the browser entry, commands and findings view activate without Node. Both host modes passed locally in VS Code 1.141.0. These checks do not automate credential entry, source-upload consent, a deployed browser origin or another operating system.

## Boundaries

Desktop source collection requires Git in the extension host and Workspace Trust. Unsaved and untracked files are excluded; stage new files first. Binary, non-UTF-8, symlink and submodule changes require a separate committed analysis. Limits are 100 changed files and 1 MiB of full source. Renames are represented as removal plus addition. The web entry delegates source retrieval to MDT's repository analysis. No source is executed, no files are changed, and no commits or pushes are made by either entry.

## Privacy and publication

The configured MDT server receives full source, file paths and revision metadata for desktop changes, or repository/revision identifiers for browser analysis. No telemetry is sent. The server controls retrieval and retention; review its policy. Disconnect deletes that entry's local secret and cached job. Desktop and web hosts retain separate connection state. Sign out in the web app to revoke the same session server-side. Before store publication, choose and verify the actual publisher identity, repository/license, support contact, and public privacy URL.
