const { test } = require("node:test");
const assert = require("node:assert/strict");
const { create } = require("../src/nukkad/static/activity.js");
function fixture(api) {
  const node = (tag, text, className) => ({
    tag,
    textContent: text || "",
    className,
    children: [],
    append(...items) {
      this.children.push(...items);
    },
    replaceChildren(...items) {
      this.children = items;
    },
  });
  const target = node("div"),
    navigated = [],
    opened = [],
    edited = [],
    requests = [];
  const ui = create({
    api: async (...args) => {
      requests.push(args);
      return api(...args);
    },
    node,
    target: () => target,
    dateFor: (value) => value,
    labelFor: (value) => value,
    navigation: { go: (...args) => navigated.push(args) },
    openWalk: (walk) => opened.push(walk),
    editWalk: (walk) => edited.push(walk),
    planWalk: () => {},
  });
  const all = (item) => [item, ...item.children.flatMap(all)];
  return { ui, target, navigated, opened, edited, requests, all };
}
const visit = {
  id: "visit:experience",
  kind: "place_visit",
  recorded_at: "2026-10-12",
  timezone: "Asia/Kolkata",
  place_id: "saved park",
  place_name: "Sample park",
  note: "I loved seeing dogs.",
  photo_count: 1,
};
test("a direct visit replaces the misleading empty walk history and links its memory", async () => {
  const f = fixture(async () => ({
    entries: [visit],
    planned_walk_count: 0,
    place_visit_count: 1,
  }));
  await f.ui.load();
  const nodes = f.all(f.target);
  assert.ok(
    nodes.some((n) => n.textContent === "1 place visit · 0 planned walks"),
  );
  assert.ok(nodes.some((n) => n.textContent === "Sample park"));
  assert.ok(nodes.some((n) => n.textContent.includes("Reported place visit")));
  assert.ok(!nodes.some((n) => n.textContent.includes("first outing")));
  const link = nodes.find((n) => n.tag === "a");
  assert.equal(link.href, "/?view=folder&place=saved%20park");
  let prevented = 0;
  link.onclick({
    button: 0,
    preventDefault() {
      prevented++;
    },
  });
  assert.deepEqual(f.navigated, [["place-folder", "saved park"]]);
  assert.equal(prevented, 1);
  link.onclick({
    button: 0,
    ctrlKey: true,
    preventDefault() {
      throw Error("modified click intercepted");
    },
  });
  assert.deepEqual(f.requests, [["/activity"]]);
});
test("mixed activity retains existing walk actions without classifying visits as routes", async () => {
  const quest = {
    id: "walk",
    stops: [{ name: "Sample destination" }],
    status: "accepted",
    estimated_minutes: 30,
    meters: 1200,
  };
  const f = fixture(async () => ({
    entries: [
      visit,
      {
        kind: "planned_walk",
        recorded_at: "2026-10-11",
        quest,
        outcome: {
          status: "completed",
          reached_ids: ["stop"],
          note: "My walk note",
        },
      },
    ],
    planned_walk_count: 1,
    place_visit_count: 1,
  }));
  await f.ui.load();
  const nodes = f.all(f.target);
  nodes.find((n) => n.textContent === "View walk").onclick();
  nodes.find((n) => n.textContent === "Edit note & visits").onclick();
  assert.deepEqual(f.opened, [quest]);
  assert.deepEqual(f.edited, [quest]);
  assert.equal(nodes.filter((n) => n.tag === "article").length, 2);
});
test("late activity results cannot replace another screen and empty state covers both paths", async () => {
  let finish;
  const f = fixture(() => new Promise((resolve) => (finish = resolve)));
  let current = true;
  const pending = f.ui.load(() => current);
  current = false;
  finish({ entries: [visit], planned_walk_count: 0, place_visit_count: 1 });
  await pending;
  assert.equal(f.target.children.length, 0);
  const empty = fixture(async () => ({
    entries: [],
    planned_walk_count: 0,
    place_visit_count: 0,
  }));
  await empty.ui.load();
  const nodes = empty.all(empty.target);
  nodes.find((n) => n.textContent === "Open my neighbourhood").onclick();
  assert.deepEqual(empty.navigated, [["setup"]]);
  assert.ok(nodes.some((n) => n.textContent.includes("Both appear here")));
});
