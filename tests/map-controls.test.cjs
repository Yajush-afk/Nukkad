const { test } = require("node:test");
const assert = require("node:assert/strict");
const { create, percentage } = require("../src/nukkad/static/map-controls.js");
function fixture() {
  let zoom = 15;
  const events = {};
  const container = {
    addEventListener(k, cb) {
      events[k] = cb;
    },
  };
  const target = {
    children: [],
    classList: { add() {} },
    setAttribute() {},
    append(...x) {
      this.children.push(...x);
    },
  };
  const node = (tag, text) => ({ tag, textContent: text, setAttribute() {} });
  const map = {
    getZoom: () => zoom,
    getMinZoom: () => 12,
    getMaxZoom: () => 19,
    scrollWheelZoom: { disable() {} },
    on(k, cb) {
      events[k] = cb;
    },
    getContainer: () => container,
    setZoom(x) {
      zoom = x;
      events.zoomend();
    },
    zoomOut() {
      this.setZoom(zoom - 1);
    },
    zoomIn() {
      this.setZoom(zoom + 1);
    },
  };
  return { target, map, events, ui: create({ map, target, node }) };
}
test("baseline percentage, limits and horizontal reset controls", () => {
  const f = fixture();
  assert.equal(percentage(16, 15), 200);
  assert.equal(percentage(14, 15), 50);
  f.target.children[2].onclick();
  assert.equal(f.target.children[1].textContent, "200%");
  f.map.setZoom(19);
  assert.equal(f.target.children[2].disabled, true);
  f.target.children[1].onclick();
  assert.equal(f.map.getZoom(), 15);
  f.map.setZoom(12);
  assert.equal(f.target.children[0].disabled, true);
});
test("ordinary wheel passes through while deliberate pinch changes zoom", () => {
  const f = fixture();
  let prevented = false;
  const event = {
    deltaY: -100,
    preventDefault() {
      prevented = true;
    },
  };
  f.events.wheel(event);
  assert.equal(prevented, false);
  assert.equal(f.map.getZoom(), 15);
  f.events.wheel({ ...event, ctrlKey: true });
  assert.equal(prevented, true);
  assert.equal(f.map.getZoom(), 16);
});
test("a fitted route can set its own baseline and reset action", () => {
  const f = fixture();
  f.ui.setBaseline(14);
  assert.equal(f.target.children[1].textContent, "200%");
});

test('delayed map fitting checks both navigation and walk identity',()=>{
 const source=require('node:fs').readFileSync('src/nukkad/static/app.js','utf8');
 const route=source.slice(source.indexOf('async function renderRouteMap('),source.indexOf('// Resolve routes'));
 assert.match(route,/if \(!current\(\) \|\| quest\?\.id !== value.id\) return/);
 assert.match(route,/routeFitId!==value.id/);
 assert.match(source,/map.setView\(\[area.area.start.lat,area.area.start.lon\],15\)/);
 assert.doesNotMatch(source,/getCurrentPosition/);
});
