# Local Qwen Collision Analytics Evaluation

Generated from 5 independent measured runs per question and model, following one warm-up question per model. All runs use temperature 0, a 4096-token output safety cap, and a 60-second timeout per model call.

## Models

| Ollama tag | Model ID | Parameters | Quantization | Context metadata | Size |
|---|---|---:|---|---:|---:|
| `qwen3:1.7b` | `8f68893c685c` | 2.0B | Q4_K_M | 40960 | 1.36 GB |
| `qwen3:4b` | `359d7dd4bcda` | 4.0B | Q4_K_M | 262144 | 2.50 GB |
| `qwen3:4b-q4_K_M` | `2bfd38a7daaf` | 4.0B | Q4_K_M | 40960 | 2.62 GB |

## Questions and ground truth

### overall_totals

How many total collisions, injuries, and fatalities are in the collision dataset?

Expected tool: `get_summary_statistics`

Expected arguments: `{"filters": null}`

Expected result:

```json
{
  "total_collisions": 239588,
  "total_fatalities": 2479,
  "total_injuries": 181254
}
```

### fatal_2020

For 2020 only, how many Fatal-severity collision records, injuries, and fatalities were there?

Expected tool: `get_summary_statistics`

Expected arguments: `{"filters": {"end_year": 2020, "severity": "Fatal", "start_year": 2020}}`

Expected result:

```json
{
  "total_collisions": 262,
  "total_fatalities": 285,
  "total_injuries": 166
}
```

### busiest_hour_2022

Analyze the collision distribution by hour for 2022. Which hour had the most collisions, and how many occurred in that hour?

Expected tool: `get_temporal_trends`

Expected arguments: `{"filters": {"end_year": 2022, "start_year": 2022}, "period": "hour"}`

Expected result:

```json
[
  {
    "collision_count": 564,
    "hour": 0,
    "total_fatalities": 9,
    "total_injuries": 391
  },
  {
    "collision_count": 565,
    "hour": 1,
    "total_fatalities": 11,
    "total_injuries": 339
  },
  {
    "collision_count": 566,
    "hour": 2,
    "total_fatalities": 15,
    "total_injuries": 330
  },
  {
    "collision_count": 374,
    "hour": 3,
    "total_fatalities": 6,
    "total_injuries": 204
  },
  {
    "collision_count": 339,
    "hour": 4,
    "total_fatalities": 7,
    "total_injuries": 195
  },
  {
    "collision_count": 436,
    "hour": 5,
    "total_fatalities": 8,
    "total_injuries": 300
  },
  {
    "collision_count": 619,
    "hour": 6,
    "total_fatalities": 11,
    "total_injuries": 396
  },
  {
    "collision_count": 980,
    "hour": 7,
    "total_fatalities": 6,
    "total_injuries": 718
  },
  {
    "collision_count": 1073,
    "hour": 8,
    "total_fatalities": 9,
    "total_injuries": 849
  },
  {
    "collision_count": 753,
    "hour": 9,
    "total_fatalities": 8,
    "total_injuries": 597
  },
  {
    "collision_count": 794,
    "hour": 10,
    "total_fatalities": 8,
    "total_injuries": 654
  },
  {
    "collision_count": 866,
    "hour": 11,
    "total_fatalities": 7,
    "total_injuries": 745
  },
  {
    "collision_count": 880,
    "hour": 12,
    "total_fatalities": 6,
    "total_injuries": 730
  },
  {
    "collision_count": 1041,
    "hour": 13,
    "total_fatalities": 7,
    "total_injuries": 899
  },
  {
    "collision_count": 1245,
    "hour": 14,
    "total_fatalities": 6,
    "total_injuries": 994
  },
  {
    "collision_count": 1537,
    "hour": 15,
    "total_fatalities": 20,
    "total_injuries": 1302
  },
  {
    "collision_count": 1444,
    "hour": 16,
    "total_fatalities": 10,
    "total_injuries": 1173
  },
  {
    "collision_count": 1568,
    "hour": 17,
    "total_fatalities": 14,
    "total_injuries": 1246
  },
  {
    "collision_count": 1316,
    "hour": 18,
    "total_fatalities": 19,
    "total_injuries": 1096
  },
  {
    "collision_count": 924,
    "hour": 19,
    "total_fatalities": 13,
    "total_injuries": 738
  },
  {
    "collision_count": 876,
    "hour": 20,
    "total_fatalities": 13,
    "total_injuries": 719
  },
  {
    "collision_count": 873,
    "hour": 21,
    "total_fatalities": 14,
    "total_injuries": 676
  },
  {
    "collision_count": 830,
    "hour": 22,
    "total_fatalities": 18,
    "total_injuries": 578
  },
  {
    "collision_count": 703,
    "hour": 23,
    "total_fatalities": 14,
    "total_injuries": 438
  }
]
```

### top_hotspots

Find the top 10 geographic collision hotspots using a 0.01-degree grid. What is the highest-ranked grid cell and its collision count?

Expected tool: `get_geographic_hotspots`

Expected arguments: `{"filters": null, "grid_size": 0.01, "limit": 10}`

Expected result:

