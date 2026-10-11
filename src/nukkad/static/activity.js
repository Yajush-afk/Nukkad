/* Visits do not need a generated route. Reading activity never starts AI. */
(function (root) {
  "use strict";
  function create({
    api,
    node,
    target,
    dateFor,
    labelFor,
    navigation,
    openWalk,
    editWalk,
    planWalk,
  }) {
    function noteText(item, text) {
      if (!text) return;
      item.append(
        node("p", text.length > 280 ? text.slice(0, 280) + "…" : text),
      );
      if (text.length > 280) {
        const full = node("details");
        full.append(node("summary", "Read the full note"), node("p", text));
        item.append(full);
      }
    }
    const button = (label, click) => {
      const element = node("button", label);
      element.type = "button";
      element.onclick = click;
      return element;
    };
    async function load(current = () => true) {
      const activity = await api("/activity");
      if (!current()) return;
      const container = target();
      container.replaceChildren();
      container.append(
        node(
          "p",
          `${activity.place_visit_count} place ${activity.place_visit_count === 1 ? "visit" : "visits"} · ${activity.planned_walk_count} planned ${activity.planned_walk_count === 1 ? "walk" : "walks"}`,
          "collection-count",
        ),
      );
      if (!activity.entries.length) {
        const empty = node("div", undefined, "entry");
        empty.append(
          node("h3", "Your first outing starts here."),
          node(
            "p",
            "Add an experience from your map, or plan a walk. Both appear here.",
            "hint",
          ),
          button("Open my neighbourhood", () => navigation.go("setup")),
          button("Plan a walk", planWalk),
        );
        container.append(empty);
        return;
      }
      for (const entry of activity.entries) {
        const item = node("article", undefined, "entry");
        if (entry.kind === "place_visit") {
          item.append(
            node(
              "p",
              `${dateFor(entry.recorded_at, entry.timezone)} · Reported place visit`,
              "eyebrow",
            ),
            node("h3", entry.place_name),
            node(
              "p",
              `${entry.photo_count} ${entry.photo_count === 1 ? "photo" : "photos"} · Visited without a planned route`,
              "hint",
            ),
          );
          noteText(item, entry.note);
          const link = node("a", "Open place memory", "download-link");
          link.href = `/?view=folder&place=${encodeURIComponent(entry.place_id)}`;
          link.onclick = (event) => {
            if (
              event.button !== 0 ||
              event.metaKey ||
              event.ctrlKey ||
              event.shiftKey ||
              event.altKey
            )
              return;
            event.preventDefault();
            void navigation.go("place-folder", entry.place_id);
          };
          item.append(link);
        } else {
          const value = entry.quest,
            outcome = entry.outcome;
          item.append(
            node(
              "p",
              `${dateFor(entry.recorded_at, value.timezone)} · Planned walk · ${outcome ? labelFor(outcome.status) : value.status === "accepted" ? "Saved walk" : labelFor(value.status)}`,
              "eyebrow",
            ),
            node("h3", value.stops.map((stop) => stop.name).join(" / ")),
            node(
              "p",
              `${value.estimated_minutes} min planned · ${(value.meters / 1000).toFixed(2)} km${outcome ? ` · ${outcome.reached_ids.length} stops reported reached` : ""}`,
              "hint",
            ),
          );
          noteText(item, outcome?.note);
          const actions = node("div", undefined, "buttonrow");
          actions.append(button("View walk", () => openWalk(value)));
          if (value.status === "accepted")
            actions.append(
              button(outcome ? "Edit note & visits" : "Add note & visits", () =>
                editWalk(value),
              ),
            );
          item.append(actions);
        }
        container.append(item);
      }
    }
    return { load };
  }
  root.NukkadActivity = { create };
  if (typeof module !== "undefined") module.exports = root.NukkadActivity;
})(globalThis);
