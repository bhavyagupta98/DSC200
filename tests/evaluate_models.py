import asyncio
import csv
import json
import math
import re
import sys
import time
from pathlib import Path
from statistics import mean, median

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from agents import ModelSettings, set_tracing_disabled
from agents.lifecycle import RunHooksBase
from agents.mcp import MCPServerStdio
from openai import AsyncOpenAI

from src import analytics
from src.chat import OLLAMA_URL, create_agent, ollama_request, run_agent


RESULTS_PATH = PROJECT_ROOT / "evaluation" / "results.csv"
REPORT_PATH = PROJECT_ROOT / "evaluation" / "report.md"
MODELS = ["qwen3:1.7b", "qwen3:4b", "qwen3:4b-q4_K_M"]
RUNS_PER_QUESTION = 5
MODEL_SETTINGS = ModelSettings(
    temperature=0,
    max_tokens=4096,
    timeout=60,
    parallel_tool_calls=False,
    include_usage=True,
    preserve_raw_usage=True,
)


def evaluation_cases():
    totals = analytics.summary_statistics()

    fatal_2020_filters = {
        "start_year": 2020,
        "end_year": 2020,
        "severity": "Fatal",
    }
    fatal_2020 = analytics.summary_statistics(fatal_2020_filters)

    hourly_filters = {"start_year": 2022, "end_year": 2022}
    hourly = analytics.temporal_trends("hour", hourly_filters)
    busiest_hour = max(hourly, key=lambda item: item["collision_count"])

    hotspots = analytics.geographic_hotspots(grid_size=0.01, limit=10)
    top_hotspot = hotspots[0]

    comparison_filters = {
        "start_year": 2019,
        "end_year": 2021,
        "severity": "Fatal",
        "alcohol_involved": True,
    }
    comparison = analytics.temporal_trends("year", comparison_filters)
    highest_year = max(comparison, key=lambda item: item["collision_count"])

    return [
        {
            "id": "overall_totals",
            "question": (
                "How many total collisions, injuries, and fatalities are in the "
                "collision dataset?"
            ),
            "tool": "get_summary_statistics",
            "arguments": {"filters": None},
            "result": totals,
            "answer_values": [
                totals["total_collisions"],
                totals["total_injuries"],
                totals["total_fatalities"],
            ],
        },
        {
            "id": "fatal_2020",
            "question": (
                "For 2020 only, how many Fatal-severity collision records, "
                "injuries, and fatalities were there?"
            ),
            "tool": "get_summary_statistics",
            "arguments": {"filters": fatal_2020_filters},
            "result": fatal_2020,
            "answer_values": [
                fatal_2020["total_collisions"],
                fatal_2020["total_injuries"],
                fatal_2020["total_fatalities"],
            ],
        },
        {
            "id": "busiest_hour_2022",
            "question": (
                "Analyze the collision distribution by hour for 2022. Which hour "
                "had the most collisions, and how many occurred in that hour?"
            ),
            "tool": "get_temporal_trends",
            "arguments": {"period": "hour", "filters": hourly_filters},
            "result": hourly,
            "answer_values": [
                busiest_hour["hour"],
                busiest_hour["collision_count"],
            ],
        },
        {
            "id": "top_hotspots",
            "question": (
                "Find the top 10 geographic collision hotspots using a 0.01-degree "
                "grid. What is the highest-ranked grid cell and its collision count?"
            ),
            "tool": "get_geographic_hotspots",
            "arguments": {"filters": None, "grid_size": 0.01, "limit": 10},
            "result": hotspots,
            "answer_values": [
                top_hotspot["latitude_cell"],
                top_hotspot["longitude_cell"],
                top_hotspot["collision_count"],
            ],
        },
        {
            "id": "fatal_alcohol_year_comparison",
            "question": (
                "Compare annual collision counts for Fatal, alcohol-involved "
                "collisions from 2019 through 2021. Which year had the highest "
                "count, and what was it?"
            ),
            "tool": "get_temporal_trends",
            "arguments": {"period": "year", "filters": comparison_filters},
            "result": comparison,
            "answer_values": [
                highest_year["year"],
                highest_year["collision_count"],
            ],
        },
    ]


def json_value(value):
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(key): json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(item) for item in value]
    if hasattr(value, "model_dump"):
        return json_value(value.model_dump())
    if hasattr(value, "__dict__"):
        return json_value(vars(value))
    return str(value)


