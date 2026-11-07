import { test, expect } from "@playwright/test";

// Issue #7: the chat panel against the real backend with a scripted provider
// (tests/chat_fake_provider.py) and an open merge-lab session. No network leaves the machine.
test.use({ baseURL: "http://127.0.0.1:8767" });

const panel = (page) => page.getByTestId("chat-panel");

async function ask(page, text) {
  const answers = panel(page).getByTestId("chat-answer");
  const before = await answers.count();
  await panel(page).getByLabel("Message").fill(text);
  await panel(page).getByRole("button", { name: "Send" }).click();
  const answer = answers.nth(before);
  await expect(answer).toBeVisible();
  return answer;
}

test("chat is off until configured, then streams, calls tools, proposes, fails and stops", async ({ page, context }, testInfo) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Graph acceptance project" })).toBeVisible();

  // Off by default: the panel opens with Ctrl+J and points to Settings.
  await page.keyboard.press("Control+j");
  await expect(panel(page).getByTestId("chat-setup")).toContainText("Chat is off");
  await panel(page).getByRole("button", { name: "Set up the AI provider" }).click();
  await expect(page.getByRole("tab", { name: "AI provider" })).toHaveAttribute("aria-selected", "true");
  await page.getByRole("switch", { name: "Turn on the chat" }).click();
  await page.getByLabel("Provider", { exact: true }).selectOption("local");
  await expect(page.getByLabel("Base URL", { exact: true })).toHaveValue("http://localhost:11434/v1");
  await page.getByLabel("Model", { exact: true }).fill("fake-model");
  await page.getByRole("button", { name: "Test connection" }).click();
  await expect(page.getByText("Connected. fake-model is available.")).toBeVisible();
  await expect(page.getByTestId("ai-status")).toHaveText("The chat is ready.");
  expect(await page.getByLabel(/API key/).inputValue()).toBe("");

  // Reopen the chat from the title bar: the context chips show the view and the merge session.
  await page.getByRole("button", { name: "Chat", exact: true }).click();
  await expect(panel(page)).toBeHidden();
  await page.getByRole("button", { name: "Chat", exact: true }).click();
  const chips = panel(page).getByRole("list", { name: "What the chat can see" });
  await expect(chips).toContainText("View: Settings");
  await expect(chips).toContainText("Merge: Chat merge");
  await chips.getByRole("button", { name: "Remove Settings from the chat context" }).click();
  await expect(chips).not.toContainText("View: Settings");

  // Streaming: the answer grows over several polls, then ends.
  let answer = await ask(page, "hello");
  await expect(answer).toContainText("Hello from the fake provider. Ask me to search the project.");
  await expect(answer.locator("strong")).toHaveText("fake");

  // A tool call through the shared registry, and an object link into the Inspector.
  answer = await ask(page, "search net sales");
  await expect(answer.getByTestId("chat-tool")).toContainText("Searched objects");
  const link = answer.getByRole("button", { name: "Net Sales", exact: true });
  await expect(link).toBeVisible();
  await link.click();
  await expect(page.locator(".breadcrumb-view")).toHaveText("Inspector");
  await expect(page.locator("main")).toContainText("Net Sales");
  await expect(chips).toContainText("Selected: Net Sales");
  await expect(chips).toContainText("View: Inspector");

  // A proposal goes to the open merge session as a normal proposal; the chat cannot accept it.
  await chips.getByRole("button", { name: "Remove Net Sales from the chat context" }).click();
  answer = await ask(page, "propose a description");
  const proposal = answer.getByTestId("chat-proposal");
  await expect(proposal).toContainText("Proposal: Margin");
  await expect(proposal).toContainText("Nothing changes until you accept it in Merge models.");
  const session = await (await page.request.get("/api/devcenter/session")).json();
  expect(session.proposals.open.map((item) => item.target_id)).toContain("measure:Sales/Margin");
  answer = await ask(page, "accept it");
  await expect(answer).toContainText("I cannot accept proposals.");
  await expect(answer.getByTestId("chat-tool")).toHaveClass(/is-failed/);

  // The error state.
  answer = await ask(page, "fail please");
  await expect(answer.getByRole("alert")).toContainText("The provider refused the API key");

  // Stop a running answer.
  answer = await ask(page, "slow");
  await panel(page).getByRole("button", { name: "Stop" }).click();
  await expect(answer).toContainText("Stopped.");
  await expect(panel(page).getByRole("button", { name: "Send" })).toBeVisible();

  // Copy as markdown.
  await panel(page).getByRole("button", { name: "Copy as Markdown" }).click();
  const copied = await page.evaluate(() => navigator.clipboard.readText());
  expect(copied).toContain("**You:** hello");
  expect(copied).toContain("> Proposal for Margin");

  await page.screenshot({ path: testInfo.outputPath("chat-panel.png") });

  // The proposal is a normal proposal card in Merge models.
  await proposal.getByRole("button", { name: "Review in Merge models" }).click();
  await expect(page.locator(".breadcrumb-view")).toHaveText("Merge models");
  await page.screenshot({ path: testInfo.outputPath("chat-merge.png") });

  // Ctrl+J closes it again; the page never scrolls sideways with the panel open.
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.keyboard.press("Control+j");
  await expect(panel(page)).toBeHidden();
});
