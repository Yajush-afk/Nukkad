const { test } = require("node:test");
const assert = require("node:assert/strict");
const { create } = require("../src/nukkad/static/place-experience.js");
function fixture(api) {
  const node = (tag, text) => ({
    tag,
    textContent: text || "",
    children: [],
    append(...x) {
      this.children.push(...x);
    },
    replaceChildren(...x) {
      this.children = x;
    },
    setAttribute(k, v) {
      this[k] = v;
    },
    focus() {
      this.focused = true;
    },
  });
  const target = node("div"),
    notices = [],
    changes = [];
  let active = true;
  const ui = create({
    node,
    api,
    notify: (x) => notices.push(x),
    onSaved: (x) => changes.push(x),
    newId: () => "a".repeat(32),
  });
  const render = () =>
    ui.render(
      target,
      { id: "park", name: "Sample park" },
      () => active,
      "2026-10-12",
    );
  const find = (n, tag) =>
    n.tag === tag ? n : n.children.map((x) => find(x, tag)).find(Boolean);
  return {
    target,
    notices,
    changes,
    render,
    find,
    leave: () => (active = false),
  };
}
test("map visit is place-only, explicit and retains its unsaved draft", async () => {
  const calls = [];
  const f = fixture(async (path, options) => calls.push({ path, options }));
  let form = f.render();
  const note = f.find(form, "textarea");
  note.value = "I noticed green leaves.";
  note.oninput();
  form = f.render();
  assert.equal(f.find(form, "textarea").value, note.value);
  await form.onsubmit({ preventDefault() {} });
  assert.equal(calls.length, 1);
  assert.equal(calls[0].options.method, "PUT");
  assert.equal(calls[0].options.body.note, note.value);
  assert.match(calls[0].path, /places\/park\/experiences/);
  assert.equal(f.changes[0], "park");
  assert.equal(f.notices.length, 1);
});
test("duplicate submissions send one request and departed selections receive no feedback", async () => {
  let release,
    calls = 0;
  const f = fixture(() => {
    calls++;
    return new Promise((resolve) => (release = resolve));
  });
  const form = f.render(),
    note = f.find(form, "textarea");
  note.value = "A reported visit.";
  note.oninput();
  const pending = form.onsubmit({ preventDefault() {} });
  await form.onsubmit({ preventDefault() {} });
  assert.equal(calls, 1);
  f.leave();
  release();
  await pending;
  assert.deepEqual(f.notices, []);
});
test("upload failure preserves the saved visit and retries only remaining files", async () => {
  let writes = 0,
    uploads = 0,
    fail = true;
  const f = fixture(async (path) => {
    if (path.includes("/photos")) {
      uploads++;
      if (fail) {
        fail = false;
        throw Error("Broken photo");
      }
    } else writes++;
  });
  const form = f.render(),
    note = f.find(form, "textarea");
  note.value = "A park visit.";
  note.oninput();
  const inputs = [];
  function walk(n) {
    if (n.tag === "input") inputs.push(n);
    n.children.forEach(walk);
  }
  walk(form);
  const photos = inputs.find((n) => n.type === "file");
  photos.files = [new Blob(["image"])];
  photos.onchange();
  await form.onsubmit({ preventDefault() {} });
  assert.equal(writes, 1);
  assert.equal(f.notices.length, 0);
  await form.onsubmit({ preventDefault() {} });
  assert.equal(writes, 2);
  assert.equal(uploads, 2);
  assert.equal(f.notices.length, 1);
});
