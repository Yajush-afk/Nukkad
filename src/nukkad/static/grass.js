/* A rooted pixel meadow. Only the blades bend; the bed never scrolls. */
(function (root) {
  "use strict";
  const PIXEL_SIZE = 6;
  const colours = ["#b9d298", "#a8c584", "#c8ddaa", "#a0bd7e"];
  const noise = (x, y) => {
    const value = Math.sin(x * 12.9898 + y * 78.233) * 43758.5453;
    return value - Math.floor(value);
  };
  function field(width, height) {
    const blades = [];
    for (let y = 4; y <= height + 7; y += 7) {
      for (let x = -3; x <= width + 3; x += 7) {
        const seed = noise(x, y);
        const rootX = x + Math.round(seed * 4);
        const rootY = y + Math.round(noise(y, x) * 3);
        for (let side = -1; side <= 1; side++) {
          blades.push({
            x: rootX + side,
            y: rootY,
            height: 3 + Math.floor(noise(x + side + 9, y) * 4),
            lean: side * 1.2,
            phase: seed * Math.PI * 2,
            colour:
              colours[Math.floor(noise(x + side, y + 13) * colours.length)],
          });
        }
      }
    }
    return blades;
  }
  function bend(blade, fraction, time) {
    // Coherent gusts travel through the field, with small differences between tufts.
    const gust = Math.sin(time * 1.35 - blade.x * 0.045 - blade.y * 0.025);
    const flutter = Math.sin(time * 2.1 + blade.phase) * 0.18;
    return Math.round(
      blade.lean * fraction + (gust * 2.1 + flutter) * fraction * fraction,
    );
  }
  function draw(context, width, height, blades, time) {
    context.fillStyle = "#e3edc9";
    context.fillRect(0, 0, width, height);
    for (const blade of blades) {
      context.fillStyle = blade.colour;
      for (let step = 0; step <= blade.height; step++) {
        context.fillRect(
          blade.x + bend(blade, step / blade.height, time),
          blade.y - step,
          1,
          1,
        );
      }
    }
  }
  function mount({ footer, canvas, fallback, browser }) {
    const document = browser.document;
    const reduced = browser.matchMedia("(prefers-reduced-motion: reduce)");
    let context;
    try {
      context = canvas.getContext("2d", { alpha: false });
    } catch {
      /* Use the local SVG. */
    }
    if (!context) {
      footer.dataset.grass = "static";
      footer.dataset.grassMoving = "false";
      return;
    }
    let blades = [],
      visible = false,
      frame = 0,
      last = null,
      time = 0,
      suspended = false;
    canvas.hidden = false;
    fallback.hidden = true;
    footer.dataset.grass = "canvas";
    function paint() {
      draw(context, canvas.width, canvas.height, blades, time);
    }
    function resize() {
      const box = footer.getBoundingClientRect();
      if (!box.width || !box.height) return;
      const width = Math.ceil(box.width / PIXEL_SIZE),
        height = Math.ceil(box.height / PIXEL_SIZE);
      if (width === canvas.width && height === canvas.height && blades.length)
        return;
      canvas.width = width;
      canvas.height = height;
      context.imageSmoothingEnabled = false;
      blades = field(width, height);
      paint();
    }
    function tick(now) {
      if (last === null) last = now;
      if (now - last >= 1000 / 15) {
        time += Math.min(now - last, 150) / 1000;
        last = now;
        paint();
      }
      frame = browser.requestAnimationFrame(tick);
    }
    function update() {
      browser.cancelAnimationFrame(frame);
      frame = 0;
      last = null;
      const moving =
        visible && !document.hidden && !reduced.matches && !suspended;
      footer.dataset.grassMoving = String(moving);
      if (moving) frame = browser.requestAnimationFrame(tick);
    }
    const resizeObserver = new browser.ResizeObserver(resize);
    const observer = new browser.IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting;
      update();
    });
    resizeObserver.observe(footer);
    observer.observe(footer);
    reduced.addEventListener("change", update);
    document.addEventListener("visibilitychange", update);
    browser.addEventListener("pagehide", () => {
      suspended = true;
      update();
    });
    browser.addEventListener("pageshow", () => {
      suspended = false;
      update();
    });
    resize();
    update();
  }
  root.NukkadGrass = { field, bend, draw, mount, PIXEL_SIZE };
  if (typeof module !== "undefined") module.exports = root.NukkadGrass;
  else {
    const footer = root.document.querySelector(".site-footer");
    const canvas = root.document.getElementById("pixel-grass");
    const fallback = root.document.getElementById("grass-fallback");
    if (footer && canvas && fallback)
      mount({ footer, canvas, fallback, browser: root });
  }
})(globalThis);
