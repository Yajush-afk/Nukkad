# Interface checks

The regular CI suite runs Python interface contracts and dependency-free Node
checks for navigation and decorative motion. `tests/browser-smoke.cjs` additionally
exercises real Chromium: desktop/mobile layouts, keyboard navigation, Back/Forward,
scroll restoration, unsaved fields, direct URLs, reduced motion and unavailable WebGL.

Use a new empty data directory for the primary browser server. These checks expect
an unconfigured neighbourhood and must not run against the personal server.

```sh
NUKKAD_DATA_DIR="$(mktemp -d /tmp/nukkad-interface-data.XXXXXX)" uv run nukkad serve --port 8003
```

In another terminal, install browser tooling outside the project:

```sh
npm install --prefix /tmp/nukkad-browser-check playwright@1.64.0 --no-audit --no-fund
/tmp/nukkad-browser-check/node_modules/.bin/playwright install chromium
NODE_PATH=/tmp/nukkad-browser-check/node_modules NUKKAD_BROWSER_URL=http://localhost:8003 node tests/browser-smoke.cjs
```

Optionally set `NUKKAD_MAP_BROWSER_URL` to a second server using an isolated copy
of saved map data. This enables real-map disclosure, zoom and pan checks without
saving any changes. `NUKKAD_BROWSER_OUTPUT` chooses the ignored screenshot directory.
No app runtime dependency on Playwright is introduced.

## Working-page feedback, suggestions and place editing

Automated tests cover queued/persistent feedback, paused timers, truthful clipboard success/failure, offline suggestion indexing, alias identity, provider limits/failures, obsolete queries and selection revision guards. Isolated browser checks verified mobile notifications preserve scroll, keyboard suggestion selection works while online results fail, and selecting a location does not activate it.

Custom-place editing now sits immediately below map details. A map entrance adjustment retains name/type/observation and clears public confirmation. Returning from Home retains the unsaved draft. Synthetic browser checks exercise duplicate submission and a delayed save while another place is selected. No coordinate controls are exposed; coordinates remain internal. Outside-area creation is rejected before graph loading. Reports preserve correction history and canonical identity.

Map controls use horizontal zoom buttons and a percentage reset. Neighbourhood 100% means zoom 15; My start restores the saved point without GPS. Route 100% is its fitted bounds. Controlled browser wheel events passed through without zoom; Ctrl+wheel pinch changed zoom and prevented only that deliberate gesture. Touch zoom remains enabled in Leaflet; physical touch/phone checks remain pending. Delayed fitting checks navigation and walk identity. Saved maps appear before collapsed setup; missing and unconfirmed starts reveal setup. Settings contains snapshot provenance; each real map retains readable linked OSM attribution in addition to footer thanks.

## Dashboard and gallery

The visible history label is Dashboard and its heading is Your neighbourhood notebook; `?view=history` and folder URLs remain unchanged. Folder links use locally bundled tab artwork, saved cover photos or static cream/green/sky gradients. Cards stay within 330 px; folder photos use three desktop columns and two mobile columns. Current Location CARD renders first; editing, card actions and earlier versions use disclosures. Hover/focus motion is disabled for reduced motion.

An unresolved readiness response no longer delays cards/photos/journals or manual actions. Revision guards reject older readiness responses. Browser checks verified current-card-first ordering, responsive grids, unsaved summary retention and Back/Forward. A direct-preview reload exposed an old dependency on the uninitialised Neighbourhood map; removal and focused regression coverage now allow every stop and export action to render independently.

The isolated HTTP integration fixture exercises explicit search, import, start confirmation, local suggestions, custom-place verification, route preview, generation with labelled model fallback, acceptance/export, outcome/place note, synthetic photo upload, manual card creation/edit/export and stable collection/version counts. All writes and images stay in temporary/synthetic data. Real Photon availability, physical phone gestures and outdoor trials remain separate from deterministic software checks.

### Viewport progress alignment

The selected-place screenshot exposed a legacy `#job` transform in the later theme
stylesheet. The rail was correctly fixed to the viewport, but its progress child
was translated 180 px left. Removed the obsolete centring and explicitly reset
child positioning. Browser geometry now places progress at the rail's right edge,
24 px from the usable desktop viewport. Existing notification timers, persistent
errors and cancellation remain unchanged. The stylesheet regression and notification
suite pass; no personal records were written for this check.

### Selected-place experience and report panel

Confirmed the original panel had no experience action and only offered access
corrections. The isolated browser now opens a place-only note/date/photo form;
Report this place switches to a report form inside the same panel, with no nested
report disclosure or separate card. The neighbourhood setup disclosure closes on
place selection. Experience drafts survive reselection, duplicate submissions are
blocked, and departed selections suppress feedback. An isolated saved visit joined
the existing folder as a second visit without changing its one-card count.

HTTP regressions cover direct visits without quests, idempotency, stale edits,
future dates, source aliases, dependent journal/interest/card invalidation, photo
upload and backup/restore. Personal data was not used for test writes.

