# SANDAG Collision Analytics

This project cleans SANDAG collision data, stores it in DuckDB, and provides a
Streamlit dashboard, reusable analytics functions, an MCP server, and an
optional local-model chat interface. The repository includes the generated
database at `data/collisions.duckdb`, so normal setup does not require rebuilding
the data.

## Contents

- [macOS setup](#macos-setup)
- [Windows setup](#windows-setup)
- [CI and evaluation](#ci-and-evaluation)
- [Using the project](#using-the-project)
- [Rebuilding the data](#rebuilding-the-data)
- [macOS troubleshooting](#macos-troubleshooting)
- [Windows troubleshooting](#windows-troubleshooting)

## macOS setup

Run all commands from the repository root, which contains `README.md`.

### 1. Create the environment

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

### 2. Run the tests

```bash
.venv/bin/python -m pytest
```

### 3. Start the dashboard

```bash
.venv/bin/python -m streamlit run src/dashboard.py
```

Open `http://localhost:8501` if Streamlit does not open it automatically. The
dashboard uses the included DuckDB database and does not require Ollama, MCP, a
GPU, or an API key. Press `Ctrl+C` in the terminal to stop it.

### 4. Enable chat (optional)

Install Ollama and the local model once:

```bash
brew install ollama
ollama pull qwen3:4b-q4_K_M
```

Then start the dashboard with its chat page:

```bash
.venv/bin/python -m streamlit run src/dashboard.py -- --chat
```

The application starts `ollama serve` when needed and uses Apple Metal when it
is available. No OpenAI API key is required.

## Windows setup

Use PowerShell and run all commands from the repository root.

### 1. Create the environment

```powershell
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 2. Run the tests

```powershell
.venv\Scripts\python.exe -m pytest
```

### 3. Start the dashboard

```powershell
.venv\Scripts\python.exe -m streamlit run src\dashboard.py
```

Open `http://localhost:8501` if necessary. Keep PowerShell open while using the
dashboard and press `Ctrl+C` to stop it.

### 4. Enable chat (optional)

Install Ollama for Windows, then run:

```powershell
ollama pull qwen3:4b-q4_K_M
.venv\Scripts\python.exe -m streamlit run src\dashboard.py -- --chat
```

## CI and evaluation

The default CI command installs dependencies and runs the pytest suite only.
Add `--nfr` to also run the performance and conversational-accuracy evaluations
and regenerate the reports under `evaluation/`.

### macOS

```bash
# Tests only
./mac_ci.sh

# Tests and all NFR evaluations
./mac_ci.sh --nfr
```

### Google Colab

Select a GPU runtime for faster local-model evaluation, then run:

```python
!git clone --branch main --single-branch https://github.com/bhavyagupta98/DSC200.git /content/DSC200
%cd /content/DSC200

# Tests only
!bash colab_ci.sh

# Tests and all NFR evaluations
!bash colab_ci.sh --nfr
```

The NFR run:

- generates filter-latency reports across DuckDB data scales;
- compares direct backend and MCP latency;
- evaluates single-turn conversational accuracy;
- writes the model interaction audit trail to `evaluation/agent.log`; and
- validates that every expected report and plot was generated.

The model-backed evaluations use `qwen3:4b-q4_K_M` and may take several
minutes. The runner reports whether Ollama is using CPU or GPU and rejects a
silent CPU fallback when an NVIDIA GPU is available. Conversational accuracy
uses one independent run for each of 12 prompts, so its result can vary between
executions.

Windows does not have a dedicated CI wrapper. Run the PowerShell pytest command
from [Windows setup](#windows-setup), or use the Colab workflow for the complete
NFR evaluation.

## Using the project

### Query the analytics functions

Start a Python console with the virtual-environment interpreter:

```bash
# macOS
.venv/bin/python
```

```powershell
# Windows PowerShell
.venv\Scripts\python.exe
```

Example queries:

```python
from pprint import pprint
from src import analytics

pprint(analytics.summary_statistics())
pprint(analytics.summary_statistics({
    "start_year": 2020,
    "end_year": 2020,
    "severity": "Fatal",
}))
pprint(analytics.temporal_trends(
    "year", {"start_year": 2020, "end_year": 2023}
))
pprint(analytics.collision_type_distribution(
    {"start_year": 2023, "end_year": 2023}, limit=5
))
```

Supported filters are:

- years: `start_year`, `end_year` (2014 through 2023);
- dates: `start_date`, `end_date` in `YYYY-MM-DD` format;
- categories: `severity`, `weather`, `collision_type`, `weekday`, `location`;
- flags: `pedestrian_accident`, `bicycle_accident`, `motorcycle_accident`,
  `truck_accident`, `alcohol_involved`; and
- map bounds: `min_latitude`, `max_latitude`, `min_longitude`,
  `max_longitude`.

Run `analytics.filter_options()` to see valid category values.

### Inspect the MCP server

Install Node.js if needed, then start MCP Inspector from the repository root.

macOS:

```bash
npx @modelcontextprotocol/inspector .venv/bin/python -m src.mcp_server
```

Windows PowerShell:

```powershell
npx @modelcontextprotocol/inspector .venv\Scripts\python.exe -m src.mcp_server
```

Use `-m src.mcp_server`; running `python src/mcp_server.py` directly can break
package imports. The MCP server uses the included database and does not require
Ollama or an API key.

### Query DuckDB directly

```python
import duckdb

connection = duckdb.connect("data/collisions.duckdb", read_only=True)
row_count = connection.execute(
    "SELECT count(*) FROM collisions"
).fetchone()[0]
connection.close()
```

## Rebuilding the data

Rebuilding is optional because the processed Parquet file and DuckDB database
are included. The 155 MB source CSV is excluded from Git; its compressed copy,
`sandag_collisions_full.csv.gz`, is included.

Restore the CSV:

```bash
gzip -dk sandag_collisions_full.csv.gz
```

On Windows, use an archive tool that supports gzip and keep the original `.gz`
file. Then run the pipeline:

```bash
# macOS
.venv/bin/python collision_pipeline.py
```

```powershell
# Windows PowerShell
.venv\Scripts\python.exe collision_pipeline.py
```

The pipeline atomically replaces `data/processed/collisions.parquet` and
`data/collisions.duckdb`; repeated runs do not append duplicates. The restored
CSV has SHA-256 checksum
`0ed40cde74182e5e6f11eb98d95fc1e7369d55b4173e9d9fb4dd3f2692b0d975`.

## macOS troubleshooting

Confirm that the terminal is in the repository root and the environment works:

```bash
pwd
test -f README.md && echo "Repository root OK"
test -f data/collisions.duckdb && echo "Database found"
.venv/bin/python --version
.venv/bin/python -c "import duckdb, streamlit; print('Dependencies OK')"
```

If the virtual-environment interpreter is missing, repeat macOS setup step 1.
If port 8501 is busy, use another port:

```bash
.venv/bin/python -m streamlit run src/dashboard.py --server.port 8502
```

For chat problems, verify that Ollama and the model are available:

```bash
ollama --version
ollama list
curl http://127.0.0.1:11434/api/version
```

The NFR runner writes Ollama startup details to `evaluation/ollama-ci.log`.

## Windows troubleshooting

Confirm that PowerShell is in the repository root:

```powershell
Get-Location
Test-Path .\README.md
Test-Path .\src\dashboard.py
Test-Path .\data\collisions.duckdb
```

All three `Test-Path` commands should return `True`. Confirm Python and the
dependencies:

```powershell
py --version
.venv\Scripts\python.exe --version
.venv\Scripts\python.exe -c "import duckdb, streamlit; print('Dependencies OK')"
```

If the virtual-environment interpreter is missing or an import fails, repeat
Windows setup step 1. If port 8501 is busy, use:

```powershell
.venv\Scripts\python.exe -m streamlit run src\dashboard.py --server.port 8502
```

Then open `http://localhost:8502`. For chat problems, confirm that Ollama is
running and that `qwen3:4b-q4_K_M` appears in `ollama list`.
