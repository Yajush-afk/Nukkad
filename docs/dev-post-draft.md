---
title: "Nukkad: a local AI invitation to notice your neighbourhood"
published: false
tags: devchallenge, hf26challenge
---

<!-- REVIEW DRAFT. Add a viewable demo link and review the evidence before publication. No post has been published by this repository. -->

My entry for the [Hacktoberfest Week 1 Touch Grass challenge](https://dev.to/challenges/hacktoberfest-week1-2026-10-05).

## What I Built

Nukkad turns a little free time into a small neighbourhood walk. Give it your interests and 20–60 minutes; a local open-weight model orders nearby eligible destinations, and a walking planner checks the entire trip back to your start. You review it, save a phone image or print a card, and close the laptop.

The idea starts with a familiar barrier: wanting to go outside without making a whole expedition out of it. I wanted to begin close to home around Rajhans Apartments in Indirapuram, rather than build another feed of places to scroll through. The suggested location still needs a personally confirmed public start and entrance checks.

After a walk, report what you reached, skipped or could not resolve, and keep a note in your own words. Your map marks reported destinations. A local journal extract and tentative interests are yours to review; accepted insights can help order a later quest. It never claims you walked every surrounding street because you visited one place.

## Demo

**[PUBLICATION MARKER: add the reviewed, viewable video link.]**

The repository includes an isolated synthetic demo you can reproduce without downloading a map. It generates using your installed local model and begins without fabricated visits or notes. The area and features are explicitly artificial; its card must never be used for navigation.

A live browser walkthrough on 9 October used Gemma 4 E2B to generate a synthetic two-stop card in 10.17 seconds, with validated local ranking and wording. Acceptance, PNG download, a not-taken outcome and an exact-quote architecture proposal worked, and the note/proposal survived reload. This was software evidence, not an outdoor outing. Opening the UI at a phone-sized viewport checked layout; actual phone card use still needs to be recorded.

### Taking it outside

**No physical outing has been recorded in the current evidence.** Before adding an outdoor account here, record the actual start, attempted stops, manually measured screen/outdoor time, entrance problems and any turn-back. Include failures. Do not replace this statement with a successful story until an outing actually happened. The app's design aims to shorten preparation; a measured reduction in screen time is not yet established.

## Code

[Nukkad on GitHub](https://github.com/Yajush-afk/Nukkad)

Start with the [installation guides](https://github.com/Yajush-afk/Nukkad/blob/main/docs/setup.md) or [synthetic demo](https://github.com/Yajush-afk/Nukkad/blob/main/docs/demo.md). Application code is MIT licensed, Leaflet retains its BSD licence, and OSM data is credited under ODbL. Model weights are downloaded separately under the chosen model's terms.

## How I Built It

The application runs on a laptop: Python 3.12, FastAPI, SQLite, OSMnx/NetworkX, Astral daylight calculations, local Leaflet geometry, CairoSVG card export and Ollama. Gemma 4 E2B is the measured default. Saved map snapshots retain raw source, graph fingerprint, acquisition date and the original eligible-place denominator.

The division of responsibilities matters. Gemma receives a bounded set of eligible IDs, explicit interests and reviewed local context. Its ranking must contain each ID exactly once, and its reasons must come from grounded choices. Code computes all outbound and return legs and checks distance, walking time, stop time, reserve, daylight and current eligibility again at acceptance/export. An imported polygon centre does not become a fictitious entrance.

Wander offers small observation invitations. Seek uses only a selected stop's recorded feature evidence and labels its source. Wording goes through separate claim/layout checks. Ranking and wording failures have independent fallback labels; an apparently nice card is not automatically evidence of successful inference.

Return notes are preserved exactly. The model selects an exact journal excerpt and proposes interests with exact source quotes and explicit positive preference evidence. Pending/rejected interests do not affect later rankings. This conservative English-oriented check prevents some unsupported inferences; it does not prove an interpretation is right, so review remains necessary.

### What I measured

On the development laptop (about 14 GiB RAM, RTX 3050 Ti with 4 GiB VRAM), a separate ten-case Gemma 4 E2B response/ID benchmark had a 4.953 s median and a 75.936 s maximum, including first-case loading. Those are task timings, not complete outing or app-startup timings.

The 8 October full-generation comparison used ten artificial contexts and the same candidates, planner and constraints for nearest-unvisited, deterministic interest ranking and local AI. Nine cases were feasible: all nine used validated AI ranking, six used AI wording and three used wording templates. One constrained case correctly produced no quest in every mode. With an already loaded model, median generation was 5.16 s and maximum 10.77 s. AI selected a different stop sequence from the interest baseline in two cases. Blinded human ratings remain pending; different is not necessarily better.

Deterministic tests cover failure paths, updates, persistence and the core API loop. Actual-model synthetic evaluations ran under a Python-process guard denying non-loopback socket connections and recorded zero such attempts. That guard does not disconnect the whole laptop or constrain the independently running Ollama daemon. A physically disconnected trial remains to be recorded. Detailed dates, protocols and limits are in the [evaluation guide](https://github.com/Yajush-afk/Nukkad/blob/main/docs/evaluation.md).

## Why Does Open Innovation Matter?

The useful context here is personal: nearby places, reported visits, casual observations and tentative interests. With local weights, Nukkad can send that context to a model running on the same laptop and keep it in a database the user controls. Generation does not need a paid API key or a hosted notes service. The UI, model, saved graph, fonts and renderer are available locally after setup; initial downloads and optional forecast refreshes still need internet.

Open components also let the implementation expose and change its behaviour. The model adapter is replaceable, the baseline rules and validators are inspectable, and a person can remove an inferred interest or correct a destination. Gemma 3 passed the separate ID/response benchmark and one sequential synthetic production-generation check with validated AI ranking and wording in 19.03 seconds. That supports model swapping, not equivalent quality or speed. I have not fine-tuned a model or claimed a recommendation-quality win over a closed service.

The concrete advantage over a hosted inference dependency is control of context and runtime: no inference account, upload of return notes or per-request API bill is required. It still consumes hardware, storage and electricity. Openness made that architecture possible and made the failures easier to inspect. Whether these walks feel more useful than simple deterministic suggestions still needs human comparison and real use.

### Remaining limits

OSM may omit an entrance or describe access incorrectly. The card has no live GPS, current gate verification, guaranteed accessible route or street-level air sensor. Optional U.S. AQI gating uses a regional CAMS global forecast via Open-Meteo; unknown/stale or above-threshold data blocks quests when enabled. Phone readability, 2–3 actual outings, physical disconnection and blinded ratings are outstanding human checks, not completed milestones.

## Prize Categories

**Best Use of Gemma**: Gemma 4 E2B performs actual local destination ranking and grounded wording; labelled fallbacks remain visible. No other partner category is claimed here.

<!-- The official template's agent-session section is optional. Add a reviewed session link only if desired. Recheck challenge rules and every claim before publishing. -->
