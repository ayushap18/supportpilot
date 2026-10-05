# Connect GitHub to SupportPilot

## What this connection does

An administrator connects GitHub to an existing SupportPilot workspace. Teammates with access to that workspace can inspect its selected repository snapshots. GitHub authorization does not replace the workspace login or automatically invite every GitHub contributor.

The pilot discovers accessible repositories page by page. Select repositories deliberately, then synchronize their recent commits, issues, contributor activity, and source inventory. The interface reports scan limits: a bounded snapshot is not a complete code audit. Queue a coding-agent analysis when you need reasoning over the checked-out repository.

## Sign in with GitHub (workspace tokens)

The home page offers **Sign up** and **Sign in**:

- **Sign up:** verify with GitHub → choose a repository you can push to → SupportPilot creates a workspace connected to that repository and shows a workspace token **once** → continue to the dashboard.
- **Sign in:** verify with GitHub → enter your workspace token. The server checks that the token belongs to the same GitHub account → dashboard.
- **Forgot your token?** On the sign-in page after verifying with GitHub, choose the workspace and **Regenerate**. The previous token is revoked immediately.
- **Server-issued tokens** from `SUPPORTPILOT_API_TOKENS_JSON` still work through "Use a server-issued token" (`/#token`).

Only a SHA-256 hash of each workspace token is stored. Repository admins and maintainers get the admin role; other writers get the agent role.

1. Create an OAuth App at https://github.com/settings/developers → **New OAuth App**.
   - Homepage URL: `http://127.0.0.1:8000`
   - Authorization callback URL: `http://127.0.0.1:8000/api`. GitHub accepts any sub-path, so this one callback covers both `/api/auth/github/callback` (sign-in) and `/api/github/callback` (in-app connect).
2. Put the credentials in `.env` and restart:

```dotenv
SUPPORTPILOT_GITHUB_CLIENT_ID=...
SUPPORTPILOT_GITHUB_CLIENT_SECRET=...
SUPPORTPILOT_INTEGRATION_ENCRYPTION_KEY=...   # Fernet key, see below
# For deployments: SUPPORTPILOT_GITHUB_LOGIN_REDIRECT_URI=https://YOUR-SERVICE/api/auth/github/callback
```

The sign-in session lasts 30 minutes in an HttpOnly cookie. Workspace tokens stay in browser memory only.

## Team invitations

Workspace admins open **Workspace → Team**, enter a GitHub username, and choose Member or Admin. The invited person opens SupportPilot, verifies with GitHub, and sees **You're invited** during sign-up or sign-in. Accepting checks on GitHub that their account can read the workspace's repository, then issues their own token (shown once). Admins can revoke pending invitations.

## Issues become tickets

Open issues labelled `support` (configurable with `SUPPORTPILOT_GITHUB_SUPPORT_LABEL`) become tickets when you sync a repository, once per issue, linked back to the issue. Pull requests and closed issues are ignored. Issue text is redacted with the standard secret patterns.

For a deployed server, add a repository webhook:

- Payload URL: `https://YOUR-SERVICE/api/github/webhook`, content type `application/json`.
- Secret: the same value as `SUPPORTPILOT_GITHUB_WEBHOOK_SECRET`. Requests with a wrong signature are rejected, and the endpoint is disabled until the secret is set.
- Events: **Issues**, **Pushes**, **Pull requests**, and **Workflow runs**. Newly opened, labelled, or reopened `support` issues become tickets immediately. A push marks the repository snapshot "new commits since last sync". Pushes, issue and PR changes, and failed workflow runs appear in **Mission control → Live activity** without a manual sync.

Webhooks cannot reach `127.0.0.1`; locally, use sync.

## Quick start: server token

For a single team or local install, skip OAuth and give the server a personal access token:

```dotenv
SUPPORTPILOT_GITHUB_TOKEN=github_pat_or_ghp_token
```

