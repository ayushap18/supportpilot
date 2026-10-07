import { expect, test, type Page } from "@playwright/test";
const TOKEN = "browser-test-token-at-least-24-characters";
async function connect(page: Page, token = TOKEN) {
  // Switching identities: drop any session this tab restored from a previous sign-in.
  await page.goto("/");
  await page.evaluate(() => {
    sessionStorage.clear();
    localStorage.clear();
  });
  await page.goto("about:blank");
  await page.goto("/#token");
  await page.getByLabel("Workspace token").fill(token);
  await page.getByRole("button", { name: "Connect workspace" }).click();
  await expect(
    page.getByRole("heading", { name: "Your support, in focus.", exact: true }),
  ).toBeVisible();
}
test("engineering workspace displays configuration, queues local work, and preserves unknown cost", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.setViewportSize({ width: 1440, height: 1000 });
  await connect(page);
  await page.getByRole("button", { name: "Repositories", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Repository intelligence" }),
  ).toBeVisible();
  await expect(page.getByText("GitHub setup", { exact: true })).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Your code belongs here" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Agent runs", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Antigravity CLI", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Queue agent run" }).click();
  await page.getByLabel("Agent provider").selectOption("codex");
  const task = `Inspect repository tests without editing files ${Date.now()}`;
  await page.getByLabel("Agent task").fill(task);
  await page.getByRole("button", { name: "Queue task", exact: true }).click();
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await expect(
    page.getByText("No runner is online for this workspace"),
  ).toBeVisible();
  await expect(page.getByText("No runner online")).toBeVisible();
  await expect(
    page.locator(".engineering-command").filter({ hasText: "--push" }),
  ).toContainText("watch --repository");
  await expect(
    page
      .locator(".engineering-command")
      .filter({ hasText: 'login --repository "$PWD"' }),
  ).toContainText("watch --repository");
  for (const command of await page.locator(".engineering-command").all())
    await expect(command).not.toContainText(TOKEN);
  await expect(page.getByText("Cost: unknown", { exact: true })).toBeVisible();
  // An online runner that cannot take the run is named with the reason.
  await page.request.post("/api/agents/runners/heartbeat", {
    headers: { Authorization: `Bearer ${TOKEN}` },
    data: {
      runner_id: "other-box",
      providers: ["claude_code"],
      allow_edits: false,
    },
  });
  await expect(
    page.getByText("No online runner can take this run"),
  ).toBeVisible();
  await expect(
    page.getByText(/other-box does not have the codex CLI installed/),
  ).toBeVisible();
  // A runner heartbeat flips the panel through polling, without a manual refresh.
  await page.request.post("/api/agents/runners/heartbeat", {
    headers: { Authorization: `Bearer ${TOKEN}` },
    data: { runner_id: "ci-laptop", providers: ["codex"], allow_edits: false },
  });
  await expect(page.getByText("Local runner online")).toBeVisible();
  await expect(
    page.getByText("Waiting for ci-laptop to pick this up…"),
  ).toBeVisible();
  await page.screenshot({
    path: "../docs/screenshots/agent-runs.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "Cancel run", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Cancel run", exact: true }),
  ).not.toBeVisible();
  await expect(
    page.locator(".engineering-run-list button").filter({ hasText: task }),
  ).toContainText("cancelled");
  await connect(page);
  await page.getByRole("button", { name: "Agent runs", exact: true }).click();
  await expect(
    page.locator(".engineering-run-list button").filter({ hasText: task }),
  ).toContainText("cancelled");
  expect(errors).toEqual([]);
});
test("agent role can inspect engineering views without managing execution", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await connect(page, "browser-agent-token-at-least-24-characters");
  await page.getByRole("button", { name: "Open navigation" }).click();
  await page.getByRole("button", { name: "Agent runs", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Queue agent run" }),
  ).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "Cancel run", exact: true }),
  ).toHaveCount(0);
  await page.screenshot({
    path: "../docs/screenshots/agents-mobile.png",
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});

