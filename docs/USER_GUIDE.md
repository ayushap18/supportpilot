# SupportPilot user guide

SupportPilot is a standalone support workspace: create tickets inside the application, investigate them against your knowledge library, and record human review. External help-desk intake and customer-message delivery are not connected.

## Connect a workspace

1. Start the application using the [README setup](../README.md#run-locally), then open `http://127.0.0.1:8000`.
2. Open your private local `.env`. Find `SUPPORTPILOT_API_TOKENS_JSON` and copy only the value of `token` for your identity, without quotation marks.
3. Paste it into **Workspace token** and choose **Connect workspace**.
4. Check the workspace, role, and fixture/live badge. Your token determines your workspace and reviewer identity; entering it does not create an external integration.

The browser keeps the token in memory. Refreshing the page requires reconnecting. Keep tokens out of screenshots, commits, and support tickets. If connection fails, verify the token matches the running server configuration and restart the server after changing `.env`.

## The dashboard

| View | What it is for |
| --- | --- |
| Overview | Stored ticket totals, current review backlog, seven UTC days of activity, and readiness items |
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

- **Fixture:** deterministic demonstration answers, lexical retrieval, and synthetic RelayDesk account/service/incident records. Use the example tickets to learn the workflow. Adding a document makes it searchable, but fixture routing does not become a general-purpose AI model.
- **Live:** hosted model generation and embeddings use your workspace documents. Synthetic seed documents are excluded, and account/service/incident tools are disabled until real adapters exist. Add relevant knowledge before investigating. Requests that need disconnected tools should seek more context or escalate.

The live adapter and deployment configuration are implemented; real provider quality and a public Render deployment remain unverified. Follow the [release checklist](RELEASE_CHECKLIST.md) and [deployment guide](DEPLOYMENT.md) before using customer data.