### Intermittent neighbourhood acquisition

The reported main-provider 504 / backup-provider 500 is reproduced by controlled
HTTP responses. Previously the download stopped after those two failures. The new
regression recovers through four smaller sections, preserves the original bounds,
and deduplicates source nodes. Failed sections, conflicting edits, missing geometry,
rate limits and cancellation leave the previous target and active snapshot intact.

A separate live acquisition using the personal area's location/radius (read only)
succeeded in a temporary data directory, importing 162 destinations and writing a
walking graph. It took 47.6 seconds including graph processing. This proves that
acquisition worked at that time, not that public Overpass availability is guaranteed
or that the revised query is always faster. The personal snapshot was not replaced.

## Original notes and visit writing (12 October 2026)

Reproduced the reported direct-visit gap with read-only inspection: the personal visit
and photo were stored, but no card, journal or inference job existed. Dashboard displayed
one reported place alongside a misleading empty planned-walk history. The original note
appeared under “The longer story.” Regression coverage now separates original experiences
from generated writing and names extractive fallbacks accurately.

An isolated Gemma 4 E2B run on the supplied visit text reproduced a two-attempt journal
fallback in 10.22 seconds, including cold model loading. Controlled regressions cover
positive discovery, supported paraphrases, independent interest validation, and editorial
placeholders. These are software checks; outdoor and phone trials remain pending.

### Automatic place memories

An isolated browser save of a synthetic place, the supplied note and a generated
circle image saved the note/photo before starting a preparation job. The first
model attempt produced a valid card but an extractive journal fallback; the UI
reported that distinction and retained its retry action. After the corrected
journal contract, a browser retry produced both a local-AI journal and a card
without changing the experience ID or uploading its photo again. The one-photo
case makes no cover-selection inference call.

The final writing prompt was also checked directly against installed Gemma 4 E2B
with the supplied text: it produced validated third-person prose in 1.41 seconds
warm, including one corrective retry. The draft remains brief and factual; passing
validation does not establish literary quality, which remains subject to user
review. Tests cover pending retry coalescing, outdated revisions, failed vision
preserving a useful journal, unchanged-source fallback protection, historical-map
editing, and delayed feedback. Mobile folder/experience checks at 390 × 844 had no
horizontal overflow. All writes used isolated data; physical trials remain pending.

### Dashboard activity

Read-only endpoint tests cover direct-only activity, mixed walks/visits, active
photo counts, alias resolution, repeated reads, editing without duplicate entries,
empty setup and no inference/graph requests. UI regressions retain existing walk
actions, semantic folder links and obsolete-response guards.

An isolated browser rendered two direct visits and one planned walk with the right
labels and counts. Keyboard Enter opened a visit's folder; Back restored Dashboard
and Forward reopened the folder. Desktop (1366 × 768) and mobile (390 × 844) had no
horizontal overflow. Reading/navigation left the six existing jobs unchanged.

### Place-folder alignment

An isolated folder reproduced the supplied screenshot: floating the Back button
shifted the rendered heading text about 116 px left, while the Location Card label
started 180 px left of its centred preview and inherited 10 px heading text.
`tests/folder-layout.browser.js`, evaluated in the collaborative preview, reproduces
those geometry failures using the real DOM and styles.

The header now uses normal grid flow with Back on a separate row. Current-card
labels, status, download, editor and card actions share the preview's 440 px maximum
width; earlier-version previews retain their existing sizing. The label uses 12 px
body typography. The same geometry probe passes at 1920, 390 and 320 px widths,
including a long wrapping place name and an expanded card editor. No horizontal
overflow or button/title overlap was present. Checks used synthetic folder data;
the personal database and media were not changed.

To repeat: open an isolated folder with a current card, then evaluate the contents
of `tests/folder-layout.browser.js` using the collaborative preview. Expect
`pass: true`. This browser probe supplements CI; Node only checks its syntax.

### Wind through the pixel footer

The footer has a complete pale-green bed drawn at one logical pixel per six CSS
pixels, matching the hero sky's scale. Tuft positions are deterministic. Passing
wind bends blade tips while every root remains fixed; the ground does not translate.
The locally bundled SVG covers the same footer when Canvas 2D is unavailable.

The renderer draws at most 15 frames per second and suspends offscreen, in hidden
tabs, on page exit and for reduced motion. A ResizeObserver and window-resize
listener rebuild the field when its dimensions change. Browser checks confirmed
full-width coverage, changed pixel data during wind, offscreen suspension, six-pixel
scaling at 1280 and 390 px widths, no horizontal overflow and clickable contacts.
A sampled 211 × 75 frame rendered in approximately 1 ms on this machine; this is a
single rendering measurement, not an energy-use benchmark. Motion/reduced-motion,
resize, rooted geometry and missing-canvas fallbacks have deterministic Node coverage.
Credits remain beneath the creator line and use a pale glass surface for readability.
Physical phone checks remain pending.
