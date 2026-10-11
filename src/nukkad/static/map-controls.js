(function (root) {
  "use strict";
  const percentage = (zoom, baseline) =>
    Math.round(100 * 2 ** (zoom - baseline));
  function create({ map, target, node, baseline = 15, reset }) {
    let base = baseline;
    const minus = node("button", "−"),
      value = node("button", "100%"),
      plus = node("button", "+");
    for (const button of [minus, value, plus]) button.type = "button";
    minus.setAttribute("aria-label", "Zoom out");
    plus.setAttribute("aria-label", "Zoom in");
    value.setAttribute("aria-label", "Restore map to 100%");
    target.setAttribute("role", "group");
    target.setAttribute("aria-label", "Map zoom");
    target.classList.add("map-zoom");
    target.append(minus, value, plus);
    const update = () => {
      value.textContent = percentage(map.getZoom(), base) + "%";
      minus.disabled = map.getZoom() <= map.getMinZoom();
      plus.disabled = map.getZoom() >= map.getMaxZoom();
    };
    minus.onclick = () => map.zoomOut(1, { animate: false });
    plus.onclick = () => map.zoomIn(1, { animate: false });
    value.onclick = () => (reset ? reset() : map.setZoom(base));
    map.scrollWheelZoom.disable();
    map.on("zoomend", update);
    const container = map.getContainer();
    let pinchDelta = 0;
    container.addEventListener(
      "wheel",
      (event) => {
        // Browsers represent trackpad pinch as Ctrl+wheel. Ordinary wheel passes to the page.
        if (!event.ctrlKey || event.deltaY === 0) {
          pinchDelta = 0;
          return;
        }
        event.preventDefault();
        pinchDelta += event.deltaY * (event.deltaMode === 1 ? 16 : 1);
        if (Math.abs(pinchDelta) < 60) return;
        const step = pinchDelta < 0 ? 1 : -1;
        pinchDelta = 0;
        map.setZoom(
          Math.max(
            map.getMinZoom(),
            Math.min(map.getMaxZoom(), map.getZoom() + step),
          ),
          { animate: false },
        );
      },
      { passive: false },
    );
    update();
    return {
      setBaseline(next) {
        base = next;
        update();
      },
      update,
    };
  }
  root.NukkadMapControls = { create, percentage };
  if (typeof module !== "undefined") module.exports = root.NukkadMapControls;
})(typeof window === "undefined" ? globalThis : window);
