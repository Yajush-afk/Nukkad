/* Run with Playwright available and an isolated Nukkad server. No saved data is changed. */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require("playwright");
(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({
    viewport: { width: 1280, height: 800 },
  });
  const base = process.env.NUKKAD_BROWSER_URL || "http://localhost:8003";
  const output =
    process.env.NUKKAD_BROWSER_OUTPUT || "artifacts/interface-browser";
  fs.mkdirSync(output, { recursive: true });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(base);
  await page.waitForFunction(() => typeof navigation !== "undefined");
  await page.evaluate(() => initialized);
  for (const [width, height, name] of [
    [1280, 800, "desktop"],
    [375, 812, "mobile"],
    [320, 568, "small-mobile"],
  ]) {
    await page.setViewportSize({ width, height });
    await page.evaluate(() => window.scrollTo({ top: 0, behavior: "instant" }));
    await page.waitForTimeout(180);
    const layout = await page.evaluate(() => {
      const hero = document.getElementById("sky-hero").getBoundingClientRect();
      const story = document
        .getElementById("how-it-works")
        .getBoundingClientRect();
      const brand = document.querySelector(".brand").getBoundingClientRect();
      const star = document
        .querySelector(".github-star")
        .getBoundingClientRect();
      const nav = document.querySelector("nav").getBoundingClientRect();
      return {
        hero: { x: hero.x, y: hero.y, w: hero.width, h: hero.height },
        storyY: story.y,
        clientWidth: document.documentElement.clientWidth,
        overflow:
          document.documentElement.scrollWidth >
          document.documentElement.clientWidth,
        brand: { x: brand.x, right: brand.right, bottom: brand.bottom },
        star: { x: star.x, right: star.right, bottom: star.bottom },
        navY: nav.y,
        pause: !!document.getElementById("sky-motion"),
      };
    });
    assert.equal(layout.hero.x, 0);
    assert.equal(layout.hero.y, 0);
    assert.equal(layout.hero.w, layout.clientWidth);
    assert.ok(layout.hero.h >= height);
    assert.ok(layout.storyY >= height);
    assert.equal(layout.overflow, false);
    assert.equal(layout.pause, false);
    assert.ok(layout.brand.right <= width && layout.star.right <= width);
    if (width < 900)
      assert.ok(
        layout.navY >= Math.max(layout.brand.bottom, layout.star.bottom),
      );
    await page.screenshot({
      path: path.join(output, `hero-${name}.png`),
      animations: "disabled",
    });
  }
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.locator(".imagined-map").scrollIntoViewIfNeeded();
  const fictional = await page.evaluate(() => ({
    image: !!document.querySelector("#home .imagined-map img"),
    map: !!document.querySelector("#home #map"),
    links: document.querySelectorAll(".imagined-map a,.imagined-map button")
      .length,
  }));
  assert.deepEqual(fictional, { image: true, map: false, links: 0 });
  await page.screenshot({
    path: path.join(output, "fictional-map.png"),
    animations: "disabled",
  });
  await page.evaluate(() =>
    window.scrollTo({ top: 1000, behavior: "instant" }),
  );
  await page.evaluate(async () => {
    await show("setup");
    document.getElementById("location-query").value = "Unsaved example";
    await show("history");
    await show("settings");
  });
  await page.goBack();
  await page.waitForFunction(() => document.body.dataset.panel === "history");
  await page.goBack();
  await page.waitForFunction(() => document.body.dataset.panel === "setup");
  assert.equal(
    await page.locator("#location-query").inputValue(),
    "Unsaved example",
  );
  await page.goBack();
  await page.waitForFunction(() => document.body.dataset.panel === "home");
  await page.waitForTimeout(150);
  assert.equal(await page.evaluate(() => scrollY), 1000);
  await page.goForward();
  await page.waitForFunction(() => document.body.dataset.panel === "setup");
  await page.goto(base + "/?view=preview&walk=missing");
  await page.waitForFunction(() => document.body.dataset.panel === "history");
  assert.match(
    await page.locator("#message").textContent(),
    /could not be opened/,
  );
  await page.goto(base + "/?view=plan");
  await page.evaluate(() => initialized);
  await page.waitForTimeout(150);
  assert.equal(await page.evaluate(() => document.body.dataset.panel), "setup");
  await page.goto(base + "/#how-it-works");
  await page.evaluate(() => initialized);
  await page.waitForTimeout(100);
  assert.ok(await page.evaluate(() => scrollY > 300));
  const entries = await page.evaluate(() => history.length);
  await page.locator('nav button[data-panel="home"]').click();
  assert.equal(await page.evaluate(() => scrollY), 0);
  assert.equal(await page.evaluate(() => history.length), entries);
  await page.goto(base + "/?view=settings");
  await page.waitForFunction(() => document.body.dataset.panel === "settings");
  await page.reload();
  await page.waitForFunction(() => document.body.dataset.panel === "settings");
  const reduced = await browser.newPage({ reducedMotion: "reduce" });
  await reduced.goto(base);
  await reduced.evaluate(() => initialized);
  assert.equal(
    await reduced.locator("#sky-hero").getAttribute("data-moving"),
    "false",
  );
  assert.match(
    await reduced.locator("#typewriter").textContent(),
    /haven't finished/,
  );
  await reduced.close();
  const fallback = await browser.newPage();
  await fallback.addInitScript(() => {
    const getContext = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (name, ...args) {
      return name === "webgl" ? null : getContext.call(this, name, ...args);
    };
  });
  await fallback.goto(base);
  await fallback.evaluate(() => initialized);
  assert.equal(
    await fallback.locator("#sky-hero").getAttribute("data-sky"),
    "css",
  );
  assert.equal(await fallback.locator("#sky-fallback").isVisible(), true);
  await fallback.close();
  await page.goto(base);
  await page.locator('nav button[data-panel="setup"]').focus();
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => document.body.dataset.panel === "setup");
  if (process.env.NUKKAD_MAP_BROWSER_URL) {
    await page.goto(
      process.env.NUKKAD_MAP_BROWSER_URL + "/?view=neighbourhood",
    );
    await page.evaluate(() => initialized);
    await page.locator("#map").scrollIntoViewIfNeeded();
    await page.locator("#map-details summary").scrollIntoViewIfNeeded();
    const y = await page.evaluate(() => scrollY);
    await page.locator("#map-details summary").evaluate((el) => el.click());
    assert.equal(await page.locator("#map-details").getAttribute("open"), "");
    assert.equal(await page.evaluate(() => scrollY), y);
    const interactive = await page.evaluate(() => {
      const y = scrollY;
      const z = map.getZoom();
      map.setZoom(z + 1, { animate: false });
      map.panBy([20, 20], { animate: false });
      return { zoom: map.getZoom() === z + 1, stable: scrollY === y };
    });
    assert.deepEqual(interactive, { zoom: true, stable: true });
  }
  // An actual job callback must stay quiet if the user leaves its screen.
  await page.goto(base);
  await page.evaluate(() => initialized);
  let release, seen;
  const observed = new Promise((resolve) => {
    seen = resolve;
  });
  const held = new Promise((resolve) => {
    release = resolve;
  });
  await page.route("**/api/jobs/browser-smoke", async (route) => {
    seen();
    await held;
    await route.fulfill({
      json: {
        status: "complete",
        result: { quest_id: "example" },
        message: "Ready",
      },
    });
  });
  await page.evaluate(() => {
    window.smokeJump = false;
    window.smokeJob = runJob(
      { id: "browser-smoke", title: "Create walking quest" },
      () => {
        window.smokeJump = true;
      },
    );
  });
  await observed;
  await page.evaluate(() => show("settings"));
  release();
  await page.evaluate(() => window.smokeJob);
  assert.equal(await page.evaluate(() => window.smokeJump), false);
  assert.equal(
    await page.evaluate(() => document.body.dataset.panel),
    "settings",
  );
  await page.unroute("**/api/jobs/browser-smoke");
  let mapRelease, mapSeen;
  const mapObserved = new Promise((resolve) => {
    mapSeen = resolve;
  });
  const mapHeld = new Promise((resolve) => {
    mapRelease = resolve;
  });
  await page.route("**/api/jobs/browser-smoke-map", async (route) => {
    mapSeen();
    await mapHeld;
    await route.fulfill({
      json: {
        status: "complete",
        result: { snapshot_id: "example" },
        message: "Ready",
      },
    });
  });
  await page.evaluate(() => {
    window.smokeMapJob = runJob(
      { id: "browser-smoke-map", title: "Update public starting point" },
      () => {},
    );
  });
  await mapObserved;
  await page.evaluate(() => show("home"));
  mapRelease();
  await page.evaluate(() => window.smokeMapJob);
  assert.equal(await page.evaluate(() => areaNeedsRefresh), true);
  await page.evaluate(() => show("setup"));
  assert.equal(await page.evaluate(() => areaNeedsRefresh), false);
  await page.unroute("**/api/jobs/browser-smoke-map");
  assert.deepEqual(errors, []);
  await browser.close();
  console.log(
    "Browser smoke checks passed: responsive hero, static map, history, drafts, deep links, reduced motion and map tools.",
  );
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
