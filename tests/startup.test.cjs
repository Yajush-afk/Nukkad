const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

test("session startup does not load the working map or component diagnostics", async () => {
  const calls = [];
  const chain = {
    setView() {
      return this;
    },
    addTo() {
      return this;
    },
    addAttribution() {
      return this;
    },
    on() {},
  };
  const context = vm.createContext({
    sessionToken: null,
    api: async (path) => {
      calls.push(path);
      return path === "/session"
        ? { token: "synthetic" }
        : path === "/profile"
          ? { interests: [] }
          : {};
    },
    L: {
      map: () => chain,
      geoJSON: () => chain,
      layerGroup: () => chain,
      control: { attribution: () => chain },
    },
    $: () => ({ elements: {}, value: "" }),
    area: null,
    loadArea: () => {
      calls.push("/area");
      return new Promise(() => {});
    },
    refreshReadiness: () => {
      calls.push("/readiness");
    },
    selectMapPoint() {},
  });
  const source = fs.readFileSync("src/nukkad/static/app.js", "utf8");
  vm.runInContext(
    source.slice(
      source.indexOf("async function init()"),
      source.indexOf("async function refreshReadiness("),
    ),
    context,
  );
  const started = context.init();
  await new Promise((r) => setImmediate(r));
  assert.deepEqual(calls, ["/session"]);
  await started;
});

test("the actual Home resolver never waits for session, map, or readiness", async () => {
  let config;
  const calls = [];
  const context = vm.createContext({
    window: {},
    navigation: null,
    initialized: new Promise(() => {}),
    areaNeedsRefresh: true,
    NukkadNavigation: {
      createNavigation: (value) => {
        config = value;
        return {};
      },
    },
    api: async (path) => {
      calls.push(path);
      throw Error("Home should not fetch backend data");
    },
    report() {},
  });
  const source = fs.readFileSync("src/nukkad/static/app.js", "utf8");
  vm.runInContext(
    source.slice(
      source.indexOf("navigation = NukkadNavigation.createNavigation("),
      source.indexOf("const collectionUI ="),
    ),
    context,
  );
  const route = { view: "home", walk: null };
  const resolved = await Promise.race([
    config.resolve(route, () => true),
    new Promise((r) => setImmediate(() => r("blocked"))),
  ]);
  assert.equal(resolved, route);
  assert.deepEqual(calls, []);
});

test("Get started uses lightweight status for missing, unconfirmed and confirmed starts", async () => {
  const source = fs.readFileSync("src/nukkad/static/app.js", "utf8");
  for (const saved of [
    null,
    { public_start_confirmed: false },
    { public_start_confirmed: true },
  ]) {
    const button = {};
    const shown = [];
    let checks = 0;
    const context = vm.createContext({
      $: () => button,
      area: null,
      navigation: { checkpoint: () => () => true },
      loadAreaSummary: async () => {
        checks++;
        context.area = { area: saved };
      },
      show: async (id) => shown.push(id),
      report: (error) => {
        throw error;
      },
    });
    vm.runInContext(
      source.slice(
        source.indexOf('$("open-quest").onclick'),
        source.indexOf('$("plan-walk").onclick'),
      ),
      context,
    );
    await button.onclick();
    assert.equal(checks, 1);
    assert.deepEqual(shown, [
      saved?.public_start_confirmed ? "quest-form-panel" : "setup",
    ]);
  }
});

test("mutations wait for the local session while reads remain available", async () => {
  const calls = [];
  let release;
  const context = vm.createContext({
    initialized: new Promise((r) => {
      release = r;
    }),
    sessionToken: null,
    FormData: class {},
    fetch: async (url, options) => {
      calls.push({ url, options });
      return { ok: true, json: async () => ({}) };
    },
  });
  const source = fs.readFileSync("src/nukkad/static/app.js", "utf8");
  vm.runInContext(
    source.slice(
      source.indexOf("async function api("),
      source.indexOf("function renderPanel("),
    ),
    context,
  );
  const pending = context.api("/settings", {
    method: "PUT",
    body: { tone: "quiet" },
  });
  await context.api("/settings");
  assert.equal(calls.length, 1);
  assert.equal(calls[0].options.method, undefined);
  context.sessionToken = "synthetic-token";
  release();
  await pending;
  assert.equal(calls[1].options.headers["X-Nukkad-Token"], "synthetic-token");
});