Restart SupportPilot. **Repositories** then shows "Connected as <login> · server token", and every workspace on this server uses that token. Prefer a fine-grained token limited to the repositories you need. A classic token with `repo` scope can reach every private repository the account can. Rotate the token immediately if it is ever pasted into chat, logs, or commits. To disconnect, remove the variable and restart. Use OAuth instead when workspaces need separate GitHub identities.

## Configure OAuth

1. Create a GitHub OAuth app for your deployment in GitHub's developer settings. Use your SupportPilot origin as the homepage.
2. Set its authorization callback to exactly `https://YOUR-SERVICE/api/github/callback`. Local development uses `http://127.0.0.1:8000/api/github/callback`.
3. Configure these server-side variables in your private `.env` or deployment secret settings:

```dotenv
SUPPORTPILOT_GITHUB_CLIENT_ID=your-oauth-client-id
SUPPORTPILOT_GITHUB_CLIENT_SECRET=your-oauth-client-secret
SUPPORTPILOT_GITHUB_REDIRECT_URI=https://YOUR-SERVICE/api/github/callback
SUPPORTPILOT_INTEGRATION_ENCRYPTION_KEY=your-generated-fernet-key
```

Generate a key privately on your machine, with the project environment active:

```bash
python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

Keep the key stable across restarts, and back it up separately from the database. Losing it prevents decrypting existing connections. Do not put credentials in repository files, browser storage, issue bodies, or screenshots.

4. Restart SupportPilot. Connect your workspace as an admin and open **Repositories → Connect GitHub**.
5. Review GitHub's consent screen. OAuth `repo` access is broad and may include private repositories; organization policy can restrict authorization. Repository selection limits what SupportPilot synchronizes, not the permission GitHub grants the OAuth app.
6. Complete authorization, then reconnect with your workspace token after returning if requested. The token is intentionally kept only in browser memory.
7. Select a repository and synchronize it. Inspect the resulting timestamp and limits. Import repository documentation only when you want it available to the workspace's AI investigations.

A failed connection should show a recoverable message. Confirm the callback matches, the encryption key is valid, and GitHub permits the account/organization access. Changing server configuration requires a restart.

## Issues and agent work

Create a local ticket with enough context. In the selected repository, review the ticket and explicitly choose **Create GitHub issue**. This is an external write visible to repository collaborators. The saved link connects the local ticket and remote issue. An uncertain network response must be reconciled before another create attempt.

Queue a task in **Agent runs**, link its ticket and repository, and follow the displayed local bridge command. The CLI authenticates on your machine using your own provider account. Review the result, branch/patch, test output, and usage. A completed run means the process finished; it does not prove the issue is solved. Review, publish, and merge changes in GitHub through your normal process.

## Documentation and contributor activity

Import README/`docs/` text or Markdown from a selected repository. Imports are versioned knowledge sources, not instructions that the server executes. Imported documentation can be managed through Knowledge. Uploaded `.md`, `.markdown`, and `.txt` files are previewed before saving and follow the same indexing limits. Binary files and PDFs are not supported in this release.

Contributor data shows recorded repository events/commits within the snapshot bounds. It does not measure work hours, productivity, private off-repository work, or all GitHub account activity. Teammates see data through workspace access, not simply because their names appear in a repository's contributor list.

## Validation and rollout

Automated tests use mocked GitHub and CLI responses. A real OAuth connection, repository authorization, docs import, issue creation, and a provider run require your credentials and explicit in-app actions. Start with a test repository and non-sensitive documentation, then verify permissions and output before wider use.

For organization-scale installations, migrate to a GitHub App with selected-repository permissions, explicit member onboarding, signed webhooks, durable synchronization jobs, and isolated execution workers. OAuth connection and the manual local bridge are the current pilot architecture.

[Official GitHub OAuth flow](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/authorizing-oauth-apps) · [Engineering plan](ENGINEERING_WORKSPACE_PLAN.md) · [Agent bridge](AGENT_BRIDGE.md)
