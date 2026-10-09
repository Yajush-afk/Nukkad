# Installation and your first walk

## Requirements

Nukkad is a laptop application with a browser interface. The phone receives an exported image or printed card; it does not run the laptop model or provide live GPS navigation.

- Python **3.12**, Git and [uv](https://docs.astral.sh/uv/getting-started/installation/).
- [Ollama](https://docs.ollama.com/) with a downloaded local model.
- Cairo and DejaVu Sans fonts for PNG export and measured card typography. [CairoSVG installation guidance](https://cairosvg.org/documentation/) describes platform dependencies.
- Several GB of free disk space for weights and Python dependencies. Development measurements used about 14 GiB RAM and a 4 GiB laptop GPU; this is a measured configuration, not a minimum hardware guarantee. See [model-runtime.md](model-runtime.md).
- Internet during initial installation, model download and neighbourhood acquisition. Subsequent core use needs the saved weights and area, not internet.

Linux is the verified development platform. On Debian/Ubuntu, install `libcairo2`, `libffi-dev` and `fonts-dejavu-core` through your package manager. Native Windows/macOS installation and actual phone readability have not been verified; follow the platform Cairo guidance before assuming export works. Keep the repository's Python range at 3.12 when reproducing these results.

## Install the application

```sh
git clone https://github.com/Yajush-afk/Nukkad.git
cd Nukkad
uv sync --locked
```

The lockfile fixes the dependency versions used by CI. `uv` obtains Python 3.12 if necessary. A local wheel can also be built with `uv build`; it includes the frontend, Leaflet assets and vendor licence.

## Prepare local inference

Install Ollama from its official instructions, start its local server, and download the selected model:

```sh
ollama pull gemma4:e2b
ollama list
```

If starting the server yourself on Linux/macOS, this keeps its endpoint local and disables cloud features:

```sh
OLLAMA_HOST=127.0.0.1:11434 OLLAMA_NO_CLOUD=1 ollama serve
```

Do not start a second server if Ollama is already running as a service. Set those variables in the existing service or use Ollama's `disable_ollama_cloud` configuration, then restart it. [Official Ollama FAQ](https://docs.ollama.com/faq) documents both methods and the default localhost binding. Nukkad connects only to `http://127.0.0.1:11434`; it rejects cloud model names and remotely backed inventory entries.

Gemma 4 E2B was selected after laptop measurements. Gemma 3 `gemma3:4b-it-q4_K_M` passed the separate response/ID benchmark and one sequential synthetic full-generation check with AI ranking and wording (19.03 s); this does not establish equivalent recommendation quality or repeatable performance. You may pull another local model and select it in Settings, but re-evaluate its structured output, latency and fallbacks. No API key or paid inference service is required. Hardware, electricity, downloads and storage still have costs.

## Launch

```sh
uv run nukkad serve
```

Open **http://localhost:8000** on the same laptop. Settings reports the selected model and whether its weights are present. The first request may include model loading and be much slower than a warm request. Generate in daylight if daylight gating is enabled.

Data defaults to the platform's local application-data directory (`~/.local/share/nukkad` on this Linux installation). To choose a separate directory:

```sh
NUKKAD_DATA_DIR=./user-data uv run nukkad serve --port 8000
```

Use the same directory on later launches. One running application owns each data directory. Browser tabs may share that server. The `--model` option supplies the initial selection; once Settings has been saved, the saved selection takes precedence.

## Set up your locality

1. Choose **Set up my neighbourhood**. Start near Rajhans Apartments, Ahinsa Khand-1, Indirapuram, or enter another area.
2. Confirm the coordinates of a real **public walking start**. The suggested coordinates are approximate and do not identify a verified apartment gate. Do not check the confirmation box until you have checked the actual location.
3. Use `Asia/Kolkata`, a 2,000 m radius and the default walking policy initially. The extract includes an additional 700 m routing buffer. Generation does not automatically expand the area.
4. Select **Download / import area** while online. The background task downloads OSM XML and saves an immutable graph, geometry, registry, acquisition time and graph fingerprint.
5. Inspect the map and entrances. Imported places are unverified. A polygon centre is for display, never an assumed entrance. A place without a credible mapped or supplied entrance stays out of routing.
6. If the public start needs adjusting, click the saved map to select coordinates, update the setup form, confirm it and choose **Use saved extract with this start**. This creates a new snapshot from the existing extract without a new download. Coordinates must still fall within its useful coverage.
7. Add a personally known public place using **Add a public place**. Supply an entrance and confirm access. Optional observed features become explicit evidence for Seek mode. A public-access confirmation cannot override an OSM prohibition.

If download fails, you can import a neighbourhood `.osm` or `.xml` extract in the same form. It must contain walking ways and their referenced nodes, entrances and relevant place features; images, GeoJSON and road-only extracts are not substitutes. Uploads are limited to 32 MiB. The selected start must snap within 50 m of an eligible graph node. Missing coverage or sparse vertices require a better extract or an accurately chosen start, not an arbitrary confirmation.

Refresh deliberately by submitting a new download/import. Each refresh creates a new baseline, keeps past snapshots/history and resnaps stored entrances. It does not verify that a place is open today.

## Generate, review and go

1. Choose **Make a little adventure**, enter 20–60 available minutes and your explicit interests. Add optional context such as a slow walk or a familiar destination.
2. **Wander** uses bounded observation invitations. **Seek** requires recorded feature evidence and uses at most two stops to keep the card readable. Seek may have no eligible destinations in a sparse map.
3. Wait for the local generation job. The model orders eligible place IDs and selects grounded reasons; code computes every walking leg, return, distance, stop time, reserve and daylight allowance. Ranking and wording fallbacks are labelled separately.
4. Review numbered stops, streets, return, access uncertainty, generation time and latest departure. Inspect the actual surroundings yourself; mapped eligibility cannot guarantee safe or public access.
5. **Accept this walk** rechecks current eligibility and timing. A delayed or next-day card may be declined; generate a fresh one. PNG export also revalidates.
6. Download the 1080 × 1920 **phone image**, or use **Print A4** with A4 portrait and inspect print preview. Transfer the image by USB or Bluetooth, open it on the actual phone and check legibility before leaving. Keep a full-resolution copy. The card has no live map tiles, directions updates or GPS.
7. Take the card outside and turn back or skip a destination when access or conditions differ. Settings uses an assumed walking speed, not a measured pace.

After returning, choose **I’m back / record outcome**. Report reached, skipped or unresolved stops and completed, turned-back or not-taken status. Notes, outdoor minutes and manually measured screen minutes are optional. Editing updates the same outcome; it does not add another visit.

Review a journal extract and exact-quote interest proposals individually. Explicit interests apply immediately; inferred interests apply only after acceptance. Pending/rejected interests are excluded, removal stops future use, and note edits invalidate derived drafts. Open Field notes to revisit outcomes. See [field-notebook.md](field-notebook.md) for the actual-use evidence to collect.

## Offline preparation

Before disconnecting, install dependencies, download the local weights, save an area and verify PNG export. Keep Ollama and Nukkad running locally. The frontend, map library, graph, geometry and notes are saved locally; no third-party tiles or web fonts are fetched.

Optional regional U.S. AQI gating defaults off. When enabled, missing/stale or above-threshold estimates block quests. A fresh cached estimate can be used offline until stale, but the app cannot silently assume good conditions. See [architecture.md](architecture.md) and the physical-disconnection protocol in [evaluation.md](evaluation.md).

