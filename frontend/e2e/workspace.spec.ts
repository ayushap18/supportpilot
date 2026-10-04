import { expect, test } from "@playwright/test";

const TOKEN = "browser-test-token-at-least-24-characters";

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
    page.getByRole("heading", { name: "Resolve with evidence." }),
  ).toBeVisible();
  await page.getByLabel("Workspace token").fill(TOKEN);
  await page.getByRole("button", { name: "Connect workspace" }).click();
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
  await page.goto("/");
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
  await page.goto("/");
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
  await page.goto("/");
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
  await page.getByRole("button", { name: "Ticket inbox", exact: true }).click();
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
