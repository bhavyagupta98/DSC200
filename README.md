# SANDAG Collision Data

This project cleans the SANDAG collision CSV and stores the result in a
persistent DuckDB database. The generated database can be queried directly at
`data/collisions.duckdb`; application startup does not rebuild it.

Install dependencies:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Run the tests:

```bash
.venv/bin/python -m pytest
```

## Reproduce tests and evaluation reports in Google Colab

Use a GPU Colab runtime for substantially faster local-model evaluation. Run
this in one Colab cell, replacing the branch if needed:

```python
!git clone --branch main --single-branch https://github.com/bhavyagupta98/DSC200.git /content/DSC200
%cd /content/DSC200
!bash colab_ci.sh
```

The runner creates an isolated project environment using `virtualenv` on Colab
(or standard `venv` elsewhere), installs the pinned dependencies, `zstd`, and
Ollama, downloads `qwen3:4b-q4_K_M`, runs the test suite, and regenerates every
evaluation report, plot, and `evaluation/agent.log`. It exits with a nonzero
status if any stage or expected artifact fails. The two model-backed
evaluations can take several minutes, especially on a CPU-only runtime.

Run the one-time ingestion:

```bash
.venv/bin/python collision_pipeline.py
```

This creates `data/processed/collisions.parquet` and
`data/collisions.duckdb`. Rerunning the command atomically replaces the table
instead of appending duplicate records.

## Restore the raw CSV and rebuild

The 155 MB raw CSV is excluded by `.gitignore`. The repository includes the
same data as `sandag_collisions_full.csv.gz`, compressed to approximately 21 MB.
From a fresh clone, restore the ignored CSV while keeping the archive:

```bash
gzip -dk sandag_collisions_full.csv.gz
```

Then verify and rebuild the generated artifacts:

```bash
.venv/bin/python -m pytest
.venv/bin/python collision_pipeline.py
```

The decompressed source has SHA-256 checksum
`0ed40cde74182e5e6f11eb98d95fc1e7369d55b4173e9d9fb4dd3f2692b0d975`.

## Inspect the MCP server

From the project root, start MCP Inspector with:

```bash
npx @modelcontextprotocol/inspector .venv/bin/python -m src.mcp_server
```

`.venv/bin/python` is the path to the Python interpreter in this project's
virtual environment. If you use a different environment, replace it with that
environment's Python path. You can find the active interpreter with:

```bash
which python
```

In MCP Inspector's manual STDIO configuration, set the command to your Python
environment path and provide `-m` and `src.mcp_server` as separate arguments.

## Run the analytics dashboard

The dashboard uses Streamlit and the existing DuckDB database. It does not
require Ollama, MCP, a GPU, or an API key. From the project root on macOS or
Linux, run:

```bash
.venv/bin/python -m streamlit run src/dashboard.py
```

Streamlit prints a local URL, normally `http://localhost:8501`, and may open it
automatically in a browser. Stop the dashboard with `Ctrl+C` in the terminal.

Without `--chat`, the command continues to show only the analytics dashboard
and does not start Ollama.

## Enable the collision analytics chat page

The chat uses Streamlit, the OpenAI Agents SDK, the existing MCP server, and a
local Ollama model. It runs as a second page inside the dashboard and does not
require an OpenAI API key.

Install Ollama and download the quantized 4B model once:

```bash
brew install ollama
ollama pull qwen3:4b-q4_K_M
```

Then launch the dashboard with the chat page enabled:

```bash
.venv/bin/python -m streamlit run src/dashboard.py -- --chat
```

The app starts `ollama serve` when no server is already available, preloads the
model, and unloads it when the Streamlit process exits normally. If the app
started Ollama, it also stops that owned server. Closing only the browser tab
does not stop Streamlit; stop the terminal process with `Ctrl+C` to trigger
cleanup.

To use another installed model, set `OLLAMA_MODEL` before launch:

```bash
OLLAMA_MODEL=qwen3:1.7b .venv/bin/python -m streamlit run src/dashboard.py -- --chat
```

Query the existing database:

```python
import duckdb

connection = duckdb.connect("data/collisions.duckdb", read_only=True)
rows = connection.execute("SELECT count(*) FROM collisions").fetchone()[0]
connection.close()
```




######
######
######
######

## Windows quick start

Use PowerShell and run every command from the cloned project folder—the folder
that contains `README.md`. The database is already included, so there is no
need to rebuild or download the data.

### 1. Set up the project (first time only)

```powershell
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 2. Run the tests

```powershell
.venv\Scripts\python.exe -m pytest
```

Continue when the command finishes without failures.

### 3. Run the dashboard

```powershell
.venv\Scripts\python.exe -m streamlit run src\dashboard.py
```

The dashboard should open in a browser. If it does not, open
`http://localhost:8501` yourself. Keep PowerShell open while using the
dashboard, and press `Ctrl+C` there to stop it.

