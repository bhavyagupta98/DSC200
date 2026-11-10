# Specification: Data Cleaning and DuckDB Ingestion

## 1. Objective

Implement a simple, reproducible Python pipeline to clean the SANDAG collision dataset and ingest it into a persistent DuckDB database.

The database will be used by the analytics backend, dashboard, and MCP server.

**Requirements:**
- Use Python, Pandas, PyArrow, and DuckDB.
- Keep the code simple, modular and readable.
- Avoid unnecessary abstractions, frameworks, and complicated logic.
- Use minimal, meaningful comments. Avoid verbose comments.
- Write unit tests before processing the actual dataset.
- Do not make additional data-cleaning decisions without confirmation.

## 2. Input Dataset

File: `sandag_collisions_full.csv`

Expected properties:
- 239,588 records
- 52 columns
- Approximately 155 MB
- Years: 2014–2023

Read the CSV using Pandas.

Treat empty cells and literal `NULL` as missing values. Do not automatically convert strings such as `None` or `Not Stated` to null.

Preserve the original CSV without modifications.

## 3. Data Cleaning Rules

### 3.1 Missing Values

- Do not drop rows simply because some fields are missing.
- Preserve missing values as `NULL` in DuckDB.
- Do not replace missing numeric values with zero.
- Do not apply mean, median, or other imputation.
- Keep missing `state_route`, `postmile`, `distance`, `control_device`, `stwd_vehtype_at_fault`, and other contextual fields as null.
- Preserve `None` when it represents a valid categorical value.
- Standardize `Not Stated` to `Unknown` only in derived analytical fields. Preserve original values otherwise.
- Do not remove records missing `collision_time`. They should remain available for analyses that do not require time of day.
- Do not remove 2023 records because of missing `distance`, `location_sandag`, or `reservation_sandag`.

If any unexpected missing-value pattern requires a new transformation, request confirmation before implementing it.

### 3.2 Duplicate Records

The dataset has:
- 239,588 records.
- 239,587 unique `sandag_case_id` values.
- One duplicated case ID: `6820212021`.

**Retain both records.**

- Do not deduplicate using `sandag_case_id`.
- Do not impose a unique constraint on this field.
- Include both records in standard aggregations.
- Do not remove other duplicates automatically if discovered. Report them and request confirmation.

### 3.3 Severity Normalization

Standardize:

- `PDO` → `Property Damage Only`
- `Property Damage Only` → `Property Damage Only`

Preserve all other existing severity categories.

Create `severity_normalized` rather than overwriting the original severity column.

If any additional severity categories are discovered, request confirmation before applying a new mapping.

### 3.4 Date and Time

- Parse `collision_date` into a proper date type.
- Extract `collision_year`, `collision_month`, and `collision_weekday`.
- Parse `collision_time` and extract `collision_hour` as an integer from 0 to 23.
- Ignore the dummy `1900-01-01` date portion in `collision_time`.
- Preserve missing collision times as null.
- Validate that years fall within 2014–2023.
- Do not invent times or dates for missing values.

If invalid or unexpected date/time formats appear, report them and request confirmation before applying additional fixes.

### 3.5 Coordinates

- Store `latitude_sandag` and `longitude_sandag` as numeric values.
- Preserve the original coordinate values without rounding.
- Validate coordinate ranges:
  - Latitude: 32.5405 to 33.4917
  - Longitude: -117.59378 to -116.08329
- Do not modify, interpolate, or infer coordinates.
- Report any missing or out-of-range coordinates rather than automatically removing records.

These ranges are validation expectations from the initial analysis, not automatic deletion thresholds.

### 3.6 Numeric Fields

- Convert casualty counts, party counts, and other applicable numeric columns to appropriate numeric types.
- Preserve missing numeric values as null.
- Validate casualty counts are nonnegative.
- Validate consistency between total casualties and detailed injury counts where applicable.
- Preserve unusual `distance` values, including values exceeding 100,000.
- Do not cap, remove, or modify outliers without confirmation.

### 3.7 Categorical Fields

- Preserve categorical values unless a transformation is explicitly specified.
- Do not automatically merge similar categories.
- Do not replace `None`, `Not Stated`, or other categorical values without an explicit rule.
- Preserve existing road, weather, collision type, and vehicle involvement information.

## 4. Database Schema

Use a persistent DuckDB database.

Suggested location:

`data/collisions.duckdb`

Create a table named `collisions`.

Requirements:
- Define explicit DuckDB column types.
- Include the original 52 columns.
- Include derived fields for date/time and normalized severity.
- Use `DATE` for collision dates.
- Use `INTEGER` or `BIGINT` for numeric counts as appropriate.
- Use `DOUBLE` for latitude and longitude.
- Use `VARCHAR` for categorical fields and identifiers where appropriate.
- Use nullable columns for missing values.
- Do not enforce uniqueness on `sandag_case_id`.
- Avoid unnecessary indexes and additional tables.

Inspect the actual dataset before finalizing each column type. If the inferred schema conflicts with expected data, request confirmation rather than silently coercing values.

## 5. Pipeline

Implement the following workflow:

