"use strict";

// Decorative motion is isolated from the map, forms and local AI workflow.
(() => {
  const hero = document.getElementById("sky-hero");
  const canvas = document.getElementById("pixel-sky");
  const control = document.getElementById("sky-motion");
  const fallback = document.getElementById("sky-fallback");
  const text = document.getElementById("typewriter");
  const reduced = matchMedia("(prefers-reduced-motion: reduce)");
  const phrase = text.textContent;
  let paused = false;
  let visible = false;
  let frame = 0;
  let lastFrame = 0;
  let time = 0;
  let gl;
  let program;
  let timeUniform;
  let resolutionUniform;
  let typeTimer = 0;
  let index = 0;

  function finishTyping() {
    clearTimeout(typeTimer);
    text.textContent = phrase;
    hero.classList.remove("typing");
  }
  function typeNext() {
    if (paused || reduced.matches) return finishTyping();
    text.textContent = phrase.slice(0, ++index);
    if (index < phrase.length) typeTimer = setTimeout(typeNext, 48);
    else hero.classList.remove("typing");
  }

  // This is the supplied domain-warped billow shader adapted to native WebGL.
  // Render one fragment per 6 CSS pixels, then scale with nearest-neighbour
  // sampling: pixel art does not need a full-resolution GPU framebuffer.
  const vertex = `
    attribute vec2 position;
    void main() { gl_Position = vec4(position, 0.0, 1.0); }
  `;
  const fragment = `
    precision highp float;
    uniform vec2 uResolution;
    uniform float uTime;
    const mat2 R = mat2(0.80, 0.60, -0.60, 0.80);
    float hash(vec2 p) { return fract(sin(dot(p, vec2(41.31, 289.17))) * 26737.367); }
    float noise(vec2 p) {
      vec2 i = floor(p), f = fract(p);
      f = f * f * (3.0 - 2.0 * f);
      return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), f.x),
                 mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), f.x), f.y);
    }
    float fbm(vec2 p) {
      float s = 0.0, a = 0.5;
      for (int i = 0; i < 4; i++) { s += a * noise(p); p = R * p * 2.03 + 19.19; a *= 0.5; }
      return s;
    }
    float billow(vec2 p) {
      float s = 0.0, a = 0.5;
      for (int i = 0; i < 5; i++) { s += a * (1.0 - abs(2.0 * noise(p) - 1.0)); p = R * p * 2.11 + 13.37; a *= 0.5; }
      return s;
    }
    float density(vec2 p, vec2 c, vec2 r, float seed) {
      vec2 q = p - c;
      float ry = q.y > 0.0 ? r.y : r.y * 0.42;
      float env = 1.0 - length(vec2(q.x / r.x, q.y / ry));
      if (env < -0.35) return 0.0;
      vec2 dp = q * (2.4 / r.x) + seed;
      dp += 0.6 * vec2(fbm(dp * 1.4 + uTime * 0.04), fbm(dp * 1.4 + 7.7 - uTime * 0.03));
      return env + (billow(dp * 1.6) - 0.62) * 0.62;
    }
    vec3 cloud(vec3 color, vec3 sky, vec2 p, float aspect, float speed,
               float phase, float y, vec2 r, float seed, float distance) {
      float cx = mix(-r.x - 0.25, aspect + r.x + 0.25, fract(uTime * speed + phase));
      vec2 c = vec2(cx, y + sin(uTime * 0.05 + phase * 6.2831) * 0.012);
      float d = floor(density(p, c, r, seed) / 0.1) * 0.1;
      if (d < 0.02) return color;
      float up = density(p + vec2(0.0, r.y * 0.55), c, r, seed);
      float occlusion = floor(clamp((up - d) * 1.1 + d * 0.55, 0.0, 1.0) * 3.0) / 3.0;
      vec3 cream = vec3(0.984, 0.973, 0.949);
      vec3 shaded = mix(cream * 1.04, mix(cream * 0.60, sky, 0.38), occlusion * 0.85);
      return mix(shaded, sky, distance * 0.35);
    }
    void main() {
      vec2 uv = floor(gl_FragCoord.xy) / uResolution;
      float aspect = uResolution.x / uResolution.y;
      vec2 p = vec2(uv.x * aspect, uv.y);
      vec3 sky = mix(vec3(0.47, 0.70, 0.87), vec3(0.12, 0.30, 0.58), uv.y);
      vec3 color = sky;
      color = cloud(color, sky, p, aspect, 0.003, 0.10, 0.84, vec2(0.20, 0.10), 43.7, 1.0);
      color = cloud(color, sky, p, aspect, 0.004, 0.62, 0.73, vec2(0.24, 0.12), 71.3, 0.85);
      color = cloud(color, sky, p, aspect, 0.005, 0.33, 0.66, vec2(0.34, 0.16), 17.3, 0.55);
      color = cloud(color, sky, p, aspect, 0.006, 0.80, 0.52, vec2(0.30, 0.15), 29.9, 0.45);
      color = cloud(color, sky, p, aspect, 0.008, 0.05, 0.30, vec2(0.46, 0.20), 91.1, 0.15);
      color = cloud(color, sky, p, aspect, 0.010, 0.48, 0.18, vec2(0.56, 0.24), 57.2, 0.0);
      // Keep the wordmark and subline readable as bright clouds drift behind them.
      float textZone = 1.0 - smoothstep(0.18, 0.60, length((uv - vec2(0.5, 0.57)) * vec2(1.0, 1.2)));
      color = mix(color, sky, textZone * 0.85);
      gl_FragColor = vec4(color, 1.0);
    }
  `;

  function compile(type, source) {
    const shader = gl.createShader(type);
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
      gl.deleteShader(shader);
      throw Error("Sky shader unavailable");
    }
    return shader;
  }
  function draw() {
    if (!gl || gl.isContextLost()) return;
    gl.uniform1f(timeUniform, time);
    gl.drawArrays(gl.TRIANGLES, 0, 6);
  }
  function resize() {
    const box = hero.getBoundingClientRect();
    if (!box.width || !box.height) return;
    hero.style.setProperty("--sky-width", `${box.width}px`);
    if (!gl || gl.isContextLost()) return;
    canvas.width = Math.ceil(box.width / 6);
    canvas.height = Math.ceil(box.height / 6);
    gl.viewport(0, 0, canvas.width, canvas.height);
    gl.uniform2f(resolutionUniform, canvas.width, canvas.height);
    draw();
  }
  function tick(now) {
    if (!lastFrame) lastFrame = now;
    if (now - lastFrame >= 1000 / 24) {
      time += Math.min(now - lastFrame, 100) / 1000;
      lastFrame = now;
      draw();
    }
    frame = requestAnimationFrame(tick);
  }
  function updateMotion() {
    cancelAnimationFrame(frame);
    frame = 0;
    lastFrame = 0;
    const stopped = paused || reduced.matches;
    control.setAttribute("aria-pressed", String(stopped));
    control.textContent = stopped ? "Resume sky ▷" : "Pause sky Ⅱ";
    // Respect an OS motion preference even if the user clicks Resume.
    control.disabled = reduced.matches;
    if (reduced.matches) control.textContent = "Still sky";
    if (stopped) finishTyping();
    const moving =
      visible &&
      !stopped &&
      !document.hidden &&
      document.body.dataset.panel === "home";
    hero.dataset.moving = String(moving);
    if (gl && moving) {
      frame = requestAnimationFrame(tick);
    }
  }
  function setupSky() {
    try {
      gl = canvas.getContext("webgl", {
        alpha: false,
        antialias: false,
        depth: false,
        stencil: false,
        powerPreference: "low-power",
      });
      if (!gl) throw Error("WebGL unavailable");
      const shaders = [
        compile(gl.VERTEX_SHADER, vertex),
        compile(gl.FRAGMENT_SHADER, fragment),
      ];
      program = gl.createProgram();
      shaders.forEach((shader) => gl.attachShader(program, shader));
      gl.linkProgram(program);
      shaders.forEach((shader) => gl.deleteShader(shader));
      if (!gl.getProgramParameter(program, gl.LINK_STATUS))
        throw Error("Sky program unavailable");
      gl.useProgram(program);
      const buffer = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
      gl.bufferData(
        gl.ARRAY_BUFFER,
        new Float32Array([-1, -1, 1, -1, -1, 1, -1, 1, 1, -1, 1, 1]),
        gl.STATIC_DRAW,
      );
      const position = gl.getAttribLocation(program, "position");
      gl.enableVertexAttribArray(position);
      gl.vertexAttribPointer(position, 2, gl.FLOAT, false, 0, 0);
      timeUniform = gl.getUniformLocation(program, "uTime");
      resolutionUniform = gl.getUniformLocation(program, "uResolution");
      canvas.hidden = false;
      fallback.hidden = true;
      hero.dataset.sky = "webgl";
      resize();
    } catch {
      // The bundled static pixel sky remains usable without graphics support.
      gl = null;
      canvas.hidden = true;
      fallback.hidden = false;
      hero.dataset.sky = "css";
      resize();
    }
    updateMotion();
  }
  canvas.addEventListener("webglcontextlost", (event) => {
    event.preventDefault();
    cancelAnimationFrame(frame);
    gl = null;
    canvas.hidden = true;
    fallback.hidden = false;
    hero.dataset.sky = "css";
    updateMotion();
  });
  canvas.addEventListener("webglcontextrestored", setupSky);
  control.addEventListener("click", () => {
    paused = !paused;
    updateMotion();
  });
  reduced.addEventListener("change", updateMotion);
  document.addEventListener("visibilitychange", updateMotion);
  document.addEventListener("nukkad:panel", () => {
    finishTyping();
    updateMotion();
  });
  new ResizeObserver(resize).observe(hero);
  new IntersectionObserver(([entry]) => {
    visible = entry.isIntersecting;
    updateMotion();
  }).observe(hero);
  window.addEventListener("pagehide", () => {
    cancelAnimationFrame(frame);
    finishTyping();
  });
  window.addEventListener("pageshow", updateMotion);
  setupSky();
  if (!reduced.matches) {
    text.textContent = "";
    hero.classList.add("typing");
    typeTimer = setTimeout(typeNext, 250);
  }
})();
