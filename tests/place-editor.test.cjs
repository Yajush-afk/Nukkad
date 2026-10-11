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

test("typing a custom name keeps a map entrance but invalidates an online candidate", () => {
  const vm = require("node:vm"),
    fs = require("node:fs");
  const elements = new Map();
  const get = (id) => {
    if (!elements.has(id))
      elements.set(id, {
        hidden: false,
        addEventListener() {},
        scrollIntoView() {},
        focus() {},
        elements: {
          lat: { value: "" },
          lon: { value: "" },
          confirmed: { checked: false },
        },
      });
    return elements.get(id);
  };
  let config;
  const context = vm.createContext({
    $: get,
    placeEditorState: { changed() {} },
    selectedPointLayer: { clearLayers() {} },
    L: { circleMarker: () => ({ addTo() {} }) },
    NukkadSuggestions: {
      create: (value) => {
        config = value;
        return { cancel() {} };
      },
    },
    api() {},
    node() {},
    navigation: { checkpoint: () => () => true },
    map: { panTo() {} },
    area: { places: [] },
    document: { body: { dataset: { panel: "setup" } } },
  });
  const source = fs.readFileSync("src/nukkad/static/app.js", "utf8");
  vm.runInContext(
    source.slice(
      source.indexOf("let placeEntranceReady"),
      source.indexOf("function selectMapPoint("),
    ),
    context,
  );
  context.setPlaceEntrance({ lat: 28, lon: 77 });
  config.invalidate();
  assert.equal(get("pin-form").elements.lat.value, 28);
  config.select({ point: { lat: 29, lon: 78 } });
  config.invalidate();
  assert.equal(get("pin-form").elements.lat.value, "");
});
