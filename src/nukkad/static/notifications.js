(function (root) {
  "use strict";
  function create({
    target,
    node,
    setTimer = setTimeout,
    clearTimer = clearTimeout,
    now = Date.now,
  }) {
    const visible = [],
      pending = [];
    function resume(item) {
      if (item.error || item.hovered || item.focused || item.timer) return;
      item.started = now();
      item.timer = setTimer(() => dismiss(item), item.remaining);
    }
    function pause(item) {
      if (!item.timer) return;
      clearTimer(item.timer);
      item.timer = null;
      item.remaining = Math.max(0, item.remaining - (now() - item.started));
    }
    function draw() {
      while (visible.length < 3 && pending.length) {
        const item = pending.shift();
        const box = node(
          "div",
          undefined,
          "notification" + (item.error ? " notification-error" : ""),
        );
        box.setAttribute("role", item.error ? "alert" : "status");
        box.setAttribute("aria-atomic", "true");
        const icon = node("span", item.error ? "!" : "✓", "notification-icon");
        icon.setAttribute("aria-hidden", "true");
        const dismissButton = node("button", "×", "notification-dismiss");
        dismissButton.type = "button";
        dismissButton.setAttribute("aria-label", "Dismiss notification");
        dismissButton.onclick = () => dismiss(item);
        box.append(icon, node("span", item.text), dismissButton);
        box.onmouseenter = () => {
          item.hovered = true;
          pause(item);
        };
        box.onmouseleave = () => {
          item.hovered = false;
          resume(item);
        };
        box.onfocusin = () => {
          item.focused = true;
          pause(item);
        };
        box.onfocusout = (event) => {
          if (box.contains?.(event.relatedTarget)) return;
          item.focused = false;
          resume(item);
        };
        item.box = box;
        visible.push(item);
        target.append(box);
        resume(item);
      }
    }
    function dismiss(item) {
      pause(item);
      const index = visible.indexOf(item);
      if (index < 0) return;
      visible.splice(index, 1);
      item.box.remove();
      draw();
    }
    function notify(text, error = false) {
      if (!text) return;
      const old = [...visible, ...pending].find(
        (item) => item.text === text && item.error === error,
      );
      if (old) {
        pause(old);
        old.remaining = 5000;
        if (visible.includes(old)) resume(old);
        return;
      }
      pending.push({ text, error, remaining: 5000 });
      draw();
    }
    return { notify };
  }
  async function copyEmail({
    clipboard,
    tooltip,
    notify,
    setTimer = setTimeout,
  }) {
    try {
      await clipboard.writeText("yajush24606@gmail.com");
      tooltip.textContent = "Mail Copied";
      tooltip.hidden = false;
      setTimer(() => {
        tooltip.hidden = true;
      }, 2000);
      return true;
    } catch (_) {
      tooltip.hidden = true;
      notify(
        "Could not copy the email. Select the address and copy it manually.",
        true,
      );
      return false;
    }
  }
  root.NukkadNotifications = { create, copyEmail };
  if (typeof module !== "undefined") module.exports = root.NukkadNotifications;
})(typeof window === "undefined" ? globalThis : window);
