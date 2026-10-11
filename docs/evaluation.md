# Reliability and AI comparison

Run `uv run pytest -q`, `uv run ruff check src tests`, `uv run ruff format --check src tests`, and `node --check src/nukkad/static/app.js`. CI runs deterministic Python checks without model downloads or access to personal data.

Run `uv run nukkad evaluate --model gemma4:e2b --output artifacts/my-comparison` against an installed local model. The output directory must be new. Evaluation builds an explicitly artificial walking graph with eight destination types and twelve contexts. Nearest-unvisited, interest-aware deterministic and local-AI rankings use the same candidate pool, planner, time/distance/daylight constraints and stop limit. Candidate membership, rankings, modes, prompts and runtime metadata are retained in private diagnostics.

The deterministic interest rule is category matches plus an unvisited bonus of one, minus round-trip kilometres, with stable distance/ID ties. Keyword mappings are recorded in each diagnostic export and defined in `planning.py`. This is a deliberately simple baseline, not a learned preference model.

## Measured local run, 8 October 2026

The final varied fixture run used Gemma 4 E2B on the documented development laptop. Nine feasible cases used validated local AI ranking; six used validated AI observation wording and three retained template fallback. The constrained tenth case produced no quest in all three modes. Full generation measured a median of **5.16 seconds**, maximum **10.77 seconds**, over the nine feasible cases with an already loaded model. This excludes application startup, map acquisition, image export and physical walking.

AI selected a different stop sequence from the interest baseline in two cases (architecture and sparse notes). This demonstrates influence, not superiority. Blinded ratings remain **pending**. No actual outings or phone readability results are implied.

An earlier linear fixture gave the model little choice and did not establish useful destination differences. Its run also exposed false rejection of general observation wording. The final fixture adds independent branches, and that historical run used a restricted reason catalogue. The current implementation writes bounded subjective explanations with evidence IDs; newer results must be reported separately.

## Blinded review

Open `case-NN-A/B/C.svg` without opening `blinding-key.json` or diagnostics. All cards use the same rendering and neutral comparison labels. In `ratings.json`, rate interest fit, willingness to go, variety and prompt usefulness from 1–5. Record ties, losses and comments. Then open the key. Small samples support descriptive findings only; report failures and model losses alongside wins.

## Offline evidence boundary

The real-model comparison runs inside a process-level socket guard that rejects non-loopback connections; it recorded zero such attempts. A deterministic integration test starts a fresh app, serves local assets, creates and accepts a quest, exports PNG, saves an outcome, reviews memory and confirms persistence after restart under the same guard, with controlled model responses. These are distinct forms of evidence.

This guard does not disable the whole machine's network or sandbox the independently running Ollama daemon. For a physical offline check, finish setup/model/map downloads, disable Wi-Fi/Ethernet, keep loopback and Ollama running, restart Nukkad, reload the browser, generate a new quest, export a card, save an outcome and reopen history. Record model/fallback modes. Air-quality gating must be disabled or have a fresh cached estimate that meets the selected threshold. Do not claim a physical disconnected trial until it has actually been performed.

See [field-notebook.md](field-notebook.md) for actual neighbourhood and phone evidence.

## Backend stabilisation checks, 11 October 2026

The controlled software suite covers the six diagnosed regressions: same-outcome refresh, delayed saves, accepted-interest preview context, sidepath carriageway exclusion, segment snapping, and relation-only destinations. Recovery includes accepted quests, card export, original notes, reviewed interests, optimistic source conflicts and interrupted jobs. Duplicate outcome saves retain their existing revision. The T3 browser check on isolated port 8005 verified a real E2B written journal, editing, earlier versions, Back restoration, and Home/Neighbourhood/My walks/Settings routes.

The current evaluation adds conflicting preferences, older place-relevant notes and three written-journal cases. It preserves candidate pools and planner constraints across comparisons. Diagnostics report every generation attempt, retry rule, mode and load/token timing. CI uses controlled responses; real model measurements remain separate private artifacts. A validated response may still interpret evidence incorrectly. Source quotes and manual review are required; changed stop ordering is not evidence of superior recommendations.

### Current E2B result

The 11 October run used the production generation pipeline on twelve cases: eleven had feasible routes, and the deliberately constrained case produced no quest in every method. All eleven feasible cases used validated AI ranking; eight used AI activities and three kept templates after bounded corrective attempts. Generation median was **5.87 s**, maximum **7.39 s**; the first case was already warm (inspect stage load durations rather than calling it a cold run). All three sparse journal cases used AI, **0.576–0.879 s**. The source and output were inspected: the turned-back and not-taken cases retained those reports without claiming a completed visit. Activities remained somewhat repetitive, and evidence/membership failures remain a practical model limitation. There is no superiority claim; blinded ratings remain pending.
