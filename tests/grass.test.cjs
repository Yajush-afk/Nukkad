const { test } = require("node:test");
const assert = require("node:assert/strict");
const {
  field,
  bend,
  draw,
  mount,
  PIXEL_SIZE,
} = require("../src/nukkad/static/grass.js");

test("the grass bed is deterministic, fills every row and keeps roots fixed in wind", () => {
  const blades = field(120, 60);
  assert.equal(PIXEL_SIZE, 6);
  assert.deepEqual(blades, field(120, 60));
  assert.ok(Math.min(...blades.map((b) => b.x)) < 0);
  assert.ok(Math.max(...blades.map((b) => b.x)) >= 120);
  for (let y = 4; y <= 60; y += 7)
    assert.ok(blades.some((b) => b.y >= y && b.y <= y + 3));
  for (const blade of blades) {
    assert.equal(Math.abs(bend(blade, 0, 0)), 0);
    assert.equal(Math.abs(bend(blade, 0, 5)), 0);
  }
  assert.ok(blades.some((b) => bend(b, 1, 0) !== bend(b, 1, 1.5)));
});
test("the renderer covers the whole background and paints only integer pixels", () => {
  const calls = [];
  draw({ fillRect: (...args) => calls.push(args) }, 30, 20, field(30, 20), 1);
  assert.deepEqual(calls[0], [0, 0, 30, 20]);
  for (const call of calls.slice(1)) {
    assert.ok(call.every(Number.isInteger));
    assert.deepEqual(call.slice(2), [1, 1]);
  }
});
function fixture({ reduced = false, available = true } = {}) {
  const events = {},
    documentEvents = {},
    mediaEvents = {},
    frames = new Map(),
    calls = [];
  let intersection,
    resize,
    next = 1;
  const size = { width: 600, height: 240 };
  const footer = {
    dataset: {},
    getBoundingClientRect: () => size,
  };
  const context = { fillRect: (...args) => calls.push(args) };
  const canvas = {
    width: 300,
    height: 150,
    hidden: true,
    getContext: () => (available ? context : null),
  };
  const fallback = { hidden: false };
  const media = {
    matches: reduced,
    addEventListener: (event, fn) => (mediaEvents[event] = fn),
  };
  const document = {
    hidden: false,
    addEventListener: (event, fn) => (documentEvents[event] = fn),
  };
  const browser = {
    document,
    matchMedia: () => media,
    addEventListener: (event, fn) => (events[event] = fn),
    requestAnimationFrame: (fn) => {
      const id = next++;
      frames.set(id, fn);
      return id;
    },
    cancelAnimationFrame: (id) => frames.delete(id),
    ResizeObserver: class {
      constructor(fn) {
        resize = fn;
      }
      observe() {}
    },
    IntersectionObserver: class {
      constructor(fn) {
        intersection = fn;
      }
      observe() {}
    },
  };
  mount({ footer, canvas, fallback, browser });
  return {
    size,
    footer,
    canvas,
    fallback,
    media,
    document,
    context,
    frames,
    calls,
    events,
    documentEvents,
    mediaEvents,
    visible: (value) => intersection([{ isIntersecting: value }]),
    resize: () => resize(),
    tick: (now) => {
      const [id, fn] = frames.entries().next().value;
      frames.delete(id);
      fn(now);
    },
  };
}
test("motion is bounded and stops offscreen, in hidden tabs, for reduced motion and page exit", () => {
  const f = fixture();
  assert.equal(f.footer.dataset.grass, "canvas");
  assert.deepEqual([f.canvas.width, f.canvas.height], [100, 40]);
  assert.equal(f.frames.size, 0);
  f.visible(true);
  assert.equal(f.frames.size, 1);
  const initial = f.calls.length;
  f.tick(0);
  f.tick(30);
  assert.equal(f.calls.length, initial);
  f.tick(70);
  assert.ok(f.calls.length > initial);
  f.visible(false);
  assert.equal(f.frames.size, 0);
  f.visible(true);
  f.document.hidden = true;
  f.documentEvents.visibilitychange();
  assert.equal(f.frames.size, 0);
  f.document.hidden = false;
  f.documentEvents.visibilitychange();
  assert.equal(f.frames.size, 1);
  f.media.matches = true;
  f.mediaEvents.change();
  assert.equal(f.frames.size, 0);
  f.media.matches = false;
  f.mediaEvents.change();
  assert.equal(f.frames.size, 1);
  f.events.pagehide();
  assert.equal(f.frames.size, 0);
  f.events.pageshow();
  assert.equal(f.frames.size, 1);
  const before = f.calls.length;
  f.resize();
  assert.equal(f.calls.length, before);
  f.size.width = 390;
  f.size.height = 300;
  f.events.resize();
  assert.deepEqual([f.canvas.width, f.canvas.height], [65, 50]);
});
test("reduced motion starts with a complete still meadow and missing canvas retains the SVG", () => {
  const still = fixture({ reduced: true });
  still.visible(true);
  assert.ok(still.calls.length > 0);
  assert.equal(still.frames.size, 0);
  assert.equal(still.footer.dataset.grassMoving, "false");
  const missing = fixture({ available: false });
  assert.equal(missing.footer.dataset.grass, "static");
  assert.equal(missing.fallback.hidden, false);
  assert.equal(missing.canvas.hidden, true);
  assert.equal(missing.frames.size, 0);
});
