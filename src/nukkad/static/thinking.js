(function (root) {
  "use strict";
  const phrases = [
    "A little local magic…",
    "Connecting the little details…",
    "Giving this a little thought…",
    "Good things take a moment…",
  ];

  // A tiny local shader keeps the fluid sphere independent of a 3D library.
  function renderer(canvas) {
    const gl = canvas.getContext("webgl", { alpha: true, antialias: false });
    if (!gl) return null; // The CSS sphere remains visible without WebGL.
    function shader(type, source) {
      const value = gl.createShader(type);
      gl.shaderSource(value, source);
      gl.compileShader(value);
      if (!gl.getShaderParameter(value, gl.COMPILE_STATUS)) {
        gl.deleteShader(value);
        return null;
      }
      return value;
    }
    const vertex = shader(gl.VERTEX_SHADER, `
      attribute vec2 position;
      varying vec2 uv;
      void main() { uv = position; gl_Position = vec4(position, 0., 1.); }
    `);
    const fragment = shader(gl.FRAGMENT_SHADER, `
      precision mediump float;
      uniform float time;
      varying vec2 uv;
      void main() {
        vec2 p = uv * 1.08;
        float radius = length(p);
        float edge = 1. + .025 * sin(atan(p.y, p.x) * 5. + time);
        float alpha = 1. - smoothstep(edge - .025, edge, radius);
        vec3 n = vec3(p, sqrt(max(0., 1. - dot(p, p))));
        float flow = sin(n.x * 5. + sin(n.y * 6. + time * .7) + time * .6)
                   * cos(n.y * 4. - n.z * 5. + time * .4);
        float bands = smoothstep(-.65, .8, flow);
        vec3 color = mix(vec3(.015, .03, .52), vec3(.13, .28, 1.), bands);
        float light = max(0., dot(n, normalize(vec3(-.5, .6, 1.))));
        color *= .45 + light * .65;
        float shine = pow(max(0., dot(normalize(n), normalize(vec3(-.4, .65, 1.)))), 28.);
        color += vec3(.65, .76, 1.) * shine * .85;
        color += vec3(.12, .18, .6) * pow(1. - n.z, 3.);
        gl_FragColor = vec4(color, alpha);
      }
    `);
    if (!vertex || !fragment) {
      if (vertex) gl.deleteShader(vertex);
      if (fragment) gl.deleteShader(fragment);
      return null;
    }
    const program = gl.createProgram();
    gl.attachShader(program, vertex);
    gl.attachShader(program, fragment);
    gl.linkProgram(program);
    gl.deleteShader(vertex);
    gl.deleteShader(fragment);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      gl.deleteProgram(program);
      return null;
    }
    gl.useProgram(program);
    const buffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
    const position = gl.getAttribLocation(program, "position");
    gl.enableVertexAttribArray(position);
    gl.vertexAttribPointer(position, 2, gl.FLOAT, false, 0, 0);
    const time = gl.getUniformLocation(program, "time");
    return (seconds) => {
      gl.viewport(0, 0, canvas.width, canvas.height);
      gl.uniform1f(time, seconds);
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    };
  }

  function create({
    canvas, phrase, onChange = () => {},
    document: page = root.document,
    motion = root.matchMedia("(prefers-reduced-motion: reduce)"),
    requestFrame = root.requestAnimationFrame.bind(root),
    cancelFrame = root.cancelAnimationFrame.bind(root),
    setTimer = setTimeout, clearTimer = clearTimeout,
    makeRenderer = renderer,
  }) {
    let active = false, frame = null, timer = null, draw, index = 0, lastFrame = 0;
    function clear() {
      if (frame !== null) cancelFrame(frame);
      if (timer !== null) clearTimer(timer);
      frame = timer = null;
    }
    function animate(time) {
      // 30fps is plenty for a 44px orb alongside local inference.
      if (time - lastFrame >= 33) {
        draw(time / 1000);
        lastFrame = time;
      }
      frame = requestFrame(animate);
    }
    function cycle() {
      index = (index + 1) % phrases.length;
      phrase.textContent = phrases[index];
      onChange();
      timer = setTimer(cycle, 4200);
    }
    function sync() {
      clear();
      if (!active || page.hidden) return;
      if (draw) draw(0);
      if (motion.matches) return;
      if (draw) frame = requestFrame(animate);
      timer = setTimer(cycle, 4200);
    }
    page.addEventListener("visibilitychange", sync);
    motion.addEventListener("change", sync);
    canvas.addEventListener("webglcontextlost", (event) => {
      event.preventDefault();
      draw = null;
      sync();
    });
    canvas.addEventListener("webglcontextrestored", () => {
      draw = undefined;
      if (active) {
        try { draw = makeRenderer(canvas); } catch (_) { draw = null; }
      }
      sync();
    });
    return {
      start() {
        active = true;
        index = 0;
        phrase.textContent = phrases[0];
        if (draw === undefined) {
          try { draw = makeRenderer(canvas); } catch (_) { draw = null; }
        }
        sync();
      },
      stop() { active = false; clear(); },
    };
  }
  root.NukkadThinking = { create };
  if (typeof module !== "undefined") module.exports = root.NukkadThinking;
})(typeof window === "undefined" ? globalThis : window);
