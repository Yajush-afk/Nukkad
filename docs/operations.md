# Operation, updates and recovery

## Back up local data

From the same environment and data directory used by the server:

```sh
uv run nukkad backup
```

For a custom directory, prefix the command with `NUKKAD_DATA_DIR=./user-data`. The command prints the ZIP path under the data directory's `backups` folder. It uses SQLite's consistent backup API and includes the referenced raw extracts and walking graphs. Notes, outcomes, preferences, corrections and snapshot geometry live in the database. PNG exports can be regenerated; model weights, fonts and Python dependencies are not included.

The archive contains personal notes and coordinates and is **not encrypted**. Keep it private; never attach it to an issue or commit it. Unix data directories are created with mode 700 and database/backup files with mode 600. This does not protect against another process running as your OS user, privileged software or physical disk access.

## Restore without overwriting

Stop the application and restore into a **new** directory:

```sh
uv run nukkad restore --archive /path/to/nukkad-backup.zip --destination ./restored-data
NUKKAD_DATA_DIR=./restored-data uv run nukkad serve
```

Restore rejects an existing destination, unexpected ZIP members, path traversal, unsupported database versions and missing/damaged graph fingerprints. The uncompressed archive limit is 256 MiB; larger histories need an explicit future migration/export strategy. Restore validates the saved database and graph, not the current real-world access or freshness of a forecast. Downloaded Ollama weights remain a separate setup requirement. Confirm history/settings and generate a current quest before adopting the restored directory.

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
| Start has no nearby walking node | Choose an accurate mapped public start or acquire a denser/more complete extract. The snap limit is 50 m. |
| Map download/import fails | Preserve the working saved snapshot, retry deliberately when online or import complete OSM XML below 32 MiB. Failed/cancelled acquisition does not replace the active area. |
| No walk fits time/distance | Try a larger allowed budget, fewer stops or a closer destination after inspecting the area. Full return distance, dwell and reserve count; individually feasible stops can fail as a combination. |
| Daylight/dated-card rejection | Check timezone/system clock and generate a current card early enough to return before the margin. Night demonstrations are synthetic only; do not infer outdoor suitability from disabling the policy. |
| AQI blocks generation | Inspect retrieval and forecast-valid timestamps and the chosen threshold. Refresh only when enabled and online. Missing/stale data is unknown; a regional estimate does not measure your street. |
| Card export cannot load Cairo | Install native Cairo and DejaVu Sans, then restart. Verify a full-resolution PNG before relying on it outside. |
| Reflection falls back | The model may time out, return an empty/non-exact excerpt, or propose unsupported preferences. Your outcome remains saved; a labelled exact extract is offered without inferred interests. |
| Original note edited | Old derived memory becomes stale/removed. Generate and review a fresh reflection; original note and revision history remain in the outcome. |
| Busy/application owner error | One worker handles acquisition/generation/reflection and one server owns a data directory. Finish/cancel the job, stop an old server normally, or use an explicitly separate demo directory. |
| Host/origin/session rejection | Use localhost/127.0.0.1 on the configured port and reload the browser. The per-process session token changes after server restart. Remote hosting and permissive CORS are not supported. |
| Incorrect/missing place | Inspect its popup, record not-there/closed/not-accessible with details, or supply verified entrance coordinates. Prohibited map tags cannot be overridden. Corrections affect later quests. |

For bugs, report application commit, Python/Ollama/model versions, ranking/prose modes and a minimal **synthetic** reproducer. Keep raw notes, exact personal starts, cards, database, extracts and diagnostic exports private. `.gitignore` covers standard artifact/data paths; custom folders outside those paths still require care.