def parse_json_value(value):
    value = json_value(value)
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def parse_tool_result(value):
    value = json_value(value)
    if isinstance(value, dict) and value.get("type") == "text" and "text" in value:
        return parse_json_value(value["text"])
    if isinstance(value, list):
        return [parse_tool_result(item) for item in value]
    return parse_json_value(value)


class EvaluationHooks(RunHooksBase):
    def __init__(self):
        self.llm_started = []
        self.llm_latency = 0.0
        self.mcp_latency = 0.0
        self.input_tokens = 0
        self.output_tokens = 0
        self.total_tokens = 0
        self.model_requests = 0
        self.raw_usage = []
        self.tool_calls = []

    async def on_llm_start(self, context, agent, system_prompt, input_items):
        self.llm_started.append(time.perf_counter())

    async def on_llm_end(self, context, agent, response):
        if self.llm_started:
            self.llm_latency += time.perf_counter() - self.llm_started.pop()
        usage = response.usage
        self.input_tokens += usage.input_tokens
        self.output_tokens += usage.output_tokens
        self.total_tokens += usage.total_tokens
        self.model_requests += usage.requests
        if response.raw_usage is not None:
            self.raw_usage.append(json_value(response.raw_usage))

    async def on_tool_start(self, context, agent, tool):
        arguments = getattr(context, "tool_input", None)
        if arguments is None:
            arguments = getattr(context, "tool_arguments", None)
        self.tool_calls.append(
            {
                "name": tool.name,
                "arguments": parse_json_value(arguments),
                "started": time.perf_counter(),
                "latency_seconds": None,
                "result": None,
            }
        )

    async def on_tool_end(self, context, agent, tool, result):
        for call in reversed(self.tool_calls):
            if call["name"] == tool.name and call["latency_seconds"] is None:
                elapsed = time.perf_counter() - call["started"]
                call["latency_seconds"] = elapsed
                call["result"] = parse_tool_result(result)
                self.mcp_latency += elapsed
                break


def normalized_arguments(tool_name, arguments):
    if not isinstance(arguments, dict):
        return arguments
    normalized = dict(arguments)
    if normalized.get("filters") == {}:
        normalized["filters"] = None
    if tool_name in {
        "get_summary_statistics",
        "get_temporal_trends",
        "get_severity_distribution",
        "get_geographic_hotspots",
    }:
        normalized.setdefault("filters", None)
    if tool_name == "get_geographic_hotspots":
        normalized.setdefault("grid_size", 0.01)
        normalized.setdefault("limit", 10)
    return normalized


def values_equal(actual, expected):
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        return math.isclose(float(actual), float(expected), rel_tol=0, abs_tol=1e-9)
    if isinstance(actual, list) and isinstance(expected, list):
        return len(actual) == len(expected) and all(
            values_equal(left, right) for left, right in zip(actual, expected)
        )
    if isinstance(actual, dict) and isinstance(expected, dict):
        return actual.keys() == expected.keys() and all(
            values_equal(actual[key], expected[key]) for key in actual
        )
    return actual == expected


def response_has_numbers(response, expected_values):
    text = re.sub(r"(?<=\d),(?=\d{3}\b)", "", response or "")
    observed = [float(item) for item in re.findall(r"-?\d+(?:\.\d+)?", text)]
    return all(
        any(
            math.isclose(float(expected), item, rel_tol=0, abs_tol=1e-8)
            for item in observed
        )
        for expected in expected_values
    )


def assess(case, hooks, final_response):
    names = [call["name"] for call in hooks.tool_calls]
    tool_selection_correct = names == [case["tool"]]
    arguments_correct = False
    tool_result_correct = False
    if len(hooks.tool_calls) == 1:
        call = hooks.tool_calls[0]
        arguments_correct = values_equal(
            normalized_arguments(call["name"], call["arguments"]),
            case["arguments"],
        )
        tool_result_correct = values_equal(call["result"], case["result"])
    numerical_answer_correct = response_has_numbers(
        final_response, case["answer_values"]
    )
    return {
        "tool_selection_correct": tool_selection_correct,
        "arguments_correct": arguments_correct,
        "tool_result_correct": tool_result_correct,
        "numerical_answer_correct": numerical_answer_correct,
        "accurate": all(
            (
                tool_selection_correct,
                arguments_correct,
                tool_result_correct,
                numerical_answer_correct,
            )
        ),
    }


