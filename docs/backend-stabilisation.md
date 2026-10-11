# Backend guarantees and limits

## Regression coverage

| Failure | Coverage |
| --- | --- |
| A completed reflection hidden after returning | `outcome.test.cjs`: same-outcome refresh preserves unsaved fields |
| A delayed save replacing another note screen | `outcome.test.cjs`: operation checkpoints and originating outcome |
| Accepted interests absent from preview | `test_audit_regressions.py`: shared reviewed-interest context, no writes |
| `foot=use_sidepath` carriageway used | `test_snapping.py`: restrictions and separate connected paths |
| A midpoint on a long street rejected | `test_snapping.py`: metric projection, ordered temporary junctions |
| Relation destinations missing | `test_polygons.py`: relation-only destinations, member assembly, holes |

Routing adds temporary junctions to a derived graph. Original GraphML and fingerprints remain unchanged. A geometric snap is not evidence that a person can cross a wall or enter a polygon. Entrance confirmation remains necessary. Reviewed aliases preserve historical IDs; similar nearby names require explicit review.

## Memory publication

Outcomes preserve original notes and successive edits. Repeated identical saves are idempotent. Generated journals reference exact passages and stay separate from inferred interests. Journal acceptance does not activate preferences. Publication compares both the source outcome and the journal captured before inference; newer reviews or edits cause a conflict. Restart marks unfinished jobs interrupted. Cancellation blocks publication while the single local worker finishes its current request.

English validators reject known unsupported claims, names, quantities, emotion changes and unsafe route assertions. They cannot prove semantic fidelity. Users must review generated journals and interests. Model output is never authority for access, attendance, health, or route feasibility.

## Evidence scope

Deterministic CI tests isolated records and controlled responses. Real Ollama runs use explicitly synthetic maps and notes with process-level non-loopback socket denial. Browser checks use a separate data directory and port. None of these demonstrates a real outing, a physically disconnected machine, actual phone readability, or recommendation superiority. Those checks remain pending with the user.

Model timing includes measured loading when reported in Ollama metadata. Warm timings cannot be described as startup timings. Failed stages retain useful routes and clearly labelled fallback wording. There is no silent model switch or automatic download.

## Local operations

History, notes and deterministic operation remain accessible without the chosen model. Readiness checks distinguish saved-map integrity, start, destinations, renderer and model. Current daylight and optional cached AQI are checked when generating/accepting/exporting, not promised by a readiness flag. Only the local Ollama endpoint is permitted. A cloud-tag selection produces a labelled fallback and cannot send source data remotely.

Detailed evaluations contain source notes and generated text; keep them private. Ordinary attempt metrics contain task/version, model/runtime metadata, timings, counts and failure categories, without raw prompts, notes or images.

## Place-memory completion

Photo inputs enforce five active files per reached experience, decoded format, 20 MiB and 40-megapixel limits. Originals remain private; derived files and exported cards omit EXIF/GPS metadata. Hash checks reject damaged saved media before serving or inference. Versioned manifests include media and cards, enforce configurable archive limits and validate relationships before restoring into a new directory.

Location Card jobs use verified local vision, supplied photo IDs and one visit's current note. The fixed renderer owns layout, names and dates. User edits, accepted journals and older cards survive regeneration. Optimistic checks reject stale revisions and changes to place identity. Direct folder routes, Back/Forward and tab-local unsaved edits are supported. Automated coverage includes unknown cover IDs, unsupported models, failed/stale/cancelled jobs, alias grouping, deleted covers, repeated visits, timezone rendering and version-aware journal reviews.

Model outputs remain reviewable suggestions. A five-image synthetic cover choice was semantically poor despite valid ownership. This limitation is recorded rather than hidden behind validation rates. Physical outings, phone checks, machine disconnection and blinded ratings remain user-owned pending work.

Readiness also checks additive document versions, including gallery and journal records. A future unsupported version invalidates cached readiness and is reported as damaged/incompatible saved data; backup validation refuses it. Legacy unversioned records remain supported, and ordinary history remains accessible.
