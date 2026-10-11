const { test } = require("node:test");
const assert = require("node:assert/strict");
const { create } = require("../src/nukkad/static/suggestions.js");
function fixture() {
  const timers = [],
    requests = [],
    selected = [];
  const node = (tag, text) => ({
    tag,
    textContent: text,
    attrs: {},
    children: [],
    setAttribute(k, v) {
      this.attrs[k] = v;
    },
    removeAttribute(k) {
      delete this.attrs[k];
    },
    append(...x) {
      this.children.push(...x);
    },
    replaceChildren(...x) {
      this.children = x;
    },
    addEventListener(k, cb) {
      this[k] = cb;
    },
  });
  const input = node("input");
  input.value = "";
  const target = node("ul");
  target.id = "matches";
  const status = node("p");
  let resolveNext;
  const api = (path, options) =>
    new Promise((resolve) => requests.push({ path, options, resolve }));
  const ui = create({
    input,
    target,
    status,
    node,
    api,
    scope: "neighbourhood",
    select: (x) => selected.push(x),
    setTimer: (cb) => {
      timers.push(cb);
      return cb;
    },
    clearTimer: (cb) => {
      const i = timers.indexOf(cb);
      if (i >= 0) timers.splice(i, 1);
    },
  });
  return { input, target, status, ui, requests, timers, selected };
}
const item = (id, group = "On your map") => ({
  id,
  name: id,
  label: "Sample city",
  group,
  point: { lat: 1, lon: 1 },
  place_id: id,
});
test("local suggestions precede online, keyboard requires selection and preserves highlight", async () => {
  const f = fixture();
  f.input.value = "Sample";
  const change = f.ui.changed();
  assert.equal(f.requests[0].options.body.online, false);
  f.requests[0].resolve({ matches: [item("one"), item("two")] });
  await change;
  assert.equal(f.selected.length, 0);
  f.input.keydown({ key: "ArrowDown", preventDefault() {} });
  f.input.keydown({ key: "ArrowDown", preventDefault() {} });
  f.timers.shift()();
  f.requests[1].resolve({
    matches: [item("one"), item("two"), item("three", "Online results")],
    online: {},
  });
  await new Promise((r) => setImmediate(r));
  assert.equal(f.input.attrs["aria-activedescendant"], "matches-option-1");
  f.input.keydown({ key: "Enter", preventDefault() {} });
  assert.equal(f.selected[0].id, "two");
  assert.equal(f.target.hidden, true);
});
test("obsolete local replies cannot replace new query and short text never sends requests", async () => {
  const f = fixture();
  f.input.value = "ab";
  await f.ui.changed();
  assert.equal(f.requests.length, 0);
  f.input.value = "first";
  const a = f.ui.changed();
  f.input.value = "second";
  const b = f.ui.changed();
  f.requests[1].resolve({ matches: [item("second")] });
  await b;
  f.requests[0].resolve({ matches: [item("first")] });
  await a;
  assert.equal(
    f.target.children.find((x) => x.tag === "li" && x.attrs.role === "option")
      .children[0].textContent,
    "second",
  );
  f.input.keydown({ key: "Escape" });
  assert.equal(f.target.hidden, true);
});
test("online failure leaves local matches visible", async () => {
  const f = fixture();
  f.input.value = "Sample";
  const change = f.ui.changed();
  f.requests[0].resolve({ matches: [item("local")] });
  await change;
  f.timers.shift()();
  f.requests[1].resolve({
    matches: [item("local")],
    online: { status: "unavailable", message: "Provider unavailable" },
  });
  await new Promise((r) => setImmediate(r));
  assert.equal(f.target.hidden, false);
  assert.equal(f.status.textContent, "Provider unavailable");
});

test("explicit Search results replace autocomplete results and support keyboard choice", () => {
  const f = fixture();
  f.ui.show([item("explicit")]);
  f.input.keydown({ key: "ArrowDown", preventDefault() {} });
  f.input.keydown({ key: "Enter", preventDefault() {} });
  assert.equal(f.selected[0].id, "explicit");
});
