import asyncio
import json
import math
import os
import random
import shutil
import statistics
import subprocess
import sys
import time
import uuid
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

import matplotlib
from agents import Agent, OpenAIChatCompletionsModel, RunHooks, Runner, set_tracing_disabled
from agents.mcp import MCPServerStdio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from openai import AsyncOpenAI


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATABASE_PATH = PROJECT_ROOT / "data" / "collisions.duckdb"
REPORT_PATH = PROJECT_ROOT / "evaluation" / "mcp_latency_summary.md"
PLOT_PATH = PROJECT_ROOT / "evaluation" / "mcp_latency_comparison.png"

REPETITIONS = 100
WARMUPS = 2
AGENT_RUNS_PER_QUERY = 3
SEED = 200

matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(PROJECT_ROOT))

from src.analytics import (
    collision_type_distribution,
    geographic_hotspots,
    severity_distribution,
    summary_statistics,
    temporal_trends,
)
from src.chat import AGENT_INSTRUCTIONS, OLLAMA_MODEL, OLLAMA_URL


QUERY_CASES = (
    {
        "id": "summary_statistics",
        "label": "Summary statistics",
        "mcp_tool": "get_summary_statistics",
        "function": summary_statistics,
        "arguments": {"filters": {"start_year": 2022, "end_year": 2022}},
        "prompt": (
            "How many total collisions, fatalities, and injuries were recorded "
            "in 2022?"
        ),
    },
    {
        "id": "temporal_trends",
        "label": "Temporal trends",
        "mcp_tool": "get_temporal_trends",
        "function": temporal_trends,
        "arguments": {"period": "year", "filters": {"severity": "Fatal"}},
        "prompt": "List the number of fatal collisions for every year in the dataset.",
    },
    {
        "id": "severity_distribution",
        "label": "Severity distribution",
        "mcp_tool": "get_severity_distribution",
        "function": severity_distribution,
        "arguments": {"filters": {"start_year": 2022, "end_year": 2022}},
        "prompt": "Give me the complete severity distribution for collisions in 2022.",
    },
    {
        "id": "collision_type_distribution",
        "label": "Collision types",
        "mcp_tool": "get_collision_type_distribution",
        "function": collision_type_distribution,
        "arguments": {
            "filters": {"start_year": 2022, "end_year": 2022},
            "limit": 5,
        },
        "prompt": (
            "What were the five most common collision types in 2022? Include "
            "the count for each."
        ),
    },
    {
        "id": "geographic_hotspots",
        "label": "Geographic hotspots",
        "mcp_tool": "get_geographic_hotspots",
        "function": geographic_hotspots,
        "arguments": {
            "filters": {"alcohol_involved": True},
            "grid_size": 0.01,
            "limit": 10,
        },
        "prompt": (
            "List the top 10 alcohol-related collision hotspots using the "
            "standard 0.01 degree grid. Include coordinates and collision counts."
        ),
    },
)


def elapsed_ms(started_ns):
    return (time.perf_counter_ns() - started_ns) / 1_000_000


def percentile_95(values):
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


def server_parameters():
    environment = os.environ.copy()
    environment["COLLISIONS_DB_PATH"] = str(DATABASE_PATH)
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "src.mcp_server"],
        cwd=PROJECT_ROOT,
        env=environment,
    )


def parse_tool_result(result):
    if result.isError:
        raise RuntimeError("MCP tool returned an error")
    if result.structuredContent and "result" in result.structuredContent:
        return result.structuredContent["result"]
    if not result.content or any(
        not hasattr(item, "text") for item in result.content
    ):
        raise ValueError("MCP tool returned an unexpected response")
    decoded = [json.loads(item.text) for item in result.content]
    return decoded[0] if len(decoded) == 1 else decoded


def execute_direct(case):
    return case["function"](db_path=DATABASE_PATH, **case["arguments"])


