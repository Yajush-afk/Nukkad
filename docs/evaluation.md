# Reliability and AI comparison

Run `uv run pytest -q`, `uv run ruff check src tests`, `uv run ruff format --check src tests`, and `node --check src/nukkad/static/app.js`. CI runs deterministic Python checks without model downloads or access to personal data.

Run `uv run nukkad evaluate --model gemma4:e2b --output artifacts/my-comparison` against an installed local model. The output directory must be new. Evaluation builds an explicitly artificial walking graph with eight destination types and ten contexts. Nearest-unvisited, interest-aware deterministic and local-AI rankings use the same candidate pool, planner, time/distance/daylight constraints and stop limit. Candidate membership, rankings, modes, prompts and runtime metadata are retained in private diagnostics.

The deterministic interest rule is category matches plus an unvisited bonus of one, minus round-trip kilometres, with stable distance/ID ties. Keyword mappings are recorded in each diagnostic export and defined in `planning.py`. This is a deliberately simple baseline, not a learned preference model.

## Measured local run, 8 October 2026

The final varied fixture run used Gemma 4 E2B on the documented development laptop. Nine feasible cases used validated local AI ranking; six used validated AI observation wording and three retained template fallback. The constrained tenth case produced no quest in all three modes. Full generation measured a median of **5.16 seconds**, maximum **10.77 seconds**, over the nine feasible cases with an already loaded model. This excludes application startup, map acquisition, image export and physical walking.

AI selected a different stop sequence from the interest baseline in two cases (architecture and sparse notes). This demonstrates influence, not superiority. Blinded ratings remain **pending**. No actual outings or phone readability results are implied.

An earlier linear fixture gave the model little choice and did not establish useful destination differences. Its run also exposed false rejection of general observation wording. The final fixture adds independent branches, and ranking reasons are selected from grounded per-place choices. This narrows unsupported descriptive claims while keeping destination ordering under model control.

## Blinded review

Open `case-NN-A/B/C.svg` without opening `blinding-key.json` or diagnostics. All cards use the same rendering and neutral comparison labels. In `ratings.json`, rate interest fit, willingness to go, variety and prompt usefulness from 1–5. Record ties, losses and comments. Then open the key. Small samples support descriptive findings only; report failures and model losses alongside wins.

## Offline evidence boundary

The real-model comparison runs inside a process-level socket guard that rejects non-loopback connections; it recorded zero such attempts. A deterministic integration test starts a fresh app, serves local assets, creates and accepts a quest, exports PNG, saves an outcome, reviews memory and confirms persistence after restart under the same guard, with controlled model responses. These are distinct forms of evidence.

This guard does not disable the whole machine's network or sandbox the independently running Ollama daemon. For a physical offline check, finish setup/model/map downloads, disable Wi-Fi/Ethernet, keep loopback and Ollama running, restart Nukkad, reload the browser, generate a new quest, export a card, save an outcome and reopen history. Record model/fallback modes. Air-quality gating must be disabled or have a fresh cached estimate that meets the selected threshold. Do not claim a physical disconnected trial until it has actually been performed.

See [field-notebook.md](field-notebook.md) for actual neighbourhood and phone evidence.
