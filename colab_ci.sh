#!/usr/bin/env bash

set -Eeuo pipefail
export PYTHONUNBUFFERED=1
export MPLBACKEND=Agg
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1

PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
OLLAMA_MODEL_NAME="${OLLAMA_MODEL:-qwen3:4b-q4_K_M}"
RUNNER_LABEL="${RUNNER_LABEL:-Colab CI}"
VENV_PATH="${VENV_PATH:-${PROJECT_ROOT}/.venv}"
OLLAMA_LOG_PATH="${PROJECT_ROOT}/evaluation/ollama-ci.log"
OLLAMA_RUNTIME_PATH="${PROJECT_ROOT}/.ollama-runtime"
OLLAMA_SERVER_PID=""
ACTIVE_COMMAND_PID=""
RUNNER_PYTHON=""
NVIDIA_GPU_AVAILABLE=0
NVIDIA_GPU_NAME=""

cleanup() {
    if [[ -n "${ACTIVE_COMMAND_PID}" ]] && \
        kill -0 "${ACTIVE_COMMAND_PID}" 2>/dev/null; then
        kill "${ACTIVE_COMMAND_PID}"
        wait "${ACTIVE_COMMAND_PID}" 2>/dev/null || true
    fi
    if [[ -n "${OLLAMA_SERVER_PID}" ]] && kill -0 "${OLLAMA_SERVER_PID}" 2>/dev/null; then
        kill "${OLLAMA_SERVER_PID}"
        wait "${OLLAMA_SERVER_PID}" 2>/dev/null || true
    fi
}
trap cleanup EXIT

report_failure() {
    local exit_code="$?"
    printf '\nERROR: colab_ci.sh failed at line %s with exit code %s.\n' \
        "${BASH_LINENO[0]}" "${exit_code}" >&2
    exit "${exit_code}"
}
trap report_failure ERR

step() {
    printf '\n==> %s\n' "$1"
}

run_with_progress() {
    local label="$1"
    local elapsed_seconds=0
    local command_status=0
    shift

    "$@" &
    ACTIVE_COMMAND_PID="$!"
    while kill -0 "${ACTIVE_COMMAND_PID}" 2>/dev/null; do
        sleep 1
        elapsed_seconds=$((elapsed_seconds + 1))
        if (( elapsed_seconds % 30 == 0 )); then
            printf '    %s still running (%ss elapsed)\n' \
                "${label}" "${elapsed_seconds}"
        fi
    done
    if wait "${ACTIVE_COMMAND_PID}"; then
        command_status=0
    else
        command_status="$?"
    fi
    ACTIVE_COMMAND_PID=""
    return "${command_status}"
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
if [[ "$(uname -s)" == "Linux" ]]; then
    if [[ ! -x "${VENV_PATH}/bin/python" ]] || \
        ! "${VENV_PATH}/bin/python" -m pip --version >/dev/null 2>&1; then
        "${PYTHON_BIN}" -m pip install --quiet virtualenv
        "${PYTHON_BIN}" -m virtualenv --clear "${VENV_PATH}"
    fi
    RUNNER_PYTHON="${VENV_PATH}/bin/python"
    printf 'Using the project environment: %s\n' "${VENV_PATH}"
else
    if [[ ! -x "${VENV_PATH}/bin/python" ]]; then
        "${PYTHON_BIN}" -m venv "${VENV_PATH}"
    fi
    RUNNER_PYTHON="${VENV_PATH}/bin/python"
fi
"${RUNNER_PYTHON}" -m pip install --upgrade pip
"${RUNNER_PYTHON}" -m pip install -r requirements.txt

export OLLAMA_MODEL="${OLLAMA_MODEL_NAME}"
export MPLCONFIGDIR="${PROJECT_ROOT}/.cache/matplotlib"
mkdir -p "${MPLCONFIGDIR}"

step "Running the test suite"
"${RUNNER_PYTHON}" -u -c \
    'import sys; print(f"Python preflight passed: {sys.executable}", flush=True)'
"${RUNNER_PYTHON}" -u -m pytest tests -vv -s --maxfail=1 \
    -o faulthandler_timeout=30
printf 'Test suite completed successfully.\n'

step "Generating filter-scaling latency artifacts"
run_with_progress "Filter-scaling benchmark" \
    "${RUNNER_PYTHON}" -u evaluation/benchmark_filter_latency.py \
        --rebuild-snapshots

step "Installing Ollama when needed"
if [[ -x "${OLLAMA_RUNTIME_PATH}/bin/ollama" ]]; then
    export PATH="${OLLAMA_RUNTIME_PATH}/bin:${PATH}"
fi
if ! command -v ollama >/dev/null 2>&1; then
    if ! command -v zstd >/dev/null 2>&1; then
        if ! command -v apt-get >/dev/null 2>&1; then
            printf 'Ollama requires zstd, and apt-get is unavailable.\n' >&2
            exit 1
        fi
        apt-get update -qq
        apt-get install -y -qq zstd
    fi
    if [[ "$(uname -s)" == "Linux" ]]; then
        if [[ "$(uname -m)" != "x86_64" ]]; then
            printf 'The Colab runner expects an x86_64 runtime.\n' >&2
            exit 1
        fi
        OLLAMA_ARCHIVE="$(mktemp --suffix=.tar.zst)"
        mkdir -p "${OLLAMA_RUNTIME_PATH}"
        curl -fL --progress-bar \
            https://ollama.com/download/ollama-linux-amd64.tar.zst \
            -o "${OLLAMA_ARCHIVE}"
        tar --zstd -xf "${OLLAMA_ARCHIVE}" -C "${OLLAMA_RUNTIME_PATH}"
        rm -f "${OLLAMA_ARCHIVE}"
        export PATH="${OLLAMA_RUNTIME_PATH}/bin:${PATH}"
    else
        OLLAMA_INSTALLER="$(mktemp)"
        curl -fsSL https://ollama.com/install.sh -o "${OLLAMA_INSTALLER}"
        sh "${OLLAMA_INSTALLER}"
        rm -f "${OLLAMA_INSTALLER}"
    fi
fi
if ! command -v ollama >/dev/null 2>&1; then
    printf 'Ollama installation completed without an executable on PATH.\n' >&2
    exit 1
fi

step "Detecting accelerator hardware"
if command -v nvidia-smi >/dev/null 2>&1 && \
    nvidia-smi --query-gpu=name --format=csv,noheader >/dev/null 2>&1; then
    NVIDIA_GPU_AVAILABLE=1
    NVIDIA_GPU_NAME="$(nvidia-smi --query-gpu=name --format=csv,noheader | sed -n '1p')"
    export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}"
    printf 'NVIDIA GPU detected: '
    nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
    printf 'CUDA_VISIBLE_DEVICES=%s\n' "${CUDA_VISIBLE_DEVICES}"
