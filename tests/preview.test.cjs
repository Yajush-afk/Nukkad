const { test } = require("node:test");
const assert = require("node:assert/strict");
const vm = require("node:vm");
const fs = require("node:fs");
test("a saved preview reload renders all stops and next actions without the neighbourhood map", () => {
  const elements = new Map();
  const node = (tag, text) => ({
    tag,
    textContent: text,
    children: [],
    append(...x) {
      this.children.push(...x);
    },
    replaceChildren(...x) {
      this.children = x;
    },
    setAttribute() {},
  });
  const $ = (id) => {
    if (!elements.has(id)) elements.set(id, node("div"));
    return elements.get(id);
  };
  const context = vm.createContext({
    $,
    node,
    quest: null,
    navigation: { checkpoint: () => () => true, isCurrent: () => true },
    renderRouteMap: async () => {},
    report: (e) => {
      throw e;
    },
    timeFor: () => "",
    dateFor: () => "",
    accessNote: () => "Mapped entrance",
    disclosure: (title, ...children) => {
      const x = node("details", title);
      x.append(...children);
      return x;
    },
  });
  const source = fs.readFileSync("src/nukkad/static/app.js", "utf8");
  vm.runInContext(
    source.slice(
      source.indexOf("function renderQuest("),
      source.indexOf("async function loadHistory("),
    ),
    context,
  );
  context.renderQuest(
    {
      id: "saved",
      status: "accepted",
      estimated_minutes: 25,
      meters: 600,
      stops: [{ id: "p", name: "Sample park" }],
      latest_departure: "",
      generated_at: "",
      timezone: "UTC",
      sunset: "",
      settings: { daylight_required: true },
      ranking_mode: "basic rules",
      prose_mode: "standard prompts",
      prompts: { p: { text: "Notice outlines." } },
      legs: [{ streets: ["Lane"] }, { streets: ["Lane"] }],
      reasons: {},
      model: "test",
      generation_seconds: 0,
    },
    false,
  );
  assert.equal(
    $("quest-content").children.filter((x) => x.tag === "div").length,
    2,
  );
  assert.equal($("download").hidden, false);
  assert.equal($("return").hidden, false);
  assert.equal($("card-preview").hidden, false);
});
