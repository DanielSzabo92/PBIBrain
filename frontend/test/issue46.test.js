import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const SRC = fileURLToPath(new URL("../src/", import.meta.url));

test("Issue #46: Motion token scale, keyframes cleanup, and comment reconciliation", async () => {
  const themeCss = await readFile(path.join(SRC, "theme.css"), "utf8");
  const appCss = await readFile(path.join(SRC, "app.css"), "utf8");

  // Motion token scale in theme.css
  assert.ok(themeCss.includes("--dur-press: 90ms;"), "theme.css defines --dur-press");
  assert.ok(themeCss.includes("--dur-fast: 120ms;"), "theme.css defines --dur-fast");
  assert.ok(themeCss.includes("--dur-flash: 150ms;"), "theme.css defines --dur-flash (150ms tint flash)");
  assert.ok(themeCss.includes("--dur: 180ms;"), "theme.css defines --dur");
  assert.ok(themeCss.includes("--dur-enter: 180ms;"), "theme.css defines --dur-enter (180ms row enter)");
  assert.ok(themeCss.includes("--dur-exit: 180ms;"), "theme.css defines --dur-exit (180ms row exit)");
  assert.ok(themeCss.includes("--dur-pane: 240ms;"), "theme.css defines --dur-pane");
  assert.ok(themeCss.includes("--dur-slow: 280ms;"), "theme.css defines --dur-slow");
  assert.ok(themeCss.includes("--dur-fit: 320ms;"), "theme.css defines --dur-fit");

  // Comment reconciliation
  assert.ok(
    themeCss.includes("bounded progress indicators run only while active") ||
    !themeCss.includes(", no loops."),
    "theme.css reconciles loop comment to permit intentional progress indicators"
  );

  // Unused shimmer removed
  assert.ok(!appCss.includes("@keyframes shimmer"), "Unused shimmer keyframe removed from app.css");

  // New keyframes for microinteractions
  assert.ok(appCss.includes("@keyframes count-pop"), "app.css defines @keyframes count-pop");
  assert.ok(appCss.includes("@keyframes node-enter"), "app.css defines @keyframes node-enter");
  assert.ok(appCss.includes("@keyframes row-enter"), "app.css defines @keyframes row-enter");
});

test("Issue #46: List row enter and exit animation with tokenized durations", async () => {
  const appCss = await readFile(path.join(SRC, "app.css"), "utf8");
  const appJsx = await readFile(path.join(SRC, "App.jsx"), "utf8");

  // .review-item animations
  assert.ok(appCss.includes("row-enter var(--dur-enter)"), "review-item has row-enter animation");
  assert.ok(appCss.includes("var(--dur-exit)"), "review-item transition uses --dur-exit");
  assert.ok(appCss.includes(".review-item.is-exiting"), "review-item defines .is-exiting exit state");

  // .object-review-item animations in Inspector
  assert.ok(appCss.includes(".object-review-item"), "app.css styles .object-review-item");
  assert.ok(appCss.includes(".object-review-item.is-exiting"), "app.css defines .object-review-item.is-exiting");

  // Exit animation logic in ReviewItem and CandidateActions
  assert.ok(appJsx.includes("setExiting(true)"), "ReviewItem activates exit animation");
  assert.ok(appJsx.includes("prefers-reduced-motion"), "Exit animation delay respects reduced motion");
});

test("Issue #46: Mutated rows and cells tint flash with --dur-flash", async () => {
  const compareCss = await readFile(path.join(SRC, "devcenter/components/compare.css"), "utf8");
  const compareGrid = await readFile(path.join(SRC, "devcenter/components/CompareGrid.jsx"), "utf8");
  const rowDetail = await readFile(path.join(SRC, "devcenter/components/CompareRowDetail.jsx"), "utf8");

  // compare.css uses var(--dur-flash) for row-saved-flash
  assert.ok(compareCss.includes("row-saved-flash var(--dur-flash)"), "compare.css uses --dur-flash for saved flash");
  assert.ok(compareCss.includes(".dc-mc-saved"), "compare.css defines .dc-mc-saved");
  assert.ok(compareCss.includes("fade-in var(--dur-flash)"), "dc-mc-saved has fade-in transition");

  // CompareGrid triggerRowFlash uses 150ms timeout
  assert.ok(compareGrid.includes("150"), "CompareGrid triggerRowFlash sets 150ms flash duration");

  // CompareRowDetail triggers saved flash
  assert.ok(rowDetail.includes("savedFlash"), "CompareRowDetail maintains savedFlash state");
});

