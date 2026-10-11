const { test } = require("node:test");
const assert = require("node:assert/strict");
const { create } = require("../src/nukkad/static/place-experience.js");
function fixture(api, overrides = {}) {
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
    ...overrides,
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
      if (fail && uploads === 2) {
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
  photos.files = [new Blob(["saved image"]), new Blob(["broken image"])];
  photos.onchange();
  await form.onsubmit({ preventDefault() {} });
  assert.equal(writes, 1);
  assert.equal(f.notices.length, 0);
  assert.equal(photos.disabled, false);
  photos.files = [new Blob(["replacement image"])];
  photos.onchange();
  await form.onsubmit({ preventDefault() {} });
  assert.equal(writes, 2);
  assert.equal(uploads, 3);
  assert.equal(f.notices.length, 1);
});

test("saving starts AI once after every supplied photo, using the final source revision", async () => {
  const calls = [],
    generations = [];
  const f = fixture(
    async (path) => {
      calls.push(path);
      return path.includes("photos")
        ? { experience_revision: "photo-" + calls.length }
        : { revision: "note-revision" };
    },
    {
      onGenerate: async (visit, current) => {
        generations.push({ ...visit, live: current(), writes: calls.length });
        return { card_id: "card", journal_mode: "local AI journal" };
      },
    },
  );
  const form = f.render(),
    note = f.find(form, "textarea");
  note.value = "I loved this visit.";
  note.oninput();
  const all = (n) => [n, ...n.children.flatMap(all)];
  const photos = all(form).find((n) => n.type === "file");
  photos.files = [new Blob(["one"]), new Blob(["two"])];
  photos.onchange();
  await form.onsubmit({ preventDefault() {} });
  await form.onsubmit({ preventDefault() {} });
  assert.equal(generations.length, 1);
  assert.equal(generations[0].writes, 3);
  assert.equal(generations[0].revision, "photo-3");
  assert.ok(
    all(form).some((n) =>
      /Location Card and AI story are ready/.test(n.textContent),
    ),
  );
});

test("AI failure keeps the saved visit and retry does not reupload or create another visit", async () => {
  let writes = 0,
    attempts = 0;
  const f = fixture(
    async () => {
      writes++;
      return { revision: "saved-revision" };
    },
    {
      onGenerate: async (visit, current, retry) => {
        attempts++;
        if (!retry) throw Error("Selected model is unavailable");
        return { journal_mode: "local AI journal" };
      },
    },
  );
  const form = f.render(),
    note = f.find(form, "textarea");
  note.value = "I enjoyed tree shapes.";
  note.oninput();
  await form.onsubmit({ preventDefault() {} });
  const all = (n) => [n, ...n.children.flatMap(all)];
  let retry = all(form).find((n) => n.textContent === "Retry local AI");
  assert.equal(retry.hidden, false);
  assert.equal(writes, 1);
  await retry.onclick();
  assert.equal(writes, 1);
  assert.equal(attempts, 2);
  assert.equal(retry.hidden, true);
});
