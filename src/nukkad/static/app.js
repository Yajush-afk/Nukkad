"use strict";
const $ = (id) => document.getElementById(id);
let navigation,
  areaNeedsRefresh = false,
  mapLoaded = false,
  area,
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
  const reports={closed:"Reported closed",not_there:"Reported missing",not_accessible:"Reported inaccessible"};
  if(!place.valid) return reports[place.last_report] || "Unavailable for walking suggestions";
  if(place.access === "prohibited") return "Not open to public walking";
  if(!place.entrance) return "Entrance not confirmed";
  return place.access === "confirmed" ? "Public access checked — check again on arrival" : "Mapped entrance — check public access";
}
const notifications = NukkadNotifications.create({ target: $("notifications"), node });
function message(text, error = false) {
  notifications.notify(text, error);
}
async function api(path, options = {}) {
  if (
    ["POST", "PUT", "PATCH", "DELETE"].includes(options.method?.toUpperCase())
  )
    await initialized;
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
function renderPanel(id) {
  document.body.dataset.panel = id;
  document.dispatchEvent(new Event("nukkad:panel"));
  document.querySelectorAll(".panel").forEach((e) => (e.hidden = e.id !== id));
  const active =
    id === "quest-form-panel"
      ? "setup"
      : ["preview", "outcome", "place-folder"].includes(id)
        ? "history"
        : id;
  document.querySelectorAll("nav [data-panel]").forEach((button) => {
    if (button.dataset.panel === active)
      button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  });
  message("");
  if (id === "setup") setTimeout(() => map?.invalidateSize(), 30);
  if (id === "quest-form-panel")
    $("walk-context").textContent = area?.area
      ? `${area.area.name} · ${area.area.timezone} · returning to your start`
      : "Preparing your walking start…";
}
function show(id) {
  return navigation.go(id, quest?.id);
}
function report(error) {
  message(error.message || String(error), true);
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
    "Writing a grounded journal and tentative interests locally":
      "Writing a draft from your note…",
    "Saving reviewable drafts": "Saving a draft for you to review…",
  };
  return stages[text] || text;
}
async function runJob(value, finished, current = navigation.checkpoint()) {
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
        if (job.status === "complete") {
          if (current()) return await finished(job.result, current);
          const mapChanged = !!job.result?.snapshot_id;
          if (mapChanged) areaNeedsRefresh = true;
          // Progress is global; record-specific completion feedback is not.
          // Returning to a record refreshes its saved results.

          return;
        }
        throw Error(job.message);
      }
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }
  } catch (error) {
    if (current()) throw error;
    // A departed screen must not publish a delayed record error.
  } finally {
    activeJob = null;
    $("job").hidden = true;
    $("main").removeAttribute("aria-busy");
    buttons.forEach((button, index) => {
      button.disabled = states[index];
    });
  }
}
async function loadArea(current = () => true) {
  createMap();
  const loaded = await api("/area");
  if (!current()) return;
  area = loaded;
  mapLoaded = true;
  areaNeedsRefresh = false;
  geometryLayer.clearLayers();
  placesLayer.clearLayers();
  routeLayer.clearLayers();
  selectedPointLayer.clearLayers();
  $("place-detail").replaceChildren();
  const saved = !!area.area;
  for (const id of ["map-empty"]) $(id).hidden = saved;
  for (const id of ["map-help", "map-details", "choose-start", "reuse-map"])
    $(id).hidden = !saved;
  $("plan-walk").hidden = !area.area?.public_start_confirmed;
  $("area-status").textContent = !saved
    ? "Not set up"
    : area.area.public_start_confirmed
      ? "Map saved"
      : "Confirm start";
  $("duplicate-review").replaceChildren();
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
      bubblingMouseEvents: false,
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
  startDuplicateReview(current);
}
function inspectPlace(place) {
  placeEditorState.changed();
  reportEntrance = null;
  $("add-place-details").hidden = true;
  selectedPointLayer.clearLayers();
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
  const corrections = disclosure("Report this place");
  const form = node("form",undefined,"form-grid");
  const select=node("select");
  for(const [value,label] of [["verify","I checked public access"],["entrance","Correct the entrance"],["not_there","This place is not here"],["closed","This place is closed"],["not_accessible","I could not access it"]]){
    const option=node("option",label);option.value=value;select.append(option);
  }
  const actionLabel=node("label","What did you find?","wide");actionLabel.append(select);
  const detail=node("input");detail.placeholder="What did you check or observe?";detail.maxLength=500;detail.minLength=3;detail.required=true;
  const detailLabel=node("label","Your observation","wide");detailLabel.append(detail);
  const entranceSummary=node("p","Choose the actual entrance on the map.","hint wide");
  const publicCheck=node("input");publicCheck.type="checkbox";
  const publicLabel=node("label",undefined,"check wide");publicLabel.append(publicCheck,node("span","I checked this entrance is on a public walking path."));
  let selected=null;
  const toggleEntrance=()=>{
    placeEditorState.changed();
    entranceSummary.hidden=publicLabel.hidden=select.value!=="entrance";
    publicCheck.required=select.value==="entrance";
    reportEntrance=select.value==="entrance"?{select(point){
      placeEditorState.changed();selected={lat:point.lat,lon:point.lng};publicCheck.checked=false;
      entranceSummary.textContent="New entrance chosen on your saved map. Confirm public access before saving.";pointMarker(point);
    }}:null;
  };
  select.onchange=toggleEntrance;toggleEntrance();
  corrections.ontoggle=()=>{if(corrections.open)toggleEntrance();else reportEntrance=null;};
  const button=node("button","Save report");button.type="submit";
  form.append(actionLabel,detailLabel,entranceSummary,publicLabel,button);
  form.onsubmit=async event=>{
    event.preventDefault();const current=placeEditorState.begin(navigation.checkpoint());if(!current)return;button.disabled=true;
    try{
      const data={action:select.value,detail:detail.value};
      if(select.value==="entrance"){
        if(!selected||!publicCheck.checked)throw Error("Choose an entrance on the map and confirm its public path.");
        data.entrance=selected;
      }
      await api("/places/"+place.id,{method:"PATCH",body:data});areaNeedsRefresh=true;
      if(!current())return;await loadArea(current);if(!current())return;
      inspectPlace(area.places.find(item=>item.id===place.id));message("Place report saved.");
    }catch(error){if(current())report(error);}
    finally{placeEditorState.finish();button.disabled=false;}
  };
  corrections.append(form);target.append(corrections);

}
const placeEditorState = NukkadPlaceEditor.create();
let placeEntranceReady = false, reportEntrance = null;
function pointMarker(point) {
  selectedPointLayer.clearLayers();
  L.circleMarker([point.lat, point.lng ?? point.lon], {radius:9,color:"#b36c12",fillColor:"#f5f1e7",fillOpacity:1}).addTo(selectedPointLayer);
}
function setPlaceEntrance(point, reviewed = true) {
  placeEditorState.changed();
  const form = $("pin-form");
  form.elements.lat.value = point.lat;
  form.elements.lon.value = point.lng ?? point.lon;
  form.elements.confirmed.checked = false;
  placeEntranceReady = reviewed;
  $("place-entrance").textContent = reviewed
    ? "Entrance chosen on your saved map. Check public access before saving."
    : "Suggested map point. Check the actual entrance on the map before confirming.";
  $("check-place-entrance").hidden = reviewed;
  pointMarker(point);
}
function beginPlaceEditor(point) {
  placeEditorState.changed();
  reportEntrance = null;
  $("add-place-details").hidden = false;
  if (point) setPlaceEntrance(point);
  $("add-place-details").scrollIntoView({block:"nearest"});
  $("place-query").focus({preventScroll:true});
}
$("add-place").onclick = () => beginPlaceEditor();
$("cancel-place").onclick = () => {
  placeEditorState.changed();
  placeSuggestions.cancel();
  $("pin-form").reset();
  placeEntranceReady = false;
  $("place-entrance").textContent = "Choose an entrance on the map or search for a place.";
  $("check-place-entrance").hidden = true;
  $("add-place-details").hidden = true;
  selectedPointLayer.clearLayers();
};
$("check-place-entrance").onclick = () => {
  const form=$("pin-form");
  if(form.elements.lat.value !== "") setPlaceEntrance({lat:Number(form.elements.lat.value),lon:Number(form.elements.lon.value)});
};
const placeSuggestions = NukkadSuggestions.create({
  input:$("place-query"),target:$("place-suggestions"),status:$("place-search-status"),scope:"place",api,node,
  current:()=>document.body.dataset.panel === "setup" && !$("add-place-details").hidden,
  invalidate:()=>{
    placeEditorState.changed();
    const form=$("pin-form");form.elements.lat.value=form.elements.lon.value="";form.elements.confirmed.checked=false;
    placeEntranceReady=false;$("check-place-entrance").hidden=true;
    $("place-entrance").textContent="Choose an entrance on the map or choose a suggestion.";
    selectedPointLayer.clearLayers();
  },
  select:(match)=>{
    const existing=area?.places.find(place=>place.id===match.place_id);
    if(existing){$("add-place-details").hidden=true;inspectPlace(existing);map.panTo([existing.point.lat,existing.point.lon]);return;}
    setPlaceEntrance(match.point,false);map.panTo([match.point.lat,match.point.lon]);
  },
});
function selectMapPoint(point) {
  if(reportEntrance){reportEntrance.select(point);return;}
  if(!$("add-place-details").hidden){setPlaceEntrance(point);return;}
  placeEditorState.changed();
  pointMarker(point);
  const target=$("place-detail");
  target.replaceChildren(node("h3","Use this point"),node("p","Choose the actual entrance on a public path.","hint"));
  const actions=node("div",undefined,"buttonrow");
  const start=node("button","Use as my start");start.type="button";
  start.onclick=()=>{
    const form=$("area-form");form.elements.lat.value=point.lat;form.elements.lon.value=point.lng;
    form.elements.public_start_confirmed.checked=false;hasSelectedLocation=true;locationRevision++;
    $("location-query").value=area.area.name;$("reuse-map").hidden=false;
    $("location-results").hidden=true;$("location-status").hidden=true;
    $("selected-location").textContent="Point chosen on your saved map. Confirm public access, then save this start.";
    form.scrollIntoView({block:"nearest"});form.elements.public_start_confirmed.focus({preventScroll:true});
  };
  const add=node("button","Add a place here");add.type="button";add.onclick=()=>beginPlaceEditor(point);
  actions.append(start,add);target.append(actions);target.scrollIntoView({block:"nearest"});
}
function renderQuest(value, navigate = true) {
  if (navigate && !navigation.isCurrent("preview", value.id))
    return navigation.go("preview", value.id, { quest: value });
  quest = value;
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
async function loadHistory(current = () => true) {
  const [values, outcomes] = await Promise.all([
    api("/quests"),
    api("/outcomes"),
  ]);
  if (!current()) return;
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
  await interestControls($("interest-review"), undefined, current);
}
document
  .querySelectorAll("a[data-panel], button[data-panel]")
  .forEach((button) => {
    button.onclick = (event) => {
      event.preventDefault();
      if (document.body.dataset.panel === button.dataset.panel)
        window.scrollTo({ top: 0, behavior: "instant" });
      else show(button.dataset.panel);
    };
  });
$("open-quest").onclick = async () => {
  const current = navigation.checkpoint();
  try {
    await loadAreaSummary();
    if (current())
      await show(
        area?.area?.public_start_confirmed ? "quest-form-panel" : "setup",
      );
  } catch (error) {
    if (current()) report(error);
  }
};
$("plan-walk").onclick = () => show("quest-form-panel");
$("choose-start").onclick = async () => {
  const showing = show("setup");
  const stillHere = navigation.checkpoint();
  await showing;
  if (!stillHere()) return;
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
function selectLocation(match) {
  hasSelectedLocation = true;
  const form = $("area-form");
  form.elements.lat.value = match.point.lat;
  form.elements.lon.value = match.point.lon;
  form.elements.name.value = match.name.slice(0,100);
  form.elements.public_start_confirmed.checked = false;
  $("selected-location").textContent = match.label;
  $("location-status").textContent = "Location selected. Fetch your neighbourhood map below.";
  $("location-status").hidden = false;
}
const neighbourhoodSuggestions = NukkadSuggestions.create({
  input: $("location-query"), target: $("location-results"), status: $("location-status"),
  scope: "neighbourhood", api, node, select: selectLocation, invalidate: clearLocationSelection,
  current: () => document.body.dataset.panel === "setup",
});
$("location-form").onsubmit = async (event) => {
  event.preventDefault();
  neighbourhoodSuggestions.cancel();
  clearLocationSelection();
  const current = navigation.checkpoint();
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
    if (revision !== locationRevision || !current()) return;
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
        neighbourhoodSuggestions.choose(match);
      };
      button.setAttribute("aria-pressed", "false");
      item.append(button);
      target.append(item);
    }
    target.hidden = !result.matches.length;
  } catch (error) {
    if (revision === locationRevision && current()) {
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
  const current = navigation.checkpoint();
  try {
    const file = $("area-form").elements.extract.files[0];
    let job;
    if (file) {
      const data = new FormData();
      data.append("metadata", JSON.stringify(areaInput()));
      data.append("extract", file);
      job = await api("/areas/import", { method: "POST", body: data });
    } else job = await api("/areas", { method: "POST", body: areaInput() });
    await runJob(
      job,
      async (_, stillHere) => {
        await loadArea();
        if (stillHere()) show("setup");
      },
      current,
    );
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
  const current = navigation.checkpoint();
  try {
    await runJob(
      await api("/areas/reuse", { method: "POST", body: areaInput() }),
      async (_, stillHere) => {
        await loadArea();
        if (stillHere()) show("setup");
      },
      current,
    );
  } catch (e) {
    if (current()) report(e);
  }
};
$("pin-form").onsubmit = async (event) => {
  event.preventDefault();
  const current = placeEditorState.begin(navigation.checkpoint());
  if(!current) return;
  $("save-place").disabled=true;
  try {
    if(!placeEntranceReady) throw Error("Choose or check the actual entrance on the map before saving.");
    const v=formValues("pin-form");
    const saved=await api("/places",{method:"POST",body:{name:v.name,kind:v.kind,entrance:{lat:Number(v.lat),lon:Number(v.lon)},descriptors:v.descriptor?[v.descriptor]:[],public_access_confirmed:!!v.confirmed}});
    areaNeedsRefresh=true;
    if(!current())return;
    await loadArea(current);
    if(!current())return;
    $("cancel-place").click();
    inspectPlace(area.places.find(place=>place.id===saved.id)||saved);
    map.panTo([saved.point.lat,saved.point.lon]);
    message("Place saved. You can now find it on your map.");
  } catch(error){if(current())report(error);}
  finally {placeEditorState.finish();$("save-place").disabled=false;}
};
$("quest-form").onsubmit = async (event) => {
  event.preventDefault();
  const current = navigation.checkpoint();
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
      async (result, stillHere) => {
        const value = await api("/quests/" + result.quest_id);
        if (stillHere()) return renderQuest(value);
      },
      current,
    );
  } catch (e) {
    if (current()) report(e);
  }
};
$("accept").onclick = async () => {
  const current = navigation.checkpoint();
  try {
    const value = await api("/quests/" + quest.id + "/accept", {
      method: "POST",
    });
    if (current()) renderQuest(value);
  } catch (e) {
    if (current()) report(e);
  }
};
$("print").onclick = async () => {
  const current = navigation.checkpoint();
  try {
    await api("/quests/" + quest.id + "/accept", { method: "POST" });
    await $("card-preview").decode();
    if (current()) window.print();
  } catch (error) {
    if (current()) report(error);
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
  const current = navigation.checkpoint();
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
    if (!current()) return;
    message("Walking settings saved.");
    void refreshReadiness(current).catch((error) => {
      if (current()) report(error);
    });
  } catch (e) {
    if (current()) report(e);
  }
};
async function init() {
  sessionToken = (await api("/session")).token;
}
function createMap() {
  if (map) return;
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
}
let summaryTask, profileTask, settingsTask;
let profileLoaded = false,
  settingsLoaded = false;
