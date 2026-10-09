# Local model feasibility

Measured on 8 October 2026 with Ollama 0.34.0, approximately 14 GiB RAM,
and an RTX 3050 Ti laptop GPU with 4 GiB VRAM. Context length: 4096;
generation temperature: 0; extended thinking disabled for Gemma 4.

| Model | Cases | Median task time | Maximum task time | Result |
| --- | --- | --- | --- | --- |
| Gemma 4 E4B | First case only | Not established | 120.12 seconds | Request deadline exceeded; batch stopped |
| Gemma 3 4B Q4_K_M | 10 | 17.763 seconds | 18.170 seconds | All ID and response-shape checks passed |
| Gemma 4 E2B | 10 | 4.953 seconds | 75.936 seconds | All ID and response-shape checks passed |

Gemma 4 E2B is the selected default. Its first measured case included model
loading; subsequent cases took 4.381–5.225 seconds. Model digest:
`b37049369adfe3d2b653af0ab301a062ca5cbe96ace6aa0d3f2559ee9b563fc2`.

Each case ranks eight synthetic places and generates two observation prompts.
These timings exclude route calculation, map acquisition, and card export.
The benchmark records per-request loading and token metrics in the private
application-data directory. Run it again on another machine before relying on
these figures.

An initial unconstrained list schema allowed omitted IDs. Exact list length and
ID enums improved membership reliability; duplicate checks still run in code.
Manual inspection found useful interest-dependent rankings but also unsupported
assumptions in some reasons (for example, assuming a park is quiet). Passing
shape checks is not proof of grounded prose or good recommendations. Production
generation needs its separate prose validators and visibly labelled fallbacks;
the full-product and blinded quality evaluations remain separate evidence.

No outdoor use or health benefit is established by this synthetic benchmark.

## Second-model generation check, 9 October 2026

A separate, sequential production-generation call with `gemma3:4b-it-q4_K_M`
produced validated local AI ranking **and** wording on the artificial demo graph
in **19.03 seconds**. Its digest was
`a2af6cc3eb7fa8be8504abaf9b04e88f17a119ec3f04a3addf55f92841195f5a`.
The Python-process loopback guard recorded zero non-loopback attempts; it did
not disable the independently running Ollama daemon's network. This single
compatibility check supports swapping the selected local model through the
same adapter. It is not a blinded quality comparison, a complete field trial,
or a like-for-like latency comparison with the ten-case E2B run.
