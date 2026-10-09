"use strict";
const $ = (id) => document.getElementById(id);
let area,
  quest,
  activeJob,
  map,
  geometryLayer,
  placesLayer,
  routeLayer,
  sessionToken,
  questMap,
  questLayers;
const node = (tag, text, className) => {
  const e = document.createElement(tag);
  if (text !== undefined) e.textContent = text;
  if (className) e.className = className;
  return e;
};
function message(text) {
  $("message").textContent = text;
  $("message").hidden = !text;
}
async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (sessionToken) headers["X-Nukkad-Token"] = sessionToken;
  if (options.body && !(options.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(options.body);
  }
  const r = await fetch("/api" + path, { ...options, headers });
  if (!r.ok) {
    let body = await r.json();
    throw Error(
      typeof body.detail === "string"
        ? body.detail
        : "Check the entered values.",
    );
  }
  return r.json();
}
function show(id) {
  document.querySelectorAll(".panel").forEach((e) => (e.hidden = e.id !== id));
  message("");
  if (id === "home") setTimeout(() => map.invalidateSize(), 30);
  if (id === "history") loadHistory().catch(report);
  if (id === "settings") api("/air-quality").then(renderAir).catch(report);
  window.scrollTo(0, 0);
}
function report(error) {
  message(error.message || String(error));
}
function formValues(id) {
  return Object.fromEntries(new FormData($(id)));
}
async function runJob(value, finished) {
  activeJob = value.id;
  $("job").hidden = false;
  while (activeJob === value.id) {
    const job = await api("/jobs/" + value.id);
    $("job-message").textContent = job.message;
    if (
      ["complete", "failed", "cancelled", "interrupted"].includes(job.status)
    ) {
      activeJob = null;
      $("job").hidden = true;
      if (job.status === "complete") return finished(job.result);
      throw Error(job.message);
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
}
async function loadArea() {
  area = await api("/area");
  geometryLayer.clearLayers();
  placesLayer.clearLayers();
  routeLayer.clearLayers();
  if (!area.area) return;
  $("area-name").textContent = area.area.name.toUpperCase();
  $("progress").textContent =
    `${area.progress.mapped_visited} / ${area.progress.mapped_total} mapped places · ${area.progress.custom_visited} custom pins reached · snapshot ${new Date(area.acquired_at).toLocaleDateString()}`;
  geometryLayer.addData(area.geometry);
  map.setView([area.area.start.lat, area.area.start.lon], 15);
  for (const place of area.places) {
    const marker = L.circleMarker([place.point.lat, place.point.lon], {
      radius: place.visited ? 7 : 5,
      color: place.valid ? "#243a31" : "#979c92",
      fillColor: place.visited ? "#cb6034" : "#f6f2e8",
      fillOpacity: 1,
      weight: 1,
    }).addTo(placesLayer);
    marker.on("click", () => inspectPlace(place));
  }
  for (const [name, value] of Object.entries(area.area)) {
    if ($("area-form").elements[name] && typeof value !== "object") {
      const input = $("area-form").elements[name];
      if (input.type === "checkbox") input.checked = value;
      else input.value = value;
    }
  }
  $("area-form").elements.lat.value = area.area.start.lat;
  $("area-form").elements.lon.value = area.area.start.lon;
}
function inspectPlace(place) {
  const target = $("place-detail");
  target.replaceChildren(
    node("h2", place.name),
    node(
      "p",
      `${place.kind} · ${place.source} · ${place.verification} · access ${place.access}`,
      "hint",
    ),
    node("p", place.descriptors.join(" · "), "hint"),
  );
  const select = node("select");
  for (const [value, label] of [
    ["verify", "Verify public access"],
    ["entrance", "Correct entrance"],
    ["not_there", "Not there"],
    ["closed", "Closed"],
    ["not_accessible", "Not accessible"],
  ]) {
    const option = node("option", label);
    option.value = value;
    select.append(option);
  }
  const detail = node("input");
  detail.placeholder = "Required: what you checked or observed";
  detail.maxLength = 500;
  detail.setAttribute("aria-label", "Place correction details");
  const button = node("button", "Save correction");
  button.onclick = async () => {
    try {
      const data = { action: select.value, detail: detail.value };
      if (select.value === "entrance") {
        data.entrance = {
          lat: Number($("pin-form").elements.lat.value),
          lon: Number($("pin-form").elements.lon.value),
        };
      }
      await api("/places/" + place.id, { method: "PATCH", body: data });
      await loadArea();
      message("Place correction saved.");
    } catch (e) {
      report(e);
    }
  };
  target.append(select, detail, button);
}
function renderQuest(value) {
  renderRouteMap(value).catch(report);
  quest = value;
  show("preview");
  const target = $("quest-content");
  target.replaceChildren(
    node(
      "p",
      `${value.estimated_minutes} min · ${(value.meters / 1000).toFixed(2)} km · ${new Date(value.generated_at).toLocaleDateString(undefined, { timeZone: value.timezone })}`,
    ),
  );
  target.append(
    node("span", value.ranking_mode + " ranking", "badge"),
    node("span", value.prose_mode + " prompts", "badge"),
    node(
      "p",
      `Model: ${value.model} · Generation: ${value.generation_seconds} seconds`,
      "hint",
    ),
  );
  routeLayer.clearLayers();
  for (const leg of value.legs)
    L.polyline(
      leg.coordinates.map((p) => [p[1], p[0]]),
      { color: "#cb6034", weight: 4 },
    ).addTo(routeLayer);
  value.stops.forEach((place, index) => {
    const section = node("div", undefined, "stop");
    section.append(
      node("h2", `${index + 1}. ${place.name}`),
      node("p", value.prompts[place.id].text),
      node("p", "Via " + value.legs[index].streets.join(" → "), "hint"),
      node("p", `${place.verification} · access ${place.access}`, "hint"),
    );
    const evidence = value.prompts[place.id].evidence;
    if (evidence)
      section.append(
        node(
          "p",
          `Recorded detail (${evidence.source}): “${evidence.description}”. Look from the public path; skip if not visible.`,
          "hint",
        ),
      );
    if (value.reasons[place.id])
      section.append(node("p", value.reasons[place.id], "hint"));
    target.append(section);
  });
  target.append(
    node("p", "Return via " + value.legs.at(-1).streets.join(" → "), "hint"),
    node(
      "p",
      "Leave by " +
        new Date(value.latest_departure).toLocaleTimeString([], {
          hour: "2-digit",
          minute: "2-digit",
          timeZone: value.timezone,
        }) +
        " · Sunset " +
        new Date(value.sunset).toLocaleTimeString([], {
          hour: "2-digit",
          minute: "2-digit",
          timeZone: value.timezone,
        }),
      "hint",
    ),
  );
  const accepted = value.status === "accepted";
  $("accept").hidden = accepted;
  $("download").hidden = !accepted;
  $("download").href = "/api/quests/" + value.id + "/card.png";
  $("download").onclick = async (event) => {
    event.preventDefault();
    try {
      const response = await fetch($("download").href);
      if (!response.ok) throw Error((await response.json()).detail);
      const url = URL.createObjectURL(await response.blob());
      const link = node("a");
      link.href = url;
      link.download = `nukkad-${value.id}.png`;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) {
      report(error);
    }
  };
  $("print").hidden = !accepted;
  $("return").hidden = !accepted;
  $("card-preview").hidden = false;
  $("card-preview").src = "/api/quests/" + value.id + "/card.svg";
}
async function loadHistory() {
  const values = await api("/quests");
  $("history-list").replaceChildren();
  if (!values.length)
    $("history-list").append(
      node("p", "Your notebook begins with your first walk."),
    );
  for (const value of values) {
    const item = node("div", undefined, "entry");
    item.append(
      node(
        "h2",
        new Date(value.created_at).toLocaleDateString() +
          " · " +
          value.stops.map((p) => p.name).join(" / "),
      ),
      node(
        "p",
        value.status + " · " + value.ranking_mode + " / " + value.prose_mode,
        "hint",
      ),
    );
    const button = node("button", "Open walk");
    button.onclick = () => renderQuest(value);
    item.append(button);
    $("history-list").append(item);
  }
  if (window.loadMemory) await window.loadMemory();
}
document
  .querySelectorAll("[data-panel]")
  .forEach((button) => (button.onclick = () => show(button.dataset.panel)));
$("open-quest").onclick = () => show(area?.area ? "quest-form-panel" : "setup");
$("cancel-job").onclick = () =>
  api("/jobs/" + activeJob + "/cancel", { method: "POST" }).catch(report);
function areaInput() {
  const v = formValues("area-form");
  return {
    name: v.name,
    timezone: v.timezone,
    start: { lat: Number(v.lat), lon: Number(v.lon) },
    radius_meters: Number(v.radius_meters),
    public_start_confirmed: !!v.public_start_confirmed,
  };
}
$("area-form").onsubmit = async (event) => {
  event.preventDefault();
  try {
    const file = $("area-form").elements.extract.files[0];
    let job;
    if (file) {
      const data = new FormData();
      data.append("metadata", JSON.stringify(areaInput()));
      data.append("extract", file);
      job = await api("/areas/import", { method: "POST", body: data });
    } else job = await api("/areas", { method: "POST", body: areaInput() });
    await runJob(job, async () => {
      await loadArea();
      show("home");
    });
  } catch (e) {
    report(e);
  }
};
$("area-form").elements.extract.onchange = (event) => {
  $("acquire-area").textContent = event.target.files.length
    ? "Import saved map"
    : "Fetch my neighbourhood";
};
$("reuse-map").onclick = async () => {
  try {
    await runJob(
      await api("/areas/reuse", { method: "POST", body: areaInput() }),
      async () => {
        await loadArea();
        show("home");
      },
    );
  } catch (e) {
    report(e);
  }
};
$("pin-form").onsubmit = async (event) => {
  event.preventDefault();
  try {
    const v = formValues("pin-form");
    await api("/places", {
      method: "POST",
      body: {
        name: v.name,
        kind: v.kind,
        entrance: { lat: Number(v.lat), lon: Number(v.lon) },
        descriptors: v.descriptor ? [v.descriptor] : [],
        public_access_confirmed: !!v.confirmed,
      },
    });
    await loadArea();
    message("Public pin saved.");
  } catch (e) {
    report(e);
  }
};
$("quest-form").onsubmit = async (event) => {
  event.preventDefault();
  try {
    await api("/profile", {
      method: "PUT",
      body: { interests: $("interests").value.split(",") },
    });
    const v = formValues("quest-form");
    await runJob(
      await api("/quests", {
        method: "POST",
        body: { minutes: Number(v.minutes), mode: v.mode, state: v.state },
      }),
      async (result) => renderQuest(await api("/quests/" + result.quest_id)),
    );
  } catch (e) {
    report(e);
  }
};
$("accept").onclick = async () => {
  try {
    renderQuest(
      await api("/quests/" + quest.id + "/accept", { method: "POST" }),
    );
  } catch (e) {
    report(e);
  }
};
$("print").onclick = async () => {
  try {
    await api("/quests/" + quest.id + "/accept", { method: "POST" });
    window.print();
  } catch (error) {
    report(error);
  }
};
$("settings-form").onsubmit = async (event) => {
  event.preventDefault();
  try {
    const v = formValues("settings-form");
    const data = {};
    for (const [name, value] of Object.entries(v))
      data[name] = ["model", "tone"].includes(name) ? value : Number(value);
    data.daylight_required =
      $("settings-form").elements.daylight_required.checked;
    data.air_quality_enabled =
      $("settings-form").elements.air_quality_enabled.checked;
    data.air_quality_threshold =
      v.air_quality_threshold === "" ? null : Number(v.air_quality_threshold);
    await api("/settings", { method: "PUT", body: data });
    message("Walking settings saved.");
  } catch (e) {
    report(e);
  }
};
async function init() {
  sessionToken = (await api("/session")).token;
  map = L.map("map", { attributionControl: false }).setView(
    [28.6394, 77.3606],
    15,
  );
  geometryLayer = L.geoJSON(null, {
    style: (feature) => ({
      color: "#c3cdbd",
      weight: 2,
      fillColor: feature.properties?.kind === "park" ? "#cedcc2" : "#dce2d6",
      fillOpacity: 0.4,
    }),
  }).addTo(map);
  placesLayer = L.layerGroup().addTo(map);
  routeLayer = L.layerGroup().addTo(map);
  map.on("click", (event) => {
    for (const id of ["area-form", "pin-form"]) {
      const form = $(id);
      form.elements.lat.value = event.latlng.lat.toFixed(6);
      form.elements.lon.value = event.latlng.lng.toFixed(6);
    }
    $("area-form").elements.public_start_confirmed.checked = false;
    message(
      "Selected map point. Open neighbourhood setup to confirm the public start or add a pin.",
    );
  });
  await loadArea();
  const profile = await api("/profile");
  $("interests").value = profile.interests.join(", ");
  const settings = await api("/settings");
  for (const [name, value] of Object.entries(settings)) {
    const input = $("settings-form").elements[name];
    if (!input) continue;
    if (input.type === "checkbox") input.checked = value;
    else input.value = value ?? "";
  }
  const ready = await api("/readiness");
  $("readiness").textContent =
    "Local model: " + ready.model_status + " · Database: " + ready.database;
  for (const model of ready.models) {
    const item = node("option");
    item.value = model;
    $("models").append(item);
  }
}
init().catch(report);
$("return").onclick = async () => {
  try {
    show("outcome");
    $("outcome-stops").replaceChildren();
    const existing = await api("/quests/" + quest.id + "/outcome");
    for (const [index, place] of quest.stops.entries()) {
      const label = node("label", `${index + 1}. ${place.name}`);
      const select = node("select");
      select.name = "stop-" + place.id;
      for (const status of ["unresolved", "reached", "skipped"]) {
        const option = node("option", status);
        option.value = status;
        select.append(option);
      }
      select.value =
        existing?.stops.find((item) => item.id === place.id)?.status ||
        "unresolved";
      label.append(select);
      $("outcome-stops").append(label);
    }
    for (const name of [
      "status",
      "note",
      "reason",
      "actual_minutes",
      "screen_minutes",
    ])
      $("outcome-form").elements[name].value =
        existing?.[name] ?? (name === "status" ? "completed" : "");
    $("journal-review").replaceChildren();
    if (existing && window.showJournal) await window.showJournal(existing);
  } catch (e) {
    report(e);
  }
};
$("outcome-form").onsubmit = async (event) => {
  event.preventDefault();
  try {
    const v = formValues("outcome-form");
    const outcome = await api("/quests/" + quest.id + "/outcome", {
      method: "PUT",
      body: {
        status: v.status,
        note: v.note,
        reason: v.reason,
        actual_minutes:
          v.actual_minutes === "" ? null : Number(v.actual_minutes),
        screen_minutes:
          v.screen_minutes === "" ? null : Number(v.screen_minutes),
        stops: quest.stops.map((place) => ({
          id: place.id,
          status: v["stop-" + place.id],
        })),
      },
    });
    await loadArea();
    message(
      "Outcome saved. Places are marked only where you reported reaching them.",
    );
    if (window.showJournal) await window.showJournal(outcome);
  } catch (e) {
    report(e);
  }
};
window.showJournal = async (outcome) => {
  const target = $("journal-review");
  target.replaceChildren(node("h2", "Your original note"));
  const original = node("pre", outcome.original_note);
  original.style.whiteSpace = "pre-wrap";
  target.append(original);
  const generate = node("button", "Draft a reflection with local AI");
  generate.onclick = async () => {
    try {
      await runJob(
        await api("/outcomes/" + outcome.id + "/reflect", { method: "POST" }),
        async () => {
          await window.showJournal(
            await api("/quests/" + outcome.id + "/outcome"),
          );
        },
      );
    } catch (e) {
      report(e);
    }
  };
  target.append(generate);
  const journal = await api("/outcomes/" + outcome.id + "/journal");
  if (journal) {
    target.append(
      node("h2", "Journal draft"),
      node("p", journal.mode + " · " + journal.status, "hint"),
    );
    const draft = node("textarea");
    draft.value = journal.text;
    draft.maxLength = 2000;
    draft.setAttribute("aria-label", "Review journal draft");
    target.append(draft);
    for (const status of ["accepted", "rejected"]) {
      const button = node(
        "button",
        status === "accepted" ? "Accept / save edits" : "Reject draft",
      );
      button.onclick = async () => {
        try {
          await api("/outcomes/" + outcome.id + "/journal", {
            method: "PATCH",
            body: { status, text: draft.value },
          });
          await window.showJournal(outcome);
        } catch (e) {
          report(e);
        }
      };
      target.append(button);
    }
  }
  const holder = node("div");
  target.append(holder);
  await interestControls(holder, outcome.id);
};
async function interestControls(target, source) {
  const items = await api("/interests");
  target.replaceChildren();
  for (const item of items.filter(
    (item) =>
      (!source || item.source_note_id === source) &&
      !["superseded", "invalidated"].includes(item.status),
  )) {
    const section = node("div", undefined, "entry");
    section.append(
      node("h2", item.theme),
      node("p", "“" + item.quote + "”"),
      node(
        "p",
        "Source note " +
          item.source_note_id +
          " · " +
          item.status +
          " · Interpretation is tentative.",
        "hint",
      ),
    );
    const input = node("input");
    input.value = item.theme;
    input.maxLength = 100;
    input.setAttribute("aria-label", "Edit interest theme");
    section.append(input);
    for (const [status, label] of [
      ["accepted", "Accept / save edits"],
      ["rejected", "Reject"],
      ["removed", "Remove"],
    ]) {
      const button = node("button", label);
      button.onclick = async () => {
        try {
          await api("/interests/" + item.id, {
            method: "PATCH",
            body: { status, text: input.value },
          });
          await interestControls(target, source);
        } catch (e) {
          report(e);
        }
      };
      section.append(button);
    }
    target.append(section);
  }
  if (!target.children.length)
    target.append(
      node(
        "p",
        "No proposals to review yet. Only accepted interests influence future quests.",
        "hint",
      ),
    );
}
window.loadMemory = async () => {
  const outcomes = await api("/outcomes");
  for (const outcome of outcomes) {
    const item = node("div", undefined, "entry");
    item.append(
      node(
        "h2",
        new Date(outcome.created_at).toLocaleDateString() +
          " · " +
          outcome.status,
      ),
      node("p", outcome.note),
      node(
        "p",
        outcome.reached_ids.length +
          " reported stops reached · " +
          (outcome.actual_minutes ?? "unreported") +
          " outdoor minutes",
        "hint",
      ),
    );
    const button = node("button", "Review outcome and reflection");
    button.onclick = async () => {
      try {
        quest = await api("/quests/" + outcome.quest_id);
        $("return").click();
      } catch (e) {
        report(e);
      }
    };
    item.append(button);
    $("history-list").append(item);
  }
  await interestControls($("interest-review"));
};

$("refresh-air").onclick = async () => {
  try {
    const value = await api("/air-quality/refresh", { method: "POST" });
    renderAir(value);
  } catch (e) {
    report(e);
  }
};

function renderAir(value) {
  const target = $("air-quality");
  target.replaceChildren(node("h2", "Regional air quality"));
  target.append(
    node(
      "p",
      value.status === "known"
        ? `U.S. AQI ${value.value} · regional model estimate`
        : `Estimate: ${value.status}`,
    ),
  );
  if (value.source) target.append(node("p", value.source, "hint"));
  if (value.retrieved_at)
    target.append(
      node(
        "p",
        `Retrieved ${new Date(value.retrieved_at).toLocaleString()} · forecast valid ${new Date(value.valid_at).toLocaleString()}`,
        "hint",
      ),
    );
  target.append(
    node(
      "p",
      value.limitation ||
        "Regional estimates cannot establish conditions on your street.",
      "hint",
    ),
  );
}

async function renderRouteMap(value) {
  const saved = await api(`/snapshots/${value.snapshot_id}/map`);
  if (quest?.id !== value.id) return;
  if (!questMap) {
    questMap = L.map("quest-map", { attributionControl: false }).setView(
      [value.start.lat, value.start.lon],
      16,
    );
    questLayers = L.featureGroup().addTo(questMap);
    L.control
      .attribution({ prefix: false })
      .addAttribution("Map data © OpenStreetMap contributors")
      .addTo(questMap);
  }
  questLayers.clearLayers();
  L.geoJSON(saved.geometry, {
    style: {
      color: "#c3cdbd",
      weight: 2,
      fillColor: "#dce2d6",
      fillOpacity: 0.4,
    },
  }).addTo(questLayers);
  const routes = [];
  for (const [index, leg] of value.legs.entries()) {
    routes.push(
      L.polyline(
        leg.coordinates.map((point) => [point[1], point[0]]),
        {
          color: index === value.legs.length - 1 ? "#537560" : "#cb6034",
          weight: 4,
        },
      ).addTo(questLayers),
    );
  }
  for (const [index, stop] of value.stops.entries()) {
    const number = node("span", String(index + 1));
    L.marker([stop.entrance.lat, stop.entrance.lon], {
      icon: L.divIcon({
        html: number,
        className: "number-pin",
        iconSize: [30, 30],
        iconAnchor: [15, 15],
      }),
    })
      .addTo(questLayers)
      .bindTooltip(node("span", stop.name));
  }
  L.circleMarker([value.start.lat, value.start.lon], {
    radius: 8,
    color: "#243a31",
    fillColor: "#f6f2e8",
    fillOpacity: 1,
  })
    .addTo(questLayers)
    .bindTooltip("Start + return");
  setTimeout(() => {
    questMap.invalidateSize();
    questMap.fitBounds(L.featureGroup(routes).getBounds(), {
      padding: [35, 35],
    });
  }, 40);
}
