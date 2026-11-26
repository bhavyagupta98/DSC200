import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

import duckdb
from agents import (
    Agent,
    OpenAIChatCompletionsModel,
    RunHooks,
    Runner,
    set_tracing_disabled,
)
from agents.mcp import MCPServerStdio
from openai import AsyncOpenAI


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATABASE_PATH = PROJECT_ROOT / "data" / "collisions.duckdb"
REPORT_PATH = PROJECT_ROOT / "evaluation" / "conversational_accuracy_summary.md"
LOG_PATH = PROJECT_ROOT / "evaluation" / "agent.log"
RUNS_PER_CASE = 3

sys.path.insert(0, str(PROJECT_ROOT))

from src.analytics import (
    collision_type_distribution,
    geographic_hotspots,
    severity_distribution,
    summary_statistics,
    temporal_trends,
)
from src.chat import AGENT_INSTRUCTIONS, OLLAMA_MODEL, OLLAMA_URL


TEST_CASES = (
    {
        "id": "summary_2022_direct",
        "query": "Summary statistics",
        "variant": "Direct",
        "prompt": (
            "How many total collisions, fatalities, and injuries were recorded "
            "in 2022?"
        ),
        "tool": "get_summary_statistics",
        "function": summary_statistics,
        "arguments": {"filters": {"start_year": 2022, "end_year": 2022}},
        "answer_kind": "summary",
    },
    {
        "id": "summary_2022_paraphrase",
        "query": "Summary statistics",
        "variant": "Paraphrase",
        "prompt": (
            "Give me the 2022 collision summary, including the collision, "
            "fatality, and injury totals."
        ),
        "tool": "get_summary_statistics",
        "function": summary_statistics,
        "arguments": {"filters": {"start_year": 2022, "end_year": 2022}},
        "answer_kind": "summary",
    },
    {
        "id": "fatal_trend_direct",
        "query": "Temporal trends",
        "variant": "Direct",
        "prompt": "List the number of fatal collisions for every year in the dataset.",
        "tool": "get_temporal_trends",
        "function": temporal_trends,
        "arguments": {"period": "year", "filters": {"severity": "Fatal"}},
        "answer_kind": "temporal",
    },
    {
        "id": "fatal_trend_paraphrase",
        "query": "Temporal trends",
        "variant": "Paraphrase",
        "prompt": (
            "Show the yearly trend in fatal collision counts, with one count "
            "for each year."
        ),
        "tool": "get_temporal_trends",
        "function": temporal_trends,
        "arguments": {"period": "year", "filters": {"severity": "Fatal"}},
        "answer_kind": "temporal",
    },
    {
        "id": "severity_2022_direct",
        "query": "Severity distribution",
        "variant": "Direct",
        "prompt": "Give me the complete severity distribution for collisions in 2022.",
        "tool": "get_severity_distribution",
        "function": severity_distribution,
        "arguments": {"filters": {"start_year": 2022, "end_year": 2022}},
        "answer_kind": "severity",
    },
    {
        "id": "severity_2022_paraphrase",
        "query": "Severity distribution",
        "variant": "Paraphrase",
        "prompt": (
            "Break down all 2022 collisions by normalized severity and include "
            "the collision count for every category."
        ),
        "tool": "get_severity_distribution",
        "function": severity_distribution,
        "arguments": {"filters": {"start_year": 2022, "end_year": 2022}},
        "answer_kind": "severity",
    },
    {
        "id": "collision_types_2022_direct",
        "query": "Collision types",
        "variant": "Direct",
        "prompt": (
            "What were the five most common collision types in 2022? "
            "Include the count for each."
        ),
        "tool": "get_collision_type_distribution",
        "function": collision_type_distribution,
        "arguments": {
            "filters": {"start_year": 2022, "end_year": 2022},
            "limit": 5,
        },
        "answer_kind": "collision_type",
    },
    {
        "id": "collision_types_2022_paraphrase",
        "query": "Collision types",
        "variant": "Paraphrase",
        "prompt": "Rank the top 5 collision types for 2022 by collision count.",
        "tool": "get_collision_type_distribution",
        "function": collision_type_distribution,
        "arguments": {
            "filters": {"start_year": 2022, "end_year": 2022},
            "limit": 5,
        },
        "answer_kind": "collision_type",
    },
    {
        "id": "alcohol_hotspots_direct",
        "query": "Geographic hotspots",
        "variant": "Direct",
        "prompt": (
            "List the top 10 alcohol-related collision hotspots using the "
            "standard 0.01 degree grid. Include coordinates and collision counts."
        ),
        "tool": "get_geographic_hotspots",
        "function": geographic_hotspots,
        "arguments": {
            "filters": {"alcohol_involved": True},
            "grid_size": 0.01,
            "limit": 10,
        },
        "answer_kind": "hotspot",
    },
    {
        "id": "alcohol_hotspots_paraphrase",
        "query": "Geographic hotspots",
        "variant": "Paraphrase",
        "prompt": (
            "Where were the ten busiest grid cells for alcohol-involved "
            "collisions? Use grid size 0.01 and report each cell's count."
        ),
        "tool": "get_geographic_hotspots",
        "function": geographic_hotspots,
        "arguments": {
            "filters": {"alcohol_involved": True},
            "grid_size": 0.01,
            "limit": 10,
        },
        "answer_kind": "hotspot",
    },
    {
        "id": "fatal_alcohol_summary_compound",
        "query": "Summary statistics",
        "variant": "Compound",
        "prompt": (
            "For 2019 through 2023, give total collisions, fatalities, and "
            "injuries for fatal collisions involving alcohol."
        ),
        "tool": "get_summary_statistics",
        "function": summary_statistics,
        "arguments": {
            "filters": {
                "start_year": 2019,
                "end_year": 2023,
                "severity": "Fatal",
                "alcohol_involved": True,
            }
        },
        "answer_kind": "summary",
    },
    {
        "id": "san_diego_collision_types_compound",
        "query": "Collision types",
        "variant": "Compound",
        "prompt": (
            "Rank the top 5 collision types in San Diego from 2019 through "
            "2022 for Fatal or Injury (Severe) collisions when weather was "
            "Clear or Raining. Include the count for each type."
        ),
        "tool": "get_collision_type_distribution",
        "function": collision_type_distribution,
        "arguments": {
            "filters": {
                "start_year": 2019,
                "end_year": 2022,
                "severity": ["Fatal", "Injury (Severe)"],
                "weather": ["Clear", "Raining"],
                "location": "San Diego",
            },
            "limit": 5,
        },
        "answer_kind": "collision_type",
    },
)


