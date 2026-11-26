#!/usr/bin/env bash

set -Eeuo pipefail

PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
OLLAMA_MODEL_NAME="${OLLAMA_MODEL:-qwen3:4b-q4_K_M}"
VENV_PATH="${VENV_PATH:-${PROJECT_ROOT}/.venv}"
OLLAMA_LOG_PATH="${PROJECT_ROOT}/evaluation/ollama-ci.log"
OLLAMA_SERVER_PID=""
RUNNER_PYTHON=""

cleanup() {
    if [[ -n "${OLLAMA_SERVER_PID}" ]] && kill -0 "${OLLAMA_SERVER_PID}" 2>/dev/null; then
        kill "${OLLAMA_SERVER_PID}"
        wait "${OLLAMA_SERVER_PID}" 2>/dev/null || true
    fi
}
trap cleanup EXIT

step() {
    printf '\n==> %s\n' "$1"
}

require_file() {
    if [[ ! -f "$1" ]]; then
        printf 'Required file is missing: %s\n' "$1" >&2
        exit 1
    fi
}

cd "${PROJECT_ROOT}"

step "Validating repository inputs"
require_file "requirements.txt"
require_file "data/collisions.duckdb"
require_file "data/processed/collisions.parquet"
require_file "evaluation/benchmark_filter_latency.py"
require_file "evaluation/benchmark_mcp_latency.py"
require_file "evaluation/benchmark_conversational_accuracy.py"

step "Preparing the Python environment"
if [[ "${PROJECT_ROOT}" == /content/* ]]; then
    RUNNER_PYTHON="$(command -v "${PYTHON_BIN}")"
    printf 'Using the isolated Colab runtime: %s\n' "${RUNNER_PYTHON}"
else
    if [[ ! -x "${VENV_PATH}/bin/python" ]]; then
        "${PYTHON_BIN}" -m venv "${VENV_PATH}"
    fi
    RUNNER_PYTHON="${VENV_PATH}/bin/python"
fi
"${RUNNER_PYTHON}" -m pip install --upgrade pip
"${RUNNER_PYTHON}" -m pip install -r requirements.txt

step "Installing Ollama when needed"
if ! command -v ollama >/dev/null 2>&1; then
    OLLAMA_INSTALLER="$(mktemp)"
    curl -fsSL https://ollama.com/install.sh -o "${OLLAMA_INSTALLER}"
    sh "${OLLAMA_INSTALLER}"
    rm -f "${OLLAMA_INSTALLER}"
fi

step "Starting Ollama"
if ! curl -fsS http://127.0.0.1:11434/api/version >/dev/null 2>&1; then
    ollama serve >"${OLLAMA_LOG_PATH}" 2>&1 &
    OLLAMA_SERVER_PID="$!"
    for _ in $(seq 1 60); do
        if curl -fsS http://127.0.0.1:11434/api/version >/dev/null 2>&1; then
            break
        fi
        if ! kill -0 "${OLLAMA_SERVER_PID}" 2>/dev/null; then
            printf 'Ollama exited during startup. See %s\n' "${OLLAMA_LOG_PATH}" >&2
            exit 1
        fi
        sleep 1
    done
fi
if ! curl -fsS http://127.0.0.1:11434/api/version >/dev/null 2>&1; then
    printf 'Ollama did not become ready within 60 seconds.\n' >&2
    exit 1
fi

step "Downloading ${OLLAMA_MODEL_NAME}"
ollama pull "${OLLAMA_MODEL_NAME}"
export OLLAMA_MODEL="${OLLAMA_MODEL_NAME}"
export MPLCONFIGDIR="${PROJECT_ROOT}/.cache/matplotlib"
mkdir -p "${MPLCONFIGDIR}"

step "Running the test suite"
"${RUNNER_PYTHON}" -m pytest -q

step "Generating filter-scaling latency artifacts"
"${RUNNER_PYTHON}" evaluation/benchmark_filter_latency.py \
    --rebuild-snapshots

step "Generating MCP and end-to-end agent latency artifacts"
"${RUNNER_PYTHON}" evaluation/benchmark_mcp_latency.py

step "Generating conversational accuracy artifacts"
"${RUNNER_PYTHON}" evaluation/benchmark_conversational_accuracy.py

step "Validating generated artifacts"
GENERATED_ARTIFACTS=(
    "evaluation/filter_latency_summary.md"
    "evaluation/filter_latency_trends.png"
    "evaluation/mcp_latency_summary.md"
    "evaluation/mcp_latency_comparison.png"
    "evaluation/conversational_accuracy_summary.md"
    "evaluation/agent.log"
)
for artifact in "${GENERATED_ARTIFACTS[@]}"; do
    if [[ ! -s "${artifact}" ]]; then
        printf 'Expected artifact is missing or empty: %s\n' "${artifact}" >&2
        exit 1
    fi
    printf '  %s\n' "${artifact}"
done

printf '\nColab CI completed successfully.\n'
