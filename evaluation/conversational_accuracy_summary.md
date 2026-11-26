# Single-Turn Conversational Accuracy

Model: `qwen3:4b-q4_K_M` · Database: full DuckDB · Cases: 12 · Runs per case: 3 · Independent single-turn prompts

| Query | Variant | Tool | Arguments | Result | Required facts | Overall |
|---|---|---:|---:|---:|---:|---:|
| Summary statistics | Direct | 2/3 | 2/3 | 2/3 | 3/3 | 2/3 |
| Summary statistics | Paraphrase | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| Temporal trends | Direct | 3/3 | 3/3 | 3/3 | 2/3 | 2/3 |
| Temporal trends | Paraphrase | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| Severity distribution | Direct | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| Severity distribution | Paraphrase | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| Collision types | Direct | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| Collision types | Paraphrase | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| Geographic hotspots | Direct | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| Geographic hotspots | Paraphrase | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| Summary statistics | Compound | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| Collision types | Compound | 3/3 | 0/3 | 0/3 | 0/3 | 0/3 |
| **Overall** | **36 runs** | **35/36 (97%)** | **32/36 (89%)** | **32/36 (89%)** | **32/36 (89%)** | **31/36 (86%)** |

Tool selection passes only when exactly one expected tool is called. Arguments are compared semantically with documented MCP defaults. Required facts pass only when each expected label/value pair appears in the same output clause. Free-form explanatory prose is not graded.

Actual model usage: **72 LLM calls** across 36 agent runs; mean **17550.0 ms per LLM call**. See `agent.log` for the complete audit trail.

The production model sampling configuration is unchanged. Results can vary between runs because model generation is nondeterministic; three independent runs per prompt expose that variability instead of presenting a seeded evaluation as production behavior.