test("repository snapshot supports diff review, docs import, and explicit issue publishing", async ({
  page,
  request,
}) => {
  const created = await request.post("/api/tickets", {
    headers: { Authorization: `Bearer ${TOKEN}` },
    data: {
      subject: "Repository issue publishing test",
      description:
        "Investigate the webhook validation failure after changing the request header.",
      product_version: "v2",
      account_id: null,
      log: "",
    },
  });
  expect(created.ok()).toBeTruthy();
  const ticket = await created.json();
  const repo = {
    id: "fixture-repository",
    full_name: "example/support-demo",
    default_branch: "main",
    html_url: "https://github.com/example/support-demo",
    description: "Browser test fixture repository",
    private: true,
  };
  const sha = "a".repeat(40);
  let issueWrites = 0,
    imports = 0;
  const snapshot = {
    repo,
    commits: [
      {
        sha,
        message: "Fix webhook signature handling (test fixture)",
        author: "demo-contributor",
        date: "2026-10-04T10:00:00Z",
        html_url: `https://github.com/example/support-demo/commit/${sha}`,
      },
    ],
    issues: [],
    contributors: [
      {
        login: "demo-contributor",
        contributions: 12,
        html_url: "https://github.com/demo-contributor",
      },
    ],
    docs: [{ path: "docs/webhooks.md", size: 1200, sha }],
    files: [{ path: "README.md" }],
    activity: [
      {
        id: "1",
        actor: "demo-contributor",
        type: "PushEvent",
        summary: "Push (test fixture)",
        created_at: "2026-10-04T10:00:00Z",
      },
    ],
    analysis: {
      summary: "Browser test fixture inventory",
      has_readme: true,
      has_tests: true,
      has_ci: true,
      has_docs: true,
    },
    limits: { files_truncated: false },
  };
  await page.route("**/api/github/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    let data: unknown;
    if (path.endsWith("/status"))
      data = {
        configured: true,
        connected: true,
        login: "browser-test-fixture",
        scopes: ["repo"],
        missing: [],
      };
    else if (path.endsWith("/repositories")) data = { items: [repo] };
    else if (path.endsWith(`/commits/${sha}`))
      data = {
        sha,
        message: "Fix webhook signature handling",
        stats: { additions: 1, deletions: 1, total: 2 },
        files: [
          {
            filename: "src/webhooks.ts",
            status: "modified",
            additions: 1,
            deletions: 1,
            patch: "-oldHeader\n+newHeader",
            patch_available: true,
            patch_truncated: false,
          },
        ],
        limits: { files_truncated: false, upstream_may_have_more: false },
      };
    else if (path.endsWith("/import-docs")) {
      imports++;
      data = {
        imported: [{ path: "docs/webhooks.md", document_id: "fixture-doc" }],
        skipped: [],
        errors: [],
      };
    } else if (path.endsWith("/issues")) {
      issueWrites++;
      expect(route.request().postDataJSON()).toEqual({ ticket_id: ticket.id });
      data = {
        number: 42,
        html_url: "https://github.com/example/support-demo/issues/42",
      };
    } else data = snapshot;
    await route.fulfill({ json: data });
  });
  await connect(page);
  await page.getByRole("button", { name: "Repositories", exact: true }).click();
  await page.getByLabel("Selected repository").selectOption(repo.id);
  await expect(page.getByText("CI workflows", { exact: true })).toBeVisible();
  await page
    .getByRole("button", { name: "Sync repository", exact: true })
    .click();
  await expect(page.getByText("Repository snapshot updated.")).toBeVisible();
  await page.screenshot({
    path: "../docs/screenshots/repositories.png",
    fullPage: true,
  });
  await page.getByRole("tab", { name: "Commits", exact: true }).click();
  await page.getByRole("button", { name: "Inspect aaaaaaa" }).click();
  await expect(page.getByRole("dialog")).toContainText("+newHeader");
  await page.keyboard.press("Escape");
  await page.getByRole("tab", { name: "Activity", exact: true }).click();
  await expect(page.getByRole("tabpanel")).toContainText("Push (test fixture)");
  await page.getByRole("tab", { name: "Documentation", exact: true }).click();
  await page
    .getByRole("button", { name: "Import docs into knowledge" })
    .click();
  await expect(
    page.getByText("Knowledge import: 1 imported, 0 skipped, 0 errors."),
  ).toBeVisible();
  expect(imports).toBe(1);
  await page.getByRole("tab", { name: "Issues", exact: true }).click();
  await page.getByRole("button", { name: "Choose ticket for issue" }).click();
  await page.getByLabel("Ticket to publish").selectOption(ticket.id);
  expect(issueWrites).toBe(0);
  await expect(
    page.getByText(
      "Publish to example/support-demo. This sends ticket content to GitHub.",
    ),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Create GitHub issue", exact: true })
    .click();
  await expect(
    page.getByText("GitHub issue #42 created. Sync to refresh the issue list."),
  ).toBeVisible();
  expect(issueWrites).toBe(1);
});

