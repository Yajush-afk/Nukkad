const { test } = require("node:test");
const assert = require("node:assert/strict");
const { create } = require("../src/nukkad/static/collection.js");
function fixture(overrides = {}) {
  const make = (tag, text) => ({
    tag,
    textContent: text || "",
    children: [],
    value: "",
    append(...items) {
      this.children.push(...items);
    },
    prepend(...items) {
      this.children.unshift(...items);
    },
    replaceChildren(...items) {
      this.children = items;
    },
    setAttribute(key, value) {
      this[key] = value;
    },
  });
  const elements = new Map();
  const get = (id) => {
    if (!elements.has(id)) elements.set(id, make("div"));
    return elements.get(id);
  };
  const navigated = [];
  const ui = create({
    node: make,
    $: get,
    navigation: {
      checkpoint: () => () => true,
      go: (...args) => navigated.push(args),
    },
    api: async (path) =>
      path === "/readiness"
        ? { local_ai_ready: true, model_capabilities: ["vision"] }
        : {
            card_count: 1,
            folders: [
              {
                id: "place",
                name: "Sample park",
                visits: 2,
                photos: 5,
                cover_photo_id: "photo",
                current_card_id: "card",
              },
            ],
          },
    runJob: async () => {},
    report: (error) => {
      throw error;
    },
    message: () => {},
    ...overrides,
  });
  const all = (item) => [item, ...item.children.flatMap(all)];
  return { ui, get, all, navigated };
}
test("place collection shows reported counts and semantic folder links without summaries", async () => {
  const f = fixture();
  await f.ui.load(() => true);
  const nodes = f.all(f.get("place-collection"));
  assert.ok(
    nodes.some((x) => x.textContent === "1 Location Card · 1 reported place"),
  );
  const tile = nodes.find((x) => x.tag === "a");
  assert.match(tile.href, /view=folder&place=place/);
  assert.ok(nodes.some((x) => x.tag === "img" && x.loading === "lazy"));
  tile.onclick({ button: 0, preventDefault() {} });
  assert.deepEqual(f.navigated, [["place-folder", "place"]]);
});
test("a folder starts with its Location Card and groups photos by visit", async () => {
  const f = fixture();
  await f.ui.renderFolder(
    {
      id: "place",
      name: "Sample park",
      current_card: {
        id: "card",
        experience_id: "visit",
        photo_id: "photo",
        summary: "They noticed the outlines.",
        visit_date: "2026-10-11",
        mode: "Local vision AI",
      },
      visits: [
        {
          id: "visit",
          outcome_id: "walk",
          visit_date: "2026-10-11",
          note: "I noticed outlines.",
          photos: [{ id: "photo" }],
        },
      ],
      card_versions: [],
    },
    () => true,
  );
  const target = f.get("folder-content");
  assert.equal(target.children[0].children[0].textContent, "Location CARD");
  const nodes = f.all(target);
  assert.ok(nodes.some((x) => x.textContent === "Photos, visit by visit."));
  assert.ok(nodes.some((x) => x.textContent === "The longer story."));
  assert.ok(
    nodes.some(
      (x) => x.tag === "img" && x.src === "/api/location-cards/card/export.png",
    ),
  );
  assert.equal(
    nodes.filter(
      (x) => x.tag === "p" && x.textContent === "They noticed the outlines.",
    ).length,
    0,
  );
});

test("place journal history is readable and an empty unsaved edit survives rerender", async () => {
  const f = fixture();
  const folder = {
    id: "place",
    name: "Sample park",
    current_card: null,
    card_versions: [],
    visits: [
      {
        id: "visit",
        outcome_id: "walk",
        visit_date: "2026-10-11",
        note: "I noticed outlines.",
        photos: [],
        journal: {
          version_id: "new",
          mode: "local AI journal",
          status: "pending",
          text: "They noticed outlines.",
        },
        journal_versions: [
          {
            version_id: "old",
            mode: "User edited",
            status: "accepted",
            text: "They kept their earlier edit.",
          },
        ],
      },
    ],
  };
  await f.ui.renderFolder(folder, () => true);
  let nodes = f.all(f.get("folder-content"));
  assert.ok(nodes.some((x) => x.textContent === "1 earlier journal version"));
  assert.ok(
    nodes.some((x) => x.textContent === "They kept their earlier edit."),
  );
  const editor = nodes.find((x) => x.tag === "textarea");
  editor.value = "";
  editor.oninput();
  await f.ui.renderFolder(folder, () => true);
  nodes = f.all(f.get("folder-content"));
  assert.equal(nodes.find((x) => x.tag === "textarea").value, "");
});

const sampleFolder = () => ({
  id: "place",
  name: "Sample park",
  current_card: {
    id: "card",
    experience_id: "visit",
    photo_id: "photo",
    summary: "They noticed outlines.",
    visit_date: "2026-10-11",
    mode: "Manual template",
  },
  visits: [
    {
      id: "visit",
      outcome_id: "walk",
      visit_date: "2026-10-11",
      note: "I noticed outlines.",
      photos: [{ id: "photo" }],
    },
  ],
  card_versions: [],
});
test("folder reading and manual controls render before readiness resolves", async () => {
  let release;
  const f = fixture({
    api: () => new Promise((resolve) => (release = resolve)),
  });
  await f.ui.renderFolder(sampleFolder(), () => true);
  let nodes = f.all(f.get("folder-content"));
  assert.ok(nodes.some((x) => x.textContent === "Photos, visit by visit."));
  assert.equal(
    nodes.find((x) => x.textContent === "Create manual template").disabled,
    false,
  );
  assert.equal(
    nodes.find((x) => x.textContent === "Regenerate with local AI").disabled,
    true,
  );
  release({ local_ai_ready: true, model_capabilities: ["vision"] });
  await new Promise((r) => setImmediate(r));
  assert.equal(
    nodes.find((x) => x.textContent === "Regenerate with local AI").disabled,
    false,
  );
});
test("stale readiness cannot enable a newer folder and failure keeps manual actions", async () => {
  const pending = [];
  const f = fixture({
    api: () =>
      new Promise((resolve, reject) => pending.push({ resolve, reject })),
  });
  await f.ui.renderFolder(sampleFolder(), () => true);
  await f.ui.renderFolder({ ...sampleFolder(), id: "new" }, () => true);
  const nodes = f.all(f.get("folder-content"));
  pending[0].resolve({ local_ai_ready: true, model_capabilities: ["vision"] });
  await new Promise((r) => setImmediate(r));
  assert.equal(
    nodes.find((x) => x.textContent === "Regenerate with local AI").disabled,
    true,
  );
  pending[1].reject(Error("Offline"));
  await new Promise((r) => setImmediate(r));
  assert.equal(
    nodes.find((x) => x.textContent === "Create manual template").disabled,
    false,
  );
  assert.ok(
    nodes.some((x) => x.textContent.includes("manual templates still work")),
  );
});
test("unsaved card text survives rerender including an empty edit", async () => {
  const f = fixture();
  const folder = sampleFolder();
  await f.ui.renderFolder(folder, () => true);
  let nodes = f.all(f.get("folder-content"));
  const input = nodes.find((x) => x.tag === "textarea");
  input.value = "";
  input.oninput();
  await f.ui.renderFolder(folder, () => true);
  nodes = f.all(f.get("folder-content"));
  assert.equal(nodes.find((x) => x.tag === "textarea").value, "");
  assert.equal(
    nodes.find(
      (x) =>
        x.tag === "details" &&
        x.children[0].textContent === "Edit this Location Card",
    ).open,
    true,
  );
});