test("Issue #46: Badges and count pills count tween and smooth transitions", async () => {
  const appCss = await readFile(path.join(SRC, "app.css"), "utf8");
  const devcenterCss = await readFile(path.join(SRC, "devcenter/devcenter.css"), "utf8");
  const tabsJsx = await readFile(path.join(SRC, "components/ui/tabs.jsx"), "utf8");

  // Count transitions and pop animation
  assert.ok(appCss.includes(".count-pill") && appCss.includes("count-pop"), "count-pill has count-pop animation");
  assert.ok(appCss.includes(".nav-count") && appCss.includes("count-pop"), "nav-count has count-pop animation");
  assert.ok(devcenterCss.includes(".ui-tabs-count") && devcenterCss.includes("count-pop"), "ui-tabs-count has count-pop animation");

  // Key trigger on count changes in tabs
  assert.ok(tabsJsx.includes("key={count}"), "TabsTrigger re-triggers count-pop when count changes");
});

test("Issue #46: Details pane open smooth fitView and group expand reflow", async () => {
  const appCss = await readFile(path.join(SRC, "app.css"), "utf8");
  const graphJsx = await readFile(path.join(SRC, "components/GraphView.jsx"), "utf8");

  // Canvas card smooth margin transition
  assert.ok(appCss.includes(".graph-canvas-card") && appCss.includes("margin-right var(--dur-fit)"), "graph-canvas-card has smooth margin transition");

  // Flow node enter animation
  assert.ok(appCss.includes(".flow-node") && appCss.includes("node-enter var(--dur-enter)"), "flow-node animates enter on group expand");

  // GraphView re-fits on pane open and close
  assert.ok(graphJsx.includes("wasDocked"), "GraphView tracks wasDocked to re-fit on open and close");
  assert.ok(graphJsx.includes("canvasApi.current?.fit()"), "GraphView re-fits view when group is toggled");
});

test("Issue #46: Apply progress dialog stable layout and smooth phase transitions", async () => {
  const applyCss = await readFile(path.join(SRC, "devcenter/screens/plan/apply.css"), "utf8");

  // Stable minimum height to prevent height jumping
  assert.ok(applyCss.includes(".dc-apply-dialog {") && applyCss.includes("min-height: 440px"), "dc-apply-dialog sets fixed min-height");
  assert.ok(applyCss.includes(".dc-apply-dialog .ui-dialog-body {") && applyCss.includes("min-height: 280px"), "ui-dialog-body sets fixed min-height");
  assert.ok(applyCss.includes("transition: min-height var(--dur-pane)"), "ui-dialog-body smoothly transitions min-height");

  // Phase entrance animation
  assert.ok(applyCss.includes(".dc-apply-progress,"), "apply.css defines phase entrance animations");
});

test("Issue #46: Stronger hover tokens and interactive feedback on type chips and lineage rows", async () => {
  const themeCss = await readFile(path.join(SRC, "theme.css"), "utf8");
  const appCss = await readFile(path.join(SRC, "app.css"), "utf8");

  // Stronger surface-hover tokens
  assert.ok(themeCss.includes("--surface-hover: #222226;"), "theme.css dark mode has stronger surface-hover");
  assert.ok(themeCss.includes("--surface-hover: #ebebe7;"), "theme.css light mode has stronger surface-hover");

  // Type chips hover feedback
  assert.ok(appCss.includes(".type-strip-item:hover"), "app.css defines type-strip-item:hover");
  assert.ok(appCss.includes("translateY(-1px)"), "type-strip-item has subtle hover lift");

  // Lineage and relationship rows hover feedback
  assert.ok(appCss.includes(".relationship-row:hover"), "relationship-row has visible hover state");
  assert.ok(appCss.includes(".detail-related:hover"), "detail-related has visible hover state");
});

test("Issue #46: Strict prefers-reduced-motion safety across all motion layers", async () => {
  const appCss = await readFile(path.join(SRC, "app.css"), "utf8");
  const compareCss = await readFile(path.join(SRC, "devcenter/components/compare.css"), "utf8");
  const applyCss = await readFile(path.join(SRC, "devcenter/screens/plan/apply.css"), "utf8");
  const devcenterCss = await readFile(path.join(SRC, "devcenter/devcenter.css"), "utf8");

  // app.css reduced motion
  assert.ok(appCss.includes(".spin { animation: none !important; }"), "Spinners stop under reduced motion");
  assert.ok(appCss.includes(".statusbar-progress::after { animation: none !important;"), "Progress bar stops under reduced motion");

  // compare.css reduced motion
  assert.ok(compareCss.includes("@media (prefers-reduced-motion: reduce)"), "compare.css disables animations under reduced motion");

  // apply.css reduced motion
  assert.ok(applyCss.includes("@media (prefers-reduced-motion: reduce)"), "apply.css disables animations under reduced motion");

  // devcenter.css reduced motion
  assert.ok(devcenterCss.includes("@media (prefers-reduced-motion: reduce)"), "devcenter.css disables animations under reduced motion");
});
