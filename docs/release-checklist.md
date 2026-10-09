# Release evidence and submission checks

## Verified software evidence

- CI runs Python lint/format, deterministic tests and JavaScript syntax checks without downloading weights.
- Separate local-model benchmark and ten-context comparison results are described with dates and scope in [model-runtime.md](model-runtime.md) and [evaluation.md](evaluation.md).
- A live synthetic browser flow on 9 October used actual Gemma 4 E2B ranking/wording (10.17 s), numbered preview, acceptance, PNG download, a not-taken outcome and an exact-quote architecture proposal. The proposal and original note survived reload. This establishes interface/runtime behaviour, not an outing or recommendation quality.
- Phone-sized browser layout was inspected; actual phone export readability is pending.
- Fresh wheel installation and a new isolated demo directory reproduce the packaged assets and saved synthetic graph. See setup/demo instructions; local weights and Cairo remain external requirements.
- A 2 min 15 s local synthetic browser recording shows actual packaged E2B generation (7.46 s), acceptance/export, a not-taken outcome, reviewed architecture interest and a later quest (3.17 s). The later route changed from destinations 2/3 to 2/4 and contained an architecture-match reason after explicit interests were cleared. Other inputs also changed, so this demonstrates the review/context flow rather than isolating a causal preference effect. The recording is a local review artifact, not a published outdoor demo.
- A sequential Gemma 3 synthetic generation used the same adapter and returned AI ranking/wording in 19.03 s. This single compatibility check does not establish comparative quality or equivalent speed.

Do not infer evidence for later revisions solely from an earlier run. Re-run checks after changes to ranking, eligibility, memory or card layout. Keep original private diagnostics and record commit/model digest when making public performance claims.

## Human checks still required

- [ ] Confirm a real public start and useful entrances around Rajhans; the approximate seed is not a verified gate.
- [ ] Transfer an accepted full-resolution card to the actual phone and check map, text, return and date outside.
- [ ] Attempt 2–3 real outings, including partial/failed attempts if they occur. Save outcomes and manually measured screen/outdoor times.
- [ ] Record access/navigation faults, correct them and check a subsequent quest responds.
- [ ] Review a real note's interest proposal and inspect its actual influence on a later recommendation.
- [ ] Perform the complete fresh-start loop with machine Wi-Fi/Ethernet disconnected after setup. The process socket guard is separate evidence.
- [ ] Rate the blinded comparison cards, including ties/losses, before opening their key.
- [x] Check a second model through production generation and disclose modes/timing; retain the single-case and synthetic limitations.

Use [field-notebook.md](field-notebook.md). These require observations from the user and cannot be completed by fictional history or synthetic test output.

## Public materials

- [ ] Record/review a genuine demo, label synthetic portions and time cuts, and add a viewable video/deployed-demo link.
- [ ] Check screenshot/video/diagnostic content for personal notes and precise private starts; use deliberate public locations or synthetic fixtures.
- [ ] Resolve every bracketed publication marker in [dev-post-draft.md](dev-post-draft.md). If human evidence is absent, retain the explicit limitation rather than inventing it.
- [ ] Verify every claimed capability and metric against the referenced revision/run.
- [ ] Recheck the official rules at publication, review the final text and publish one DEV template post with `devchallenge` and `hf26challenge` tags, repository, demo and open-innovation explanation.

The [official challenge](https://dev.to/challenges/hacktoberfest-week1-2026-10-05) and [contest rules](https://dev.to/page/hacktoberfest-week1-2026-10-05-contest-rules) were rechecked on **9 October 2026**. The cutoff is **12 October 2026, 06:59 UTC / 12:29 PM IST**. A video is an accepted demo format; an agent-session link is optional. Open pieces must materially power the build. Best Use of Gemma is relevant to the actual local Gemma use; other partner categories must reflect tools actually used.

Engineering completion, field evidence and a published contest submission are separate states. The local draft is intentionally unpublished. Repository PR merges do not submit an entry to DEV.
