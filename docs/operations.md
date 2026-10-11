# Operation, updates and recovery

## Back up local data

From the same environment and data directory used by the server:

```sh
uv run nukkad backup
```

For a custom directory, prefix the command with `NUKKAD_DATA_DIR=./user-data`. The command prints the ZIP path under the data directory's `backups` folder. It uses SQLite's consistent backup API and includes the referenced raw extracts and walking graphs. Notes, outcomes, preferences, corrections and snapshot geometry live in the database. Backups include private photo originals, necessary derived variants and all stored Location Card versions with a versioned hash manifest. Outdoor quest PNG exports can be regenerated; model weights, fonts and Python dependencies are not included.

The archive contains personal notes and coordinates and is **not encrypted**. Keep it private; never attach it to an issue or commit it. Unix data directories are created with mode 700 and database/backup files with mode 600. This does not protect against another process running as your OS user, privileged software or physical disk access.

## Restore without overwriting

Stop the application and restore into a **new** directory:

```sh
uv run nukkad restore --archive /path/to/nukkad-backup.zip --destination ./restored-data
NUKKAD_DATA_DIR=./restored-data uv run nukkad serve
```

Restore rejects an existing destination, unexpected ZIP members, path traversal, unsupported database versions and missing/damaged graph fingerprints. The default uncompressed archive limit is 4 GiB. Preflight checks run before backup creation. Use the same explicit `--max-archive-mib` increase on backup and restore for larger collections. Restore validates the saved database and graph, not the current real-world access or freshness of a forecast. Downloaded Ollama weights remain a separate setup requirement. Confirm history/settings and generate a current quest before adopting the restored directory.

## Update

1. Back up, save the printed archive path and stop Nukkad normally with Ctrl+C. Graceful shutdown waits for the current worker to finish; cancellation prevents its result from being published but does not immediately stop Ollama inference.
2. Pull the intended release/main revision and run `uv sync --locked`.
3. Start with the **same** `NUKKAD_DATA_DIR` as before. Verify history and model selection. Keep the backup until the update is satisfactory.

Data is separate from installed code. This release uses database schema version 1 and does not implement arbitrary version migrations. An unexpected version should be investigated instead of deleting history. Following an abrupt interruption, unfinished jobs are marked interrupted on the next start; start a fresh request. A cancelled job cannot publish a late quest or reflection.

## Troubleshooting

| Symptom | Action |
| --- | --- |
| Model unavailable/missing | Check `ollama list`, the local server at 127.0.0.1:11434 and the selected exact tag. Pull weights during setup; cloud tags are rejected. |
| Cold generation is slow | Allow for weight loading and CPU/GPU memory. Try the measured E2B default. There is a shared 120 s ranking/prose deadline and one corrective attempt per stage; a smaller model can still fail validation. Read the resulting fallback labels. |
| No eligible destinations | Inspect entrances, graph connectivity, prohibitions and recorded features for Seek. Supply confirmed public pins; do not use polygon centres as entrances. |
| Start has no nearby eligible street segment | Choose an accurate public start near an eligible street, or acquire a more complete extract. Projection uses street geometry with a 50 m limit; it does not establish access through barriers. |
| Map download/import fails | Read the per-provider reason: HTTP 504 means that provider's query timed out; HTTP 429 indicates rate limiting; a connection error is distinct. Retry later instead of repeatedly clicking. Automatic fetching uses a bounded selective query and an independent Overpass fallback. Optional XML import is under Advanced. Failed/cancelled acquisition does not replace the active area. |
| No walk fits time/distance | Try a larger allowed budget, fewer stops or a closer destination after inspecting the area. Full return distance, dwell and reserve count; individually feasible stops can fail as a combination. |
| Daylight/dated-card rejection | Check timezone/system clock and generate a current card early enough to return before the margin. Night demonstrations are synthetic only; do not infer outdoor suitability from disabling the policy. |
| AQI blocks generation | Inspect retrieval and forecast-valid timestamps and the chosen threshold. Refresh only when enabled and online. Missing/stale data is unknown; a regional estimate does not measure your street. |
| Card export cannot load Cairo | Install native Cairo and DejaVu Sans, then restart. Verify a full-resolution PNG before relying on it outside. |
| Reflection falls back | The model may time out, return unsupported wording or source passages, or propose unsupported preferences. Your outcome remains saved; a labelled exact extract is offered without inferred interests. |
| Original note edited | Old derived memory becomes stale/removed. Generate and review a fresh reflection; original note and revision history remain in the outcome. |
| Busy/application owner error | One worker handles acquisition/generation/reflection and one server owns a data directory. Finish/cancel the job, stop an old server normally, or use an explicitly separate demo directory. |
| Host/origin/session rejection | Use localhost/127.0.0.1 on the configured port and reload the browser. The per-process session token changes after server restart. Remote hosting and permissive CORS are not supported. |
| Incorrect/missing place | Inspect its popup, record not-there/closed/not-accessible with details, or supply verified entrance coordinates. Prohibited map tags cannot be overridden. Corrections affect later quests. |