```text
sandag_collisions_full.csv
        |
        v
Read CSV
        |
        v
Validate Schema
        |
        v
Clean and Transform
        |
        v
Validate Cleaned Data
        |
        v
Save Cleaned Parquet
        |
        v
Ingest into DuckDB
        |
        v
Validate Database
```

Requirements:
- Keep cleaning and ingestion functions separate.
- Ensure the pipeline can be rerun without duplicating database records.
- Use batch operations, not row-by-row inserts.
- Write the cleaned dataset to `data/processed/collisions.parquet`.
- Create the DuckDB file only after all cleaning validations pass.
- Avoid silently overwriting a valid database if a pipeline step fails.
- Keep the pipeline deterministic.

## 6. Testing

**Implement and run tests before processing the full CSV.**

Use `pytest` and small synthetic Pandas DataFrames.

### Unit tests

Cover:

1. Missing values remain null.
2. Literal `NULL` and blank fields are treated as missing.
3. Valid categorical `None` values are preserved.
4. `Not Stated` is preserved in original fields.
5. `PDO` normalization works correctly.
6. Missing collision times remain null.
7. Collision hours are extracted correctly.
8. Date-derived fields are calculated correctly.
9. Both records sharing a case ID are preserved.
10. Coordinates are parsed and validated correctly.
11. Numeric conversions preserve null values.
12. Unexpected values trigger validation failures rather than silent data modifications.

### Ingestion tests

Using a temporary DuckDB database:

- Create the schema.
- Insert a small cleaned sample.
- Verify row counts and column types.
- Verify null handling.
- Verify duplicate case IDs are retained.
- Verify basic SQL aggregations.
- Verify that ingestion can be rerun without duplicating records.
- Verify that the database persists after closing and reopening the connection.

Use temporary files for tests. Do not modify the production database.

**Do not process or ingest the full dataset until all tests pass.**

## 7. Full Dataset Ingestion

After tests pass:

1. Read the actual CSV.
2. Validate the expected columns and data types.
3. Apply only the approved cleaning transformations.
4. Generate the cleaned Parquet file.
5. Ingest the cleaned records into DuckDB.
6. Close and reopen DuckDB to verify persistence.
7. Execute validation queries.

Expected results:

- Total records: 239,588.
- Years: 2014–2023.
- Both records with duplicated case ID are retained.
- Original severity counts are preserved, with only the specified normalization in the derived column.
- Missing values are preserved according to the cleaning rules.

Verify casualty totals and other key aggregates against the original analysis, accounting for any explicitly documented transformations.

If any unexpected discrepancy appears, stop and report it. Do not silently adjust the expected values.

## 8. Data Quality Report

Generate a concise report containing:

- Original and cleaned row counts.
- Column counts and schema.
- Missing-value counts for important columns.
- Duplicate case ID observations.
- Severity distribution after normalization.
- Invalid date/time or coordinate observations.
- Any unexpected issues.
- DuckDB ingestion row count.
- Test execution results.

The report should clearly distinguish known issues from newly discovered issues.

## 9. Persistence and Repository Setup

The database should be generated once and remain available across application restarts.

- Use a file-backed DuckDB database, not an in-memory database.
- Configure the application to open `data/collisions.duckdb`.
- Commit the generated database file to Git if it fits repository hosting limits.
- Check its final size before committing. If it exceeds the limit, report the issue and request confirmation on an alternative distribution approach.
- Do not require users to rerun cleaning or ingestion every time the application starts.
- Keep the raw CSV out of Git unless explicitly required.
- Do not automatically rebuild or modify the database on application startup.
- Document the one-time ingestion command in the README.

The backend should be able to query the existing database immediately after cloning the repository.

## 10. Implementation Guidelines

- Use straightforward Python functions and a small number of files.
- Prefer standard library functionality where appropriate.
- Use Pandas for cleaning and DuckDB SQL for database ingestion.
- Avoid unnecessary classes, inheritance, configuration frameworks, and complex abstractions.
- Use descriptive function and variable names.
- Add short comments only where the logic is not obvious.
- Keep database connection management simple.
- Do not implement dashboard functions, analytics APIs, or MCP tools in this phase.

## 11. Confirmation Rules

**Do not make cleaning decisions beyond those explicitly defined in this specification.**

If any of the following occurs, stop and ask for confirmation:

- Unexpected columns or missing required columns.
- Unexpected data types or parsing failures.
- New severity categories requiring normalization.
- Invalid dates or coordinates.
- New duplicate patterns requiring a decision.
- Additional data transformations or row removals.
- A database schema conflict.
- Significant discrepancies in expected row counts or aggregates.
- A database file too large to commit.

Report the issue, affected column, number of affected records, and proposed options.

Do not silently fix unexpected issues.

## 12. Completion Criteria

The task is complete when:

- Unit and ingestion tests pass.
- The full dataset has been cleaned using only approved rules.
- Cleaned Parquet has been generated.
- DuckDB contains all 239,588 records.
- Schema and null handling have been verified.
- The database remains accessible after restarting the application.
- A concise data quality report has been generated.
- The README documents how to access the database and rerun ingestion if necessary.
- No unresolved data-quality decisions remain.

**Implementation order:** First implement the cleaning functions and tests, then run the tests. Only after they pass should you process the actual CSV and generate the persistent DuckDB database.