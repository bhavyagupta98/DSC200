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

Run the one-time ingestion:

```bash
.venv/bin/python collision_pipeline.py
```

This creates `data/processed/collisions.parquet`, `data/collisions.duckdb`, and
`DATA_QUALITY_REPORT.md`. Rerunning the command atomically replaces the table
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

## Run the collision analytics chat

The chat uses Streamlit, the OpenAI Agents SDK, the existing MCP server, and a
local Ollama model. It does not require an OpenAI API key.

Install Ollama and download the quantized 4B model once:

```bash
brew install ollama
ollama pull qwen3:4b-q4_K_M
```

Then launch the app from the project root:

```bash
.venv/bin/streamlit run src/chat.py
```

If the virtual environment is already active, the equivalent command is:

```bash
streamlit run src/chat.py
```

The app starts `ollama serve` when no server is already available, preloads the
model, and unloads it when the Streamlit process exits normally. If the app
started Ollama, it also stops that owned server. Closing only the browser tab
does not stop Streamlit; stop the terminal process with `Ctrl+C` to trigger
cleanup.

To use another installed model, set `OLLAMA_MODEL` before launch:

```bash
OLLAMA_MODEL=qwen3:1.7b streamlit run src/chat.py
```

Query the existing database:

```python
import duckdb

connection = duckdb.connect("data/collisions.duckdb", read_only=True)
rows = connection.execute("SELECT count(*) FROM collisions").fetchone()[0]
connection.close()
```