For bugs, report application commit, Python/Ollama/model versions, ranking/prose modes and a minimal **synthetic** reproducer. Keep raw notes, exact personal starts, cards, database, extracts and diagnostic exports private. `.gitignore` covers standard artifact/data paths; custom folders outside those paths still require care.


## Readiness and generation diagnostics

`/api/readiness` reports map integrity, public start, eligible round trips, database,
renderer and local model capabilities independently. `deterministic_ready` describes
prepared components; generation still checks current daylight and optional AQI.
Checks are cached for ten seconds and invalidated by relevant record/file revisions.
Readiness never downloads maps or runs inference. Failed AI stages record their
attempt count, timing, category and fallback, without copying prompts or source notes
into ordinary metrics. Successful attempts also record the model digest, Ollama version
and generation options. Detailed comparison artifacts remain private local files.

## Place photos and recovery

Report a reached stop and save its optional experience note before uploading photos. Each visit accepts five active JPEG/PNG/WebP images, at most 20 MiB and 40 megapixels each. Decoding decides format; filenames and MIME labels are not trusted. Animated images are rejected. Originals stay private under generated file IDs; display/thumbnail/inference JPEGs have orientation applied and no EXIF/GPS metadata. The browser serves derived images only. Removing an image hides it from active collections while retaining private originals for revision history and backups.

`GET /api/media/recovery` lists missing live files, interrupted staged entries and unreferenced files. Nothing is deleted automatically. Uploads stage variants before atomic record publication; a source conflict removes only that new upload. Partial multi-file uploads retain successful images and previously saved notes. Old backups without a media manifest remain restorable. New media backups reject missing or damaged files, unsafe members, hash mismatches and inconsistent source references before publishing a restored directory.

## Create and review a Location Card

After saving a reached stop and adding photos, open **My walks → its place folder**. Choose one reported visit and request a card. The selected local model must report vision capability. No model is downloaded or silently substituted. A separate shared 180-second budget covers cover selection, a summary and the longer journal. Unsupported vision, malformed results and timeouts preserve the existing card and show an actionable job failure. A labelled manual template is available; edit its cover, crop and third-person summary in the card section.

**Save card edits** creates a new version. **Regenerate with local AI** retains previous versions and any accepted/edited journal as history. A stale editor receives a conflict rather than replacing a newer version. Changing the source note or removing a cover requires review/regeneration; marking a stop skipped removes its active collection contribution. Earlier private media and card versions remain in backups. Served variants and exported cards are checked against recorded sizes and hashes; damaged media requires restoration rather than being sent to the model.

Local interfaces: `GET /api/collection`, `GET /api/collection/{place}`, `POST /api/collection/{place}/generate` (returns a job), `PATCH /api/collection/{place}/card` (requires current `version_id`), `GET /api/location-cards/{version}` and its `/export.png`. Existing journal review/version interfaces also work with place-experience IDs. Mutation/session and busy-worker rules remain unchanged.

