# Backend Specification: Collision Analytics

## 1. Objective

Build a simple, reusable Python backend on top of the existing DuckDB database (`data/collisions.duckdb`).

The backend should support the two main analytics modules from the proposal:

1. **Geographic Collision Hotspot Analysis:** Identify areas with high historical collision counts, with filters for location, time, severity, and collision characteristics.
2. **Temporal and Severity Analytics:** Analyze collision trends across years, months, weekdays, hours, severity levels, and reported conditions.

The same backend functions must be usable by both the dashboard and MCP server.

Do not modify the existing cleaning pipeline, database schema, or data.

## 2. Code Structure

Keep the implementation limited to three Python files and one test file:

```text
src/
  db.py
  analytics.py
  mcp_server.py

tests/
  test_backend.py
```

- `db.py`: DuckDB connections, SQL execution, filter validation, and query construction.
- `analytics.py`: Common aggregation functions and analytics logic.
- `mcp_server.py`: Expose selected analytics functions as MCP tools using FastMCP.
- `test_backend.py`: Unit tests for filtering, aggregations, edge cases, and MCP integration.

Avoid additional layers, classes, utility modules, or frameworks unless absolutely necessary.

## 3. Common Filtering

Implement a reusable filter dictionary that can be passed to all analytics functions.

Support common filters such as date/year ranges, severity, weather, collision type, weekday, vehicle involvement, alcohol involvement, and geographic bounding boxes.

Filters should be optional and independently combinable.

- Multiple filters should use `AND`.
- Multiple selected values for one category should use `IN`.
- Unspecified filters should not affect results.
- Validate supported columns, input types, and date/range boundaries.
- Use parameterized SQL and a fixed allowlist of database columns.
- Reject unsupported filters instead of silently ignoring them.
- Do not expose arbitrary SQL execution to MCP or dashboard callers.

The same filtering logic must be reused throughout the backend.

## 4. Common Analytics Functions

Implement a small set of reusable functions:

- **Summary statistics:** Total collisions, fatalities, and injuries for selected filters.
- **Generic grouping and aggregation:** Group by supported columns such as year, month, weekday, hour, severity, weather, and collision type. Return collision counts and casualty totals.
- **Temporal trends:** Support year, month, weekday, and hourly analysis using the common aggregation functionality.
- **Severity distribution:** Return collision counts grouped by normalized severity.
- **Geographic hotspots:** Group nearby collision coordinates into configurable latitude/longitude grid cells and return the highest collision-count areas.
- **Filter options:** Return available values for supported categorical filters so the dashboard can populate filter controls.

Avoid writing separate SQL queries for each visualization. Specialized analytics functions should reuse the generic aggregation and filtering logic wherever possible.

Use DuckDB for filtering and aggregation rather than loading all records into Pandas.

## 5. Data Handling Rules

Follow the decisions made during data cleaning:

- Include both records sharing the duplicate case ID. Collision counts use `COUNT(*)`.
- Use `severity_normalized` for severity analysis.
- Preserve missing values as SQL `NULL`.
- Do not interpret missing numeric values as zero in individual records.
- Exclude records with missing `collision_hour` only when grouping by hour.
- Exclude missing coordinates only from geographic hotspot calculations.
- Preserve valid categorical values such as `None` and `Not Stated`.
- Missing grouping values should not appear as a category unless explicitly supported.
- For aggregations with no matching records, return empty results or zero totals, as appropriate.
- Do not modify or infer missing data.

Geographic hotspots should represent historical collision frequency, not accident risk. Do not introduce traffic-volume estimates or neighborhood boundaries.

## 6. MCP Integration

Use FastMCP to expose the relevant analytics functionality as tools.

MCP tools should call functions from `analytics.py` directly rather than implementing their own queries.

- Use clear function names, Python type hints, and short docstrings.
- Define structured input parameters and predictable, JSON-compatible outputs.
- Expose summary statistics, temporal trends, severity distributions, and hotspot rankings.
- Use the same filter rules as the dashboard.
- Return meaningful errors for invalid parameters.
- Do not allow unrestricted SQL execution or database modifications.

The MCP server should remain a thin interface over the shared analytics backend.

Do not implement a chatbot, LLM orchestration, or natural-language-to-SQL generation in this phase.

## 7. Testing

Write readable tests using `pytest` and a small temporary DuckDB database with synthetic collision records.

Tests should demonstrate how each function is intended to be used.

Cover:

- Individual filters and combinations of filters.
- Multiple categorical values.
- Invalid filter inputs.
- Correct collision counts and casualty aggregations.
- Grouping by time, severity, and other categories.
- Missing collision times and coordinates.
- Duplicate case IDs.
- Geographic grid aggregation and hotspot ranking.
- Empty query results.
- MCP tools returning results consistent with direct analytics calls.

Tests must not modify the production database.

After unit tests pass, run representative read-only queries against the actual database and verify expected totals:

- 239,588 collision records.
- 2,479 fatalities.
- 181,254 injuries.
- Years 2014–2023.

## 8. Implementation Requirements

- Keep the code simple, modular, and readable.
- Use basic Python functions rather than unnecessary classes or design patterns.
- Keep SQL centralized and reuse existing functions.
- Return dictionaries or lists that are easy to consume in the dashboard and MCP server.
- Use minimal comments and straightforward naming.
- Do not add functionality outside this specification.
- Do not modify the ingestion pipeline or database.
- Write and run tests before validating against the full dataset.
- If an unexpected schema issue or data behavior requires a new design decision, ask for confirmation rather than making assumptions.

## 9. Completion Criteria

The backend is complete when the shared filters and analytics functions work correctly, the MCP tools reuse the same functions, all tests pass, and representative queries return correct results from the persistent DuckDB database.

No dashboard implementation is required in this phase.