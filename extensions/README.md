# MDT client extensions

Both clients call the versioned MDT API; they contain no scoring model, database, GitHub App secret, or model key. Build outputs are ignored by Git and no build command publishes anything.

26 October update: rebuilt packages disclose separate source/parser/runtime coverage and preserve missing scores separately from zero. Shared client 8, browser 14 and VS Code unit 18 pass, plus 5 desktop, 4 web-worker, 4 Restricted Mode and 4 native Windows credential/consent/result/disconnect checks in actual VS Code hosts. Chrome and Edge passed authenticated connection, session recovery and logout against the local API in disposable profiles. Pending browser permissions now show recovery instructions and offer cancellation. Native permission evidence, package hashes and remaining publication gates are in [the release report](../docs/RELEASE_READINESS_2026-10-25.md).

| Client | Local artifact | Distribution now |
| --- | --- | --- |
| Browser | `browser/mdt-browser-alpha-0.1.0.zip` and `browser/dist/` | Load unpacked in Chrome/Edge; submit to a store only after publisher/privacy review |
| VS Code desktop and browser worker | `vscode/mdt-architecture-review-0.1.0.vsix` | Install from VSIX on desktop; browser distribution still needs deployed-host acceptance; publisher name is an explicit local placeholder |

Browser build: in `browser`, run `npm.cmd test`, `npm.cmd run build`, then PowerShell `Compress-Archive -Path 'dist\*' -DestinationPath 'mdt-browser-alpha-0.1.0.zip' -Force`.

VS Code build: in `vscode`, run `npm.cmd ci --ignore-scripts`, `npm.cmd test`, then `npm.cmd run package`. The package command uses the locally installed VSCE tool and packages the manifest, README, desktop runtime and a single browser-worker bundle. Source files, tests and packaging dependencies are excluded.

Shared client validation: in `packages/client`, run `npm.cmd test`. The SDK enforces endpoint validation, refuses redirects, carries short-lived bearer tokens, maps GitHub PR/compare contexts, and preserves decimal score summaries. Browser tests cover permission denial, worker/popup recovery, repository matching and stale connection responses. VS Code tests verify real staged/working Git content in disposable fixtures and browser-only repository submission with explicit confirmation and no workspace reads; they do not commit in this project.

The packages have been built and structurally inspected. Actual VS Code 1.141.0 desktop, web-worker, Restricted Mode and native Windows acceptance checks passed locally. Native upload decisions were made by the user, and the server's real partial result was preserved. These checks do not certify Chrome Web Store/Edge/Marketplace review, another OS or hosted `vscode.dev` behavior. Before public distribution, validate connect, denied access, source consent, import readiness, analysis, popup/editor restart, expired token, cancellation and result links against the deployed API. The browser editor also needs HTTPS and an exact CORS origin configured on that API.

See each client's README for setup, privacy, limitations and intended permissions. Verify a real publisher ID, repository license, support contact and public privacy URL before submitting to a store.
