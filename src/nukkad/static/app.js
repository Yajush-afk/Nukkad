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
  questLayers,
  selectedPointLayer,
  hasSelectedLocation = false,
  locationRevision = 0;
const node = (tag, text, className) => {
  const e = document.createElement(tag);
  if (text !== undefined) e.textContent = text;
  if (className) e.className = className;
  return e;
};
const labels = {
  draft: "Ready to review",
  accepted: "Approved",
  completed: "Completed",
  turned_back: "Turned back early",
  not_taken: "Not taken",
  pending: "Waiting for your review",
  rejected: "Not used",
  removed: "Removed",
  invalidated: "Needs a fresh review",
  unverified: "Not personally checked",
  verified: "Personally checked",
};
const labelFor = (value) => labels[value] || value.replaceAll("_", " ");
const dateFor = (value, timezone) =>
  new Date(value).toLocaleDateString(undefined, { timeZone: timezone });
const timeFor = (value, timezone) =>
  new Date(value).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: timezone,
  });
function disclosure(title, ...content) {
  const details = node("details", undefined, "quiet-details");
  details.append(node("summary", title), ...content);
  return details;
}
function accessNote(place) {
  if (!place.valid || place.access === "prohibited")
    return "Currently excluded from walking suggestions.";
  if (place.access === "confirmed")
    return "You reported public access. Check that it is still open when you arrive.";
  if (place.access === "mapped")
    return "Entrance shown on the map; public access has not been personally confirmed.";
  return "Public access is unknown. Check from a public path and skip if blocked.";
}
function message(text, error = false) {
  $("message").textContent = text;
  $("message").hidden = !text;
  $("message").setAttribute("role", error ? "alert" : "status");
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
  document.body.dataset.panel = id;
  document.dispatchEvent(new Event("nukkad:panel"));
  document.querySelectorAll(".panel").forEach((e) => (e.hidden = e.id !== id));
  const active = ["quest-form-panel", "preview", "outcome"].includes(id)
    ? "home"
    : id;
  document.querySelectorAll("nav [data-panel]").forEach((button) => {
    if (button.dataset.panel === active)
      button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  });
  message("");
  if (id === "home") setTimeout(() => map?.invalidateSize(), 30);
  if (id === "history") loadHistory().catch(report);
  if (id === "settings") api("/air-quality").then(renderAir).catch(report);
  if (id === "quest-form-panel")
    $("walk-context").textContent =
      `${area.area.name} · ${area.area.timezone} · returning to your start`;
  const heading = $(id).querySelector("h1");
  heading.tabIndex = -1;
  heading.focus({ preventScroll: true });
  window.scrollTo({ top: 0, behavior: "instant" });
}
function report(error) {
  message(error.message || String(error), true);
  $("message").scrollIntoView({ behavior: "instant", block: "start" });
}
function formValues(id) {
  return Object.fromEntries(new FormData($(id)));
}
function jobText(text) {
  const stages = {
    "Ranking eligible places with local AI":
      "Choosing nearby stops for your interests…",
    "Checking full walking route and daylight":
      "Checking the route home and daylight…",
    "Writing observation prompts for the fixed route":
      "Adding something to notice at each stop…",
    "Selecting a grounded journal excerpt and tentative interests locally":
      "Finding a passage and possible interests in your note…",
    "Saving reviewable drafts": "Saving a draft for you to review…",
  };
  return stages[text] || text;
}
async function runJob(value, finished) {
  activeJob = value.id;
  $("job").hidden = false;
  const buttons = [
    ...document.querySelectorAll(
      'form button[type="submit"], form button:not([type]), #reuse-map, #accept',
    ),
  ];
  const states = buttons.map((button) => button.disabled);
  buttons.forEach((button) => {
    button.disabled = true;
  });
  $("main").setAttribute("aria-busy", "true");
  try {
    while (activeJob === value.id) {
      const job = await api("/jobs/" + value.id);
      $("job-message").textContent = jobText(job.message);
      if (
        ["complete", "failed", "cancelled", "interrupted"].includes(job.status)
      ) {
        activeJob = null;
        if (job.status === "complete") return await finished(job.result);
        throw Error(job.message);
      }
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }
  } finally {
    activeJob = null;
    $("job").hidden = true;
    $("main").removeAttribute("aria-busy");
    buttons.forEach((button, index) => {
      button.disabled = states[index];
    });
  }
}
async function loadArea() {
  area = await api("/area");
  geometryLayer.clearLayers();
  placesLayer.clearLayers();
  routeLayer.clearLayers();
  selectedPointLayer.clearLayers();
  $("place-detail").replaceChildren();
  const saved = !!area.area;
  for (const id of ["map-empty"]) $(id).hidden = saved;
  for (const id of [
    "edit-area",
    "map-help",
    "map-details",
    "choose-start",
    "reuse-map",
  ])
    $(id).hidden = !saved;
  $("open-quest").textContent = !saved
    ? "Set up my neighbourhood ↗"
    : area.area.public_start_confirmed
      ? "Plan a walk ↗"
      : "Confirm my starting point ↗";
  $("home-next").textContent = !saved
    ? "Start by downloading your local map. No file upload needed."
    : area.area.public_start_confirmed
      ? "Choose your time, review the route, then take it outside."
      : "Your map is saved. Confirm a public starting point before planning a walk.";
  $("area-status").textContent = !saved
    ? "Not set up"
    : area.area.public_start_confirmed
      ? "Map saved"
      : "Confirm start";
  if (!saved) return;
  $("area-name").textContent = area.area.name;
  $("progress").textContent = area.area.public_start_confirmed
    ? `${area.progress.mapped_visited} of ${area.progress.mapped_total} mapped places visited · ${area.progress.custom_visited} added places visited`
    : "Choose a public walking start to connect nearby places.";
  $("snapshot-info").textContent =
    `Map saved ${dateFor(area.acquired_at, area.area.timezone)}. Area radius: ${area.area.radius_meters} metres. Visits are based on this saved map.`;
  hasSelectedLocation = true;
  $("selected-location").textContent =
    area.area.name +
    (area.area.public_start_confirmed
      ? " — public walking start confirmed by you."
      : " — saved map; choose and confirm a public walking start.");
  $("location-query").value = area.area.name;
  $("start-help").textContent =
    "Choose the public gate or street where your walk will begin and end. Selecting a point does not confirm that it is accessible.";
  $("start-map-hint").textContent =
    "Select a point on your map, then choose ‘Use as my start’. Save the new start here.";
  geometryLayer.addData(area.geometry);
  L.circleMarker([area.area.start.lat, area.area.start.lon], {
    radius: 8,
    color: "#344c3d",
    fillColor: "#344c3d",
    fillOpacity: 1,
    weight: 2,
  })
    .addTo(geometryLayer)
    .bindTooltip(
      area.area.public_start_confirmed
        ? "Your starting point — return here"
        : "Selected map centre — choose a public walking start",
    );
  map.setView([area.area.start.lat, area.area.start.lon], 15);
  for (const place of area.places) {
    const marker = L.circleMarker([place.point.lat, place.point.lon], {
      radius: place.visited ? 7 : 5,
      color: place.valid ? "#243a31" : "#979c92",
      fillColor: place.visited ? "#b36c12" : "#f5f1e7",
      fillOpacity: 1,
      weight: 1,
    }).addTo(placesLayer);
    marker.bindTooltip(node("span", place.name));
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
      `${labelFor(place.kind)} · ${place.visited ? "You reported visiting" : "No visit reported"}`,
      "hint",
    ),
    node("p", accessNote(place), "hint"),
  );
  if (place.descriptors.length)
    target.append(node("p", place.descriptors.join(" · "), "hint"));
  const corrections = disclosure("Update this place");
  const form = node("form", undefined, "form-grid");
  const select = node("select");
  for (const [value, label] of [
    ["verify", "I checked public access"],
    ["entrance", "Correct the entrance"],
    ["not_there", "This place is not here"],
    ["closed", "This place is closed"],
    ["not_accessible", "I could not access it"],
  ]) {
    const option = node("option", label);
    option.value = value;
    select.append(option);
  }
  const actionLabel = node("label", "What changed?");
  actionLabel.className = "wide";
  actionLabel.append(select);
  const detail = node("input");
  detail.placeholder = "What did you check or observe?";
  detail.maxLength = 500;
  detail.minLength = 3;
  detail.required = true;
  const detailLabel = node("label", "Your observation");
  detailLabel.className = "wide";
  detailLabel.append(detail);
  const latitude = node("input");
  const longitude = node("input");
  for (const [input, coordinate, min, max] of [
    [latitude, "lat", -90, 90],
    [longitude, "lon", -180, 180],
  ]) {
    input.type = "number";
    input.step = "any";
    input.min = min;
    input.max = max;
    input.value = place.entrance?.[coordinate] ?? "";
  }
  const entranceLat = node("label", "New entrance latitude");
  entranceLat.append(latitude);
  const entranceLon = node("label", "New entrance longitude");
  entranceLon.append(longitude);
  const toggleEntrance = () => {
    entranceLat.hidden = entranceLon.hidden = select.value !== "entrance";
    latitude.required = longitude.required = select.value === "entrance";
  };
  select.onchange = toggleEntrance;
  toggleEntrance();
  const button = node("button", "Save update");
  button.type = "submit";
  form.append(actionLabel, detailLabel, entranceLat, entranceLon, button);
  form.onsubmit = async (event) => {
    event.preventDefault();
    try {
      const data = { action: select.value, detail: detail.value };
      if (select.value === "entrance")
        data.entrance = {
          lat: Number(latitude.value),
          lon: Number(longitude.value),
        };
      await api("/places/" + place.id, { method: "PATCH", body: data });
      await loadArea();
      target.replaceChildren();
      message("Place update saved.");
    } catch (e) {
      report(e);
    }
  };
  corrections.append(form);
  target.append(
    corrections,
    disclosure(
      "Map source & access details",
      node(
        "p",
        `Source: ${place.source === "osm" ? "OpenStreetMap" : "Your added place"}. ${labelFor(place.verification)}. Access record: ${place.access}.`,
        "hint",
      ),
    ),
  );
}
function selectMapPoint(point) {
  selectedPointLayer.clearLayers();
  L.circleMarker([point.lat, point.lng], {
    radius: 9,
    color: "#b36c12",
    fillColor: "#f5f1e7",
    fillOpacity: 1,
  }).addTo(selectedPointLayer);
  const target = $("place-detail");
  target.replaceChildren(
    node("h2", "Use this point"),
    node(
      "p",
      "Check that this point is on the actual public path before confirming.",
      "hint",
    ),
  );
  const actions = node("div", undefined, "buttonrow");
  for (const [label, formId] of [
    ["Use as my start", "area-form"],
    ["Add a place here", "pin-form"],
  ]) {
    const button = node("button", label);
    button.onclick = () => {
      const form = $(formId);
      form.elements.lat.value = point.lat.toFixed(6);
      form.elements.lon.value = point.lng.toFixed(6);
      if (formId === "area-form") {
        form.elements.public_start_confirmed.checked = false;
        hasSelectedLocation = true;
        locationRevision++;
        $("location-query").value = area.area.name;
        $("reuse-map").hidden = false;
        $("location-results").hidden = true;
        $("location-status").hidden = true;
        $("selected-location").textContent =
          "Point chosen on your saved map. Confirm that it is on a public walking path, then save this start.";
      } else {
        form.elements.confirmed.checked = false;
        $("add-place-details").open = true;
      }
      show("setup");
      form.scrollIntoView({ block: "start" });
      form.elements[
        formId === "area-form" ? "public_start_confirmed" : "name"
      ].focus({
        preventScroll: true,
      });
    };
    actions.append(button);
  }
  target.append(actions);
  target.scrollIntoView({ block: "nearest" });
}
function renderQuest(value) {
  quest = value;
  show("preview");
  renderRouteMap(value).catch(report);
  const accepted = value.status === "accepted";
  $("preview-stage").textContent = accepted
    ? "03 / SAVE IT & HEAD OUT"
    : "02 / REVIEW YOUR WALK";
  $("preview-help").textContent = accepted
    ? "Save the image to your phone or print the card. Add a note here when you return."
    : "Check the route and stops before you save this walk.";
  $("take-along-help").textContent = accepted
    ? "Transfer the image to your phone by USB or Bluetooth before leaving. Stay on public paths and turn back if blocked. The card has no live navigation."
    : "Stay on public paths. Skip a stop or turn back if access is blocked. The saved card has no live navigation.";
  $("quest-summary").replaceChildren();
  for (const [amount, label] of [
    [`${value.estimated_minutes} min`, "Including return & stops"],
    [`${(value.meters / 1000).toFixed(2)} km`, "Total walking distance"],
    [
      String(value.stops.length),
      value.stops.length === 1 ? "Stop to explore" : "Stops to explore",
    ],
    [timeFor(value.latest_departure, value.timezone), "Latest departure"],
  ]) {
    const stat = node("div", undefined, "walk-stat");
    stat.append(node("strong", amount), node("span", label));
    $("quest-summary").append(stat);
  }
  const target = $("quest-content");
  target.replaceChildren(
    node(
      "p",
      `${dateFor(value.generated_at, value.timezone)} · ${value.timezone} · Sunset ${timeFor(value.sunset, value.timezone)}${value.settings.daylight_required ? "" : " · Daylight checks are off"}`,
      "hint",
    ),
  );
  target.append(
    node(
      "span",
      value.ranking_mode === "local AI"
        ? "Stops selected with local AI"
        : "Stops selected with basic rules",
      "badge",
    ),
    node(
      "span",
      value.prose_mode === "local AI"
        ? "Local AI observation prompts"
        : "Standard observation prompts",
      "badge",
    ),
  );
  routeLayer.clearLayers();
  for (const leg of value.legs)
    L.polyline(
      leg.coordinates.map((p) => [p[1], p[0]]),
      { color: "#b36c12", weight: 4 },
    ).addTo(routeLayer);
  value.stops.forEach((place, index) => {
    const section = node("div", undefined, "stop");
    const heading = node("div", undefined, "stop-heading");
    heading.append(
      node("span", String(index + 1).padStart(2, "0"), "stop-number"),
      node("h2", place.name),
    );
    section.append(
      heading,
      node("p", value.prompts[place.id].text),
      node("p", "Walk via " + value.legs[index].streets.join(" → "), "hint"),
      node("p", accessNote(place), "hint"),
    );
    const evidence = value.prompts[place.id].evidence;
    if (evidence)
      section.append(
        node(
          "p",
          `Recorded detail from ${evidence.source === "osm" ? "OpenStreetMap" : "your observation"}: “${evidence.description}”. Look from the public path; skip if not visible.`,
          "hint",
        ),
      );
    if (value.reasons[place.id])
      section.append(
        disclosure(
          "Why this stop?",
          node("p", value.reasons[place.id], "hint"),
        ),
      );
    target.append(section);
  });
  const home = node("div", undefined, "route-return");
  home.append(
    node("h2", "Back to your start"),
    node("p", value.legs.at(-1).streets.join(" → "), "hint"),
  );
  target.append(
    home,
    disclosure(
      "How this walk was made",
      node(
        "p",
        `Stop selection: ${value.ranking_mode}. Observation prompts: ${value.prose_mode}.`,
        "hint",
      ),
      node(
        "p",
        `Model: ${value.model}. Generated in ${value.generation_seconds} seconds. Walking paths, distance and time are checked separately from AI suggestions.`,
        "hint",
      ),
    ),
  );
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
  const [values, outcomes] = await Promise.all([
    api("/quests"),
    api("/outcomes"),
  ]);
  const byQuest = new Map(
    outcomes.map((outcome) => [outcome.quest_id, outcome]),
  );
  const target = $("history-list");
  target.replaceChildren();
  if (!values.length) {
    const empty = node("div", undefined, "entry");
    empty.append(
      node("h2", "Your first walk starts here."),
      node(
        "p",
        "Plan a route, take it outside, and return to keep a note.",
        "hint",
      ),
    );
    const button = node(
      "button",
      area?.area?.public_start_confirmed
        ? "Plan a walk"
        : "Set up my neighbourhood",
    );
    button.onclick = () => $("open-quest").click();
    empty.append(button);
    target.append(empty);
  }
  for (const value of values) {
    const outcome = byQuest.get(value.id);
    const item = node("div", undefined, "entry");
    item.append(
      node(
        "p",
        `${dateFor(value.created_at, value.timezone)} · ${outcome ? labelFor(outcome.status) : value.status === "accepted" ? "Saved walk" : labelFor(value.status)}`,
        "eyebrow",
      ),
      node("h2", value.stops.map((p) => p.name).join(" / ")),
      node(
        "p",
        `${value.estimated_minutes} min planned · ${(value.meters / 1000).toFixed(2)} km${outcome ? ` · ${outcome.reached_ids.length} stops reported reached` : ""}`,
        "hint",
      ),
    );
    if (outcome?.note) {
      item.append(
        node(
          "p",
          outcome.note.length > 280
            ? outcome.note.slice(0, 280) + "…"
            : outcome.note,
        ),
      );
      if (outcome.note.length > 280)
        item.append(disclosure("Read the full note", node("p", outcome.note)));
    }
    const actions = node("div", undefined, "buttonrow");
    const open = node("button", "View walk");
    open.onclick = () => renderQuest(value);
    actions.append(open);
    if (value.status === "accepted") {
      const note = node(
        "button",
        outcome ? "Edit note & visits" : "Add note & visits",
      );
      note.onclick = () => {
        quest = value;
        $("return").click();
      };
      actions.append(note);
    }
    item.append(actions);
    target.append(item);
  }
  await interestControls($("interest-review"));
}
document.querySelectorAll("[data-panel]").forEach((button) => {
  button.onclick = (event) => {
    event.preventDefault();
    show(button.dataset.panel);
  };
});
$("open-quest").onclick = () =>
  show(area?.area?.public_start_confirmed ? "quest-form-panel" : "setup");
