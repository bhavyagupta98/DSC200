# MCP Communication Latency

![MCP latency comparison](mcp_latency_comparison.png)

Full DuckDB; 2 warm-ups and 100 measured repetitions per query. Overhead is the paired MCP latency minus direct latency.

The protocol comparison excludes LLM inference so it isolates MCP communication overhead. Real LLM latency is measured separately below using the production model, instructions, MCP server, backend, and fresh-session lifecycle.

| Query | Direct P50 (ms) | Direct P95 (ms) | MCP P50 (ms) | MCP P95 (ms) | Overhead P50 (ms) | Overhead P95 (ms) |
|---|---:|---:|---:|---:|---:|---:|
| Summary statistics | 3.466 | 3.578 | 4.470 | 4.698 | 0.998 | 1.164 |
| Temporal trends | 3.821 | 3.951 | 5.656 | 5.871 | 1.840 | 2.026 |
| Severity distribution | 3.837 | 3.930 | 5.616 | 5.784 | 1.798 | 2.016 |
| Collision types | 4.036 | 4.142 | 5.822 | 6.042 | 1.801 | 1.989 |
| Geographic hotspots | 4.749 | 4.901 | 6.648 | 6.922 | 1.903 | 2.176 |

## MCP Startup

Startup is measured independently over 100 new stdio sessions.

| Phase | P50 (ms) | P95 (ms) |
|---|---:|---:|
| Stdio transport open | 2.454 | 2.748 |
| MCP initialization | 180.889 | 196.885 |
| Tool discovery | 1.964 | 2.062 |
| Complete startup session | 185.264 | 201.648 |

## End-to-End Agent Latency

Model: `qwen3:4b-q4_K_M`. Each query uses a fresh production MCP session and 3 independent agent runs. Values are arithmetic means; P95 is not reported for this small sample. A run is valid only when it makes exactly two LLM calls, selects the expected tool and arguments, makes one MCP call, and returns the direct-backend result.

| Query | Valid runs | LLM calls | MCP startup (ms) | Tool selection LLM (ms) | Agent tool step (ms) | Final response LLM (ms) | Total through response (ms) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Summary statistics | 2/3 | 6 | 270.1 | 24260.1 | 281.0 | 11918.8 | 36737.9 |
| Temporal trends | 3/3 | 6 | 336.1 | 15617.2 | 441.4 | 24508.9 | 40915.8 |
| Severity distribution | 3/3 | 6 | 356.7 | 13501.9 | 394.7 | 19020.5 | 33282.2 |
| Collision types | 3/3 | 6 | 339.5 | 8118.0 | 335.1 | 16904.9 | 25704.8 |
| Geographic hotspots | 3/3 | 6 | 374.2 | 11052.6 | 384.6 | 23257.1 | 35076.8 |

Measured **30 real LLM calls**; mean model-call latency was **16816.0 ms**. These LLM times are reported, but are not included in the direct-vs-MCP protocol comparison above.