class AgentLog:
    def __init__(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.temporary_path = path.with_name(
            f".{path.name}.{uuid.uuid4().hex}.tmp"
        )
        self.output = self.temporary_path.open("w", encoding="utf-8")

    def write(self, event_type, **details):
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": event_type,
            **json_safe(details),
        }
        self.output.write(json.dumps(record, ensure_ascii=False) + "\n")
        self.output.flush()

    def close(self, commit):
        self.output.close()
        if commit:
            os.replace(self.temporary_path, self.path)
        elif self.temporary_path.exists():
            self.temporary_path.unlink()


def json_safe(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if is_dataclass(value):
        return json_safe(asdict(value))
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return json_safe(model_dump(mode="json", exclude_none=True))
    return str(value)


def serialize_tool(tool):
    return {
        "name": getattr(tool, "name", type(tool).__name__),
        "description": getattr(tool, "description", None),
        "input_schema": getattr(tool, "params_json_schema", None),
        "strict": getattr(tool, "strict_json_schema", None),
    }


def visible_model_blocks(output_items):
    blocks = []
    for raw_item in json_safe(output_items):
        if not isinstance(raw_item, dict):
            continue
        item_type = raw_item.get("type")
        if item_type == "reasoning":
            continue
        if item_type == "function_call":
            try:
                tool_input = parse_arguments(raw_item.get("arguments", {}))
            except (TypeError, ValueError, json.JSONDecodeError):
                tool_input = raw_item.get("arguments")
            blocks.append(
                {
                    "type": "tool_use",
                    "id": raw_item.get("call_id"),
                    "name": raw_item.get("name"),
                    "input": tool_input,
                    "raw_arguments": raw_item.get("arguments"),
                }
            )
        elif item_type == "message":
            for content in raw_item.get("content", []):
                if not isinstance(content, dict):
                    continue
                if content.get("type") in {"output_text", "text"}:
                    blocks.append(
                        {"type": "text", "text": content.get("text", "")}
                    )
                elif content.get("type") == "refusal":
                    blocks.append(
                        {"type": "refusal", "text": content.get("refusal", "")}
                    )
        else:
            blocks.append(raw_item)
    return blocks


def observable_input_items(input_items):
    items = json_safe(input_items)
    visible = [
        item
        for item in items
        if not isinstance(item, dict) or item.get("type") != "reasoning"
    ]
    return visible, len(items) - len(visible)


class LoggedChatModel(OpenAIChatCompletionsModel):
    def __init__(self, *, log, **kwargs):
        super().__init__(**kwargs)
        self.log = log
        self.case_id = None
        self.run = None
        self.turn = 0
        self.call_durations_ms = []

    def begin_case(self, case_id, run):
        self.case_id = case_id
        self.run = run
        self.turn = 0
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
        self.turn += 1
        input_items, excluded_reasoning_items = observable_input_items(input)
        self.log.write(
            "harness",
            subtype="llm_request",
            case_id=self.case_id,
            run=self.run,
            turn=self.turn,
            model=OLLAMA_MODEL,
            system_prompt=system_instructions,
            input_items=input_items,
            excluded_reasoning_items=excluded_reasoning_items,
            tools=[serialize_tool(tool) for tool in tools],
            model_settings=model_settings,
            output_schema=output_schema,
            handoffs=handoffs,
            previous_response_id=previous_response_id,
            conversation_id=conversation_id,
            prompt=prompt,
        )
        started = time.perf_counter()
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
        duration_ms = round((time.perf_counter() - started) * 1000, 3)
        self.call_durations_ms.append(duration_ms)
        self.log.write(
            "assistant",
            case_id=self.case_id,
            run=self.run,
            turn=self.turn,
            duration_ms=duration_ms,
            message={
                "role": "assistant",
                "content": visible_model_blocks(response.output),
            },
            response_id=response.response_id,
            request_id=response.request_id,
            usage=response.usage,
            raw_usage=response.raw_usage,
        )
        return response


class TranscriptHooks(RunHooks):
    def __init__(self, log):
        self.log = log
        self.case_id = None
        self.run = None
        self.tool_started = {}

    def begin_case(self, case_id, run):
        self.case_id = case_id
        self.run = run
        self.tool_started = {}

    @staticmethod
    def context_value(context, name):
        return getattr(context, name, None)

    async def on_tool_start(self, context, agent, tool):
        call_id = self.context_value(context, "tool_call_id")
        tool_name = self.context_value(context, "tool_name") or getattr(
            tool, "name", type(tool).__name__
        )
        arguments = self.context_value(context, "tool_arguments")
        self.tool_started[call_id or tool_name] = time.perf_counter()
        self.log.write(
            "harness",
            subtype="tool_dispatch",
            case_id=self.case_id,
            run=self.run,
            tool_use_id=call_id,
            name=tool_name,
            input=arguments,
        )

    async def on_tool_end(self, context, agent, tool, result):
        call_id = self.context_value(context, "tool_call_id")
        tool_name = self.context_value(context, "tool_name") or getattr(
            tool, "name", type(tool).__name__
        )
        started = self.tool_started.pop(call_id or tool_name, None)
        duration_ms = (
            round((time.perf_counter() - started) * 1000, 3)
            if started is not None
            else None
        )
        is_error = bool(
            getattr(result, "isError", False)
            or getattr(result, "is_error", False)
        )
        self.log.write(
            "user",
            case_id=self.case_id,
            run=self.run,
            message={
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": call_id,
                        "name": tool_name,
                        "content": result,
                        "is_error": is_error,
                        "duration_ms": duration_ms,
                    }
                ],
            },
        )


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
        raise RuntimeError(
            f"Model {OLLAMA_MODEL} is not installed; run: ollama pull {OLLAMA_MODEL}"
        )

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


