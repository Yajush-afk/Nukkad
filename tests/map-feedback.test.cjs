const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
test("map failure feedback is short while exact provider details remain available", () => {
  const app = fs.readFileSync("src/nukkad/static/app.js", "utf8");
  const source = app.slice(
    app.indexOf("function report(error)"),
    app.indexOf("function formValues"),
  );
  const elements = new Map(),
    notices = [];
  const context = {
    $: (id) => {
      if (!elements.has(id)) elements.set(id, {});
      return elements.get(id);
    },
    message: (...args) => notices.push(args),
  };
  vm.runInNewContext(
    source +
      '\nreport({message:"Could not download this neighbourhood. Overpass (main): HTTP 504; Private.coffee: HTTP 500"});',
    context,
  );
  assert.equal(elements.get("map-download-error").hidden, false);
  assert.match(
    elements.get("map-download-error-detail").textContent,
    /HTTP 504/,
  );
  assert.ok(notices[0][0].length < 110);
  assert.doesNotMatch(notices[0][0], /Overpass|HTTP/);
  assert.equal(notices[0][1], true);
});