The dashboard does not require Ollama, MCP, a GPU, or an API key.

To include the local-model chat as a second page, use:

```powershell
.venv\Scripts\python.exe -m streamlit run src\dashboard.py -- --chat
```

### 4. Run queries using the existing analytics functions

The analytics functions read `data\collisions.duckdb` automatically. You do
not need to open DuckDB, write SQL, or modify any Python files.

#### Open the query console

Keep the dashboard running and open a **second PowerShell window**. In the new
window, use `cd` to enter the cloned `dsc200` folder. Then run:

```powershell
.venv\Scripts\python.exe
```

Python will display a `>>>` prompt. Enter these two lines one at a time. Do not
type the `>>>` characters.

```python
from pprint import pprint
from src import analytics
```

#### Example 1: totals for the complete dataset

At the `>>>` prompt, enter:

```python
pprint(analytics.summary_statistics())
```

Expected result:

```text
{'total_collisions': 239588,
 'total_fatalities': 2479,
 'total_injuries': 181254}
```

#### Example 2: fatal collisions in 2020

Enter these two lines one at a time:

```python
filters = {"start_year": 2020, "end_year": 2020, "severity": "Fatal"}
pprint(analytics.summary_statistics(filters))
```

Expected result:

```text
{'total_collisions': 262,
 'total_fatalities': 285,
 'total_injuries': 166}
```

To ask a different question, change the values in `filters`. For example, this
returns alcohol-related totals for 2022:

```python
filters = {"start_year": 2022, "end_year": 2022, "alcohol_involved": True}
pprint(analytics.summary_statistics(filters))
```

Expected result:

```text
{'total_collisions': 3393,
 'total_fatalities': 67,
 'total_injuries': 2371}
```

#### Other queries you can run

Copy one command at a time into the same Python console:

```python
# Show the valid severity, weather, collision type, weekday, and location values
pprint(analytics.filter_options())

# Show yearly collision totals from 2020 through 2023
pprint(analytics.temporal_trends("year", {"start_year": 2020, "end_year": 2023}))

# Show the severity breakdown for 2023
pprint(analytics.severity_distribution({"start_year": 2023, "end_year": 2023}))

# Show the five most common collision types for 2023
pprint(analytics.collision_type_distribution(
    {"start_year": 2023, "end_year": 2023}, limit=5
))

# Show the ten busiest geographic grid areas for 2023
pprint(analytics.geographic_hotspots({"start_year": 2023, "end_year": 2023}, limit=10))

# Group 2023 collisions by weather
pprint(analytics.aggregate_collisions("weather", {"start_year": 2023, "end_year": 2023}))
```

You can use the following names inside `filters`:

- Year range: `start_year`, `end_year` (2014 through 2023)
- Date range: `start_date`, `end_date` in `YYYY-MM-DD` format
- Categories: `severity`, `weather`, `collision_type`, `weekday`, `location`
- Yes/no filters: `pedestrian_accident`, `bicycle_accident`,
  `motorcycle_accident`, `truck_accident`, `alcohol_involved`
- Map area: `min_latitude`, `max_latitude`, `min_longitude`, `max_longitude`

Use `analytics.filter_options()` to find the exact spelling of category
values. Use `True` or `False` with a capital first letter for yes/no filters.
Multiple filters can be placed between the same `{}` braces and separated by
commas, as shown in the examples above.

When finished, close the Python query console with:

```python
exit()
```

### 5. Run MCP (optional)

Install Node.js first if you want to use MCP Inspector. Then run:

```powershell
npx @modelcontextprotocol/inspector .venv\Scripts\python.exe -m src.mcp_server
```

MCP uses the included database and does not require Ollama or an API key.

Always use `-m src.mcp_server`. Do not run `python src\mcp_server.py`; that can
cause `ModuleNotFoundError: No module named 'src'`.

### Optional chat page

The chat requires Ollama for Windows and the local model:

```powershell
ollama pull qwen3:4b-q4_K_M
.venv\Scripts\python.exe -m streamlit run src\dashboard.py -- --chat
```

### Windows troubleshooting

First, confirm that PowerShell is in the correct folder:

```powershell
Get-Location
Test-Path .\README.md
Test-Path .\src\dashboard.py
Test-Path .\data\collisions.duckdb
```

All three `Test-Path` commands should return `True`. If they do not, use `cd`
to enter the cloned project folder and try again.

Confirm that Python and the virtual environment work:

```powershell
py --version
.venv\Scripts\python.exe --version
.venv\Scripts\python.exe -c "import duckdb, streamlit; print('Dependencies OK')"
```

If `.venv\Scripts\python.exe` is missing, repeat step 1. If a package import
fails, repeat the `pip install` command from step 1.

If port 8501 is already being used, start the dashboard on another port:

```powershell
.venv\Scripts\python.exe -m streamlit run src\dashboard.py --server.port 8502
```

Then open `http://localhost:8502`.
