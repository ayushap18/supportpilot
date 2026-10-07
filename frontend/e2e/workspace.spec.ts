import { expect, test } from "@playwright/test";

const TOKEN = "browser-test-token-at-least-24-characters";
const AGENT_TOKEN = "browser-agent-token-at-least-24-characters";
const OTHER_TOKEN = "browser-other-token-at-least-24-characters";
const authorization = (token = TOKEN) => ({ Authorization: `Bearer ${token}` });

test("production API isolates workspaces, enforces knowledge roles, and rejects stale drafts", async ({
  request,
}) => {
  const created = await request.post("/api/tickets", {
    headers: authorization(),
    data: {
      subject: "Browser isolation signature migration",
      description:
        "After migrating to v2, webhook signature verification fails.",
      product_version: "v2",
      account_id: null,
      log: "Signature mismatch using the old header",
    },
  });
  expect(created.status()).toBe(201);
  const ticket = await created.json();
  const other = await request.get(`/api/tickets/${ticket.id}`, {
    headers: authorization(OTHER_TOKEN),
  });
  expect(other.status()).toBe(404);
  const investigationResponse = await request.post(
    `/api/tickets/${ticket.id}/investigations`,
    {
      headers: {
        ...authorization(),
        "Idempotency-Key": `browser-${ticket.id}`,
      },
    },
  );
  expect(investigationResponse.ok()).toBe(true);
  const investigation = await investigationResponse.json();
  expect(investigation.state).toBe("awaiting_review");
  const changed = await request.patch(`/api/tickets/${ticket.id}`, {
    headers: authorization(),
    data: {
      expected_revision: ticket.revision,
      description: "Updated v2 webhook context after investigation.",
    },
  });
  expect(changed.ok()).toBe(true);
  const staleEdit = await request.patch(`/api/tickets/${ticket.id}`, {
    headers: authorization(),
    data: { expected_revision: ticket.revision, priority: "urgent" },
  });
  expect(staleEdit.status()).toBe(409);
  const staleReview = await request.post(
    `/api/investigations/${investigation.id}/reviews`,
    {
      headers: authorization(),
      data: {
        draft_revision: investigation.draft_revision,
        decision: "approve",
        note: "Must reject stale context",
      },
    },
  );
  expect(staleReview.status()).toBe(409);
  const queue = await request.get("/api/queue?review=pending", {
    headers: authorization(),
  });
  expect(queue.ok()).toBe(true);
  expect(
    (await queue.json()).items.map((item: { id: string }) => item.id),
  ).not.toContain(ticket.id);
  const forbidden = await request.post("/api/knowledge/documents", {
    headers: authorization(AGENT_TOKEN),
    data: {
      title: "Agent cannot publish",
      body: "This document must never enter the knowledge index.",
      product_version: "v2",
      source_path: "internal/forbidden",
    },
  });
  expect(forbidden.status()).toBe(403);
  const searchable = await request.post("/api/knowledge/search", {
    headers: authorization(AGENT_TOKEN),
    data: { query: "webhook signature", product_version: "v2" },
  });
  expect(searchable.ok()).toBe(true);
  const operations = await request.get("/api/operations", {
    headers: authorization(),
  });
  expect(operations.ok()).toBe(true);
  const dashboard = await operations.json();
  expect(dashboard.counts.awaiting_review).toBe((await queue.json()).total);
  expect(dashboard.trends).toHaveLength(7);
  expect(dashboard.mode).toBe("fixture");
  expect(dashboard.tool_mode).toBe("synthetic");
  expect(
    dashboard.members.map(
      (member: { reviewer_id: string }) => member.reviewer_id,
    ),
  ).not.toContain("other-reviewer");
  expect(JSON.stringify(dashboard)).not.toContain(TOKEN);
});

