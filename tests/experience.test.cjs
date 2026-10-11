const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
function fixture(reducedMotion) {
  const documentEvents = {},
    mediaEvents = {};
  const hero = {
    dataset: {},
    style: { setProperty() {} },
    classList: { add() {}, remove() {} },
    getBoundingClientRect: () => ({ width: 1200, height: 800 }),
  };
  const elements = {
    "sky-hero": hero,
    "pixel-sky": { getContext: () => null, addEventListener() {} },
    "sky-fallback": {},
    typewriter: {
      textContent: "Your neighbourhood is a map you have not finished.",
    },
  };
  const media = {
    matches: reducedMotion,
    addEventListener: (event, fn) => (mediaEvents[event] = fn),
  };
  const document = {
    hidden: false,
    body: { dataset: { panel: "home" } },
    getElementById: (id) => elements[id],
    addEventListener: (event, fn) => (documentEvents[event] = fn),
  };
  const sandbox = {
    document,
    matchMedia: () => media,
    window: { addEventListener() {} },
    clearTimeout() {},
    setTimeout() {
      return 1;
    },
    cancelAnimationFrame() {},
    requestAnimationFrame() {
      return 1;
    },
    ResizeObserver: class {
      constructor(fn) {
        this.fn = fn;
      }
      observe() {
        this.fn();
      }
    },
    IntersectionObserver: class {
      constructor(fn) {
        this.fn = fn;
      }
      observe() {
        this.fn([{ isIntersecting: true }]);
      }
    },
  };
  vm.runInNewContext(
    fs.readFileSync("src/nukkad/static/experience.js", "utf8"),
    sandbox,
  );
  return { hero, elements, document, media, documentEvents, mediaEvents };
}
test("no WebGL uses the bundled fallback and visibility/panel state controls motion", () => {
  const f = fixture(false);
  assert.equal(f.hero.dataset.sky, "css");
  assert.equal(f.elements["pixel-sky"].hidden, true);
  assert.equal(f.elements["sky-fallback"].hidden, false);
  assert.equal(f.hero.dataset.moving, "true");
  f.document.hidden = true;
  f.documentEvents.visibilitychange();
  assert.equal(f.hero.dataset.moving, "false");
  f.document.hidden = false;
  f.document.body.dataset.panel = "setup";
  f.documentEvents["nukkad:panel"]();
  assert.equal(f.hero.dataset.moving, "false");
  assert.match(f.elements.typewriter.textContent, /neighbourhood/);
});
test("reduced motion keeps the sky still and displays the complete subline", () => {
  const f = fixture(true);
  assert.equal(f.hero.dataset.moving, "false");
  assert.match(f.elements.typewriter.textContent, /not finished/);
  f.media.matches = false;
  f.mediaEvents.change();
  assert.equal(f.hero.dataset.moving, "true");
});