```json
[
  {
    "collision_count": 1364,
    "latitude_cell": 32.76,
    "longitude_cell": -117.17,
    "total_fatalities": 12,
    "total_injuries": 813
  },
  {
    "collision_count": 1136,
    "latitude_cell": 32.8,
    "longitude_cell": -116.96,
    "total_fatalities": 3,
    "total_injuries": 986
  },
  {
    "collision_count": 1117,
    "latitude_cell": 32.71,
    "longitude_cell": -117.15,
    "total_fatalities": 16,
    "total_injuries": 981
  },
  {
    "collision_count": 1104,
    "latitude_cell": 32.71,
    "longitude_cell": -117.16,
    "total_fatalities": 8,
    "total_injuries": 1347
  },
  {
    "collision_count": 1057,
    "latitude_cell": 32.71,
    "longitude_cell": -117.12,
    "total_fatalities": 4,
    "total_injuries": 686
  },
  {
    "collision_count": 1041,
    "latitude_cell": 32.72,
    "longitude_cell": -117.17,
    "total_fatalities": 6,
    "total_injuries": 826
  },
  {
    "collision_count": 988,
    "latitude_cell": 32.71,
    "longitude_cell": -117.02,
    "total_fatalities": 4,
    "total_injuries": 516
  },
  {
    "collision_count": 972,
    "latitude_cell": 32.75,
    "longitude_cell": -117.21,
    "total_fatalities": 14,
    "total_injuries": 731
  },
  {
    "collision_count": 948,
    "latitude_cell": 32.77,
    "longitude_cell": -117.01,
    "total_fatalities": 9,
    "total_injuries": 525
  },
  {
    "collision_count": 917,
    "latitude_cell": 32.71,
    "longitude_cell": -117.17,
    "total_fatalities": 5,
    "total_injuries": 1129
  }
]
```

### fatal_alcohol_year_comparison

Compare annual collision counts for Fatal, alcohol-involved collisions from 2019 through 2021. Which year had the highest count, and what was it?

Expected tool: `get_temporal_trends`

Expected arguments: `{"filters": {"alcohol_involved": true, "end_year": 2021, "severity": "Fatal", "start_year": 2019}, "period": "year"}`

Expected result:

```json
[
  {
    "collision_count": 80,
    "total_fatalities": 85,
    "total_injuries": 49,
    "year": 2019
  },
  {
    "collision_count": 87,
    "total_fatalities": 96,
    "total_injuries": 54,
    "year": 2020
  },
  {
    "collision_count": 99,
    "total_fatalities": 103,
    "total_injuries": 64,
    "year": 2021
  }
]
```

## Measured comparison

Accuracy requires the expected tool, effective arguments, exact MCP result, and required numerical values in the final response.

| Model | Accuracy | Failed | Median total (s) | Median LLM (s) | Median MCP (s) | Median DuckDB (s) | Avg input tokens | Avg output tokens | Output tok/s | Tool calls |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `qwen3:1.7b` | 20.0% | 5 | 17.005 | 16.973 | 0.022 | N/A | 3140.5 | 1182.8 | 67.76 | 35 |
| `qwen3:4b` | 80.0% | 5 | 50.475 | 50.438 | 0.027 | N/A | 2723.2 | 1500.2 | 30.67 | 20 |
| `qwen3:4b-q4_K_M` | 80.0% | 5 | 23.423 | 23.395 | 0.021 | N/A | 1997.5 | 719.8 | 28.25 | 20 |

### Accuracy by question

| Question | `qwen3:1.7b` | `qwen3:4b` | `qwen3:4b-q4_K_M` |
|---|---:|---:|---:|
| overall_totals | 0.0% | 100.0% | 100.0% |
| fatal_2020 | 0.0% | 100.0% | 100.0% |
| busiest_hour_2022 | 0.0% | 100.0% | 100.0% |
| top_hotspots | 100.0% | 100.0% | 100.0% |
| fatal_alcohol_year_comparison | 0.0% | 0.0% | 0.0% |

### Failed executions

| Model | Failure reason | Count |
|---|---|---:|
| `qwen3:1.7b` | MaxTurnsExceeded: Max turns (4) exceeded | 5 |
| `qwen3:4b` | ModelTimeoutError: Model call timed out after 60 seconds. | 5 |
| `qwen3:4b-q4_K_M` | ModelTimeoutError: Model call timed out after 60 seconds. | 5 |

## Accuracy versus performance

`qwen3:4b` and `qwen3:4b-q4_K_M` had the highest measured accuracy at 80.0%. Among them, `qwen3:4b-q4_K_M` had the lower median end-to-end latency. `qwen3:1.7b` was fastest overall. Use the detailed per-run CSV to inspect failures, selected tools, arguments, MCP values, and final answers.

## Measurement notes

- Total, LLM, and MCP latency use `time.perf_counter()`.
- Each model call has a 60-second timeout to bound runaway reasoning.
- LLM latency spans each Agents SDK model call. Ollama's OpenAI-compatible endpoint supplied token usage but did not expose native `eval_duration` timing in these responses.
- DuckDB latency inside the stdio MCP subprocess is unavailable without instrumenting application query code, so it is reported as N/A rather than estimated.
- Local inference has no per-token API charge; hardware and electricity cost were not estimated.
- Each measured run starts with an independent empty conversation.
