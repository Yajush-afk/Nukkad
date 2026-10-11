const { test } = require("node:test");
const assert = require("node:assert/strict");
const { createNavigation } = require("../src/nukkad/static/navigation.js");
function fixture(resolve = async (route) => route) {
  const listeners = new Map(),
    entries = [{ url: "http://localhost:8001/", state: null }];
  let index = 0;
  const browser = {
    scrollY: 0,
    location: { href: entries[0].url },
    addEventListener(name, fn) {
      listeners.set(name, fn);
    },
    scrollTo({ top }) {
      this.scrollY = top;
    },
    history: {
      get state() {
        return entries[index].state;
      },
      replaceState(state, _, url) {
        entries[index] = {
          state,
          url: new URL(url, browser.location.href).href,
        };
        browser.location.href = entries[index].url;
      },
      pushState(state, _, url) {
        entries.splice(++index);
        entries.push({ state, url: new URL(url, browser.location.href).href });
        browser.location.href = entries[index].url;
      },
    },
  };
  const rendered = [],
    errors = [];
  const navigation = createNavigation({
    browser,
    resolve,
    render: (route) => rendered.push(route.view),
    onError: (e) => errors.push(e),
  });
  return {
    browser,
    navigation,
    rendered,
    entries,
    errors,
    async travel(delta) {
      index += delta;
      browser.location.href = entries[index].url;
      listeners.get("popstate")();
      await new Promise((r) => setImmediate(r));
    },
  };
}
test("navigation creates entries once and Back/Forward restores screens and scroll", async () => {
  const f = fixture();
  await f.navigation.start();
  f.browser.scrollY = 1200;
  await f.navigation.go("setup");
  await f.navigation.go("setup");
  assert.equal(f.entries.length, 2);
  assert.match(f.browser.location.href, /view=neighbourhood/);
  await f.navigation.go("history");
  await f.navigation.go("settings");
  await f.travel(-1);
  assert.equal(f.rendered.at(-1), "history");
  await f.travel(-1);
  assert.equal(f.rendered.at(-1), "neighbourhood");
  await f.travel(-1);
  assert.equal(f.rendered.at(-1), "home");
  assert.equal(f.browser.scrollY, 1200);
  await f.travel(1);
  assert.equal(f.rendered.at(-1), "neighbourhood");
});
test("late route responses cannot render over newer navigation", async () => {
  let release;
  const f = fixture((route) =>
    route.view === "preview"
      ? new Promise((r) => {
          release = () => r(route);
        })
      : Promise.resolve(route),
  );
  await f.navigation.start();
  const slow = f.navigation.go("preview", "saved-walk");
  await f.navigation.go("settings");
  release();
  await slow;
  assert.equal(f.rendered.at(-1), "settings");
  assert.equal(f.rendered.includes("preview"), false);
});
test("direct views restore on startup and redirects replace rather than push", async () => {
  const f = fixture(async (route) =>
    route.view === "plan" ? { view: "neighbourhood", walk: null } : route,
  );
  f.browser.location.href = "http://localhost:8001/?view=plan";
  await f.navigation.start();
  assert.equal(f.entries.length, 1);
  assert.equal(f.rendered.at(-1), "neighbourhood");
  assert.match(f.browser.location.href, /view=neighbourhood/);
});
test("history contains only navigation metadata, never supplied records or notes", async () => {
  const f = fixture(async (route, current, supplied) => ({
    ...route,
    ...supplied,
  }));
  await f.navigation.start();
  await f.navigation.go("preview", "walk-1", {
    quest: { note: "private words" },
  });
  assert.deepEqual(Object.keys(f.browser.history.state).sort(), [
    "nukkad",
    "scrollY",
    "view",
    "walk",
  ]);
  assert.equal(JSON.stringify(f.entries).includes("private words"), false);
});

test("an initial homepage anchor is revealed after asynchronous content is ready", async () => {
  const f = fixture();
  let revealed = false;
  f.browser.location.href = "http://localhost:8001/#how-it-works";
  f.browser.location.hash = "#how-it-works";
  f.browser.document = {
    getElementById: (id) =>
      id === "how-it-works"
        ? {
            scrollIntoView: () => {
              revealed = true;
            },
          }
        : null,
  };
  await f.navigation.start();
  assert.equal(revealed, true);
});

test("operation checkpoints expire when navigation leaves their screen", async () => {
  const f = fixture();
  await f.navigation.start();
  const current = f.navigation.checkpoint();
  assert.equal(current(), true);
  await f.navigation.go("settings");
  assert.equal(current(), false);
});

test('place folders restore with Back and Forward while history excludes private media',async()=>{
  const f=fixture(async(route,current,supplied)=>({...route,...supplied}));
  await f.navigation.start();await f.navigation.go('history');
  await f.navigation.go('place-folder','osm-node-2',{folder:{note:'private experience',photos:['private photo']}});
  assert.match(f.browser.location.href,/view=folder&place=osm-node-2/);
  assert.equal(f.browser.history.state.place,'osm-node-2');
  assert.equal(JSON.stringify(f.entries).includes('private experience'),false);
  await f.travel(-1);assert.equal(f.rendered.at(-1),'history');
  await f.travel(1);assert.equal(f.rendered.at(-1),'folder');
  assert.ok(f.navigation.isCurrent('folder','osm-node-2'));
});