test("investigate a migration ticket, inspect evidence, and approve the draft", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  await page.setViewportSize({ width: 1440, height: 1000 });
  const response = await page.goto("/");
  expect(response?.headers()["content-security-policy"]).toContain(
    "script-src 'self'",
  );
  await expect(page.locator("html")).toHaveClass("dark");
  await page.screenshot({
    path: "../docs/screenshots/connect.png",
    fullPage: true,
    animations: "disabled",
  });
  await expect(
    page.getByRole("heading", { name: /backed by evidence/ }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Sign in", exact: true })
    .first()
    .click();
  await expect(page).toHaveURL(/#signin$/);
  await page.getByRole("button", { name: "Use a server-issued token" }).click();
  await page.getByLabel("Workspace token").fill(TOKEN);
  await page.getByRole("button", { name: "Connect workspace" }).click();
  await expect(
    page.getByRole("heading", { name: "Your support, in focus.", exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: "../docs/screenshots/overview.png",
    fullPage: true,
    animations: "disabled",
  });
  await page.getByRole("button", { name: "New ticket" }).click();
  await page.getByLabel("Start with an example").selectOption("dev-03");
  await page
    .getByRole("button", { name: "Create ticket", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Investigate ticket", exact: true })
    .click();
  await expect(
    page.getByText("Resolution drafted", { exact: true }),
  ).toBeVisible();
  await expect(page.locator(".draft-copy")).toContainText("X-Relay-Signature");
  await page.getByRole("tab", { name: "Trace", exact: true }).click();
  await expect(page.locator(".trace-list")).toContainText(
    "citation IDs validated",
  );
  await page
    .getByLabel("Review note")
    .fill("Verified the v2 signature header against the source.");
  await page
    .getByRole("button", { name: "Approve draft", exact: true })
    .click();
  await expect(page.getByText("Draft approved", { exact: true })).toBeVisible();
  await expect(page.getByRole("status")).toContainText(
    "No customer message was sent",
  );
  await page.getByRole("tab", { name: /^Evidence/ }).click();
  await expect(page.locator(".evidence-card").first()).toBeVisible();
  expect(errors).toEqual([]);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: "../docs/screenshots/workspace.png",
    fullPage: true,
    animations: "disabled",
  });
});

test("missing context asks for details and unsupported requests escalate", async ({
  page,
}) => {
  await page.goto("/#token");
  await page.getByLabel("Workspace token").fill(TOKEN);
  await page.getByRole("button", { name: "Connect workspace" }).click();
  for (const [sample, expected] of [
    ["dev-07", "More details needed"],
    ["dev-09", "Human escalation"],
  ]) {
    await page.getByRole("button", { name: "New ticket" }).click();
    await page.getByLabel("Start with an example").selectOption(sample);
    await page
      .getByRole("button", { name: "Create ticket", exact: true })
      .click();
    await page
      .getByRole("button", { name: "Investigate ticket", exact: true })
      .click();
    await expect(page.getByText(expected, { exact: true })).toBeVisible();
  }
});

test("ticket dialog traps focus, closes with Escape, and tabs support arrow keys", async ({
  page,
}) => {
  await page.goto("/#token");
  await page.getByLabel("Workspace token").fill(TOKEN);
  await page.getByRole("button", { name: "Connect workspace" }).click();
  const trigger = page.getByRole("button", { name: "New ticket" });
  await trigger.click();
  const dialog = page.getByRole("dialog", { name: "New support ticket" });
  await expect(dialog).toBeVisible();
  await expect(
    dialog.getByRole("button", { name: "Create ticket", exact: true }),
  ).toBeInViewport();
  await page.screenshot({
    path: "../docs/screenshots/composer.png",
    fullPage: true,
    animations: "disabled",
  });
  for (let i = 0; i < 12; i++) {
    await page.keyboard.press("Tab");
    expect(
      await dialog.evaluate((element) =>
        element.contains(document.activeElement),
      ),
    ).toBe(true);
  }
  await page.keyboard.press("Escape");
  await expect(dialog).not.toBeVisible();
  await expect(trigger).toBeFocused();
  await page.getByRole("button", { name: "Tickets", exact: true }).click();
  const evidence = page.getByRole("tab", { name: /^Evidence/ });
  await evidence.focus();
  await page.keyboard.press("ArrowRight");
  await expect(
    page.getByRole("tab", { name: "Trace", exact: true }),
  ).toHaveAttribute("aria-selected", "true");
});

test("mobile workspace fits the viewport and handles a rejected token", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/#token");
  await page
    .getByLabel("Workspace token")
    .fill("not-a-valid-token-but-long-enough");
  await page.getByRole("button", { name: "Connect workspace" }).click();
  await expect(page.getByRole("alert")).toContainText("valid workspace token");
  await page.getByLabel("Workspace token").fill(TOKEN);
  await page.getByRole("button", { name: "Connect workspace" }).click();
  await page.getByRole("button", { name: "Open navigation" }).click();
  await page.getByRole("button", { name: "How it works", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Bring the context." }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Open navigation" }).click();
  await page.getByRole("button", { name: "Tickets", exact: true }).click();
  await page.getByRole("button", { name: "New ticket" }).click();
  await page.getByLabel("Start with an example").selectOption("dev-04");
  await page
    .getByRole("button", { name: "Create ticket", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Investigate ticket", exact: true })
    .click();
  await expect(
    page.getByText("Resolution drafted", { exact: true }),
  ).toBeVisible();
  await page.getByRole("tab", { name: "Trace", exact: true }).click();
  await expect(page.locator(".trace-list")).toContainText(
    "get_account_status: ok",
  );
  await page.getByText("Tool input & result", { exact: true }).first().click();
  await expect(page.locator(".trace-list")).toContainText(
    '"account_id": "acct_active"',
  );
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "../docs/screenshots/mobile.png",
    fullPage: true,
    animations: "disabled",
  });
});

test("dashboard supports triage, notes, stale context and knowledge lifecycle", async ({
  page,
}) => {
  await page.goto("/#token");
  await page.getByLabel("Workspace token").fill(TOKEN);
  await page.getByRole("button", { name: "Connect workspace" }).click();
  await expect(
    page.getByRole("heading", { name: "Your support, in focus.", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "New ticket", exact: true }).click();
  await page.getByLabel("Start with an example").selectOption("dev-03");
  await page
    .getByRole("button", { name: "Create ticket", exact: true })
    .click();
  for (const [label, value] of [
    ["Priority", "urgent"],
    ["Assignee", "browser-agent"],
    ["Ticket status", "in_progress"],
  ]) {
    const field = page.getByLabel(label, { exact: true });
    await field.selectOption(value);
    await expect(field).toBeEnabled();
    await expect(field).toHaveValue(value);
  }
  await page
    .getByLabel("Internal note", { exact: true })
    .fill(
      "Reproduced with the customer payload; checking migration instructions.",
    );
  await page.getByRole("button", { name: "Add note", exact: true }).click();
  await expect(
    page.getByText(
      "Reproduced with the customer payload; checking migration instructions.",
      { exact: true },
    ),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Investigate ticket", exact: true })
    .click();
  await expect(
    page.getByText("Resolution drafted", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Edit context", exact: true }).click();
  const context = page.getByRole("dialog").filter({
    has: page.getByRole("heading", {
      name: "Edit ticket context",
      exact: true,
    }),
  });
  await context
    .getByRole("textbox", { name: "Ticket description", exact: true })
    .fill(
      "After migrating to v2, webhook signature verification fails. The customer confirmed that the old header is still configured.",
    );
  await context
    .getByRole("button", { name: "Save context", exact: true })
    .click();
  await expect(context).not.toBeVisible();
  await expect(
    page.getByRole("button", { name: "Approve draft", exact: true }),
  ).toBeDisabled();
  await page
    .getByRole("button", { name: "Investigate again", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Approve draft", exact: true }),
  ).toBeEnabled();
  await page
    .getByRole("button", { name: "Approve draft", exact: true })
    .click();
  await expect(page.getByText("Draft approved", { exact: true })).toBeVisible();
  await page
    .getByLabel("Ticket status", { exact: true })
    .selectOption("resolved");
  await expect(page.getByLabel("Ticket status", { exact: true })).toBeEnabled();
  await expect(page.getByLabel("Ticket status", { exact: true })).toHaveValue(
    "resolved",
  );
  await page.getByRole("button", { name: "Knowledge", exact: true }).click();
  await page.getByRole("button", { name: "Add document", exact: true }).click();
  const modal = page.getByRole("dialog").filter({
    has: page.getByRole("heading", { name: "Add document", exact: true }),
  });
  await modal
    .getByLabel("Document title", { exact: true })
    .fill("Browser orchid recovery guide");
  await modal
    .getByRole("textbox", { name: "Document content", exact: true })
    .fill(
      "To recover an orchid session in v2, open Settings and rotate the orchid session key. Retain the recovery reference for the support team.",
    );
  await modal
    .getByLabel("Document version", { exact: true })
    .selectOption("v2");
  await modal
    .getByLabel("Source path", { exact: true })
    .fill("internal/orchid-recovery.md");
  await modal
    .getByRole("button", { name: "Save document", exact: true })
    .click();
  await expect(modal).not.toBeVisible();
  const card = page.locator(".document-card").filter({
    has: page.getByRole("heading", {
      name: "Browser orchid recovery guide",
      exact: true,
    }),
  });
  await expect(card).toBeVisible();
  await page
    .getByLabel("Knowledge search", { exact: true })
    .fill("orchid recovery session key");
  await page
    .getByLabel("Knowledge version", { exact: true })
    .selectOption("v2");
  const search = page.getByRole("button", {
    name: "Search knowledge",
    exact: true,
  });
  const result = page
    .locator(".evidence-card")
    .filter({ hasText: "Browser orchid recovery guide" });
  await search.click();
  await expect(result).toBeVisible();
  await card.getByRole("button", { name: "Archive", exact: true }).click();
  await expect(
    card.getByRole("button", { name: "Restore", exact: true }),
  ).toBeVisible();
  await search.click();
  await expect(
    page.getByRole("heading", { name: "Search results", exact: true }),
  ).toBeVisible();
  await expect(result).toHaveCount(0);
  await card.getByRole("button", { name: "Restore", exact: true }).click();
  await expect(
    card.getByRole("button", { name: "Archive", exact: true }),
  ).toBeVisible();
  await search.click();
  await expect(result).toBeVisible();
  await page.screenshot({
    path: "../docs/screenshots/knowledge.png",
    fullPage: true,
    animations: "disabled",
  });
  await page.getByRole("button", { name: "Activity", exact: true }).click();
  await expect(page.locator(".activity-list")).toBeVisible();
  await page.getByRole("button", { name: "Workspace", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Readiness checks", exact: true }),
  ).toBeVisible();
  await expect(page.getByText("browser-agent", { exact: true })).toBeVisible();
});

test("command palette jumps between views and opens the composer", async ({
  page,
}) => {
  await page.goto("/#token");
  await page.getByLabel("Workspace token").fill(TOKEN);
  await page.getByRole("button", { name: "Connect workspace" }).click();
  await page.keyboard.press("ControlOrMeta+k");
  await page.getByPlaceholder("Type a command or search…").fill("agent");
  await page.keyboard.press("Enter");
  await expect(
    page.getByRole("heading", { name: "Agent runs", level: 1 }),
  ).toBeVisible();
  await page.getByRole("button", { name: /Search or jump to/ }).click();
  await page.getByRole("option", { name: "New ticket" }).click();
  await expect(
    page.getByRole("heading", { name: "New support ticket" }),
  ).toBeVisible();
});

test("sign up with GitHub: pick a repository, save the token, open the dashboard", async ({
  page,
}) => {
  await page.route("**/api/auth/config", (route) =>
    route.fulfill({ json: { github: true } }),
  );
  const session = {
    login: "octocat",
    can_regenerate: false,
    workspaces: [] as object[],
  };
  await page.route("**/api/auth/session", (route) =>
    route.fulfill({ json: session }),
  );
  await page.route("**/api/auth/repos?page=1", (route) =>
    route.fulfill({
      json: {
        items: [
          { id: 1, full_name: "team/app", private: true, description: "App" },
          { id: 2, full_name: "team/site", private: false, description: null },
        ],
        has_more: false,
      },
    }),
  );
  await page.route("**/api/auth/workspaces", async (route) => {
    const { full_name } = route.request().postDataJSON();
    session.workspaces.push({
      workspace_id: "demo",
      repository: full_name,
      role: "admin",
    });
    await route.fulfill({
      status: 201,
      json: {
        token: TOKEN,
        repository: full_name,
        role: "admin",
        regenerated: false,
      },
    });
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Sign up", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Choose a repository" }),
  ).toBeVisible();
  await expect(page.getByText("Verified as @octocat")).toBeVisible();
  await page.getByLabel("Filter repositories").fill("app");
  await expect(
    page.getByRole("button", { name: "Select team/site" }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "Select team/app" }).click();
  await expect(
    page.getByRole("heading", { name: "Workspace ready" }),
  ).toBeVisible();
  await expect(page.getByLabel("Workspace token value")).toHaveText(TOKEN);
  await page.getByRole("button", { name: "Continue to dashboard" }).click();
  await expect(
    page.getByRole("heading", { name: "Your support, in focus.", exact: true }),
  ).toBeVisible();
});

test("sign in lists workspaces and checks the token; regenerating needs re-authorization", async ({
  page,
}) => {
  await page.route("**/api/auth/config", (route) =>
    route.fulfill({ json: { github: true } }),
  );
  const session = {
    login: "octocat",
    can_regenerate: false,
    workspaces: [
      { workspace_id: "demo", repository: "team/app", role: "admin" },
      { workspace_id: "gh-2", repository: "team/site", role: "agent" },
    ],
  };
  await page.route("**/api/auth/session", (route) =>
    route.fulfill({ json: session }),
  );
  const verified: { token: string; workspace_id: string }[] = [];
  await page.route("**/api/auth/verify", (route) => {
    const body = route.request().postDataJSON();
    verified.push(body);
    return body.token === TOKEN && body.workspace_id === "demo"
      ? route.fulfill({ json: { workspace_id: "demo" } })
      : route.fulfill({
          status: 403,
          json: { detail: "This workspace token does not belong to @octocat" },
        });
  });
  let regenerated = 0;
  await page.route("**/api/auth/workspaces/demo/regenerate", (route) => {
    regenerated += 1;
    return route.fulfill({
      status: 201,
      json: {
        token: TOKEN,
        repository: "team/app",
        role: "admin",
        regenerated: true,
      },
    });
  });

  await page.goto("/#signin");
  await expect(
    page.getByRole("heading", { name: "Choose your workspace" }),
  ).toBeVisible();
  await expect(page.getByRole("radio")).toHaveCount(2);
  await page.getByRole("radio", { name: /team\/site/ }).check();
  await page.getByLabel("Workspace token").fill(TOKEN);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("does not belong");
  expect(verified.at(-1)?.workspace_id).toBe("gh-2");
  await expect(
    page.getByRole("link", { name: "Forgot your token?" }),
  ).toHaveAttribute("href", "/api/auth/github/start?intent=regenerate");

  // Without a fresh authorization the regenerate page only offers re-authorization.
  await page.goto("/#regenerate");
  await expect(
    page.getByRole("link", { name: "Re-authorize with GitHub" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: /Regenerate token for/ }),
  ).toHaveCount(0);

  session.can_regenerate = true;
  await page.reload();
  await page
    .getByRole("button", { name: "Regenerate token for team/app" })
    .click();
  await expect(
    page.getByRole("heading", { name: "Token regenerated" }),
  ).toBeVisible();
  expect(regenerated).toBe(1);
  await page.getByRole("button", { name: "Continue to dashboard" }).click();
  await expect(
    page.getByRole("heading", { name: "Your support, in focus.", exact: true }),
  ).toBeVisible();
  await page.keyboard.press("ControlOrMeta+k");
  await page.getByRole("option", { name: "Disconnect" }).click();
  await expect(
    page.getByRole("heading", { name: /backed by evidence/ }),
  ).toBeVisible();
});

test("admins invite teammates and see team metrics", async ({ page }) => {
  await page.goto("/#token");
  await page.getByLabel("Workspace token").fill(TOKEN);
  await page.getByRole("button", { name: "Connect workspace" }).click();
  await expect(page.getByRole("region", { name: "Key numbers" })).toContainText(
    "Approval rate",
  );
  await page.getByRole("button", { name: "Workspace", exact: true }).click();
  await page.getByLabel("GitHub username").fill("@octo-teammate");
  await page.getByLabel("Invite role").selectOption("admin");
  await page.getByRole("button", { name: "Invite", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("@octo-teammate");
  const pending = page.getByLabel("Pending invitations");
  await expect(pending).toContainText("@octo-teammate");
  await expect(pending).toContainText("Admin");
  await page
    .getByRole("button", { name: "Revoke invitation for octo-teammate" })
    .click();
  await expect(page.getByText("No pending invitations.")).toBeVisible();
});

test("session survives reload; remember-me survives new tabs; disconnect clears it", async ({
  page,
  context,
}) => {
  const overview = (p: typeof page) =>
    p.getByRole("heading", { name: "Your support, in focus.", exact: true });
  await page.goto("/#token");
  await page.getByLabel("Workspace token").fill(TOKEN);
  await page.getByRole("button", { name: "Connect workspace" }).click();
  await expect(overview(page)).toBeVisible();
  await page.reload();
  await expect(overview(page)).toBeVisible(); // Same tab: still signed in.
  const fresh = await context.newPage();
  await fresh.goto("/");
  await expect(
    fresh.getByRole("heading", { name: /backed by evidence/ }),
  ).toBeVisible();
  await fresh.close();

  await page.keyboard.press("ControlOrMeta+k");
  await page.getByRole("option", { name: "Disconnect" }).click();
  await page.goto("/#token");
  await page.getByLabel("Keep me signed in on this device").check();
  await page.getByLabel("Workspace token").fill(TOKEN);
  await page.getByRole("button", { name: "Connect workspace" }).click();
  await expect(overview(page)).toBeVisible();
  const remembered = await context.newPage();
  await remembered.goto("/");
  await expect(overview(remembered)).toBeVisible(); // Remembered on this device.
  await remembered.keyboard.press("ControlOrMeta+k");
  await remembered.getByRole("option", { name: "Disconnect" }).click();
  await remembered.reload();
  await expect(
    remembered.getByRole("heading", { name: /backed by evidence/ }),
  ).toBeVisible();
});
