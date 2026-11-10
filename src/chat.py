import asyncio
import atexit
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

import streamlit as st
from agents import Agent, OpenAIChatCompletionsModel, Runner, set_tracing_disabled
from agents.mcp import MCPServerStdio
from openai import AsyncOpenAI


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3:4b-q4_K_M")

AGENT_INSTRUCTIONS = """
You answer questions about the SANDAG collision dataset using the MCP tools.
Always use an MCP tool for collision facts and never invent numbers.
Call exactly one appropriate tool per question unless the user explicitly asks
for separate analyses. Do not retry a successful tool call. For totals or a
single year, use get_summary_statistics. Every filter must be nested inside the
tool's filters argument; never pass a filter at the top level. For example, a
2020 query uses filters={"start_year": 2020, "end_year": 2020}. Use normalized
severity "Fatal" for fatal-collision filters and alcohol_involved=true for
alcohol questions. For hotspots, always use get_geographic_hotspots with
grid_size=0.01 and the requested limit unless the user explicitly specifies
another grid size. Explain that hotspots show historical collision frequency,
not risk. Keep answers concise and include the relevant numbers.
"""


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


def stop_ollama(runtime):
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


@st.cache_resource
def start_ollama():
    process = None
    if not ollama_is_running():
        executable = shutil.which("ollama")
        if executable is None:
            raise RuntimeError("Ollama is not installed or is not on PATH.")
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
                raise RuntimeError("Ollama exited before it became ready.")
            time.sleep(0.25)
        else:
            process.terminate()
            raise RuntimeError("Ollama did not become ready within 15 seconds.")

    try:
        installed = {
            model["name"] for model in ollama_request("/api/tags").get("models", [])
        }
        if OLLAMA_MODEL not in installed:
            raise RuntimeError(
                f"Model {OLLAMA_MODEL} is not installed. Run: "
                f"ollama pull {OLLAMA_MODEL}"
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
    except Exception:
        if process is not None and process.poll() is None:
            process.terminate()
        raise

    runtime = {"process": process, "unload_model": unload_model}
    atexit.register(stop_ollama, runtime)
    return runtime


async def ask_agent(question, conversation):
    server_params = {
        "command": sys.executable,
        "args": ["-m", "src.mcp_server"],
        "cwd": str(PROJECT_ROOT),
    }
    async with AsyncOpenAI(
        base_url=f"{OLLAMA_URL}/v1", api_key="ollama"
    ) as local_client:
        model = OpenAIChatCompletionsModel(
            model=OLLAMA_MODEL,
            openai_client=local_client,
        )
        async with MCPServerStdio(
            name="Collision Analytics",
            params=server_params,
            cache_tools_list=True,
            client_session_timeout_seconds=30,
        ) as server:
            agent = Agent(
                name="Collision Analytics Assistant",
                instructions=AGENT_INSTRUCTIONS,
                model=model,
                mcp_servers=[server],
                mcp_config={"convert_schemas_to_strict": True},
            )
            agent_input = conversation + [{"role": "user", "content": question}]
            result = await Runner.run(agent, agent_input, max_turns=4)
            return result.final_output, result.to_input_list()


st.set_page_config(page_title="Collision Analytics Chat", page_icon="🚗")
st.title("Collision Analytics Chat")
st.caption(
    f"Local model: {OLLAMA_MODEL}. Ask about totals, trends, severity, or hotspots."
)

set_tracing_disabled(True)

try:
    with st.spinner(f"Starting {OLLAMA_MODEL}..."):
        start_ollama()
except Exception as error:
    st.error(str(error))
    st.code(f"ollama pull {OLLAMA_MODEL}")
    st.stop()

if "messages" not in st.session_state:
    st.session_state.messages = []
if "agent_input" not in st.session_state:
    st.session_state.agent_input = []

if st.sidebar.button("Clear conversation"):
    st.session_state.messages = []
    st.session_state.agent_input = []
    st.rerun()

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if question := st.chat_input("Ask a collision analytics question"):
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        with st.spinner("Analyzing collisions..."):
            try:
                answer, conversation = asyncio.run(
                    ask_agent(question, st.session_state.agent_input)
                )
                st.markdown(answer)
                st.session_state.agent_input = conversation
                st.session_state.messages.append(
                    {"role": "assistant", "content": answer}
                )
            except Exception as error:
                st.error(f"Unable to complete the request: {error}")
