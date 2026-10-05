import { expect, test } from "@playwright/test";

const TOKEN = "browser-test-token-at-least-24-characters";

test("knowledge file upload validates type and previews text before indexed saving", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByLabel("Workspace token").fill(TOKEN);
  await page
    .getByRole("button", { name: "Connect workspace", exact: true })
    .click();
  await page.getByRole("button", { name: "Knowledge", exact: true }).click();
  const file = page.getByLabel("Upload knowledge file");
  await file.setInputFiles({
    name: "unsupported.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("Not an accepted document"),
  });
  await expect(page.getByRole("alert")).toContainText("Choose a Markdown");
  const title = `upload-runbook-${Date.now()}`;
  const content =
    "For an orchid integration reset, verify the delivery endpoint and rotate the callback credential through Settings.";
  await file.setInputFiles({
    name: title + ".md",
    mimeType: "text/markdown",
    buffer: Buffer.from(content),
  });
  const dialog = page.getByRole("dialog");
  await expect(
    dialog.getByRole("textbox", { name: "Document title", exact: true }),
  ).toHaveValue(title);
  await expect(
    dialog.getByRole("textbox", { name: "Document content", exact: true }),
  ).toHaveValue(content);
  await dialog
    .getByRole("button", { name: "Save document", exact: true })
    .click();
  await expect(dialog).not.toBeVisible();
  await expect(
    page.getByRole("heading", { name: title, exact: true }),
  ).toBeVisible();
  await page
    .getByLabel("Knowledge search")
    .fill("orchid integration reset delivery endpoint");
  await page
    .getByRole("button", { name: "Search knowledge", exact: true })
    .click();
  await expect(
    page.locator(".evidence-card").filter({ hasText: title }),
  ).toBeVisible();
});