def direct_result(case):
    return case["function"](db_path=DATABASE_PATH, **case["arguments"])


def parse_arguments(arguments):
    if isinstance(arguments, dict):
        return arguments
    if isinstance(arguments, str):
        return json.loads(arguments)
    raise ValueError("Tool arguments are not a JSON object")


def canonical_arguments(tool_name, arguments):
    normalized = json_safe(arguments)
    if not isinstance(normalized, dict):
        return normalized
    normalized = {
        key: value for key, value in normalized.items() if value is not None
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


def trace_items(result):
    return json_safe(result.to_input_list())


def extract_tool_activity(trace):
    calls = []
    outputs = {}
    for item in trace:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "function_call":
            try:
                arguments = parse_arguments(item.get("arguments", {}))
                argument_error = None
            except (TypeError, ValueError, json.JSONDecodeError) as error:
                arguments = None
                argument_error = str(error)
            calls.append(
                {
                    "call_id": item.get("call_id"),
                    "name": item.get("name"),
                    "arguments": arguments,
                    "raw_arguments": item.get("arguments"),
                    "argument_error": argument_error,
                }
            )
        elif item.get("type") == "function_call_output":
            outputs[item.get("call_id")] = item.get("output")
    for call in calls:
        call["raw_output"] = outputs.get(call["call_id"])
    return calls


def decode_tool_output(output):
    value = output
    for _ in range(4):
        if isinstance(value, str):
            value = json.loads(value)
            continue
        if isinstance(value, dict) and "result" in value:
            value = value["result"]
            continue
        if isinstance(value, dict) and "text" in value:
            value = value["text"]
            continue
        if isinstance(value, list) and all(
            isinstance(item, dict) and "text" in item for item in value
        ):
            decoded = [decode_tool_output(item["text"]) for item in value]
            return decoded[0] if len(decoded) == 1 else decoded
        return value
    return value


def normalized_text(value):
    return re.sub(r"\s+", " ", str(value).lower()).strip()


def numbers_in(value):
    cleaned = str(value).replace(",", "")
    return [float(number) for number in re.findall(r"-?\d+(?:\.\d+)?", cleaned)]


def has_number(value, expected):
    tolerance = 1e-8 if isinstance(expected, float) else 0
    return any(abs(number - float(expected)) <= tolerance for number in numbers_in(value))


def candidate_lines(answer):
    return [line for line in str(answer).splitlines() if line.strip()]


def line_has_fact(lines, labels, values):
    normalized_labels = [normalized_text(label) for label in labels]
    for line in lines:
        normalized_line = normalized_text(line)
        if not normalized_labels and all(has_number(line, value) for value in values):
            return True
        clauses = re.split(r",(?!\d)|;|\s+and\s+", normalized_line)
        for clause in clauses:
            if all(label in clause for label in normalized_labels) and all(
                has_number(clause, value) for value in values
            ):
                return True
    return False


def grade_answer(case, result, answer):
    lines = candidate_lines(answer)
    missing = []
    kind = case["answer_kind"]

    if kind == "summary":
        facts = (
            (["collision"], [result["total_collisions"]], "total_collisions"),
            (["fatal"], [result["total_fatalities"]], "total_fatalities"),
            (["injur"], [result["total_injuries"]], "total_injuries"),
        )
    elif kind == "temporal":
        facts = [
            ([row["year"]], [row["collision_count"]], f"year:{row['year']}")
            for row in result
        ]
    elif kind == "severity":
        facts = [
            (
                [row["severity"]],
                [row["collision_count"]],
                f"severity:{row['severity']}",
            )
            for row in result
        ]
    elif kind == "collision_type":
        facts = [
            (
                [row["collision_type"]],
                [row["collision_count"]],
                f"collision_type:{row['collision_type']}",
            )
            for row in result
        ]
    else:
        facts = [
            (
                [],
                [
                    row["latitude_cell"],
                    row["longitude_cell"],
                    row["collision_count"],
                ],
                f"hotspot:{row['latitude_cell']},{row['longitude_cell']}",
            )
            for row in result
        ]

    for labels, values, description in facts:
        if not line_has_fact(lines, labels, values):
            missing.append(description)
    return not missing, missing


def status(passed):
    return "Pass" if passed else "Fail"


def percentage(passed, total):
    return f"{passed}/{total} ({passed / total * 100:.0f}%)"


def write_report(rows):
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = REPORT_PATH.with_name(
        f".{REPORT_PATH.name}.{uuid.uuid4().hex}.tmp"
    )
    with temporary_path.open("w", encoding="utf-8") as output:
        output.write("# Single-Turn Conversational Accuracy\n\n")
        output.write(
            f"Model: `{OLLAMA_MODEL}` · Database: full DuckDB · "
            f"Cases: {len(TEST_CASES)} · Runs per case: {RUNS_PER_CASE} · "
            "Independent single-turn prompts\n\n"
        )
        output.write(
            "| Query | Variant | Tool | Arguments | Result | Required facts | Overall |\n"
        )
        output.write("|---|---|---:|---:|---:|---:|---:|\n")
        for case in TEST_CASES:
            case_rows = [row for row in rows if row["case_id"] == case["id"]]
            count = len(case_rows)
            output.write(
                f"| {case['query']} | {case['variant']} | "
                f"{sum(row['tool'] for row in case_rows)}/{count} | "
                f"{sum(row['arguments'] for row in case_rows)}/{count} | "
                f"{sum(row['result'] for row in case_rows)}/{count} | "
                f"{sum(row['answer'] for row in case_rows)}/{count} | "
                f"{sum(row['overall'] for row in case_rows)}/{count} |\n"
            )

        total = len(rows)
        output.write(
            f"| **Overall** | **{total} runs** | "
            f"**{percentage(sum(row['tool'] for row in rows), total)}** | "
            f"**{percentage(sum(row['arguments'] for row in rows), total)}** | "
            f"**{percentage(sum(row['result'] for row in rows), total)}** | "
            f"**{percentage(sum(row['answer'] for row in rows), total)}** | "
            f"**{percentage(sum(row['overall'] for row in rows), total)}** |\n"
        )

        output.write(
            "\nTool selection passes only when exactly one expected tool is called. "
            "Arguments are compared semantically with documented MCP defaults. "
            "Required facts pass only when each expected label/value pair appears "
            "in the same output clause. Free-form explanatory prose is not graded.\n\n"
        )
        llm_calls = sum(row["llm_calls"] for row in rows)
        llm_durations = [
            duration
            for row in rows
            for duration in row["llm_durations_ms"]
        ]
        output.write(
            f"Actual model usage: **{llm_calls} LLM calls** across {len(rows)} "
            f"agent runs; mean **{sum(llm_durations) / len(llm_durations):.1f} ms "
            f"per LLM call**. See `agent.log` for the complete audit trail.\n\n"
        )
        output.write(
            "The production model sampling configuration is unchanged. Results "
            "can vary between runs because model generation is nondeterministic; "
            "three independent runs per prompt expose that variability instead "
            "of presenting a seeded evaluation as production behavior.\n"
        )
    os.replace(temporary_path, REPORT_PATH)


async def evaluate_cases(log):
    environment = os.environ.copy()
    environment["COLLISIONS_DB_PATH"] = str(DATABASE_PATH)
    server_params = {
        "command": sys.executable,
        "args": ["-m", "src.mcp_server"],
        "cwd": str(PROJECT_ROOT),
        "env": environment,
    }
    rows = []
    async with AsyncOpenAI(
        base_url=f"{OLLAMA_URL}/v1", api_key="ollama"
    ) as local_client:
        model = LoggedChatModel(
            log=log,
            model=OLLAMA_MODEL,
            openai_client=local_client,
        )
        async with MCPServerStdio(
            name="Collision Analytics",
            params=server_params,
            cache_tools_list=True,
            client_session_timeout_seconds=30,
        ) as server:
            mcp_tools = await server.list_tools()
            log.write(
                "system",
                subtype="mcp_ready",
                server="Collision Analytics",
                tools=mcp_tools,
            )
            agent = Agent(
                name="Collision Analytics Assistant",
                instructions=AGENT_INSTRUCTIONS,
                model=model,
                mcp_servers=[server],
                mcp_config={"convert_schemas_to_strict": True},
            )
            hooks = TranscriptHooks(log)

            for case in TEST_CASES:
                expected_result = direct_result(case)
                for run in range(1, RUNS_PER_CASE + 1):
                    log.write(
                        "harness",
                        subtype="case_start",
                        case_id=case["id"],
                        run=run,
                        query=case["query"],
                        variant=case["variant"],
                        expected_tool=case["tool"],
                        expected_arguments=case["arguments"],
                        expected_result=expected_result,
                    )
                    log.write(
                        "user",
                        case_id=case["id"],
                        run=run,
                        message={
                            "role": "user",
                            "content": [
                                {"type": "text", "text": case["prompt"]}
                            ],
                        },
                    )
                    model.begin_case(case["id"], run)
                    hooks.begin_case(case["id"], run)
                    started = time.perf_counter()
                    try:
                        result = await Runner.run(
                            agent,
                            [{"role": "user", "content": case["prompt"]}],
                            max_turns=4,
                            hooks=hooks,
                        )
                        trace = trace_items(result)
                        calls = extract_tool_activity(trace)
                        tool_pass = (
                            len(calls) == 1
                            and calls[0]["name"] == case["tool"]
                        )
                        actual_arguments = (
                            calls[0]["arguments"] if len(calls) == 1 else None
                        )
                        arguments_pass = tool_pass and canonical_arguments(
                            case["tool"], actual_arguments
                        ) == canonical_arguments(case["tool"], case["arguments"])

                        actual_result = None
                        result_error = None
                        if len(calls) == 1 and calls[0]["raw_output"] is not None:
                            try:
                                actual_result = decode_tool_output(
                                    calls[0]["raw_output"]
                                )
                            except (
                                TypeError,
                                ValueError,
                                json.JSONDecodeError,
                            ) as error:
                                result_error = str(error)
                        result_pass = tool_pass and actual_result == expected_result
                        answer_pass, missing_facts = grade_answer(
                            case, expected_result, result.final_output
                        )
                        overall = all(
                            (tool_pass, arguments_pass, result_pass, answer_pass)
                        )
                        row = {
                            "case_id": case["id"],
                            "query": case["query"],
                            "variant": case["variant"],
                            "run": run,
                            "tool": tool_pass,
                            "arguments": arguments_pass,
                            "result": result_pass,
                            "answer": answer_pass,
                            "overall": overall,
                            "llm_calls": len(model.call_durations_ms),
                            "llm_durations_ms": list(model.call_durations_ms),
                        }
                        rows.append(row)
                        log.write(
                            "result",
                            subtype="case_result",
                            case_id=case["id"],
                            run=run,
                            duration_ms=round(
                                (time.perf_counter() - started) * 1000, 3
                            ),
                            num_turns=len(result.raw_responses),
                            result=result.final_output,
                            is_error=False,
                            result_decode_error=result_error,
                            missing_answer_facts=missing_facts,
                            grades={
                                key: row[key]
                                for key in (
                                    "tool",
                                    "arguments",
                                    "result",
                                    "answer",
                                    "overall",
                                )
                            },
                            llm_calls=row["llm_calls"],
                            llm_durations_ms=row["llm_durations_ms"],
                        )
                    except Exception as error:
                        row = {
                            "case_id": case["id"],
                            "query": case["query"],
                            "variant": case["variant"],
                            "run": run,
                            "tool": False,
                            "arguments": False,
                            "result": False,
                            "answer": False,
                            "overall": False,
                            "llm_calls": len(model.call_durations_ms),
                            "llm_durations_ms": list(model.call_durations_ms),
                        }
                        rows.append(row)
                        log.write(
                            "result",
                            subtype="case_error",
                            case_id=case["id"],
                            run=run,
                            duration_ms=round(
                                (time.perf_counter() - started) * 1000, 3
                            ),
                            result=None,
                            is_error=True,
                            error_type=type(error).__name__,
                            error=str(error),
                            grades={
                                key: row[key]
                                for key in (
                                    "tool",
                                    "arguments",
                                    "result",
                                    "answer",
                                    "overall",
                                )
                            },
                            llm_calls=row["llm_calls"],
                            llm_durations_ms=row["llm_durations_ms"],
                        )
    return rows


async def run_evaluation(log):
    if not DATABASE_PATH.exists():
        raise FileNotFoundError(f"Database not found: {DATABASE_PATH}")
    connection = duckdb.connect(str(DATABASE_PATH), read_only=True)
    try:
        row_count = connection.execute("SELECT COUNT(*) FROM collisions").fetchone()[0]
    finally:
        connection.close()

    log.write(
        "system",
        subtype="init",
        model=OLLAMA_MODEL,
        harness="openai-agents",
        ollama_url=OLLAMA_URL,
        database_path=DATABASE_PATH,
        database_rows=row_count,
        mcp_command=[sys.executable, "-m", "src.mcp_server"],
        cwd=PROJECT_ROOT,
        test_count=len(TEST_CASES),
        runs_per_case=RUNS_PER_CASE,
        agent_instructions=AGENT_INSTRUCTIONS.strip(),
    )
    rows = await evaluate_cases(log)
    write_report(rows)
    log.write(
        "result",
        subtype="run_summary",
        cases=len(TEST_CASES),
        agent_runs=len(rows),
        llm_calls=sum(row["llm_calls"] for row in rows),
        tool_passes=sum(row["tool"] for row in rows),
        argument_passes=sum(row["arguments"] for row in rows),
        result_passes=sum(row["result"] for row in rows),
        answer_passes=sum(row["answer"] for row in rows),
        overall_passes=sum(row["overall"] for row in rows),
        report_path=REPORT_PATH,
    )


def main():
    set_tracing_disabled(True)
    log = AgentLog(LOG_PATH)
    runtime = None
    completed = False
    try:
        runtime = start_ollama()
        asyncio.run(run_evaluation(log))
        completed = True
    except Exception as error:
        log.write(
            "result",
            subtype="run_error",
            is_error=True,
            error_type=type(error).__name__,
            error=str(error),
        )
        raise
    finally:
        stop_ollama(runtime)
        log.close(commit=completed)


if __name__ == "__main__":
    main()