def base_row(model, details, case, run_number):
    return {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "model": model,
        "model_id": details.get("digest", ""),
        "parameter_size": details.get("parameter_size", ""),
        "quantization": details.get("quantization_level", ""),
        "question_id": case["id"],
        "run": run_number,
        "question": case["question"],
        "expected_tool": case["tool"],
        "expected_arguments": json.dumps(case["arguments"], sort_keys=True),
        "expected_result": json.dumps(case["result"], sort_keys=True),
        "expected_answer_values": json.dumps(case["answer_values"]),
        "success": False,
        "actual_tools": "[]",
        "actual_arguments": "[]",
        "tool_results": "[]",
        "final_response": "",
        "tool_selection_correct": False,
        "arguments_correct": False,
        "tool_result_correct": False,
        "numerical_answer_correct": False,
        "accurate": False,
        "total_latency_seconds": "",
        "llm_latency_seconds": "",
        "mcp_latency_seconds": "",
        "duckdb_latency_seconds": "",
        "input_tokens": "",
        "output_tokens": "",
        "total_tokens": "",
        "model_requests": "",
        "tool_calls": 0,
        "throughput_output_tokens_per_second": "",
        "ollama_raw_usage": "[]",
        "per_token_api_cost": 0,
        "error": "",
    }


async def measured_run(agent, model, details, case, run_number):
    row = base_row(model, details, case, run_number)
    hooks = EvaluationHooks()
    started = time.perf_counter()
    try:
        result = await run_agent(agent, case["question"], hooks=hooks)
        total_latency = time.perf_counter() - started
        final_response = str(result.final_output)
        assessment = assess(case, hooks, final_response)
        row.update(assessment)
        row.update(
            {
                "success": True,
                "actual_tools": json.dumps(
                    [call["name"] for call in hooks.tool_calls]
                ),
                "actual_arguments": json.dumps(
                    [call["arguments"] for call in hooks.tool_calls],
                    sort_keys=True,
                ),
                "tool_results": json.dumps(
                    [call["result"] for call in hooks.tool_calls],
                    sort_keys=True,
                ),
                "final_response": final_response,
                "total_latency_seconds": total_latency,
                "llm_latency_seconds": hooks.llm_latency,
                "mcp_latency_seconds": hooks.mcp_latency,
                "input_tokens": hooks.input_tokens,
                "output_tokens": hooks.output_tokens,
                "total_tokens": hooks.total_tokens,
                "model_requests": hooks.model_requests,
                "tool_calls": len(hooks.tool_calls),
                "throughput_output_tokens_per_second": (
                    hooks.output_tokens / hooks.llm_latency
                    if hooks.llm_latency and hooks.output_tokens
                    else ""
                ),
                "ollama_raw_usage": json.dumps(hooks.raw_usage, sort_keys=True),
            }
        )
    except Exception as error:
        row["total_latency_seconds"] = time.perf_counter() - started
        row["llm_latency_seconds"] = hooks.llm_latency
        row["mcp_latency_seconds"] = hooks.mcp_latency
        row["input_tokens"] = hooks.input_tokens
        row["output_tokens"] = hooks.output_tokens
        row["total_tokens"] = hooks.total_tokens
        row["model_requests"] = hooks.model_requests
        row["tool_calls"] = len(hooks.tool_calls)
        row["actual_tools"] = json.dumps(
            [call["name"] for call in hooks.tool_calls]
        )
        row["actual_arguments"] = json.dumps(
            [call["arguments"] for call in hooks.tool_calls], sort_keys=True
        )
        row["tool_results"] = json.dumps(
            [call["result"] for call in hooks.tool_calls], sort_keys=True
        )
        row["error"] = f"{type(error).__name__}: {error}"
    return row


def model_inventory():
    tags = ollama_request("/api/tags").get("models", [])
    return {item["name"]: item for item in tags}


def model_details(model, inventory):
    shown = ollama_request("/api/show", {"model": model}, timeout=30)
    details = shown.get("details", {})
    return {
        "digest": inventory[model].get("digest", ""),
        "size": inventory[model].get("size", ""),
        "parameter_size": details.get("parameter_size", ""),
        "quantization_level": details.get("quantization_level", ""),
        "context_length": shown.get("model_info", {}).get(
            "qwen3.context_length", ""
        ),
    }


def metric_values(rows, name):
    return [float(row[name]) for row in rows if row[name] not in ("", None)]


def format_number(value, digits=3):
    if value in ("", None):
        return "N/A"
    return f"{value:.{digits}f}"


def is_true(value):
    return value is True or value == "True"


