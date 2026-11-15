# MCP Chat Performance and Accuracy Evaluation

Model: `qwen3:4b-q4_K_M`

The MCP server and model were started once and warmed up before all measurements. Warm-up took 15.358 seconds and is excluded from every reported latency.

Logical scope means the number of records matching the filters. All queries use the same physical DuckDB table.

## Test cases and ground truth

| Case | Scope | Matching rows | Baseline function | Expected MCP tool |
|---|---|---:|---|---|
| `full_summary` | full | 239,588 | `summary_statistics` | `get_summary_statistics` |
| `single_year_summary` | small | 18,966 | `summary_statistics` | `get_summary_statistics` |
| `five_year_summary` | medium | 109,313 | `summary_statistics` | `get_summary_statistics` |
| `fatal_2020` | small | 262 | `summary_statistics` | `get_summary_statistics` |
| `alcohol_2022` | small | 3,393 | `summary_statistics` | `get_summary_statistics` |
| `fatal_alcohol_years` | medium | 266 | `temporal_trends` | `get_temporal_trends` |
| `hourly_2022` | small | 21,282 | `temporal_trends` | `get_temporal_trends` |
| `weekday_full` | full | 239,588 | `temporal_trends` | `get_temporal_trends` |
| `severity_2023` | small | 18,966 | `severity_distribution` | `get_severity_distribution` |
| `top_hotspots_full` | full | 239,588 | `geographic_hotspots` | `get_geographic_hotspots` |

## Accuracy by query

| Case | Tool | Arguments | MCP result | Final answer | Complete accuracy | Failed runs |
|---|---:|---:|---:|---:|---:|---:|
| `full_summary` | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 0 |
| `single_year_summary` | 20.0% | 20.0% | 20.0% | 100.0% | 20.0% | 0 |
| `five_year_summary` | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 0 |
| `fatal_2020` | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 0 |
| `alcohol_2022` | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 0 |
| `fatal_alcohol_years` | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 5 |
| `hourly_2022` | 100.0% | 100.0% | 100.0% | 0.0% | 0.0% | 0 |
| `weekday_full` | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 0 |
| `severity_2023` | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 0 |
| `top_hotspots_full` | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 0 |

## Average latency by logical dataset scope

| Scope | Runs (successful) | Matching rows range | Direct analytics (s) | End to end (s) | LLM (s) | MCP tool (s) | Orchestration (s) |
|---|---:|---:|---:|---:|---:|---:|---:|
| small | 25 (25) | 262–21,282 | 0.0124 | 34.6351 | 34.5898 | 0.0473 | 0.0054 |
| medium | 10 (5) | 266–109,313 | 0.0251 | 81.6378 | 19.2992 | 0.0373 | 0.0082 |
| full | 15 (15) | 239,588–239,588 | 0.0208 | 15.0141 | 14.9885 | 0.0206 | 0.0050 |

## Overall measurements

- Measured runs: 50
- Successful executions: 45
- Complete accuracy: 72.0%
- Median end-to-end latency across all runs: 19.5734 seconds
- Average direct analytics latency across all runs: 0.0175 seconds
- Average MCP tool latency: 0.0373 seconds
- Average LLM latency: 26.3571 seconds
- Average input tokens: 2023.0
- Average output tokens: 862.2
- Average output throughput: 32.91 tokens/second
- Local inference has no per-token API charge.

## Measurement boundaries

- Direct analytics latency is the dashboard-equivalent baseline and includes DuckDB connection, query, and result conversion.
- MCP latency measures each tool call through the already-running stdio server.
- LLM latency includes all model calls made by the agent for one question.
- End-to-end latency starts immediately before the agent run and ends after the final response.
- Orchestration latency is end-to-end latency minus measured LLM and MCP tool time.
- A negative orchestration residual indicates overlapping hook intervals and is reported as unavailable rather than as a negative duration.
- DuckDB-only time inside the MCP subprocess is unavailable without production query instrumentation and is left blank in the CSV.
- Every measured question uses an independent conversation.
- Scope-table end-to-end averages include failed runs; component averages include completed runs only.

## Failures

- 5 × `ModelTimeoutError: Model call timed out after 120 seconds.`