async function loadAreaSummary() {
  if (!summaryTask)
    summaryTask = api("/area/status")
      .then((summary) => {
        if (summary.snapshot_id !== area?.snapshot_id) {
          mapLoaded = false;
          areaNeedsRefresh = true;
        }
        area = { ...area, ...summary };
      })
      .finally(() => {
        summaryTask = null;
      });
  return summaryTask;
}
async function loadProfile() {
  if (profileLoaded) return;
  if (!profileTask)
    profileTask = api("/profile")
      .then((profile) => {
        $("interests").value = profile.interests.join(", ");
        profileLoaded = true;
      })
      .finally(() => {
        profileTask = null;
      });
  return profileTask;
}
async function loadSettings() {
  if (settingsLoaded) return;
  if (!settingsTask)
    settingsTask = api("/settings")
      .then((settings) => {
        for (const [name, value] of Object.entries(settings)) {
          const input = $("settings-form").elements[name];
          if (!input) continue;
          if (input.type === "checkbox") input.checked = value;
          else input.value = value ?? "";
        }
        settingsLoaded = true;
      })
      .finally(() => {
        settingsTask = null;
      });
  return settingsTask;
}
let readinessRevision = 0;
async function refreshReadiness(current = navigation.checkpoint()) {
  const revision = ++readinessRevision;
  const ready = await api("/readiness");
  if (!current() || revision !== readinessRevision) return;
  $("model-status").textContent =
    ready.model_status === "ready"
      ? "Ready"
      : ready.model_status === "unsupported"
        ? "Unsupported model"
        : ready.model_status === "missing"
          ? "Model missing"
          : "Ollama unavailable";
  $("readiness").textContent =
    ready.model_status === "ready"
      ? `${ready.selected_model} is available on this laptop.`
      : ready.model_status === "unsupported"
        ? "Choose an installed local model. Cloud-backed inference is disabled."
        : ready.model_status === "missing"
          ? `Download ${ready.selected_model} in Ollama or choose an installed model. Basic suggestions can still be used when local AI fails.`
          : "Start Ollama on this laptop to use local AI. Basic suggestions can still be used when local AI fails.";
  if (ready.checks) {
    const issues = Object.entries(ready.checks).filter(
      ([name, check]) => name !== "model" && check.status !== "ready",
    );
    if (issues.length)
      $("readiness").append(
        node("p", issues.map(([, check]) => check.reason).join(". "), "hint"),
      );
  }
  $("models").replaceChildren();
  for (const model of ready.models) {
    const item = node("option");
    item.value = model;
    $("models").append(item);
  }
}
const initialized = init();
let photoRenderRevision = 0;
async function renderPlacePhotos(outcomeId, screenCurrent = navigation.checkpoint()) {
  const revision = ++photoRenderRevision;
  const current = ()=>screenCurrent() && revision === photoRenderRevision;
  const experiences = await api(`/outcomes/${outcomeId}/experiences`);
  if (!current()) return;
  const target = $("place-photos");
  target.replaceChildren();
  for (const experience of experiences.filter(item=>item.active)) {
    const photos = await api(`/experiences/${experience.id}/photos`);
    if (!current()) return;
    const section = node("section", undefined, "place-upload entry");
    section.append(node("h2", experience.place_name), node("p", `${photos.length}/5 photos for this reported visit. Save changed place notes before adding photos.`, "hint"));
    const grid = node("div", undefined, "photo-grid");
    for (const photo of photos) {
      const figure = node("figure");
      const image = node("img");
      image.src = `/api/photos/${photo.id}/thumbnail`;
      image.alt = `Your photo from ${experience.place_name}`;
      image.loading = "lazy";
      const remove = node("button", "Remove photo");
      remove.type = "button";
      remove.onclick = async()=>{try {await api(`/photos/${photo.id}`, {method:"DELETE"});if(screenCurrent()) await renderPlacePhotos(outcomeId, screenCurrent);}catch(error){if(screenCurrent()) report(error);}};
      figure.append(image, remove);
      grid.append(figure);
    }
    section.append(grid);
    const label = node("label", "Add photos (JPEG, PNG or WebP)");
    const input = node("input");
    input.type = "file";
    input.accept = "image/jpeg,image/png,image/webp";
    input.multiple = true;
    input.disabled = photos.length>=5;
    label.append(input);
    const upload = node("button", "Save selected photos");
    upload.type = "button";
    upload.disabled = photos.length>=5;
    upload.onclick = async()=>{
      let failure;
      try {
        const files = [...input.files];
        if(!files.length) throw Error("Choose a photo first.");
        if(files.length+photos.length>5) throw Error("Choose at most five photos in total for this visit.");
        if(files.some(file=>file.size>20*1024*1024)) throw Error("Each photo must be at most 20 MiB.");
        upload.disabled=true;
        for(const file of files){const data = new FormData();data.append("photo", file);await api(`/experiences/${experience.id}/photos`, {method:"POST",body:data});}
      } catch(error){failure=error;} finally {
        if(screenCurrent()) {await renderPlacePhotos(outcomeId,screenCurrent);if(failure) report(failure);else message("Photos saved locally.");}
      }
    };
    section.append(label, upload);
    target.append(section);
  }
}
const outcomeDrafts = new Map();
let outcomeQuest;
function retainOutcomeDraft() {
  if (outcomeQuest) outcomeDrafts.set(outcomeQuest, formValues("outcome-form"));
}
async function renderOutcome(value, existing, current) {
  if (!current()) return;
  if (outcomeQuest === value.id) {
    if (existing) {
      await window.showJournal(existing, current);
      if (current()) await renderPlacePhotos(existing.id, current);
    }
    return;
  }
  const experiences = existing ? await api(`/outcomes/${value.id}/experiences`) : [];
  if (!current()) return;
  retainOutcomeDraft();
  outcomeQuest = value.id;
  quest = value;
  $("outcome-stops").replaceChildren();
  for (const [index, place] of quest.stops.entries()) {
    const label = node("div", `${index + 1}. ${place.name}`);
    const select = node("select");
    select.name = "stop-" + place.id;
    select.setAttribute("aria-label", `${place.name}: reached status`);
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
      outcomeDrafts.get(value.id)?.["stop-" + place.id] ||
      existing?.stops.find((item) => item.id === place.id)?.status ||
      "unresolved";
    label.append(select);
    const noteLabel = node("label", "Your experience at this place (optional)");
    const note = node("textarea");
    note.name = "experience-" + place.id;
    note.maxLength = 8000;
    note.rows = 3;
    note.value = outcomeDrafts.get(value.id)?.[note.name] ?? experiences.find(item=>item.stop_id===place.id)?.note ?? "";
    noteLabel.append(note);
    label.append(noteLabel);
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
      outcomeDrafts.get(value.id)?.[name] ??
      existing?.[name] ??
      (name === "status" ? "completed" : "");
  updateOutcomeReason();
  $("journal-review").replaceChildren();
  if (existing && window.showJournal) {
    await window.showJournal(existing, current);
    if (current()) await renderPlacePhotos(existing.id, current);
  } else $("place-photos").replaceChildren();
}
$("return").onclick = () => show("outcome");

function updateOutcomeReason() {
  $("reason-label").hidden =
    $("outcome-form").elements.status.value !== "turned_back";
}
$("outcome-form").elements.status.onchange = updateOutcomeReason;
$("outcome-form").onsubmit = async (event) => {
  event.preventDefault();
  const current = navigation.checkpoint();
  const savingQuest = quest;
  try {
    const v = formValues("outcome-form");
    const outcome = await api("/quests/" + savingQuest.id + "/outcome", {
      method: "PUT",
      body: {
        status: v.status,
        note: v.note,
        reason: v.reason,
        actual_minutes:
          v.actual_minutes === "" ? null : Number(v.actual_minutes),
        screen_minutes:
          v.screen_minutes === "" ? null : Number(v.screen_minutes),
        place_experiences: savingQuest.stops.map(place=>({stop_id:place.id,note:v["experience-"+place.id] || ""})),
        stops: savingQuest.stops.map((place) => ({
          id: place.id,
          status: v["stop-" + place.id],
        })),
      },
    });
    areaNeedsRefresh = true;
    if (!current()) return;
    message(
      "Note and visits saved. Only the stops you marked as reached count as visited.",
    );
    if (window.showJournal) await window.showJournal(outcome, current);
    if (current()) await renderPlacePhotos(outcome.id, current);
  } catch (e) {
    if (current()) report(e);
  }
};
window.showJournal = async (outcome, current = navigation.checkpoint()) => {
  if (!current()) return;
  const target = $("journal-review");
  target.replaceChildren(node("h2", "Your saved note"));
  const original = node("pre", outcome.note);
  original.style.whiteSpace = "pre-wrap";
  target.append(original);
  if (outcome.original_note !== outcome.note) target.append(disclosure("First saved version", node("pre", outcome.original_note)));
  target.append(
    node(
      "p",
      "Optional: local AI can draft a third-person journal and suggest interests for separate review. Your own words stay saved.",
      "hint",
    ),
  );
  const generate = node("button", "Draft a journal");
  generate.onclick = async () => {
    const current = navigation.checkpoint();
    try {
      await runJob(
        await api("/outcomes/" + outcome.id + "/reflect", { method: "POST" }),
        async () => {
          const saved = await api("/quests/" + outcome.id + "/outcome");
          if (current()) await window.showJournal(saved, current);
        },
        current,
      );
    } catch (e) {
      if (current()) report(e);
    }
  };
  target.append(generate);
  const journal = await api("/outcomes/" + outcome.id + "/journal");
  if (!current()) return;
  if (journal) {
    target.append(
      node("h2", "Review your journal"),
      node(
        "p",
        `${labelFor(journal.status)} · ${journal.mode === "local AI journal" ? "Third-person draft written with local AI" : journal.mode === "local AI extract" ? "Earlier passage selected with local AI" : "Exact extract without AI wording"}`,
        "hint",
      ),
    );
    const draft = node("textarea");
    draft.value = journal.text;
    draft.maxLength = 2000;
    draft.setAttribute("aria-label", "Review journal draft");
    target.append(draft);
    if (journal.passages?.length) target.append(disclosure("Source passages", ...journal.passages.map(item=>node("p", item.quote, "hint"))));
    if (journal.version_id) {
      const versions = await api(`/outcomes/${outcome.id}/journal/versions`);
      if (!current()) return;
      const earlier = versions.filter(item=>item.version_id!==journal.version_id);
      if (earlier.length) target.append(disclosure("Earlier journal versions", ...earlier.map(item=>node("p", item.text))));
    }
    const actions = node("div", undefined, "buttonrow");
    for (const status of ["accepted", "rejected"]) {
      const button = node(
        "button",
        status === "accepted" ? "Save this journal" : "Discard draft",
      );
      button.onclick = async () => {
        try {
          await api("/outcomes/" + outcome.id + "/journal", {
            method: "PATCH",
            body: { status, text: draft.value, version_id: journal.version_id },
          });
          if (current()) await window.showJournal(outcome, current);
        } catch (e) {
          if (current()) report(e);
        }
      };
      actions.append(button);
    }
    target.append(actions);
  }
  const holder = node("div");
  target.append(holder);
  await interestControls(holder, outcome.id, current);
};
async function interestControls(target, source, current = navigation.checkpoint()) {
  const items = await api("/interests");
  if (!current()) return;
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
          if (current()) await interestControls(target, source, current);
        } catch (e) {
          if (current()) report(e);
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
  const current = navigation.checkpoint();
  try {
    const value = await api("/air-quality/refresh", { method: "POST" });
    if (current()) renderAir(value);
  } catch (e) {
    if (current()) report(e);
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

// Resolve routes from persistent records; navigation itself never performs writes.
navigation = NukkadNavigation.createNavigation({
  browser: window,
  prepare(route) {
    document.querySelectorAll(".panel").forEach((panel) => {
      panel.inert = false;
      panel.removeAttribute("aria-busy");
    });
    const id = NukkadNavigation.panels[route.view];
    renderPanel(id);
    const loading = route.view !== "home";
    $(id).inert = loading;
    $(id).setAttribute("aria-busy", String(loading));
    $("navigation-loading").hidden = !loading;
    $("navigation-loading").textContent = loading
      ? `Loading ${route.view === "neighbourhood" ? "your neighbourhood" : "this page"}… You can still use the navigation above.`
      : "";
  },
  settled() {
    document.querySelectorAll(".panel").forEach((panel) => {
      panel.inert = false;
      panel.removeAttribute("aria-busy");
    });
    $("navigation-loading").hidden = true;
  },
  async resolve(route, current, supplied) {
    if (!current()) return route;
    if (route.view === "plan") {
      await loadAreaSummary();
      if (!current()) return route;
    }
    if (route.view === "folder") {
      try {
        if (!route.place) throw Error("Choose a place folder first.");
        const folder = await api(
          "/collection/" + encodeURIComponent(route.place),
        );
        return { ...route, place: folder.id, folder };
      } catch (error) {
        return {
          view: "history",
          walk: null,
          notice:
            "That place folder could not be opened. Choose a reported place from My walks.",
        };
      }
    }
    if (route.view === "plan" && !area?.area?.public_start_confirmed)
      return { view: "neighbourhood", walk: null };
    if (["preview", "note"].includes(route.view)) {
      try {
        if (!route.walk) throw Error("Choose a saved walk first.");
        const value =
          supplied?.quest ||
          (await api("/quests/" + encodeURIComponent(route.walk)));
        if (!current()) return route;
        if (route.view === "note" && value.status !== "accepted")
          return { view: "preview", walk: value.id, quest: value };
        const outcome =
          route.view === "note"
            ? await api("/quests/" + encodeURIComponent(value.id) + "/outcome")
            : null;
        return { ...route, quest: value, outcome };
      } catch (error) {
        return {
          view: "history",
          walk: null,
          notice:
            "That walk could not be opened. Choose a saved walk from My walks.",
        };
      }
    }
    return route;
  },
  async render(route, current) {
    const id = NukkadNavigation.panels[route.view];
    renderPanel(id);
    if (route.view === "neighbourhood") {
      if (!mapLoaded || areaNeedsRefresh) await loadArea(current);
      else startDuplicateReview(current);
    }
    if (route.view === "plan") await loadProfile();
    if (route.view === "settings") await loadSettings();
    if (!current()) return;
    $(id).inert = false;
    const heading = $(id).querySelector("h1");
    heading.tabIndex = -1;
    heading.focus({ preventScroll: true });
    if (route.quest) quest = route.quest;
    if (route.view === "preview") renderQuest(route.quest, false);
    if (route.view === "note")
      await renderOutcome(route.quest, route.outcome, current);
    if (route.view === "history") {
      await loadHistory(current);
      if (current()) await collectionUI.load(current);
    }
    if (route.view === "folder")
      await collectionUI.renderFolder(route.folder, current);
    if (route.view === "settings") {
      $("readiness").textContent = "Checking local components…";
      void refreshReadiness(current).catch((error) => {
        if (current()) $("readiness").textContent = error.message;
      });
      void api("/air-quality")
        .then((air) => {
          if (current()) renderAir(air);
        })
        .catch((error) => {
          if (current()) report(error);
        });
    }
    if (route.notice && current()) message(route.notice);
  },
  onError: report,
});
const collectionUI = NukkadCollection.create({
  api,
  node,
  $,
  navigation,
  runJob,
  report,
  message,
});
void navigation.start();
initialized.catch((error) =>
  message(`Local session unavailable: ${error.message}`, true),
);

function startDuplicateReview(current) {
  $("duplicate-review").replaceChildren(
    node("p", "Checking for similar places…", "hint"),
  );
  void renderDuplicateReview(current).catch((error) => {
    if (current())
      $("duplicate-review").replaceChildren(
        node(
          "p",
          `Similar-place review unavailable: ${error.message}. Reopen Neighbourhood to retry.`,
          "hint",
        ),
      );
  });
}
async function renderDuplicateReview(current = () => true) {
  const pairs = await api("/places/duplicates");
  if (!current()) return;
  const target = $("duplicate-review");
  target.replaceChildren();
  if (!pairs.length) return;
  const details = disclosure("Possible duplicate places");
  details.append(
    node(
      "p",
      "Nearby places with similar names remain separate until you review them.",
      "hint",
    ),
  );
  for (const pair of pairs) {
    const section = node("div", undefined, "entry");
    section.append(
      node(
        "p",
        `${pair.names.join(" / ")} · ${pair.distance_meters} metres apart`,
      ),
    );
    for (const [decision, label] of [
      ["merge", "These are the same place"],
      ["separate", "Keep them separate"],
    ]) {
      const button = node("button", label);
      button.onclick = async () => {
        const current = navigation.checkpoint();
        try {
          await api(`/places/duplicates/${pair.id}`, {
            method: "PATCH",
            body: { decision, target_id: pair.place_ids[0] },
          });
          areaNeedsRefresh = true;
          if (current()) await loadArea();
        } catch (error) {
          if (current()) report(error);
        }
      };
      section.append(button);
    }
    details.append(section);
  }
  target.append(details);
}

function positionFeedback() {
  const rail = document.querySelector(".notification-rail");
  rail.style.bottom = "";
  if (window.innerWidth > 600) return;
  const active = document.activeElement;
  if (!active?.matches("input, textarea, select, button")) return;
  const rect = active.getBoundingClientRect();
  const viewportHeight = window.visualViewport?.height || window.innerHeight;
  if (rect.bottom > viewportHeight - rail.offsetHeight - 20)
    rail.style.bottom = Math.max(12, window.innerHeight - rect.top + 12) + "px";
}
document.addEventListener("focusin", positionFeedback);
document.addEventListener("focusout", () => setTimeout(positionFeedback, 0));
window.visualViewport?.addEventListener("resize", positionFeedback);

$("copy-email").onclick = async () => {
  $("copy-email").disabled = true;
  await NukkadNotifications.copyEmail({ clipboard: navigator.clipboard, tooltip: $("email-tooltip"), notify: message });
  $("copy-email").disabled = false;
};