def write_report(cases, details_by_model, rows, unavailable):
    lines = [
        "# Local Qwen Collision Analytics Evaluation",
        "",
        (
            f"Generated from {RUNS_PER_QUESTION} independent measured runs per "
            "question and model, following one warm-up question per model. All "
            "runs use temperature 0, a 4096-token output safety cap, and a "
            "60-second timeout per model call."
        ),
        "",
        "## Models",
        "",
        "| Ollama tag | Model ID | Parameters | Quantization | Context metadata | Size |",
        "|---|---|---:|---|---:|---:|",
    ]
    for model in MODELS:
        if model in unavailable:
            lines.append(f"| `{model}` | unavailable | N/A | N/A | N/A | N/A |")
            continue
        details = details_by_model[model]
        size_gb = details["size"] / 1_000_000_000 if details["size"] else None
        lines.append(
            f"| `{model}` | `{details['digest'][:12]}` | "
            f"{details['parameter_size']} | {details['quantization_level']} | "
            f"{details['context_length']} | {format_number(size_gb, 2)} GB |"
        )

    lines.extend(["", "## Questions and ground truth", ""])
    for case in cases:
        lines.extend(
            [
                f"### {case['id']}",
                "",
                case["question"],
                "",
                f"Expected tool: `{case['tool']}`",
                "",
                f"Expected arguments: `{json.dumps(case['arguments'], sort_keys=True)}`",
                "",
                "Expected result:",
                "",
                "```json",
                json.dumps(case["result"], indent=2, sort_keys=True),
                "```",
                "",
            ]
        )

    lines.extend(
        [
            "## Measured comparison",
            "",
            (
                "Accuracy requires the expected tool, effective arguments, exact MCP "
                "result, and required numerical values in the final response."
            ),
            "",
            (
                "| Model | Accuracy | Failed | Median total (s) | Median LLM (s) | "
                "Median MCP (s) | Median DuckDB (s) | Avg input tokens | "
                "Avg output tokens | Output tok/s | Tool calls |"
            ),
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    summaries = {}
    for model in MODELS:
        model_rows = [row for row in rows if row["model"] == model]
        if not model_rows:
            lines.append(
                f"| `{model}` | N/A | {len(cases) * RUNS_PER_QUESTION} | "
                "N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A |"
            )
            continue
        successful = [row for row in model_rows if is_true(row["success"])]
        accuracy = sum(is_true(row["accurate"]) for row in model_rows) / len(model_rows)
        failed = len(model_rows) - len(successful)
        totals = metric_values(successful, "total_latency_seconds")
        llm = metric_values(successful, "llm_latency_seconds")
        mcp = metric_values(successful, "mcp_latency_seconds")
        inputs = metric_values(successful, "input_tokens")
        outputs = metric_values(successful, "output_tokens")
        throughput = metric_values(
            successful, "throughput_output_tokens_per_second"
        )
        tools = metric_values(successful, "tool_calls")
        summaries[model] = {
            "accuracy": accuracy,
            "median_total": median(totals) if totals else None,
            "median_llm": median(llm) if llm else None,
        }
        lines.append(
            f"| `{model}` | {accuracy:.1%} | {failed} | "
            f"{format_number(median(totals) if totals else None)} | "
            f"{format_number(median(llm) if llm else None)} | "
            f"{format_number(median(mcp) if mcp else None)} | N/A | "
            f"{format_number(mean(inputs) if inputs else None, 1)} | "
            f"{format_number(mean(outputs) if outputs else None, 1)} | "
            f"{format_number(mean(throughput) if throughput else None, 2)} | "
            f"{int(sum(tools)) if tools else 0} |"
        )

    lines.extend(["", "### Accuracy by question", ""])
    lines.append("| Question | " + " | ".join(f"`{model}`" for model in MODELS) + " |")
    lines.append("|---|" + "---:|" * len(MODELS))
    for case in cases:
        values = []
        for model in MODELS:
            selected = [
                row
                for row in rows
                if row["model"] == model and row["question_id"] == case["id"]
            ]
            if not selected:
                values.append("N/A")
            else:
                values.append(
                    f"{sum(is_true(row['accurate']) for row in selected) / len(selected):.1%}"
                )
        lines.append(f"| {case['id']} | " + " | ".join(values) + " |")

    lines.extend(["", "### Failed executions", ""])
    lines.extend(["| Model | Failure reason | Count |", "|---|---|---:|"])
    for model in MODELS:
        reasons = {}
        for row in rows:
            if row["model"] == model and row["error"]:
                reasons[row["error"]] = reasons.get(row["error"], 0) + 1
        if not reasons:
            lines.append(f"| `{model}` | None | 0 |")
        else:
            for reason, count in sorted(reasons.items()):
                lines.append(f"| `{model}` | {reason} | {count} |")

    if summaries:
        best_accuracy = max(item["accuracy"] for item in summaries.values())
        most_accurate = [
            model
            for model, summary in summaries.items()
            if summary["accuracy"] == best_accuracy
        ]
        fastest = min(
            summaries,
            key=lambda model: summaries[model]["median_total"]
            if summaries[model]["median_total"] is not None
            else math.inf,
        )
        fastest_accurate = min(
            most_accurate,
            key=lambda model: summaries[model]["median_total"]
            if summaries[model]["median_total"] is not None
            else math.inf,
        )
        accurate_names = " and ".join(f"`{model}`" for model in most_accurate)
        lines.extend(
            [
                "",
                "## Accuracy versus performance",
                "",
                (
                    f"{accurate_names} had the highest measured accuracy at "
                    f"{best_accuracy:.1%}. Among them, `{fastest_accurate}` had "
                    "the lower median end-to-end latency. "
                    f"`{fastest}` was fastest overall. "
                    "Use the detailed per-run CSV to inspect failures, selected tools, "
                    "arguments, MCP values, and final answers."
                ),
            ]
        )

    lines.extend(
        [
            "",
            "## Measurement notes",
            "",
            "- Total, LLM, and MCP latency use `time.perf_counter()`.",
            "- Each model call has a 60-second timeout to bound runaway reasoning.",
            (
                "- LLM latency spans each Agents SDK model call. Ollama's "
                "OpenAI-compatible endpoint supplied token usage but did not expose native "
                "`eval_duration` timing in these responses."
            ),
            (
                "- DuckDB latency inside the stdio MCP subprocess is unavailable without "
                "instrumenting application query code, so it is reported as N/A rather "
                "than estimated."
            ),
            "- Local inference has no per-token API charge; hardware and electricity cost were not estimated.",
            "- Each measured run starts with an independent empty conversation.",
        ]
    )
    if unavailable:
        lines.append(
            "- Unavailable exact model tags: "
            + ", ".join(f"`{model}`" for model in unavailable)
            + ". No substitutes were used."
        )
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_results(rows):
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with RESULTS_PATH.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


async def evaluate():
    set_tracing_disabled(True)
    cases = evaluation_cases()
    inventory = model_inventory()
    unavailable = [model for model in MODELS if model not in inventory]
    details_by_model = {
        model: model_details(model, inventory)
        for model in MODELS
        if model not in unavailable
    }
    rows = []

    server_params = {
        "command": sys.executable,
        "args": ["-m", "src.mcp_server"],
        "cwd": str(PROJECT_ROOT),
    }
    for model in MODELS:
        if model in unavailable:
            print(f"Skipping unavailable exact model: {model}")
            continue
        print(f"Evaluating {model}")
        ollama_request(
            "/api/generate",
            {"model": model, "prompt": "", "keep_alive": -1},
            timeout=180,
        )
        try:
            async with AsyncOpenAI(
                base_url=f"{OLLAMA_URL}/v1", api_key="ollama"
            ) as local_client:
                async with MCPServerStdio(
                    name="Collision Analytics Evaluation",
                    params=server_params,
                    cache_tools_list=True,
                    client_session_timeout_seconds=60,
                ) as server:
                    agent = create_agent(
                        model, local_client, server, MODEL_SETTINGS
                    )
                    print("  warm-up")
                    try:
                        await run_agent(agent, cases[0]["question"])
                    except Exception as error:
                        print(f"  warm-up failed: {type(error).__name__}: {error}")
                    for case in cases:
                        for run_number in range(1, RUNS_PER_QUESTION + 1):
                            print(
                                f"  {case['id']} run {run_number}/{RUNS_PER_QUESTION}"
                            )
                            rows.append(
                                await measured_run(
                                    agent,
                                    model,
                                    details_by_model[model],
                                    case,
                                    run_number,
                                )
                            )
        finally:
            ollama_request(
                "/api/generate",
                {"model": model, "prompt": "", "keep_alive": 0},
                timeout=60,
            )

    if rows:
        write_results(rows)
    else:
        RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        RESULTS_PATH.write_text("", encoding="utf-8")
    write_report(cases, details_by_model, rows, unavailable)
    print(f"Wrote {RESULTS_PATH.relative_to(PROJECT_ROOT)}")
    print(f"Wrote {REPORT_PATH.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    asyncio.run(evaluate())
