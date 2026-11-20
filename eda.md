# Collision Data EDA

## Summary

- 239,588 collision records covering 2014–2023 were retained.
- The source has 52 columns; five analytical columns were added.
- The dataset records 2,479 fatalities and 181,254 injuries.
- The cleaned data is stored in `data/processed/collisions.parquet` and `data/collisions.duckdb`.

## Main observations

- Missing values are concentrated in contextual fields: `state_route` (63,196), `postmile` (46,446), `stwd_vehtype_at_fault` (36,851), `distance` (20,525), `location_sandag` (18,966), `reservation_sandag` (18,966), `control_device` (26,397), and `collision_time` (1,267).
- All 2023 records are missing `distance`, `location_sandag`, and `reservation_sandag`.
- Case ID `6820212021` appears twice, but the two records are not exact duplicates.
- Normalized severity counts are: Property Damage Only (106,687), Injury (Complaint of Pain) (76,229), Injury (Other Visible) (45,412), Injury (Severe) (8,933), and Fatal (2,327).
- Validation found no invalid dates, non-null times, coordinates, injury totals, or unexpected severity categories.

## Cleanup decisions

- Blank strings and literal `NULL` values became database nulls; rows with missing values were not dropped or imputed.
- Valid category text such as `None` and `Not Stated` was preserved.
- Numeric, boolean, date, and time fields were converted to explicit types; invalid non-null values cause the pipeline to fail.
- `PDO` was normalized to `Property Damage Only` in a new `severity_normalized` field while the original severity was retained.
- Year, month, weekday, and hour were derived from collision dates and times; missing times remain null.
- Both records with the repeated case ID were retained because a repeated ID does not prove the rows are duplicates.
- Coordinates, casualty totals, year ranges, schema, and final aggregates are validated before the outputs are accepted.
- Unusual distance values and other outliers were preserved rather than capped or removed.
- Parquet and DuckDB outputs are replaced through temporary files, so rerunning ingestion does not append duplicate records.

## Functional files

- `collision_pipeline.py` cleans, validates, and writes the source data to Parquet, DuckDB, and this EDA report.
- `src/db.py` validates filters, builds parameterized SQL, and opens DuckDB in read-only mode.
- `src/analytics.py` provides totals, trends, severity, ranked collision types, filter options, and geographic hotspots.
- `src/mcp_server.py` exposes the shared analytics functions as MCP tools without allowing arbitrary SQL or writes.
- `src/dashboard.py` renders raw analytics and optionally enables Analytics and Chat pages with the `--chat` flag.
- `src/chat.py` provides the local Ollama chat page loaded by the dashboard when `--chat` is enabled.
- `tests/test_collision_pipeline.py` tests cleaning rules, validation, persistence, and repeatable ingestion.
- `tests/test_backend.py` tests filters, analytics results, edge cases, and MCP tool delegation.
- `requirements.txt` pins the Python packages required by the pipeline and applications.