A valid supplied photo ID proves ownership, not relevance. In the synthetic five-image trial the model picked a square scene for a note about circles. Inspect the cover and text, and change them if needed. Images never establish attendance, identity, location or public access.

## Startup and neighbourhood loading

Home and its navigation do not wait for map preparation or Ollama checks. The local
session starts separately; writes wait for its token. Get started reads only saved
area metadata, then opens the planner or Neighbourhood according to public-start
confirmation. Metadata does not establish graph integrity or route feasibility.

Neighbourhood loads its working map on demand. Its loading notice leaves the header
available, so another page can be opened immediately. A response from an abandoned
page cannot publish map content or move focus. Similar-place review runs after map
rendering. Settings loads editable preferences first, then checks model/map readiness
in the background. Unsaved fields remain in the open tab.

Parsed graphs, full area responses and duplicate candidates use a bounded, per-server
cache. Corrections, source aliases, snapshot/area changes and reached outcomes change
its revision key; duplicate decisions also invalidate candidate results. Graph file
changes invalidate response entries. Opening a graph still verifies its SHA-256,
including cache hits, and routing receives an independent copy. Acceptance/export
continue to revalidate routes. Restarting clears the cache without changing saved data.

A first map visit can still take longer than subsequent visits. Loading the map is no
longer a prerequisite for Home, My walks or Settings. If a map request fails, reopen
Neighbourhood to retry; if session startup fails, reload after checking the local server.

### Location suggestions

Typing three characters shows saved-map and cached-search matches first. Photon adds up to five English online matches after a 400 ms debounce. The local server spaces provider starts by one second, allows one request and one newest pending query, uses a five-second timeout, and cools down for 60 seconds after rate limiting. Failed requests are not retried automatically. `NUKKAD_PHOTON_URL` overrides the default HTTPS endpoint (loopback HTTP is also permitted).

Autocomplete sends only the typed location and geographical context, never notes or photos. The dedicated hashed-key cache holds at most 256 queries: successful results last 24 hours and empty results ten minutes. Search metadata never loads the walking graph. Names/proximity do not merge places; known OSM aliases resolve to existing local identities. A result is a candidate, not evidence of a public entrance. Public Nominatim is used only by the deliberate Search action, never by typing. Photon failure leaves local suggestions and explicit search available.

See [Photon documentation](https://github.com/komoot/photon) and [Nominatim policy](https://operations.osmfoundation.org/policies/nominatim/).

### Working pages and notebook

The Neighbourhood map opens first for saved areas. Change neighbourhood or start contains setup controls; incomplete confirmation opens it automatically. Add a place uses an inline map entrance editor. A search centre never confirms an entrance, and moving the entrance clears its public-access checkbox. Existing suggestions open their canonical place. Reports require an observation and preserve correction history.

Wheel scrolling passes through real maps. Touch pinch remains enabled; supported Ctrl+wheel pinch affects only the map beneath it. Neighbourhood 100% is zoom 15; My start restores that view without requesting GPS. Preview 100% is the fitted route. Settings contains snapshot provenance and frozen progress explanations. Linked OpenStreetMap attribution remains beside each real map.

Dashboard preserves the history URL and shows distinct Location Card/place counts. Folder reading and manual editing do not wait for local vision readiness. Summaries remain within Location Cards; longer journals have a separate reading area. Unsaved card/journal text stays in the open tab. Success notices expire after five seconds excluding hover/focus time; errors require dismissal. Footer email copying occurs only on activation.

### Experiences from a map place

Selecting a saved place opens its experience form. Report this place switches the
same panel to access/location reporting; saving an experience does not verify an
entrance or make a place eligible for routing. A direct visit is self-reported and
creates no quest or walk outcome. It uses the persistent place identity and appears
in the existing Dashboard folder alongside visits reported through walks.

Notes and up to five optional photos are saved locally. If an upload fails, the
saved note and preceding photos remain; retry resumes with the remaining files.
A request identity prevents duplicate visits from repeated submissions. Add another
visit deliberately starts a new record. Direct visits and their media are included
in backups; existing walk-linked experiences keep their original representation.