def ollama_request(path, payload=None, timeout=10):
    data = json.dumps(payload).encode() if payload is not None else None
    request = Request(
        f"{OLLAMA_URL}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    with urlopen(request, timeout=timeout) as response:
        return json.load(response)


def ollama_is_running():
    try:
        ollama_request("/api/version")
        return True
    except (OSError, URLError):
        return False


def start_ollama():
    process = None
    if not ollama_is_running():
        executable = shutil.which("ollama")
        if executable is None:
            raise RuntimeError("Ollama is not installed or is not on PATH")
        environment = os.environ.copy()
        environment["OLLAMA_HOST"] = urlsplit(OLLAMA_URL).netloc
        process = subprocess.Popen(
            [executable, "serve"],
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for _ in range(60):
            if ollama_is_running():
                break
            if process.poll() is not None:
                raise RuntimeError("Ollama exited before becoming ready")
            time.sleep(0.25)
        else:
            process.terminate()
            raise RuntimeError("Ollama did not become ready within 15 seconds")

    installed = {
        model["name"] for model in ollama_request("/api/tags").get("models", [])
    }
    if OLLAMA_MODEL not in installed:
        if process is not None:
            process.terminate()
        raise RuntimeError(f"Model {OLLAMA_MODEL} is not installed")
    loaded = {
        model["name"] for model in ollama_request("/api/ps").get("models", [])
    }
    unload_model = OLLAMA_MODEL not in loaded
    ollama_request(
        "/api/generate",
        {"model": OLLAMA_MODEL, "prompt": "", "keep_alive": -1},
        timeout=120,
    )
    return {"process": process, "unload_model": unload_model}


def stop_ollama(runtime):
    if runtime is None:
        return
    if runtime["unload_model"] and ollama_is_running():
        try:
            ollama_request(
                "/api/generate",
                {"model": OLLAMA_MODEL, "prompt": "", "keep_alive": 0},
                timeout=30,
            )
        except (OSError, URLError):
            pass
    process = runtime["process"]
    if process is not None and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()


class TimedChatModel(OpenAIChatCompletionsModel):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.call_durations_ms = []

    def reset(self):
        self.call_durations_ms = []

    async def get_response(
        self,
        system_instructions,
        input,
        model_settings,
        tools,
        output_schema,
        handoffs,
        tracing,
        previous_response_id=None,
        conversation_id=None,
        prompt=None,
    ):
        started = time.perf_counter_ns()
        response = await super().get_response(
            system_instructions,
            input,
            model_settings,
            tools,
            output_schema,
            handoffs,
            tracing,
            previous_response_id,
            conversation_id,
            prompt,
        )
        self.call_durations_ms.append(elapsed_ms(started))
        return response


class ToolTimingHooks(RunHooks):
    def __init__(self):
        self.started_ns = None
        self.durations_ms = []

    async def on_tool_start(self, context, agent, tool):
        self.started_ns = time.perf_counter_ns()

    async def on_tool_end(self, context, agent, tool, result):
        if self.started_ns is not None:
            self.durations_ms.append(elapsed_ms(self.started_ns))
            self.started_ns = None


def parse_arguments(arguments):
    return json.loads(arguments) if isinstance(arguments, str) else arguments


def decode_tool_output(output):
    value = output
    for _ in range(4):
        if isinstance(value, str):
            value = json.loads(value)
        elif isinstance(value, dict) and "result" in value:
            value = value["result"]
        elif isinstance(value, dict) and "text" in value:
            value = value["text"]
        elif isinstance(value, list) and all(
            isinstance(item, dict) and "text" in item for item in value
        ):
            decoded = [decode_tool_output(item["text"]) for item in value]
            return decoded[0] if len(decoded) == 1 else decoded
        else:
            return value
    return value


def extract_agent_call(result):
    calls = []
    outputs = {}
    for item in result.to_input_list():
        if item.get("type") == "function_call":
            calls.append(
                {
                    "call_id": item.get("call_id"),
                    "name": item.get("name"),
                    "arguments": parse_arguments(item.get("arguments", {})),
                }
            )
        elif item.get("type") == "function_call_output":
            outputs[item.get("call_id")] = item.get("output")
    if len(calls) != 1:
        return None, None, len(calls)
    call = calls[0]
    return call, decode_tool_output(outputs.get(call["call_id"])), 1


def canonical_arguments(tool_name, arguments):
    normalized = {
        key: value for key, value in (arguments or {}).items() if value is not None
    }
    if tool_name == "get_collision_type_distribution":
        normalized.setdefault("limit", 5)
    if tool_name == "get_geographic_hotspots":
        normalized.setdefault("grid_size", 0.01)
        normalized.setdefault("limit", 10)
    filters = normalized.get("filters")
    if isinstance(filters, dict):
        normalized["filters"] = {
            key: value[0] if isinstance(value, list) and len(value) == 1 else value
            for key, value in filters.items()
            if value is not None
        }
    return normalized


async def execute_mcp(session, case):
    result = await session.call_tool(case["mcp_tool"], case["arguments"])
    return parse_tool_result(result)


async def measure_startup():
    measurements = []
    with open(os.devnull, "w", encoding="utf-8") as error_log:
        for _ in range(REPETITIONS):
            total_started = time.perf_counter_ns()
            transport_started = time.perf_counter_ns()
            async with stdio_client(
                server_parameters(), errlog=error_log
            ) as streams:
                transport_time = elapsed_ms(transport_started)
                async with ClientSession(*streams) as session:
                    initialize_started = time.perf_counter_ns()
                    await session.initialize()
                    initialize_time = elapsed_ms(initialize_started)

                    tools_started = time.perf_counter_ns()
                    tools = await session.list_tools()
                    tools_time = elapsed_ms(tools_started)
                    available_tools = {tool.name for tool in tools.tools}
                    expected_tools = {case["mcp_tool"] for case in QUERY_CASES}
                    if not expected_tools <= available_tools:
                        raise ValueError("MCP server is missing benchmark tools")
                    total_time = elapsed_ms(total_started)

            measurements.append(
                {
                    "transport_ms": transport_time,
                    "initialize_ms": initialize_time,
                    "tools_list_ms": tools_time,
                    "total_ms": total_time,
                }
            )
    return measurements


async def benchmark_queries():
    timings = {
        case["id"]: {"direct": [], "mcp": [], "overhead": []}
        for case in QUERY_CASES
    }
    baselines = {case["id"]: execute_direct(case) for case in QUERY_CASES}

    with open(os.devnull, "w", encoding="utf-8") as error_log:
        async with stdio_client(server_parameters(), errlog=error_log) as streams:
            async with ClientSession(*streams) as session:
                await session.initialize()
                await session.list_tools()

                for case in QUERY_CASES:
                    for _ in range(WARMUPS):
                        direct_result = execute_direct(case)
                        mcp_result = await execute_mcp(session, case)
                        if direct_result != baselines[case["id"]]:
                            raise ValueError(
                                f"Direct warm-up changed for {case['id']}"
                            )
                        if mcp_result != baselines[case["id"]]:
                            raise ValueError(
                                f"MCP warm-up differs for {case['id']}"
                            )

                schedule = [
                    case for case in QUERY_CASES for _ in range(REPETITIONS)
                ]
                randomizer = random.Random(SEED)
                randomizer.shuffle(schedule)

                for case in schedule:
                    paths = ["direct", "mcp"]
                    randomizer.shuffle(paths)
                    pair = {}
                    for path in paths:
                        started = time.perf_counter_ns()
                        if path == "direct":
                            result = execute_direct(case)
                        else:
                            result = await execute_mcp(session, case)
                        pair[path] = elapsed_ms(started)
                        if result != baselines[case["id"]]:
                            raise ValueError(
                                f"{path} result differs for {case['id']}"
                            )

                    case_timings = timings[case["id"]]
                    case_timings["direct"].append(pair["direct"])
                    case_timings["mcp"].append(pair["mcp"])
                    case_timings["overhead"].append(
                        pair["mcp"] - pair["direct"]
                    )

    rows = []
    for case in QUERY_CASES:
        case_timings = timings[case["id"]]
        direct = case_timings["direct"]
        mcp = case_timings["mcp"]
        overhead = case_timings["overhead"]
        rows.append(
            {
                "query": case["label"],
                "direct_p50": statistics.median(direct),
                "direct_p95": percentile_95(direct),
                "mcp_p50": statistics.median(mcp),
                "mcp_p95": percentile_95(mcp),
                "overhead_p50": statistics.median(overhead),
                "overhead_p95": percentile_95(overhead),
            }
        )
    return rows


async def benchmark_agent_latency():
    environment = os.environ.copy()
    environment["COLLISIONS_DB_PATH"] = str(DATABASE_PATH)
    params = {
        "command": sys.executable,
        "args": ["-m", "src.mcp_server"],
        "cwd": str(PROJECT_ROOT),
        "env": environment,
    }
    measurements = {case["id"]: [] for case in QUERY_CASES}
    expected_results = {case["id"]: execute_direct(case) for case in QUERY_CASES}

    async with AsyncOpenAI(
        base_url=f"{OLLAMA_URL}/v1", api_key="ollama"
    ) as local_client:
        model = TimedChatModel(
            model=OLLAMA_MODEL,
            openai_client=local_client,
        )
        for case in QUERY_CASES:
            for run in range(1, AGENT_RUNS_PER_QUERY + 1):
                total_started = time.perf_counter_ns()
                startup_started = time.perf_counter_ns()
                async with MCPServerStdio(
                    name="Collision Analytics",
                    params=params,
                    cache_tools_list=True,
                    client_session_timeout_seconds=30,
                ) as server:
                    await server.list_tools()
                    startup_ms = elapsed_ms(startup_started)
                    model.reset()
                    hooks = ToolTimingHooks()
                    agent = Agent(
                        name="Collision Analytics Assistant",
                        instructions=AGENT_INSTRUCTIONS,
                        model=model,
                        mcp_servers=[server],
                        mcp_config={"convert_schemas_to_strict": True},
                    )
                    result = await Runner.run(
                        agent,
                        [{"role": "user", "content": case["prompt"]}],
                        max_turns=4,
                        hooks=hooks,
                    )
                    total_ms = elapsed_ms(total_started)

                call, actual_result, call_count = extract_agent_call(result)
                valid = (
                    call_count == 1
                    and call["name"] == case["mcp_tool"]
                    and canonical_arguments(call["name"], call["arguments"])
                    == canonical_arguments(case["mcp_tool"], case["arguments"])
                    and actual_result == expected_results[case["id"]]
                    and len(model.call_durations_ms) == 2
                    and len(hooks.durations_ms) == 1
                )
                measurements[case["id"]].append(
                    {
                        "run": run,
                        "valid": valid,
                        "startup_ms": startup_ms,
                        "selection_ms": (
                            model.call_durations_ms[0]
                            if model.call_durations_ms
                            else None
                        ),
                        "tool_ms": (
                            hooks.durations_ms[0] if hooks.durations_ms else None
                        ),
                        "response_ms": (
                            model.call_durations_ms[1]
                            if len(model.call_durations_ms) > 1
                            else None
                        ),
                        "total_ms": total_ms,
                        "llm_calls": len(model.call_durations_ms),
                    }
                )

    rows = []
    for case in QUERY_CASES:
        runs = measurements[case["id"]]
        rows.append(
            {
                "query": case["label"],
                "runs": len(runs),
                "valid_runs": sum(run["valid"] for run in runs),
                "llm_calls": sum(run["llm_calls"] for run in runs),
                "startup_ms": statistics.mean(run["startup_ms"] for run in runs),
                "selection_ms": statistics.mean(
                    run["selection_ms"]
                    for run in runs
                    if run["selection_ms"] is not None
                ),
                "tool_ms": statistics.mean(
                    run["tool_ms"] for run in runs if run["tool_ms"] is not None
                ),
                "response_ms": statistics.mean(
                    run["response_ms"]
                    for run in runs
                    if run["response_ms"] is not None
                ),
                "total_ms": statistics.mean(run["total_ms"] for run in runs),
            }
        )
    return rows


def summarize_startup(measurements):
    labels = (
        ("Stdio transport open", "transport_ms"),
        ("MCP initialization", "initialize_ms"),
        ("Tool discovery", "tools_list_ms"),
        ("Complete startup session", "total_ms"),
    )
    return [
        {
            "phase": label,
            "p50": statistics.median(item[key] for item in measurements),
            "p95": percentile_95([item[key] for item in measurements]),
        }
        for label, key in labels
    ]


def write_report(query_rows, startup_rows, agent_rows):
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = REPORT_PATH.with_name(
        f".{REPORT_PATH.name}.{uuid.uuid4().hex}.tmp"
    )
    try:
        with temporary_path.open("w", encoding="utf-8") as output:
            output.write("# MCP Communication Latency\n\n")
            output.write(f"![MCP latency comparison]({PLOT_PATH.name})\n\n")
            output.write(
                f"Full DuckDB; {WARMUPS} warm-ups and {REPETITIONS} measured "
                "repetitions per query. "
                "Overhead is the paired MCP latency minus direct latency.\n\n"
            )
            output.write(
                "The protocol comparison excludes LLM inference so it isolates MCP "
                "communication overhead. Real LLM latency is measured separately "
                "below using the production model, instructions, MCP server, "
                "backend, and fresh-session lifecycle.\n\n"
            )
            output.write(
                "| Query | Direct P50 (ms) | Direct P95 (ms) | MCP P50 (ms) | "
                "MCP P95 (ms) | Overhead P50 (ms) | Overhead P95 (ms) |\n"
            )
            output.write("|---|---:|---:|---:|---:|---:|---:|\n")
            for row in query_rows:
                output.write(
                    f"| {row['query']} | {row['direct_p50']:.3f} | "
                    f"{row['direct_p95']:.3f} | {row['mcp_p50']:.3f} | "
                    f"{row['mcp_p95']:.3f} | {row['overhead_p50']:.3f} | "
                    f"{row['overhead_p95']:.3f} |\n"
                )

            output.write("\n## MCP Startup\n\n")
            output.write(
                f"Startup is measured independently over {REPETITIONS} new stdio "
                "sessions.\n\n"
            )
            output.write("| Phase | P50 (ms) | P95 (ms) |\n")
            output.write("|---|---:|---:|\n")
            for row in startup_rows:
                output.write(
                    f"| {row['phase']} | {row['p50']:.3f} | "
                    f"{row['p95']:.3f} |\n"
                )

            output.write("\n## End-to-End Agent Latency\n\n")
            output.write(
                f"Model: `{OLLAMA_MODEL}`. Each query uses a fresh production MCP "
                f"session and {AGENT_RUNS_PER_QUERY} independent agent runs. Values "
                "are arithmetic means; P95 is not reported for this small sample. "
                "A run is valid only when it makes exactly two LLM calls, selects "
                "the expected tool and arguments, makes one MCP call, and returns "
                "the direct-backend result.\n\n"
            )
            output.write(
                "| Query | Valid runs | LLM calls | MCP startup (ms) | Tool "
                "selection LLM (ms) | Agent tool step (ms) | Final response "
                "LLM (ms) | Total through response (ms) |\n"
            )
            output.write("|---|---:|---:|---:|---:|---:|---:|---:|\n")
            for row in agent_rows:
                output.write(
                    f"| {row['query']} | {row['valid_runs']}/{row['runs']} | "
                    f"{row['llm_calls']} | {row['startup_ms']:.1f} | "
                    f"{row['selection_ms']:.1f} | {row['tool_ms']:.1f} | "
                    f"{row['response_ms']:.1f} | {row['total_ms']:.1f} |\n"
                )

            total_calls = sum(row["llm_calls"] for row in agent_rows)
            total_llm_ms = sum(
                row["runs"] * (row["selection_ms"] + row["response_ms"])
                for row in agent_rows
            )
            output.write(
                f"\nMeasured **{total_calls} real LLM calls**; mean model-call "
                f"latency was **{total_llm_ms / total_calls:.1f} ms**. These LLM "
                "times are reported, but are not included in the direct-vs-MCP "
                "protocol comparison above.\n"
            )
        os.replace(temporary_path, REPORT_PATH)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def write_plot(rows):
    PLOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = PLOT_PATH.with_name(
        f".{PLOT_PATH.name}.{uuid.uuid4().hex}.tmp"
    )
    positions = list(range(len(rows)))
    width = 0.36
    figure, axis = plt.subplots(figsize=(11, 5.5))
    try:
        direct_bars = axis.bar(
            [position - width / 2 for position in positions],
            [row["direct_p95"] for row in rows],
            width,
            label="Direct backend",
            color="#4C78A8",
        )
        mcp_bars = axis.bar(
            [position + width / 2 for position in positions],
            [row["mcp_p95"] for row in rows],
            width,
            label="MCP",
            color="#F58518",
        )
        for row, bar in zip(rows, mcp_bars):
            gap = row["overhead_p95"]
            axis.annotate(
                f"+{gap:.1f} ms",
                (bar.get_x() + bar.get_width() / 2, bar.get_height()),
                xytext=(0, 4),
                textcoords="offset points",
                ha="center",
                va="bottom",
                fontsize=8,
            )

        axis.set_title(
            "Direct backend vs MCP protocol latency\n"
            "100 measured repetitions per query"
        )
        axis.set_ylabel("P95 latency (ms)")
        axis.set_xticks(positions, [row["query"] for row in rows], rotation=15)
        axis.grid(axis="y", alpha=0.25)
        axis.legend(frameon=False)
        axis.set_ylim(
            0,
            max(bar.get_height() for bar in (*direct_bars, *mcp_bars)) * 1.18,
        )
        figure.tight_layout()
        figure.savefig(temporary_path, format="png", dpi=180)
        os.replace(temporary_path, PLOT_PATH)
    finally:
        plt.close(figure)
        if temporary_path.exists():
            temporary_path.unlink()


async def run_benchmark():
    if not DATABASE_PATH.exists():
        raise FileNotFoundError(f"Database not found: {DATABASE_PATH}")
    startup_measurements = await measure_startup()
    query_rows = await benchmark_queries()
    agent_rows = await benchmark_agent_latency()
    startup_rows = summarize_startup(startup_measurements)
    write_plot(query_rows)
    write_report(query_rows, startup_rows, agent_rows)


if __name__ == "__main__":
    set_tracing_disabled(True)
    ollama_runtime = None
    try:
        ollama_runtime = start_ollama()
        asyncio.run(run_benchmark())
    finally:
        stop_ollama(ollama_runtime)
