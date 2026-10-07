# SupportPilot user guide

SupportPilot is a standalone support workspace: create tickets inside the application, investigate them against your knowledge library, and record human review. External help-desk intake and customer-message delivery are not connected.

## Sign in

1. Start the application using the [README quick start](../README.md#quick-start), then open `http://127.0.0.1:8000`.
2. **With GitHub** (when an OAuth App is configured): **Sign up** to choose a repository and receive a workspace token (shown once; copy it), or **Sign in** to verify with GitHub, pick your workspace, and enter its token. Lost it? **Sign in → Forgot your token?** re-authorizes with GitHub and issues a new one.
3. **With a server-issued token:** **Sign in → Use a server-issued token**, then paste the `token` value from `SUPPORTPILOT_API_TOKENS_JSON` in your private `.env`.

Reloading keeps you signed in for that tab. Tick **Keep me signed in on this device** to stay signed in across tabs and restarts; **Disconnect** clears it. Keep tokens out of screenshots, commits, and tickets.

## The dashboard

| View | What it is for |
| --- | --- |
| Overview | What needs you: key numbers, the oldest items waiting on a person, the agent pipeline, activity, readiness, and GitHub events |
| Mission control | Agent pipeline, work queue, review desk with test evidence, PR and CI status, agent reliability, knowledge freshness |
| Repositories | Connect GitHub, select repositories, sync commits/issues/activity, import docs, and publish linked issues |
| Agent runs | Queue tasks with templates and context packs, watch live logs, and review results, usage, and draft PRs |
| Tickets | Search and filter tickets; manage context, priority, ownership, status, notes, and investigations |
| Review queue | Current unreviewed drafts that still match their ticket revision |
| Knowledge | Inspect sources, test retrieval, and manage workspace documents when signed in as an admin |
| Activity | Recent ticket creation, edits, notes, investigations, and review decisions |
| Workspace | Your identity, members configured on the server, mode, limits, retention, and release prerequisites |

Counts come from stored workspace data. A successful draft outcome is a proposed resolution; it does not automatically mark the ticket resolved. Readiness items identify configuration and release work, rather than measuring service uptime or model accuracy.

## Work a ticket from start to finish

1. Choose **New ticket**. Enter the customer's problem, useful logs, product version, and account ID when relevant. In the demo workspace in fixture mode, you can start from an example.
2. Set **Priority**, **Assignee**, and **Ticket status**; each selection saves immediately. Assignees must be configured members of your workspace.
3. Add an **Internal note** for teammate context. Use **Edit context** and **Save context** when the investigation needs corrected ticket facts.
4. Choose **Investigate ticket**. Inspect the proposed response, **Evidence**, and **Trace**. The trace shows executed steps and, in fixture mode, synthetic tool activity.
5. Add a review note and **Approve draft** or **Reject draft**. Approval records the decision; customer delivery is still manual.
6. Explicitly set the ticket to **resolved** once your team considers the customer issue complete. Change its status to reopen it when needed.

A draft can propose a resolution, request missing information, or escalate. Collect missing information into the ticket and run a fresh investigation. If someone edits the ticket while you are working, stale saves fail with a conflict; refresh and apply your changes to the current revision. Any ticket edit also makes an earlier draft stale, including a priority or status change. Investigate again before reviewing it.

## Maintain useful knowledge

An **admin** can add a document with a title, plain-text or Markdown body, source path, and product version (`v1`, `v2`, or `any`). Successful saves update the source and its search index together. Use search to check what a ticket investigator can retrieve, including the version filter.

Edit a document when guidance changes. **Archive** removes its chunks from future searches while retaining the source; **Restore** indexes it again. Existing investigation evidence remains a historical snapshot. Reload after a revision conflict before attempting another edit.

Seed documents are read-only synthetic examples. Workspace documents survive application restarts. Agents can read and search knowledge but cannot add, edit, archive, or restore it. If indexing fails, the mutation fails and the previous saved source/index remains available.

## Understand the active mode

- **Fixture:** deterministic demonstration answers, lexical retrieval, and synthetic RelayDesk account/service/incident records. Use the example tickets to learn the workflow. Adding a document makes it searchable, but fixture routing is not a general-purpose model.
- **Live:** a real model drafts answers from your workspace documents: your logged-in Claude Code, Codex, or Antigravity CLI (no API key), or the Claude or OpenAI API. With GitHub integrations on, investigations check the latest GitHub Actions results and open `incident` issues of your repository. Account lookups are not connected, so account-specific requests escalate. Synthetic data is never used in live mode; import your docs before investigating.

Follow the [release checklist](RELEASE_CHECKLIST.md) and [deployment guide](DEPLOYMENT.md) before using customer data.

## Engineering workflow

See [GitHub setup](GITHUB_SETUP.md) for OAuth, webhooks, and invitations, and [Agent bridge](AGENT_BRIDGE.md) for runners. In a checkout, `supportpilot login` (once) and `supportpilot watch` start a runner; queued runs then start automatically. Repository contributors do not automatically become workspace members; admins invite them from **Workspace → Team**.

In **Knowledge**, **Upload file** previews a UTF-8 `.md`, `.markdown`, or `.txt` document before saving. The limit is 30,000 characters/120 KB; indexing and permission checks are the same as manually entered documents. PDFs and binary formats are unsupported.

Repository snapshots are bounded and refreshed explicitly. Synchronize after changes, import updated documentation, and archive knowledge files removed or renamed upstream. Review imported sources before relying on generated responses.
