(function (root) {
  "use strict";
  function create() {
    let revision = 0,
      busy = false;
    return {
      changed() {
        revision++;
      },
      begin(current) {
        if (busy) return null;
        busy = true;
        const saved = revision;
        return () => current() && saved === revision;
      },
      finish() {
        busy = false;
      },
      get busy() {
        return busy;
      },
    };
  }
  root.NukkadPlaceEditor = { create };
  if (typeof module !== "undefined") module.exports = root.NukkadPlaceEditor;
})(typeof window === "undefined" ? globalThis : window);
