# Product and implementation contracts

Nukkad turns a neighbourhood snapshot into a short, personal walking quest.
The screen is preparation and return; the walk is the experience.

## Authority

- OpenStreetMap and personal observations provide evidence, not guarantees.
- Code filters places and route segments and validates the complete return walk.
- A local model ranks eligible IDs and writes bounded observation invitations.
- Users accept a quest and review inferred interests before future use.

## Local operation

The Python process serves the interface and calls Ollama on localhost. Personal
data belongs in the operating system application-data directory, outside Git.
Map snapshots and model weights require an initial download. Streets and parks
are rendered from saved geometry rather than bulk-downloaded map tiles.

## Records and provenance

Snapshot IDs, source IDs, raw tags, retrieval dates, graph fingerprints, entrance
evidence, and user corrections must remain available. Refreshes create new
snapshots. Unknown access remains unknown; explicitly private places and routes
are excluded. A polygon centroid is not an entrance.

Visits are derived from editable outcomes. The eligible mapped-place denominator
is frozen per snapshot. User-added pins are counted separately. Reported visits
do not establish GPS tracks or traversed streets.

## Generation

There is one active local generation job. Ranking, routing, and observation
generation are separate stages. A ranking must contain supplied IDs exactly
once. Code calculates every leg, return, observation time, reserve, and daylight
limit. Ranking and prompt fallback modes are independently recorded and shown.

Prompts invite observation, never invent historical facts, distances, objects,
or permission. Retry at most once per task within a shared deadline. A usable
quest is revalidated at acceptance; delayed departure can invalidate it.

## Memory

Original notes are retained exactly. Journal drafts are editable. An inferred
interest requires an exact quote and source note, starts pending, and becomes
active only after acceptance. Editing source text invalidates unsupported
proposals. Neutral mentions are not automatically treated as preferences.

## Evidence

Deterministic fixtures test route and storage rules; real-model runs measure
runtime and output quality separately. Blinded comparisons use identical
candidates and planners. Offline claims require an actual disconnected run.
Outdoor results require a person's real observations; fixtures and automated
checks must never be described as field trials.

## Interface language and hierarchy

The main flow is set up a neighbourhood, plan a walk, review it, save a phone image
or print a card, and record a note after returning. Buttons describe the action
and the home action reflects whether a map and confirmed start exist. Selecting
map coordinates is separate from confirming or saving public access.

Forms group related decisions and explain units beside the fields. Local model
configuration, distance/time limits, air-quality settings, saved-map import,
source metadata and generation diagnostics remain available in labelled
expandable sections. An invalid field opens its containing section before focus
moves to it. Route length, total time, latest departure, access uncertainty,
daylight policy and independently labelled AI/fallback behaviour remain visible
when reviewing a walk.

My walks presents one entry per quest with its outcome and note. Visits remain
self-reported and added places remain counted separately. Reflections and
inferred interests still require explicit review; source notes can be inspected.

The two supplied PNG logos are bundled locally without image edits:
`static/brand/nukkad-light.png` in the header and `static/brand/nukkad-dark.png`
in the footer. The paper and ink colours match their backgrounds. No fonts,
logos or other interface assets are fetched from third-party hosts at runtime.
