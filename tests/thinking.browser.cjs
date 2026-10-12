/* Run against an isolated server with Playwright installed. Jobs are intercepted. */
const assert = require("node:assert/strict");
const { chromium } = require("playwright");

(async () => {
  const browser = await chromium.launch({
    headless: true,
    ...(process.env.NUKKAD_BROWSER_CHANNEL ? { channel: process.env.NUKKAD_BROWSER_CHANNEL } : {}),
  });
  try {
    const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    let status = "running", cancelRequests = 0, rejectCancel = false;
    await page.route("**/api/jobs/orb-test", (route) => route.fulfill({
      json: { id: "orb-test", status, message: "Writing your experience journal…", result: {} },
    }));
    await page.route("**/api/jobs/orb-test/cancel", (route) => {
      cancelRequests++;
      if (rejectCancel) return route.fulfill({ status: 503, json: { detail: "Try cancellation again" } });
      status = "cancelled";
      return route.fulfill({ json: { id: "orb-test", status } });
    });
    await page.goto(process.env.NUKKAD_BROWSER_URL || "http://localhost:8001");
    await page.evaluate(() => initialized);
    async function start() {
      status = "running";
      await page.evaluate(() => {
        window.orbFinished = false;
        window.orbError = null;
        window.orbSettled = false;
        runJob({ id: "orb-test" }, () => { window.orbFinished = true; })
          .catch((error) => { window.orbError = error.message; })
          .finally(() => { window.orbSettled = true; });
      });
      await page.locator("#job").waitFor({ state: "visible" });
      assert.equal(await page.locator("#main").getAttribute("aria-busy"), "true");
    }
    async function settled() {
      await page.waitForFunction(() => window.orbSettled);
      assert.equal(await page.locator("#job").isVisible(), false);
      assert.equal(await page.locator("#main").getAttribute("aria-busy"), null);
      assert.equal(await page.locator("#cancel-job").isDisabled(), false);
    }
    await start();
    const firstPhrase = await page.locator("#thinking-phrase").innerText();
    await page.waitForFunction((text) => document.getElementById("thinking-phrase").textContent !== text, firstPhrase);
    assert.match(await page.locator("#job-message").innerText(), /experience journal/);
    const firstFrame = await page.locator(".thinking-orb").screenshot();
    await page.waitForTimeout(250);
    const nextFrame = await page.locator(".thinking-orb").screenshot();
    assert.equal(firstFrame.equals(nextFrame), false, "Orb actually animates");
    await page.screenshot({ path: "artifacts/runtime/orb-desktop.png" });
    status = "complete";
    await settled();
    assert.equal(await page.evaluate(() => window.orbFinished), true);
    for (const terminal of ["failed", "interrupted"]) {
      await start();
      status = terminal;
      await settled();
      assert.equal(await page.evaluate(() => window.orbFinished), false);
      assert.match(await page.evaluate(() => window.orbError), /journal/);
    }
    await page.setViewportSize({ width: 375, height: 812 });
    await start();
    rejectCancel = true;
    await page.locator("#cancel-job").focus();
    await page.keyboard.press("Enter");
    await page.waitForFunction(() => !document.getElementById("cancel-job").disabled);
    assert.equal(cancelRequests, 1);
    rejectCancel = false;
    await page.locator("#cancel-job").focus();
    await page.keyboard.press("Enter");
    await settled();
    assert.equal(cancelRequests, 2);
    assert.equal(await page.evaluate(() => window.orbFinished), false);
    for (const width of [375, 320]) {
      await page.setViewportSize({ width, height: 812 });
      await start();
      await page.locator("#cancel-job").focus();
      await page.waitForTimeout(50);
      const layout = await page.locator("#job").boundingBox();
      assert.ok(layout.x >= 0 && layout.x + layout.width <= width);
      assert.ok(layout.y >= 0 && layout.y + layout.height <= 812);
      const bottom = await page.locator(".notification-rail").evaluate((el) => el.style.bottom);
      await page.evaluate(() => positionFeedback());
      assert.equal(await page.locator(".notification-rail").evaluate((el) => el.style.bottom), bottom);
      await page.screenshot({ path: `artifacts/runtime/orb-${width}.png` });
      await page.locator("#cancel-job").click();
      await settled();
    }
    await page.emulateMedia({ reducedMotion: "reduce" });
    await start();
    const still = await page.locator(".thinking-orb").screenshot();
    await page.waitForTimeout(250);
    assert.equal(still.equals(await page.locator(".thinking-orb").screenshot()), true);
    await page.locator("#cancel-job").click();
    await settled();
    assert.deepEqual(errors, []);
    console.log("Orb animation, phrases, terminal cleanup, keyboard cancellation/retry, mobile layout and reduced motion passed.");
  } finally {
    await browser.close();
  }
})().catch((error) => { console.error(error); process.exitCode = 1; });