test("reported agent results expose usage and reviewable GitHub artifacts", async ({
  page,
  request,
}) => {
  const headers = { Authorization: `Bearer ${TOKEN}` };
  const task = `Review an external agent report ${Date.now()}`;
  const created = await request.post("/api/agents/runs", {
    headers,
    data: { provider: "custom", task },
  });
  expect(created.status()).toBe(201);
  const run = await created.json();
  const claim = await request.post(`/api/agents/runs/${run.id}/claim`, {
    headers,
    data: { runner_id: "browser-fixture" },
  });
  const { lease } = await claim.json();
  const completed = await request.post(`/api/agents/runs/${run.id}/complete`, {
    headers,
    data: {
      lease,
      exit_code: 0,
      result:
        "Fixture report: reviewed the example patch; human review remains required.",
      usage: { input_tokens: 120, output_tokens: 30, cost_usd: 0.0123 },
      artifacts: [
        {
          kind: "pull_request",
          label: "Review example pull request",
          url: "https://github.com/example/support-demo/pull/12",
        },
      ],
    },
  });
  expect(completed.status()).toBe(200);
  await connect(page);
  await page.getByRole("button", { name: "Agent runs", exact: true }).click();
  await page
    .locator(".engineering-run-list button")
    .filter({ hasText: task })
    .click();
  await expect(page.getByText("Input: 120", { exact: true })).toBeVisible();
  await expect(page.getByText("Cost: $0.0123", { exact: true })).toBeVisible();
  await expect(
    page.getByRole("link", {
      name: "Review example pull request",
      exact: true,
    }),
  ).toHaveAttribute("href", "https://github.com/example/support-demo/pull/12");
  await expect(page.locator(".engineering-pre")).toContainText(
    "human review remains required",
  );
});

test("mission control: pipeline, review desk with fix verification, and run timeline", async ({
  page,
}) => {
  const auth = { Authorization: `Bearer ${TOKEN}` };
  const created = await page.request.post("/api/agents/runs", {
    headers: auth,
    data: { provider: "codex", task: `Mission check ${Date.now()}` },
  });
  const run = await created.json();
  const { lease } = await (
    await page.request.post(`/api/agents/runs/${run.id}/claim`, {
      headers: auth,
      data: { runner_id: "e2e" },
    })
  ).json();
  await page.request.post(`/api/agents/runs/${run.id}/complete`, {
    headers: auth,
    data: {
      lease,
      result: "Found the bug in retry.py",
      exit_code: 0,
      usage: { input_tokens: 10, output_tokens: 3 },
    },
  });

  await connect(page);
  await page
    .getByRole("button", { name: "Mission control", exact: true })
    .click();
  const pipeline = page.getByRole("region", { name: "Agent pipeline" });
  await expect(pipeline).toContainText("No agent is running");
  await expect(
    pipeline.locator(".stage-awaiting_review strong"),
  ).not.toHaveText("0");
  const card = page.locator(".mission-review").filter({ hasText: run.task });
  await card.getByRole("button", { name: "Review", exact: true }).click();
  await card
    .getByPlaceholder("e.g. test_retry FAILED")
    .fill("test_retry FAILED");
  await card.getByPlaceholder("e.g. 42 passed").fill("test_retry passed");
  await card.getByLabel("Customer confirmed the fix").check();
  await card.getByRole("button", { name: "Accept" }).click();
  await expect(card).toHaveCount(0);
  await expect(pipeline.locator(".stage-accepted strong")).not.toHaveText("0");

  await page.getByRole("button", { name: "Agent runs", exact: true }).click();
  await page.getByLabel("Search runs").fill(run.task);
  await page.getByRole("button", { name: new RegExp(run.task) }).click();
  const timeline = page.getByRole("list", { name: "Run timeline" });
  await expect(timeline).toContainText("Reviewed (accepted)");
  await expect(page.getByText("customer confirmed")).toBeVisible();
  await expect(page.getByText("Tests before: test_retry FAILED")).toBeVisible();
});
