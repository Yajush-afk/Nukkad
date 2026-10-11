const { test } = require("node:test");
const assert = require("node:assert/strict");
const { create } = require("../src/nukkad/static/place-editor.js");
test("duplicate save blocked and a selection change invalidates delayed publication", () => {
  const state = create();
  const a = state.begin(() => true);
  assert.equal(
    state.begin(() => true),
    null,
  );
  state.changed();
  assert.equal(a(), false);
  state.finish();
  assert.equal(state.begin(() => true)(), true);
});
test("leaving the screen invalidates publication without changing saved inputs", () => {
  const state = create();
  let here = true;
  const guard = state.begin(() => here);
  here = false;
  assert.equal(guard(), false);
  state.finish();
  assert.equal(state.busy, false);
});
