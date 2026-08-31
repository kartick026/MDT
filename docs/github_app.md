# GitHub App Integration

The Microservice Drift Tracker (MDT) supports authentication via a **GitHub App** rather than relying on a single Personal Access Token (PAT). This is the recommended approach for deploying MDT across an organization because it provides granular permissions, dynamic token generation, and does not depend on an individual user's account.

## 1. Creating the GitHub App

1. Go to your organization settings on GitHub: `Settings > Developer settings > GitHub Apps > New GitHub App`.
2. Give your app a name (e.g., `MDT-Internal`).
3. Set the **Homepage URL** to your MDT dashboard URL.
4. **Webhooks**:
    - **Active**: Checked
    - **Webhook URL**: `https://your-mdt-domain.com/webhook/github`
    - **Webhook secret**: Generate a secure random string (you will use this for `GITHUB_WEBHOOK_SECRET`).
5. **Permissions**:
    - **Repository contents**: `Read` (required to fetch file changes and clones)
    - **Repository metadata**: `Read` (mandatory)
6. **Subscribe to events**:
    - Check `Push`
7. Click **Create GitHub App**.

## 2. Generating the Private Key

1. On the settings page of your newly created GitHub App, scroll down to the **Private keys** section.
2. Click **Generate a private key**. This will download a `.pem` file to your computer.
3. Note your **App ID** at the top of the settings page.

## 3. Configuring MDT

Open your `.env` file and configure the new variables:

```bash
# Security secret for webhook payload verification
GITHUB_WEBHOOK_SECRET="your-webhook-secret-from-step-1"

# The App ID from step 2
GITHUB_APP_ID="123456"

# The contents of the .pem file.
# NOTE: Replace actual newlines with `\n` if setting via single-line environment variable, 
# or use proper multi-line quoting in your compose/deployment engine.
GITHUB_APP_PRIVATE_KEY="-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA...\n-----END RSA PRIVATE KEY-----"
```

Once configured, the MDT backend will automatically generate short-lived Installation Access Tokens (JWT exchanged via RS256) on the fly for each repository it needs to analyze, falling back to `GITHUB_TOKEN` only if the App is not configured or the repository is not installed in the App.
