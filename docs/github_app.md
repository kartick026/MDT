# Microservice Drift Tracker (MDT) — GitHub App & Webhook Guide

This guide details how to integrate MDT with GitHub organizations using a **GitHub App** and **Webhook Automation** to enable automated pre-merge drift gating and pull request risk reporting.

---

## 1. Why Use a GitHub App?

While a Personal Access Token (PAT) works for local development, a **GitHub App** is the recommended standard for enterprise and organization-wide deployments:
- **Granular Least-Privilege Permissions:** Scoped strictly to repository metadata and contents without granting broad account access.
- **Short-Lived Installation Tokens:** Automatically generates temporary RS256 JWT tokens that expire after 1 hour.
- **Higher Rate Limits:** GitHub Apps enjoy 5,000 to 15,000 requests/hour compared to user PATs.
- **Organization Decoupling:** Does not break when individual employees leave or rotate personal tokens.

---

## 2. Step-by-Step GitHub App Registration

1. Navigate to your GitHub Organization (or personal account):
   `Settings > Developer settings > GitHub Apps > New GitHub App`
2. **App Details:**
   - **Name:** `MDT-Drift-Tracker` (or your company's preferred name)
   - **Homepage URL:** `https://mdt.yourdomain.com`
3. **Webhook Configuration:**
   - **Active:** Checked (`true`)
   - **Webhook URL:** `https://mdt.yourdomain.com/webhook/github` (or your public ngrok/Cloudflare tunnel endpoint)
   - **Webhook secret:** Generate a high-entropy 32-character string (e.g. `openssl rand -hex 20`). Save this value for `GITHUB_WEBHOOK_SECRET`.
   - **SSL verification:** Enable SSL verification (`true`).
4. **Repository Permissions:**
   - **Repository contents:** `Read` (required to read commit diffs and inspect `docker-compose.yml`)
   - **Pull requests:** `Read & Write` (required if you want MDT to post automated impact comments on PRs)
   - **Commit statuses:** `Read & Write` (required for PR check gating)
   - **Metadata:** `Read-only` (mandatory)
5. **Subscribe to Events:**
   - Check **Push** (triggers drift analysis on git pushes)
   - Check **Pull request** (triggers impact evaluation on new or updated PRs)
6. Click **Create GitHub App**.

---

## 3. Generate Private Key & Retrieve App ID

1. On the newly created GitHub App settings page, scroll down to the **Private keys** section.
2. Click **Generate a private key**. A `.pem` file will download to your machine.
3. Keep this `.pem` file secure.
4. Note the numeric **App ID** displayed at the top of the General settings page (e.g., `948123`).

---

## 4. Environment Configuration

Add the GitHub App credentials to your `.env` file:

```bash
# Webhook signature secret
GITHUB_WEBHOOK_SECRET="your-32-character-webhook-secret"

# GitHub App ID
GITHUB_APP_ID="948123"

# GitHub App Private Key (.pem content)
# Option A: Multi-line string in Docker Compose / Kubernetes Secret
GITHUB_APP_PRIVATE_KEY="-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA0...\n-----END RSA PRIVATE KEY-----"

# Option B: Store as a mounted secret file and provide the path
GITHUB_APP_PRIVATE_KEY_PATH="/etc/secrets/github-app.pem"
```

---

## 5. Installing the App on Target Repositories

1. On your GitHub App settings page, click **Install App** in the left sidebar.
2. Select your organization or account.
3. Choose **All repositories** or select specific microservice repositories (e.g. `kartick026/MDT`).
4. Click **Install**.

---

## 6. Webhook Processing & Automated PR Gating

When a developer pushes code or opens a Pull Request, GitHub sends a JSON payload to `POST /webhook/github`.

### Webhook Verification Workflow
```
GitHub Push Event
       │ (HMAC SHA-256 Signature)
       ▼
MDT /webhook/github
       │
       ├─► 1. Verify X-Hub-Signature-256 with GITHUB_WEBHOOK_SECRET
       ├─► 2. Mint short-lived Installation Access Token via RS256
       ├─► 3. Fetch commit diff from GitHub REST API
       ├─► 4. Run HMDA Risk Analysis & AST Connection Checks
       ├─► 5. Record results to Neo4j & Analysis History
       └─► 6. (Optional) Post PR Status Check & Remediation Comment
```

### Automated PR Status Check Gating
MDT can be configured to fail status checks if the risk score exceeds a defined threshold:
- **`risk_score < 30` (LOW):** Status Check `success` — green checkmark on GitHub PR.
- **`30 <= risk_score < 60` (MEDIUM):** Status Check `success` with warning annotation.
- **`risk_score >= 60` (HIGH / CRITICAL):** Status Check `failure` — blocks merge until architectural review or What-If remediation is applied.
