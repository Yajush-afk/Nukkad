(function (root) {
  "use strict";
  function create({
    input,
    target,
    status,
    scope,
    api,
    node,
    select,
    invalidate = () => {},
    current = () => true,
    setTimer = setTimeout,
    clearTimer = clearTimeout,
  }) {
    let revision = 0,
      timer,
      controller,
      activeId = null,
      matches = [],
      local = [],
      remoteBusy = false,
      pending = null;
    input.setAttribute("role", "combobox");
    input.setAttribute("aria-autocomplete", "list");
    input.setAttribute("aria-controls", target.id);
    input.setAttribute("aria-expanded", "false");
    input.autocomplete = "off";
    target.setAttribute("role", "listbox");
    function close() {
      target.hidden = true;
      input.setAttribute("aria-expanded", "false");
      input.removeAttribute("aria-activedescendant");
      activeId = null;
    }
    function cancel() {
      revision++;
      clearTimer(timer);
      controller?.abort();
      pending = null;
      close();
    }
    function choose(item) {
      cancel();
      input.value = item.name;
      select(item);
    }
    function paint(items) {
      matches = items;
      target.replaceChildren();
      let group;
      items.forEach((item, index) => {
        if (item.group !== group) {
          group = item.group;
          const title = node("li", group, "suggestion-group");
          title.setAttribute("role", "presentation");
          target.append(title);
        }
        const option = node("li", undefined, "suggestion-option");
        option.id = target.id + "-option-" + index;
        option.setAttribute("role", "option");
        option.setAttribute("aria-selected", String(activeId === item.id));
        option.append(node("strong", item.name), node("span", item.label));
        option.onmousedown = (e) => e.preventDefault();
        option.onclick = () => choose(item);
        target.append(option);
        if (activeId === item.id)
          input.setAttribute("aria-activedescendant", option.id);
      });
      if (!items.some((x) => x.id === activeId)) {
        activeId = null;
        input.removeAttribute("aria-activedescendant");
      }
      target.hidden = !items.length;
      input.setAttribute("aria-expanded", String(!!items.length));
    }
    function valid(r) {
      return revision === r && current();
    }
    async function online(job) {
      if (remoteBusy) {
        pending = job;
        return;
      }
      remoteBusy = true;
      controller = new AbortController();
      try {
        const result = await api("/locations/suggest", {
          method: "POST",
          body: { query: job.query, scope, online: true },
          signal: controller.signal,
        });
        if (!valid(job.r)) return;
        const merged = [...local];
        const seen = new Set(merged.map((x) => x.place_id || x.id));
        for (const item of result.matches) {
          const key = item.place_id || item.id;
          if (!seen.has(key)) {
            merged.push(item);
            seen.add(key);
          }
        }
        paint(merged);
        status.textContent =
          result.online.message ||
          (!merged.length
            ? "No suggestions. Try Search or choose an entrance on your map."
            : "Choose a matching place.");
        status.hidden = false;
      } catch (error) {
        if (valid(job.r) && error.name !== "AbortError") {
          status.textContent =
            "Online suggestions unavailable. Local matches and Search still work.";
          status.hidden = false;
        }
      } finally {
        remoteBusy = false;
        controller = null;
        const next = pending;
        pending = null;
        if (next && valid(next.r)) online(next);
      }
    }
    async function changed() {
      cancel();
      invalidate();
      local = [];
      matches = [];
      target.replaceChildren();
      status.hidden = true;
      const query = input.value.trim();
      if (query.length < 3) return;
      const r = revision;
      timer = setTimer(() => online({ query, r }), 400);
      try {
        const result = await api("/locations/suggest", {
          method: "POST",
          body: { query, scope, online: false },
        });
        if (!valid(r)) return;
        local = result.matches; // Never replace already returned online matches with a slower local reply.
        const onlineItems = matches.filter((x) => x.group === "Online results");
        paint([...local, ...onlineItems]);
      } catch (error) {
        if (valid(r)) {
          status.textContent = error.message;
          status.hidden = false;
        }
      }
    }
    input.addEventListener("input", changed);
    input.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        cancel();
        return;
      }
      if (event.key === "Tab") {
        close();
        return;
      }
      if (target.hidden) return;
      if (event.key === "Enter" && activeId) {
        event.preventDefault();
        choose(matches.find((x) => x.id === activeId));
        return;
      }
      if (!["ArrowDown", "ArrowUp"].includes(event.key)) return;
      event.preventDefault();
      const index = matches.findIndex((x) => x.id === activeId);
      const next =
        event.key === "ArrowDown"
          ? (index + 1) % matches.length
          : index < 0
            ? matches.length - 1
            : (index - 1 + matches.length) % matches.length;
      activeId = matches[next].id;
      paint(matches);
    });
    input.addEventListener("blur", () => {
      setTimer(close, 150);
    });
    return { cancel, changed, choose };
  }
  root.NukkadSuggestions = { create };
  if (typeof module !== "undefined") module.exports = root.NukkadSuggestions;
})(typeof window === "undefined" ? globalThis : window);
