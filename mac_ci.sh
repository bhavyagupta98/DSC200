#!/usr/bin/env bash

set -Eeuo pipefail

PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

if [[ "$(uname -s)" != "Darwin" ]]; then
    printf 'mac_ci.sh must be run on macOS.\n' >&2
    exit 1
fi

export RUNNER_LABEL="macOS CI"
exec bash "${PROJECT_ROOT}/colab_ci.sh" "$@"