$("choose-start").onclick = () => {
  show("home");
  message(
    "Select your public starting point on the map, then choose ‘Use as my start’. Save it in Neighbourhood.",
  );
  $("map").scrollIntoView({ block: "center" });
};
$("quest-form").elements.mode.onchange = (event) => {
  $("mode-help").textContent =
    event.target.value === "seek"
      ? "Look for a detail recorded on the map or in your own place notes. Some areas may not have any yet."
      : "Open-ended invitations to notice sounds, colours and shapes.";
};
document.addEventListener(
  "invalid",
  (event) => {
    let parent = event.target.parentElement;
    while (parent) {
      if (parent.tagName === "DETAILS") parent.open = true;
      parent = parent.parentElement;
    }
  },
  true,
);
for (const [id, confirmation] of [
  ["area-form", "public_start_confirmed"],
  ["pin-form", "confirmed"],
]) {
  for (const coordinate of ["lat", "lon"]) {
    $(id).elements[coordinate].addEventListener("input", () => {
      $(id).elements[confirmation].checked = false;
    });
  }
}
$("cancel-job").onclick = () =>
  api("/jobs/" + activeJob + "/cancel", { method: "POST" }).catch(report);
function clearLocationSelection() {
  locationRevision++;
  hasSelectedLocation = false;
  $("area-form").elements.lat.value = "";
  $("area-form").elements.lon.value = "";
  $("area-form").elements.public_start_confirmed.checked = false;
  $("selected-location").textContent =
    "Search above and choose a matching location.";
  $("location-results").replaceChildren();
  $("location-results").hidden = true;
  $("location-status").hidden = true;
  $("reuse-map").hidden = true;
}
$("location-query").addEventListener("input", clearLocationSelection);
$("location-form").onsubmit = async (event) => {
  event.preventDefault();
  clearLocationSelection();
  const revision = locationRevision;
  const query = $("location-query").value.trim();
  $("search-location").disabled = true;
  $("search-location").textContent = "Searching…";
  $("location-status").hidden = false;
  $("location-status").textContent = "Looking for matching places…";
  message("");
  try {
    const result = await api("/locations/search", {
      method: "POST",
      body: { query },
    });
    if (revision !== locationRevision) return;
    const target = $("location-results");
    $("location-status").textContent = result.matches.length
      ? "Choose the location you meant:"
      : "No match found. Try the locality or a nearby landmark with the city, for example ‘Ahinsa Khand 1, Indirapuram, Ghaziabad’.";
    for (const match of result.matches) {
      const item = node("li");
      const button = node("button", undefined, "location-result");
      button.type = "button";
      button.append(node("strong", match.name), node("span", match.label));
      button.onclick = () => {
        hasSelectedLocation = true;
        const form = $("area-form");
        form.elements.lat.value = match.point.lat;
        form.elements.lon.value = match.point.lon;
        form.elements.name.value = match.name.slice(0, 100);
        form.elements.public_start_confirmed.checked = false;
        $("selected-location").textContent = match.label;
        target
          .querySelectorAll("button")
          .forEach((choice) =>
            choice.setAttribute(
              "aria-pressed",
              choice === button ? "true" : "false",
            ),
          );
        $("location-status").textContent =
          "Location selected. Fetch your neighbourhood map below.";
        $("acquire-area").focus({ preventScroll: true });
      };
      button.setAttribute("aria-pressed", "false");
      item.append(button);
      target.append(item);
    }
    target.hidden = !result.matches.length;
  } catch (error) {
    if (revision === locationRevision) {
      $("location-status").textContent = error.message;
      message(error.message, true);
    }
  } finally {
    $("search-location").disabled = false;
    $("search-location").textContent = "Search";
  }
};
function areaInput() {
  const v = formValues("area-form");
  if (!hasSelectedLocation || v.lat === "" || v.lon === "")
    throw Error(
      "Search for a location and choose a match before downloading your map.",
    );
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
    message("Place saved. You can now find it on your map.");
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
    await $("card-preview").decode();
    window.print();
  } catch (error) {
    report(error);
  }
};
let cardWasOpenBeforePrint;
window.addEventListener("beforeprint", () => {
  const card = document.querySelector(".card-details");
  cardWasOpenBeforePrint = card.open;
  card.open = true;
});
window.addEventListener("afterprint", () => {
  document.querySelector(".card-details").open = cardWasOpenBeforePrint;
});
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
    refreshReadiness().catch(report);
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
  selectedPointLayer = L.layerGroup().addTo(map);
  L.control
    .attribution({ prefix: false })
    .addAttribution(
      'Map data © <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>',
    )
    .addTo(map);
  map.on("click", (event) => {
    if (area?.area) selectMapPoint(event.latlng);
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
  await refreshReadiness();
}
async function refreshReadiness() {
  const ready = await api("/readiness");
  $("model-status").textContent =
    ready.model_status === "ready"
      ? "Ready"
      : ready.model_status === "missing"
        ? "Model missing"
        : "Ollama unavailable";
  $("readiness").textContent =
    ready.model_status === "ready"
      ? `${ready.selected_model} is available on this laptop.`
      : ready.model_status === "missing"
        ? `Download ${ready.selected_model} in Ollama or choose an installed model. Basic suggestions can still be used when local AI fails.`
        : "Start Ollama on this laptop to use local AI. Basic suggestions can still be used when local AI fails.";
  $("models").replaceChildren();
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
        const option = node(
          "option",
          {
            unresolved: "Not recorded",
            reached: "Reached this stop",
            skipped: "Skipped this stop",
          }[status],
        );
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
    updateOutcomeReason();
    $("journal-review").replaceChildren();
    if (existing && window.showJournal) await window.showJournal(existing);
  } catch (e) {
    report(e);
  }
};
function updateOutcomeReason() {
  $("reason-label").hidden =
    $("outcome-form").elements.status.value !== "turned_back";
}
$("outcome-form").elements.status.onchange = updateOutcomeReason;
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
      "Note and visits saved. Only the stops you marked as reached count as visited.",
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
  target.append(
    node(
      "p",
      "Optional: local AI can select a short passage from your note and suggest interests for you to review. Your original words stay saved.",
      "hint",
    ),
  );
  const generate = node("button", "Create a reflection draft");
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
      node("h2", "Review your reflection"),
      node(
        "p",
        `${labelFor(journal.status)} · ${journal.mode === "local AI extract" ? "Passage selected with local AI" : "Passage copied without AI"}`,
        "hint",
      ),
    );
    const draft = node("textarea");
    draft.value = journal.text;
    draft.maxLength = 2000;
    draft.setAttribute("aria-label", "Review journal draft");
    target.append(draft);
    const actions = node("div", undefined, "buttonrow");
    for (const status of ["accepted", "rejected"]) {
      const button = node(
        "button",
        status === "accepted" ? "Save this reflection" : "Discard draft",
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
      actions.append(button);
    }
    target.append(actions);
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
        `${labelFor(item.status)} · Suggested from your words. Only approved interests are used.`,
        "hint",
      ),
    );
    const input = node("input");
    input.value = item.theme;
    input.maxLength = 100;
    input.setAttribute("aria-label", "Edit interest theme");
    section.append(input);
    const actions = node("div", undefined, "buttonrow");
    for (const [status, label] of [
      ["accepted", "Use this interest"],
      ["rejected", "Don’t use"],
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
      actions.append(button);
    }
    section.append(
      actions,
      disclosure("Source note", node("p", item.source_note, "hint")),
    );
    target.append(section);
  }
  if (!target.children.length)
    target.append(
      node(
        "p",
        "No interests to review yet. You can add interests when planning a walk.",
        "hint",
      ),
    );
}
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
  target.replaceChildren(node("h3", "Latest regional estimate"));
  target.append(
    node(
      "p",
      value.status === "known"
        ? `U.S. AQI ${value.value} · regional model estimate`
        : value.status === "disabled"
          ? "Air-quality limit is off."
          : `Estimate: ${labelFor(value.status)}`,
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
          color: index === value.legs.length - 1 ? "#537560" : "#b36c12",
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
