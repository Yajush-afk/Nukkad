# Startup and navigation checks

## Cause and change

Previously, navigation started only after a sequential session → full area → duplicate
review → profile → settings → readiness chain. On the existing local installation,
browser resource measurements were approximately 2,163 ms for area, 1,624 ms for
duplicates and 1,785 ms for readiness. Those three requests alone delayed startup by
about 5.6 seconds. Already-loaded page switches were much faster (17–94 ms).

Home now requests only the local session. Other panels request their own data. A small
saved-area status endpoint serves onboarding and planner access. Duplicate review and
readiness run independently of map/form rendering. Parsed graphs and derived area
responses reuse unchanged revisions; aliases are read in one database query instead
of opening a connection per place.

## Regression evidence

The startup test first failed because initialisation requested a full map. Map tests
first failed because the status endpoint did not exist and repeated calls rebuilt the
graph/area. Focused coverage now protects:

- Home independence from unresolved session, map and readiness requests.
- Immediate pending-panel presentation and navigation away from slow responses.
- Lightweight onboarding for missing, unconfirmed and confirmed public starts.
- Session-token gating for mutations while reads remain usable.
- Parsed graph reuse with independent graph mutations and file integrity validation.
- Area invalidation for reached outcomes, corrections, aliases and snapshot revisions.
- Duplicate review invalidation and legacy source-alias compatibility.
- Bounded eviction and failed-build recovery.

## Browser checks

Used a separate synthetic data directory on port 8005; no test outcomes or photos were
added to the personal installation. Home requested only `/api/session` (3 ms observed)
and did not instantiate Leaflet. Holding `/api/area` unresolved displayed the
Neighbourhood loading state immediately. Returning Home took 3 ms; releasing the
old request left Home visible and did not mark the map loaded.

Synthetic-data page completion measurements: Neighbourhood 29 ms, My walks 35 ms,
Settings 12 ms, planner 17 ms and Home 3 ms. These are local observations, not promises
or comparisons with the much larger personal map. Back/Forward retained unsaved
planner/settings values and issued no writes. Direct Settings reload requested only
session, settings, readiness and air-quality data. The map rendered nine marker layers.
At 390 px viewport width, navigation remained available without horizontal overflow.

The About this map disclosure stayed at scroll position 1,284 px when toggled through
the DOM, and map zoom kept Neighbourhood visible. Native Enter on the focused Home
button returned Home; no panel remained inert after completion. Native disclosure
click automation failed, so that specific check used DOM activation.

Browser checks used the T3 preview, DOM evaluation, native navigation clicks and keys.
Model inference latency is outside this change: local model checks can still take time,
and a cold map request still performs preparation. Physical phone/field checks remain
user-owned.
