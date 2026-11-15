import argparse
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
from src.chat import (
    OLLAMA_URL,
    create_agent,
    ensure_ollama,
    ollama_request,
    run_agent,
)


RESULTS_PATH = PROJECT_ROOT / "evaluation" / "mcp_performance_results.csv"
REPORT_PATH = PROJECT_ROOT / "evaluation" / "mcp_performance_report.md"
EVALUATION_MODEL = "qwen3:4b-q4_K_M"
RUNS_PER_CASE = 5
MODEL_SETTINGS = ModelSettings(
    temperature=0,
    max_tokens=4096,
    timeout=120,
    parallel_tool_calls=False,
    include_usage=True,
    preserve_raw_usage=True,
)


def evaluation_cases():
    return [
        {
            "id": "full_summary",
            "scope": "full",
            "question": "How many collisions, fatalities, and injuries are in the complete dataset?",
            "analytics_function": "summary_statistics",
            "analytics_args": [None],
            "tool": "get_summary_statistics",
            "tool_arguments": {"filters": None},
        },
        {
            "id": "single_year_summary",
            "scope": "small",
            "question": "How many collisions, fatalities, and injuries occurred in 2023?",
            "analytics_function": "summary_statistics",
            "analytics_args": [{"start_year": 2023, "end_year": 2023}],
            "tool": "get_summary_statistics",
            "tool_arguments": {
                "filters": {"start_year": 2023, "end_year": 2023}
            },
        },
        {
            "id": "five_year_summary",
            "scope": "medium",
            "question": "How many collisions, fatalities, and injuries occurred from 2019 through 2023 inclusive?",
            "analytics_function": "summary_statistics",
            "analytics_args": [{"start_year": 2019, "end_year": 2023}],
            "tool": "get_summary_statistics",
            "tool_arguments": {
                "filters": {"start_year": 2019, "end_year": 2023}
            },
        },
        {
            "id": "fatal_2020",
            "scope": "small",
            "question": "For 2020 only, how many Fatal-severity collisions, fatalities, and injuries were recorded?",
            "analytics_function": "summary_statistics",
            "analytics_args": [
                {"start_year": 2020, "end_year": 2020, "severity": "Fatal"}
            ],
            "tool": "get_summary_statistics",
            "tool_arguments": {
                "filters": {
                    "start_year": 2020,
                    "end_year": 2020,
                    "severity": "Fatal",
                }
            },
        },
        {
            "id": "alcohol_2022",
            "scope": "small",
            "question": "For 2022 only, how many alcohol-involved collisions, fatalities, and injuries were recorded?",
            "analytics_function": "summary_statistics",
            "analytics_args": [
                {
                    "start_year": 2022,
                    "end_year": 2022,
                    "alcohol_involved": True,
                }
            ],
            "tool": "get_summary_statistics",
            "tool_arguments": {
                "filters": {
                    "start_year": 2022,
                    "end_year": 2022,
                    "alcohol_involved": True,
                }
            },
        },
        {
            "id": "fatal_alcohol_years",
            "scope": "medium",
            "question": "Compare yearly collision counts from 2019 through 2021 for collisions that were both Fatal severity and alcohol-involved. Which year had the most and what was the count?",
            "analytics_function": "temporal_trends",
            "analytics_args": [
                "year",
                {
                    "start_year": 2019,
                    "end_year": 2021,
                    "severity": "Fatal",
                    "alcohol_involved": True,
                },
            ],
            "tool": "get_temporal_trends",
            "tool_arguments": {
                "period": "year",
                "filters": {
                    "start_year": 2019,
                    "end_year": 2021,
                    "severity": "Fatal",
                    "alcohol_involved": True,
                },
            },
            "answer_mode": "maximum",
            "answer_fields": ["year", "collision_count"],
        },
        {
            "id": "hourly_2022",
            "scope": "small",
            "question": "Analyze collisions by hour for 2022. Which hour had the most collisions and what was the count?",
            "analytics_function": "temporal_trends",
            "analytics_args": [
                "hour",
                {"start_year": 2022, "end_year": 2022},
            ],
            "tool": "get_temporal_trends",
            "tool_arguments": {
                "period": "hour",
                "filters": {"start_year": 2022, "end_year": 2022},
            },
            "answer_mode": "maximum",
            "answer_fields": ["hour", "collision_count"],
        },
        {
            "id": "weekday_full",
            "scope": "full",
            "question": "Analyze the complete dataset by weekday. Which weekday had the most collisions and what was the count?",
            "analytics_function": "temporal_trends",
            "analytics_args": ["weekday", None],
            "tool": "get_temporal_trends",
            "tool_arguments": {"period": "weekday", "filters": None},
            "answer_mode": "maximum",
            "answer_fields": ["weekday", "collision_count"],
        },
        {
            "id": "severity_2023",
            "scope": "small",
            "question": "Analyze the severity distribution for 2023. Which severity had the most collisions and what was the count?",
            "analytics_function": "severity_distribution",
            "analytics_args": [{"start_year": 2023, "end_year": 2023}],
            "tool": "get_severity_distribution",
            "tool_arguments": {
                "filters": {"start_year": 2023, "end_year": 2023}
            },
            "answer_mode": "maximum",
            "answer_fields": ["severity", "collision_count"],
        },
        {
            "id": "top_hotspots_full",
            "scope": "full",
            "question": "Find the top 10 geographic collision hotspots in the complete dataset using a 0.01-degree grid. What is the highest-ranked cell and its collision count?",
            "analytics_function": "geographic_hotspots",
            "analytics_args": [None, 0.01, 10],
            "tool": "get_geographic_hotspots",
            "tool_arguments": {"filters": None, "grid_size": 0.01, "limit": 10},
            "answer_mode": "first",
            "answer_fields": [
                "latitude_cell",
                "longitude_cell",
                "collision_count",
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
        parsed = [parse_tool_result(item) for item in value]
        return parsed[0] if len(parsed) == 1 else parsed
    return parse_json_value(value)


class PerformanceHooks(RunHooksBase):
    def __init__(self):
        self.llm_started = []
        self.llm_latency = 0.0
        self.mcp_latency = 0.0
        self.input_tokens = 0
        self.output_tokens = 0
        self.total_tokens = 0
        self.model_requests = 0
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


def call_analytics(case):
    function = getattr(analytics, case["analytics_function"])
    return function(*case["analytics_args"])


def matching_rows(case):
    arguments = case["tool_arguments"]
    return analytics.summary_statistics(arguments.get("filters"))["total_collisions"]


def expected_answer_values(case, result):
    if case.get("answer_mode") == "maximum":
        item = max(result, key=lambda row: row["collision_count"])
        return [item[field] for field in case["answer_fields"]]
    if case.get("answer_mode") == "first":
        return [result[0][field] for field in case["answer_fields"]]
    return [
        result["total_collisions"],
        result["total_fatalities"],
        result["total_injuries"],
    ]


def normalize_arguments(tool_name, arguments):
    if not isinstance(arguments, dict):
        return arguments
    normalized = dict(arguments)
    if normalized.get("filters") == {}:
        normalized["filters"] = None
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


def response_has_values(response, expected_values):
    text = re.sub(r"(?<=\d),(?=\d{3}\b)", "", response or "")
    observed_numbers = [float(item) for item in re.findall(r"-?\d+(?:\.\d+)?", text)]
    for expected in expected_values:
        if isinstance(expected, (int, float)):
            if not any(
                math.isclose(float(expected), observed, rel_tol=0, abs_tol=1e-8)
                for observed in observed_numbers
            ):
                return False
        elif str(expected).casefold() not in text.casefold():
            return False
    return True


def assess(case, expected_result, expected_values, hooks, final_response):
    expected_tool = case["tool"]
    tool_selection_correct = [call["name"] for call in hooks.tool_calls] == [
        expected_tool
    ]
    arguments_correct = False
    result_correct = False
    if len(hooks.tool_calls) == 1:
        call = hooks.tool_calls[0]
        arguments_correct = values_equal(
            normalize_arguments(call["name"], call["arguments"]),
            case["tool_arguments"],
        )
        result_correct = values_equal(call["result"], expected_result)
    final_answer_correct = response_has_values(final_response, expected_values)
    return {
        "tool_selection_correct": tool_selection_correct,
        "arguments_correct": arguments_correct,
        "mcp_result_correct": result_correct,
        "final_answer_correct": final_answer_correct,
        "accurate": all(
            (
                tool_selection_correct,
                arguments_correct,
                result_correct,
                final_answer_correct,
            )
        ),
    }


def base_row(case, run_number, expected_result, expected_values, row_count):
    return {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "model": EVALUATION_MODEL,
        "question_id": case["id"],
        "scope": case["scope"],
        "matching_rows": row_count,
        "run": run_number,
        "question": case["question"],
        "expected_analytics_function": case["analytics_function"],
        "expected_tool": case["tool"],
        "expected_arguments": json.dumps(case["tool_arguments"], sort_keys=True),
        "expected_result": json.dumps(expected_result, sort_keys=True),
        "expected_answer_values": json.dumps(expected_values),
        "actual_tools": "[]",
        "actual_arguments": "[]",
        "mcp_results": "[]",
        "final_response": "",
        "tool_selection_correct": False,
        "arguments_correct": False,
        "mcp_result_correct": False,
        "final_answer_correct": False,
        "accurate": False,
        "baseline_latency_seconds": "",
        "total_latency_seconds": "",
        "llm_latency_seconds": "",
        "mcp_latency_seconds": "",
        "orchestration_latency_seconds": "",
        "duckdb_latency_seconds": "",
        "input_tokens": "",
        "output_tokens": "",
        "total_tokens": "",
        "model_requests": "",
        "tool_calls": 0,
        "output_tokens_per_second": "",
        "success": False,
        "error": "",
    }


async def measured_run(agent, case, run_number, expected_result, expected_values, row_count):
    row = base_row(case, run_number, expected_result, expected_values, row_count)

    baseline_started = time.perf_counter()
    baseline_result = call_analytics(case)
    row["baseline_latency_seconds"] = time.perf_counter() - baseline_started
    if not values_equal(baseline_result, expected_result):
        row["error"] = "Direct analytics result changed during evaluation"
        return row

    hooks = PerformanceHooks()
    started = time.perf_counter()
    try:
        result = await run_agent(agent, case["question"], hooks=hooks)
        total_latency = time.perf_counter() - started
        final_response = str(result.final_output)
        orchestration_latency = total_latency - hooks.llm_latency - hooks.mcp_latency
        if orchestration_latency < 0:
            orchestration_latency = ""
        row.update(assess(case, expected_result, expected_values, hooks, final_response))
        row.update(
            {
                "actual_tools": json.dumps([call["name"] for call in hooks.tool_calls]),
                "actual_arguments": json.dumps(
                    [call["arguments"] for call in hooks.tool_calls], sort_keys=True
                ),
                "mcp_results": json.dumps(
                    [call["result"] for call in hooks.tool_calls], sort_keys=True
                ),
                "final_response": final_response,
                "total_latency_seconds": total_latency,
                "llm_latency_seconds": hooks.llm_latency,
                "mcp_latency_seconds": hooks.mcp_latency,
                "orchestration_latency_seconds": orchestration_latency,
                "input_tokens": hooks.input_tokens,
                "output_tokens": hooks.output_tokens,
                "total_tokens": hooks.total_tokens,
                "model_requests": hooks.model_requests,
                "tool_calls": len(hooks.tool_calls),
                "output_tokens_per_second": (
                    hooks.output_tokens / hooks.llm_latency
                    if hooks.output_tokens and hooks.llm_latency
                    else ""
                ),
                "success": True,
            }
        )
    except Exception as error:
        total_latency = time.perf_counter() - started
        llm_latency = "" if hooks.llm_started else hooks.llm_latency
        row.update(
            {
                "total_latency_seconds": total_latency,
                "llm_latency_seconds": llm_latency,
                "mcp_latency_seconds": hooks.mcp_latency,
                "orchestration_latency_seconds": (
                    ""
                    if hooks.llm_started
                    else total_latency - hooks.llm_latency - hooks.mcp_latency
                ),
                "input_tokens": hooks.input_tokens,
                "output_tokens": hooks.output_tokens,
                "total_tokens": hooks.total_tokens,
                "model_requests": hooks.model_requests,
                "tool_calls": len(hooks.tool_calls),
                "actual_tools": json.dumps([call["name"] for call in hooks.tool_calls]),
                "actual_arguments": json.dumps(
                    [call["arguments"] for call in hooks.tool_calls], sort_keys=True
                ),
                "mcp_results": json.dumps(
                    [call["result"] for call in hooks.tool_calls], sort_keys=True
                ),
                "error": f"{type(error).__name__}: {error}",
            }
        )
    return row


def metric(rows, name):
    return [float(row[name]) for row in rows if row[name] not in ("", None)]


def format_metric(values, digits=4):
    return f"{mean(values):.{digits}f}" if values else "N/A"


def percent(rows, field):
    return sum(row[field] is True for row in rows) / len(rows) if rows else 0


def write_results(rows):
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with RESULTS_PATH.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_report(cases, prepared, rows, warmup_seconds, warmup_error):
    lines = [
        "# MCP Chat Performance and Accuracy Evaluation",
        "",
        f"Model: `{EVALUATION_MODEL}`",
        "",
        (
            f"The MCP server and model were started once and warmed up before all "
            f"measurements. Warm-up took {warmup_seconds:.3f} seconds and is excluded "
            "from every reported latency."
            if not warmup_error
            else f"Warm-up failed and measured runs were not started: `{warmup_error}`"
        ),
        "",
        "Logical scope means the number of records matching the filters. All queries use the same physical DuckDB table.",
        "",
        "## Test cases and ground truth",
        "",
        "| Case | Scope | Matching rows | Baseline function | Expected MCP tool |",
        "|---|---|---:|---|---|",
    ]
    for case in cases:
        item = prepared[case["id"]]
        lines.append(
            f"| `{case['id']}` | {case['scope']} | {item['matching_rows']:,} | "
            f"`{case['analytics_function']}` | `{case['tool']}` |"
        )

    lines.extend(
        [
            "",
            "## Accuracy by query",
            "",
            "| Case | Tool | Arguments | MCP result | Final answer | Complete accuracy | Failed runs |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for case in cases:
        selected = [row for row in rows if row["question_id"] == case["id"]]
        failed = sum(row["success"] is not True for row in selected)
        lines.append(
            f"| `{case['id']}` | {percent(selected, 'tool_selection_correct'):.1%} | "
            f"{percent(selected, 'arguments_correct'):.1%} | "
            f"{percent(selected, 'mcp_result_correct'):.1%} | "
            f"{percent(selected, 'final_answer_correct'):.1%} | "
            f"{percent(selected, 'accurate'):.1%} | {failed} |"
        )

    successful = [row for row in rows if row["success"] is True]
    lines.extend(
        [
            "",
            "## Average latency by logical dataset scope",
            "",
            "| Scope | Runs (successful) | Matching rows range | Direct analytics (s) | End to end (s) | LLM (s) | MCP tool (s) | Orchestration (s) |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for scope in ("small", "medium", "full"):
        selected = [row for row in rows if row["scope"] == scope]
        completed = [row for row in selected if row["success"] is True]
        counts = [int(row["matching_rows"]) for row in selected]
        count_range = f"{min(counts):,}–{max(counts):,}" if counts else "N/A"
        lines.append(
            f"| {scope} | {len(selected)} ({len(completed)}) | {count_range} | "
            f"{format_metric(metric(selected, 'baseline_latency_seconds'))} | "
            f"{format_metric(metric(selected, 'total_latency_seconds'))} | "
            f"{format_metric(metric(completed, 'llm_latency_seconds'))} | "
            f"{format_metric(metric(completed, 'mcp_latency_seconds'))} | "
            f"{format_metric(metric(completed, 'orchestration_latency_seconds'))} |"
        )

    lines.extend(
        [
            "",
            "## Overall measurements",
            "",
            f"- Measured runs: {len(rows)}",
            f"- Successful executions: {len(successful)}",
            f"- Complete accuracy: {percent(rows, 'accurate'):.1%}",
            f"- Median end-to-end latency across all runs: {median(metric(rows, 'total_latency_seconds')):.4f} seconds" if rows else "- Median end-to-end latency: N/A",
            f"- Average direct analytics latency across all runs: {format_metric(metric(rows, 'baseline_latency_seconds'))} seconds",
            f"- Average MCP tool latency: {format_metric(metric(successful, 'mcp_latency_seconds'))} seconds",
            f"- Average LLM latency: {format_metric(metric(successful, 'llm_latency_seconds'))} seconds",
            f"- Average input tokens: {format_metric(metric(successful, 'input_tokens'), 1)}",
            f"- Average output tokens: {format_metric(metric(successful, 'output_tokens'), 1)}",
            f"- Average output throughput: {format_metric(metric(successful, 'output_tokens_per_second'), 2)} tokens/second",
            "- Local inference has no per-token API charge.",
            "",
            "## Measurement boundaries",
            "",
            "- Direct analytics latency is the dashboard-equivalent baseline and includes DuckDB connection, query, and result conversion.",
            "- MCP latency measures each tool call through the already-running stdio server.",
            "- LLM latency includes all model calls made by the agent for one question.",
            "- End-to-end latency starts immediately before the agent run and ends after the final response.",
            "- Orchestration latency is end-to-end latency minus measured LLM and MCP tool time.",
            "- A negative orchestration residual indicates overlapping hook intervals and is reported as unavailable rather than as a negative duration.",
            "- DuckDB-only time inside the MCP subprocess is unavailable without production query instrumentation and is left blank in the CSV.",
            "- Every measured question uses an independent conversation.",
            "- Scope-table end-to-end averages include failed runs; component averages include completed runs only.",
        ]
    )
    errors = {}
    for row in rows:
        if row["error"]:
            errors[row["error"]] = errors.get(row["error"], 0) + 1
    lines.extend(["", "## Failures", ""])
    if errors:
        for error, count in sorted(errors.items()):
            lines.append(f"- {count} × `{error}`")
    else:
        lines.append("No execution failures were recorded.")

    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


async def evaluate(runs_per_case):
    set_tracing_disabled(True)
    ensure_ollama(EVALUATION_MODEL)
    installed = {item["name"] for item in ollama_request("/api/tags").get("models", [])}
    if EVALUATION_MODEL not in installed:
        raise RuntimeError(
            f"Exact model {EVALUATION_MODEL} is unavailable. Run: "
            f"ollama pull {EVALUATION_MODEL}"
        )

    cases = evaluation_cases()
    prepared = {}
    for case in cases:
        result = call_analytics(case)
        prepared[case["id"]] = {
            "result": result,
            "answer_values": expected_answer_values(case, result),
            "matching_rows": matching_rows(case),
        }

    server_params = {
        "command": sys.executable,
        "args": ["-m", "src.mcp_server"],
        "cwd": str(PROJECT_ROOT),
    }
    rows = []
    warmup_seconds = 0.0
    warmup_error = ""
    async with AsyncOpenAI(base_url=f"{OLLAMA_URL}/v1", api_key="ollama") as client:
        async with MCPServerStdio(
            name="Collision Analytics Performance Evaluation",
            params=server_params,
            cache_tools_list=True,
            client_session_timeout_seconds=120,
        ) as server:
            agent = create_agent(EVALUATION_MODEL, client, server, MODEL_SETTINGS)
            print("Warming up the loaded model and persistent MCP server...")
            started = time.perf_counter()
            try:
                await run_agent(agent, cases[0]["question"])
            except Exception as error:
                warmup_error = f"{type(error).__name__}: {error}"
            warmup_seconds = time.perf_counter() - started
            if warmup_error:
                write_report(cases, prepared, rows, warmup_seconds, warmup_error)
                raise RuntimeError(warmup_error)

            print(f"Warm-up complete in {warmup_seconds:.3f}s; measurements begin now.")
            for case in cases:
                item = prepared[case["id"]]
                for run_number in range(1, runs_per_case + 1):
                    print(f"{case['id']}: run {run_number}/{runs_per_case}")
                    rows.append(
                        await measured_run(
                            agent,
                            case,
                            run_number,
                            item["result"],
                            item["answer_values"],
                            item["matching_rows"],
                        )
                    )
                    write_results(rows)

    write_report(cases, prepared, rows, warmup_seconds, warmup_error)
    print(f"Wrote {RESULTS_PATH.relative_to(PROJECT_ROOT)}")
    print(f"Wrote {REPORT_PATH.relative_to(PROJECT_ROOT)}")


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate warmed-up MCP chat accuracy and latency"
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=RUNS_PER_CASE,
        help=f"Measured runs per question (default: {RUNS_PER_CASE})",
    )
    args = parser.parse_args()
    if args.runs <= 0:
        parser.error("--runs must be a positive integer")
    asyncio.run(evaluate(args.runs))


if __name__ == "__main__":
    main()