else
    printf 'No NVIDIA GPU detected; Ollama may use CPU or another accelerator.\n'
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

step "Loading model and verifying accelerator use"
curl -fsS http://127.0.0.1:11434/api/generate \
    -H 'Content-Type: application/json' \
    -d "{\"model\":\"${OLLAMA_MODEL_NAME}\",\"prompt\":\"\",\"keep_alive\":-1}" \
    >/dev/null
OLLAMA_PROCESS_INFO="$(curl -fsS http://127.0.0.1:11434/api/ps)"
LOADED_MODEL_COUNT="$(printf '%s' "${OLLAMA_PROCESS_INFO}" | \
    "${RUNNER_PYTHON}" -c \
    'import json, sys; print(len(json.load(sys.stdin).get("models", [])))')"
MODEL_VRAM_BYTES="$(printf '%s' "${OLLAMA_PROCESS_INFO}" | \
    "${RUNNER_PYTHON}" -c \
    'import json, sys; print(sum(m.get("size_vram", 0) for m in json.load(sys.stdin).get("models", [])))')"
if [[ "${LOADED_MODEL_COUNT}" -eq 0 ]]; then
    printf 'Ollama did not report a loaded model after preloading.\n' >&2
    exit 1
fi
if [[ "${NVIDIA_GPU_AVAILABLE}" -eq 1 && "${MODEL_VRAM_BYTES}" -eq 0 ]]; then
    printf 'A NVIDIA GPU is available, but Ollama loaded the model on CPU.\n' >&2
    printf 'See %s for GPU discovery details.\n' "${OLLAMA_LOG_PATH}" >&2
    exit 1
fi
if [[ "${MODEL_VRAM_BYTES}" -gt 0 ]]; then
    MODEL_VRAM_GIB="$("${RUNNER_PYTHON}" -c \
        'import sys; print(f"{int(sys.argv[1]) / 2**30:.2f}")' \
        "${MODEL_VRAM_BYTES}")"
    printf '\n*** OLLAMA EXECUTION DEVICE: GPU ***\n'
    if [[ -n "${NVIDIA_GPU_NAME}" ]]; then
        printf 'GPU: %s\n' "${NVIDIA_GPU_NAME}"
    fi
    printf 'Model VRAM in use: %s GiB\n\n' "${MODEL_VRAM_GIB}"
else
    printf '\n*** OLLAMA EXECUTION DEVICE: CPU ***\n'
    printf 'WARNING: Model evaluations will be slow.\n\n'
fi

step "Generating MCP and end-to-end agent latency artifacts"
run_with_progress "MCP latency benchmark" \
    "${RUNNER_PYTHON}" -u evaluation/benchmark_mcp_latency.py

step "Generating conversational accuracy artifacts"
run_with_progress "Conversational accuracy evaluation" \
    "${RUNNER_PYTHON}" -u evaluation/benchmark_conversational_accuracy.py

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

printf '\n%s completed successfully.\n' "${RUNNER_LABEL}"
