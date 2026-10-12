const { test } = require("node:test");
const assert = require("node:assert/strict");
const { create } = require("../src/nukkad/static/thinking.js");

function fixture({ reduced = false, renderer = true } = {}) {
  const frames = new Map(), timers = new Map(), events = {};
  let id = 0, draws = 0, changes = 0;
  const source = (name) => ({
    addEventListener(type, cb) { events[name + type] = cb; },
  });
  const page = { ...source("page"), hidden: false };
  const motion = { ...source("motion"), matches: reduced };
  const canvas = source("canvas"), phrase = {};
  const ui = create({
    canvas, phrase, document: page, motion,
    onChange: () => changes++,
    requestFrame: (cb) => { frames.set(++id, cb); return id; },
    cancelFrame: (key) => frames.delete(key),
    setTimer: (cb) => { timers.set(++id, cb); return id; },
    clearTimer: (key) => timers.delete(key),
    makeRenderer: () => renderer ? () => draws++ : null,
  });
  function tick(queue, time) {
    const [key, cb] = queue.entries().next().value;
    queue.delete(key);
    cb(time);
  }
  return { ui, page, motion, phrase, frames, timers, events, tick,
    draws: () => draws, changes: () => changes };
}

test("cycles throughout a job, resets for the next job and leaves no scheduled work", () => {
  const f = fixture();
  f.ui.start();
  const initial = f.phrase.textContent;
  assert.equal(f.frames.size, 1);
  f.tick(f.frames, 100);
  assert.equal(f.draws(), 2);
  f.tick(f.timers);
  assert.notEqual(f.phrase.textContent, initial);
  for (let i = 0; i < 3; i++) f.tick(f.timers);
  assert.equal(f.phrase.textContent, initial);
  assert.equal(f.changes(), 4);
  f.ui.stop();
  assert.equal(f.frames.size + f.timers.size, 0);
  f.ui.start();
  f.ui.start();
  assert.equal(f.frames.size, 1);
  assert.equal(f.timers.size, 1);
  f.ui.stop();
});

test("background tabs and reduced motion pause both animation and decorative text", () => {
  const f = fixture();
  f.ui.start();
  f.page.hidden = true;
  f.events.pagevisibilitychange();
  assert.equal(f.frames.size + f.timers.size, 0);
  f.page.hidden = false;
  f.events.pagevisibilitychange();
  assert.equal(f.frames.size + f.timers.size, 2);
  f.motion.matches = true;
  f.events.motionchange();
  assert.equal(f.frames.size + f.timers.size, 0);
  f.ui.stop();
  f.motion.matches = false;
  f.events.motionchange();
  assert.equal(f.frames.size + f.timers.size, 0);
  const reduced = fixture({ reduced: true });
  reduced.ui.start();
  assert.equal(reduced.draws(), 1);
  assert.equal(reduced.frames.size + reduced.timers.size, 0);
});

test("missing or lost WebGL retains cycling text without an animation loop", () => {
  const fallback = fixture({ renderer: false });
  fallback.ui.start();
  assert.equal(fallback.frames.size, 0);
  assert.equal(fallback.timers.size, 1);
  fallback.ui.stop();
  const f = fixture();
  f.ui.start();
  let prevented = false;
  f.events.canvaswebglcontextlost({ preventDefault() { prevented = true; } });
  assert.equal(prevented, true);
  assert.equal(f.frames.size, 0);
  assert.equal(f.timers.size, 1);
  f.events.canvaswebglcontextrestored();
  assert.equal(f.frames.size, 1);
  f.ui.stop();
  f.events.canvaswebglcontextrestored();
  assert.equal(f.frames.size + f.timers.size, 0);
});
