# MDT alpha privacy notice — publication draft

Do not publish this draft until the operator, support contact, providers and retention choices below have been filled and approved.

- Operator / support contact: **undecided**.
- Website / API / hosting providers and processing regions: **undecided**.
- Effective date and approved license: **undecided**.

MDT processes account credentials, project repository identifiers, requested revisions, supplied source snapshots, analysis results and review annotations. Passwords are hashed. Website bearer sessions are kept in session storage; the browser extension uses browser-session storage and VS Code uses SecretStorage. These mechanisms do not make source or sessions immune to a compromised device.

The browser extension sends repository/revision/PR identifiers only after an explicit action. It has no content script and does not collect general browsing history. Desktop VS Code analysis requires workspace trust and upload confirmation before sending bounded before/after source. The browser editor entry sends revision identifiers and does not read local workspace files.

For repository imports MDT requests public source from GitHub. The hosted alpha's scoped analyses use deterministic processing and do not call an LLM provider. Hosting and database providers process the data needed to operate the chosen deployment; list those providers before publication.

Job retention is configurable (default 30 days); project snapshots and pinned baselines have different retention rules documented in OPERATIONS.md. Project deletion removes owned analyses, captures, rules and reviews; short-lived quota receipts survive deletion. The operator must state actual log retention, backup retention and the account-deletion contact before release. Do not promise immediate deletion from backups unless the deployed procedure guarantees it.

Publish the completed notice at the final privacy URL, link it from store listings and the web application, and verify that it describes the deployed configuration.
