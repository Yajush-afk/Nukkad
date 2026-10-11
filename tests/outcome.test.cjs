const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

function fixture() {
  const elements = new Map();
  const make = (tag, text) => ({
    tag, textContent: text || "", children: [], value: "",
    append(...children) { this.children.push(...children); },
    replaceChildren(...children) { this.children = children; },
    setAttribute() {}, style: {},
  });
  const get = (id) => {
    if (!elements.has(id)) elements.set(id, make("div"));
    return elements.get(id);
  };
  get("outcome-form").elements = Object.fromEntries(
    ["status", "note", "reason", "actual_minutes", "screen_minutes"].map((key) => [key, make("input")]),
  );
  let revision = 0;
  const journals = new Map(), messages = [];
  const context = vm.createContext({
    Map, window: {}, $: get, node: make, quest: null,
    navigation: { checkpoint: () => { const saved = revision; return () => saved === revision; } },
    formValues: () => Object.fromEntries(Object.entries(get("outcome-form").elements).map(([key, input]) => [key, input.value])),
    updateOutcomeReason() {}, labelFor: (v) => v, show() {},
    loadArea: async () => {}, message: (v) => messages.push(v), report: (e) => { throw e; },
    interestControls: async () => {}, renderPlacePhotos: async()=>{},
    api: async (path) => path.endsWith("/experiences") ? [] : journals.get(path.split("/")[2]) || null,
  });
  const source = fs.readFileSync("src/nukkad/static/app.js", "utf8");
  vm.runInContext(source.slice(source.indexOf("const outcomeDrafts"), source.indexOf("async function interestControls")), context);
  return { context, get, journals, messages, leave: () => revision++ };
}
const walk = (id) => ({ id, stops: [] });
const outcome = (id) => ({ id, original_note: id, stops: [], note: id });
test("returning to the same outcome refreshes its journal while preserving unsaved fields", async () => {
  const f = fixture();
  await f.context.renderOutcome(walk("A"), outcome("A"), () => true);
  f.get("outcome-form").elements.note.value = "Unsaved edit";
  f.journals.set("A", { text: "Completed draft", status: "pending", mode: "local AI extract" });
  await f.context.renderOutcome(walk("A"), outcome("A"), () => true);
  assert.equal(f.get("outcome-form").elements.note.value, "Unsaved edit");
  assert.ok(f.get("journal-review").children.some((item) => item.value === "Completed draft"));
});
test("a delayed save cannot publish journal B or a message over outcome A", async () => {
  const f = fixture();
  await f.context.renderOutcome(walk("B"), outcome("B"), () => true);
  let release;
  f.context.api = () => new Promise((resolve) => { release = resolve; });
  const saving = f.get("outcome-form").onsubmit({ preventDefault() {} });
  f.leave();
  f.context.api = async () => null;
  await f.context.renderOutcome(walk("A"), outcome("A"), () => true);
  release(outcome("B"));
  await saving;
  assert.equal(f.get("journal-review").children[1].textContent, "A");
  assert.equal(f.messages.length, 0);
});
