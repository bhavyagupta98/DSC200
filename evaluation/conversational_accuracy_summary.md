# Single-Turn Conversational Accuracy

Model: `qwen3:4b-q4_K_M` · Database: full DuckDB · Cases: 12 · Runs per case: 1 · Independent single-turn prompts

| Query | Variant | Tool | Arguments | Result | Required facts | Overall |
|---|---|---:|---:|---:|---:|---:|
| Summary statistics | Direct | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| Summary statistics | Paraphrase | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| Temporal trends | Direct | 1/1 | 1/1 | 1/1 | 0/1 | 0/1 |
| Temporal trends | Paraphrase | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| Severity distribution | Direct | 1/1 | 1/1 | 1/1 | 0/1 | 0/1 |
| Severity distribution | Paraphrase | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 |
| Collision types | Direct | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| Collision types | Paraphrase | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| Geographic hotspots | Direct | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| Geographic hotspots | Paraphrase | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| Summary statistics | Compound | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| Collision types | Compound | 1/1 | 0/1 | 0/1 | 0/1 | 0/1 |
| **Overall** | **12 runs** | **11/12 (92%)** | **10/12 (83%)** | **10/12 (83%)** | **8/12 (67%)** | **8/12 (67%)** |

Tool selection passes only when exactly one expected tool is called. Arguments are compared semantically with documented MCP defaults. Required facts pass only when each expected label/value pair appears in the same output clause. Free-form explanatory prose is not graded.

Actual model usage: **23 LLM calls** across 12 agent runs; mean **16118.4 ms per LLM call**. See `agent.log` for the complete audit trail.

The production model sampling configuration is unchanged. Results can vary between executions because model generation is nondeterministic; this evaluation reports one independent run per prompt and does not present seeded behavior as production behavior.
