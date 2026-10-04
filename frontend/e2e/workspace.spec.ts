import { expect, test } from "@playwright/test";

const TOKEN = "browser-test-token-at-least-24-characters";

test("investigate a migration ticket, inspect evidence, and approve the draft", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
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
  await page.getByRole("button", { name: "Trace", exact: true }).click();
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
  expect(errors).toEqual([]);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: "../docs/screenshots/workspace.png",
    fullPage: true,
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
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "../docs/screenshots/mobile.png",
    fullPage: true,
  });
});
