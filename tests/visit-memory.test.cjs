const { test } = require("node:test");
const assert = require("node:assert/strict");
const { create } = require("../src/nukkad/static/visit-memory.js");
test("save-triggered preparation coalesces callers and never starts from reads", async () => {
  let calls = 0,
    release;
  const ui = create({
    api: async (path, options) => {
      calls++;
      assert.equal(options.method, "POST");
      assert.equal(options.body.source_revision, "r1");
      return { id: "job" };
    },
    runJob: async (job, finished) => {
      await new Promise((resolve) => (release = resolve));
      return finished({ card_id: "card", journal_mode: "local AI journal" });
    },
  });
  assert.equal(calls, 0);
  const visit = { id: "visit", revision: "r1" };
  const one = ui.prepare(visit);
  const two = ui.prepare(visit);
  assert.equal(one, two);
  await new Promise((resolve) => setImmediate(resolve));
  release();
  assert.equal((await one).card_id, "card");
  assert.equal(calls, 1);
});
test("departed-screen completion is read from the original job, without another model request", async () => {
  const calls = [];
  const ui = create({
    api: async (path, options) => {
      calls.push({ path, options });
      return options
        ? { id: "original" }
        : { status: "complete", result: { card_id: "card" } };
    },
    runJob: async () => undefined,
  });
  assert.equal(
    (await ui.prepare({ id: "visit", revision: "r1" }, () => false)).card_id,
    "card",
  );
  assert.deepEqual(
    calls.map((x) => x.path),
    ["/experiences/visit/prepare", "/jobs/original"],
  );
});
