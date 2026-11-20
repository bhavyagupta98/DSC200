import argparse
import os
import uuid
from pathlib import Path

import duckdb
import pandas as pd


ORIGINAL_COLUMNS = [
    "accident_year",
    "collision_date",
    "collision_time",
    "day_of_week",
    "primary_rd",
    "secondary_rd",
    "distance",
    "direction",
    "intersection",
    "weather_1",
    "state_hwy_ind",
    "state_route",
    "postmile",
    "location_type",
    "ramp_intersection",
    "collision_severity",
    "number_killed",
    "number_injured",
    "party_count",
    "pcf_viol_category",
    "hit_and_run",
    "type_of_collision",
    "mviw",
    "ped_action",
    "road_surface",
    "road_cond_1",
    "lighting",
    "control_device",
    "chp_road_type",
    "pedestrian_accident",
    "bicycle_accident",
    "motorcycle_accident",
    "truck_accident",
    "alcohol_involved",
    "stwd_vehtype_at_fault",
    "count_severe_inj",
    "count_visible_inj",
    "count_complaint_pain",
    "count_ped_killed",
    "count_ped_injured",
    "count_bicyclist_killed",
    "count_bicyclist_injured",
    "count_mc_killed",
    "count_mc_injured",
    "sandag_case_id",
    "latitude_sandag",
    "longitude_sandag",
    "x",
    "y",
    "location_sandag",
    "reservation_sandag",
    "shape",
]

DERIVED_COLUMNS = [
    "severity_normalized",
    "collision_year",
    "collision_month",
    "collision_weekday",
    "collision_hour",
]

INTEGER_COLUMNS = [
    "accident_year",
    "state_route",
    "number_killed",
    "number_injured",
    "party_count",
    "chp_road_type",
    "count_severe_inj",
    "count_visible_inj",
    "count_complaint_pain",
    "count_ped_killed",
    "count_ped_injured",
    "count_bicyclist_killed",
    "count_bicyclist_injured",
    "count_mc_killed",
    "count_mc_injured",
]

DOUBLE_COLUMNS = [
    "distance",
    "postmile",
    "latitude_sandag",
    "longitude_sandag",
    "x",
    "y",
]

BOOLEAN_COLUMNS = [
    "pedestrian_accident",
    "bicycle_accident",
    "motorcycle_accident",
    "truck_accident",
    "alcohol_involved",
]

SEVERITY_VALUES = {
    "PDO",
    "Property Damage Only",
    "Injury (Complaint of Pain)",
    "Injury (Other Visible)",
    "Injury (Severe)",
    "Fatal",
}

DUCKDB_SCHEMA = [
    ("accident_year", "INTEGER"),
    ("collision_date", "DATE"),
    ("collision_time", "TIME"),
    ("day_of_week", "VARCHAR"),
    ("primary_rd", "VARCHAR"),
    ("secondary_rd", "VARCHAR"),
    ("distance", "DOUBLE"),
    ("direction", "VARCHAR"),
    ("intersection", "VARCHAR"),
    ("weather_1", "VARCHAR"),
    ("state_hwy_ind", "VARCHAR"),
    ("state_route", "INTEGER"),
    ("postmile", "DOUBLE"),
    ("location_type", "VARCHAR"),
    ("ramp_intersection", "VARCHAR"),
    ("collision_severity", "VARCHAR"),
    ("number_killed", "INTEGER"),
    ("number_injured", "INTEGER"),
    ("party_count", "INTEGER"),
    ("pcf_viol_category", "VARCHAR"),
    ("hit_and_run", "VARCHAR"),
    ("type_of_collision", "VARCHAR"),
    ("mviw", "VARCHAR"),
    ("ped_action", "VARCHAR"),
    ("road_surface", "VARCHAR"),
    ("road_cond_1", "VARCHAR"),
    ("lighting", "VARCHAR"),
    ("control_device", "VARCHAR"),
    ("chp_road_type", "INTEGER"),
    ("pedestrian_accident", "BOOLEAN"),
    ("bicycle_accident", "BOOLEAN"),
    ("motorcycle_accident", "BOOLEAN"),
    ("truck_accident", "BOOLEAN"),
    ("alcohol_involved", "BOOLEAN"),
    ("stwd_vehtype_at_fault", "VARCHAR"),
    ("count_severe_inj", "INTEGER"),
    ("count_visible_inj", "INTEGER"),
    ("count_complaint_pain", "INTEGER"),
    ("count_ped_killed", "INTEGER"),
    ("count_ped_injured", "INTEGER"),
    ("count_bicyclist_killed", "INTEGER"),
    ("count_bicyclist_injured", "INTEGER"),
    ("count_mc_killed", "INTEGER"),
    ("count_mc_injured", "INTEGER"),
    ("sandag_case_id", "VARCHAR"),
    ("latitude_sandag", "DOUBLE"),
    ("longitude_sandag", "DOUBLE"),
    ("x", "DOUBLE"),
    ("y", "DOUBLE"),
    ("location_sandag", "VARCHAR"),
    ("reservation_sandag", "VARCHAR"),
    ("shape", "VARCHAR"),
    ("severity_normalized", "VARCHAR"),
    ("collision_year", "INTEGER"),
    ("collision_month", "INTEGER"),
    ("collision_weekday", "VARCHAR"),
    ("collision_hour", "INTEGER"),
]


def read_source(csv_path):
    return pd.read_csv(
        csv_path,
        dtype="string",
        keep_default_na=False,
        na_values=["", "NULL"],
    )


def validate_source_schema(frame):
    actual = list(frame.columns)
    if actual != ORIGINAL_COLUMNS:
        missing = sorted(set(ORIGINAL_COLUMNS) - set(actual))
        extra = sorted(set(actual) - set(ORIGINAL_COLUMNS))
        raise ValueError(
            f"Source columns do not match specification; missing={missing}, extra={extra}"
        )


def _convert_numeric(frame, columns, dtype):
    for column in columns:
        converted = pd.to_numeric(frame[column], errors="coerce")
        invalid = frame[column].notna() & converted.isna()
        if invalid.any():
            raise ValueError(
                f"Invalid numeric values in {column}: {int(invalid.sum())} records"
            )
        frame[column] = converted.astype(dtype)


def _convert_booleans(frame):
    for column in BOOLEAN_COLUMNS:
        normalized = frame[column].astype("string").str.lower()
        invalid = frame[column].notna() & ~normalized.isin(["true", "false"])
        if invalid.any():
            values = sorted(frame.loc[invalid, column].astype(str).unique())
            raise ValueError(f"Unexpected boolean values in {column}: {values}")
        frame[column] = normalized.map({"true": True, "false": False}).astype("boolean")


def clean_collisions(source):
    validate_source_schema(source)
    frame = source.copy()
    frame = frame.replace({"": pd.NA, "NULL": pd.NA})

    severities = set(frame["collision_severity"].dropna().astype(str).unique())
    unexpected_severities = sorted(severities - SEVERITY_VALUES)
    if unexpected_severities:
        raise ValueError(f"Unexpected collision_severity values: {unexpected_severities}")

    _convert_numeric(frame, INTEGER_COLUMNS, "Int64")
    _convert_numeric(frame, DOUBLE_COLUMNS, "Float64")
    _convert_booleans(frame)

    parsed_dates = pd.to_datetime(frame["collision_date"], errors="coerce")
    invalid_dates = frame["collision_date"].notna() & parsed_dates.isna()
    if invalid_dates.any():
        raise ValueError(f"Invalid collision_date: {int(invalid_dates.sum())} records")
    frame["collision_date"] = parsed_dates.dt.normalize()

    time_text = frame["collision_time"].astype("string")
    extracted_times = time_text.str.extract(
        r"(?:^|\s)(\d{2}:\d{2}:\d{2})(?:\.\d+)?$", expand=False
    )
    parsed_times = pd.to_datetime(extracted_times, format="%H:%M:%S", errors="coerce")
    invalid_times = frame["collision_time"].notna() & parsed_times.isna()
    if invalid_times.any():
        raise ValueError(f"Invalid collision_time: {int(invalid_times.sum())} records")
    frame["collision_time"] = parsed_times.dt.time

    frame["severity_normalized"] = frame["collision_severity"].replace(
        {"PDO": "Property Damage Only"}
    )
    frame["collision_year"] = parsed_dates.dt.year.astype("Int64")
    frame["collision_month"] = parsed_dates.dt.month.astype("Int64")
    frame["collision_weekday"] = parsed_dates.dt.day_name().astype("string")
    frame["collision_hour"] = parsed_times.dt.hour.astype("Int64")

    validate_cleaned_data(frame)
    return frame[ORIGINAL_COLUMNS + DERIVED_COLUMNS]


def validate_cleaned_data(
    frame, expected_rows=None, expected_duplicate_case_ids=None
):
    if expected_rows is not None and len(frame) != expected_rows:
        raise ValueError(f"Unexpected row count: {len(frame)}; expected {expected_rows}")

    years = frame["collision_year"].dropna()
    invalid_years = ~years.between(2014, 2023)
    if invalid_years.any():
        raise ValueError(f"Collision years outside 2014-2023: {int(invalid_years.sum())}")

    mismatched_years = (
        frame["accident_year"].notna()
        & frame["collision_year"].notna()
        & (frame["accident_year"] != frame["collision_year"])
    )
    if mismatched_years.any():
        raise ValueError(f"Accident/date year mismatch: {int(mismatched_years.sum())}")

    coordinate_ranges = {
        "latitude_sandag": (32.5405, 33.4917),
        "longitude_sandag": (-117.59378, -116.08329),
    }
    for column, (minimum, maximum) in coordinate_ranges.items():
        invalid = frame[column].notna() & ~frame[column].between(minimum, maximum)
        if invalid.any():
            raise ValueError(f"{column} outside expected range: {int(invalid.sum())}")

    casualty_columns = [
        "number_killed",
        "number_injured",
        "party_count",
        "count_severe_inj",
        "count_visible_inj",
        "count_complaint_pain",
        "count_ped_killed",
        "count_ped_injured",
        "count_bicyclist_killed",
        "count_bicyclist_injured",
        "count_mc_killed",
        "count_mc_injured",
    ]
    negative = (frame[casualty_columns] < 0).any(axis=1)
    if negative.any():
        raise ValueError(f"Negative casualty or party counts: {int(negative.sum())}")

    injury_components = frame[
        ["count_severe_inj", "count_visible_inj", "count_complaint_pain"]
    ].sum(axis=1, min_count=1)
    mismatch = frame["number_injured"].notna() & (
        frame["number_injured"] != injury_components
    )
    if mismatch.any():
        raise ValueError(f"Injury total mismatch: {int(mismatch.sum())} records")

    if expected_duplicate_case_ids is not None:
        counts = frame["sandag_case_id"].value_counts()
        actual = set(counts[counts > 1].index.astype(str))
        expected = set(expected_duplicate_case_ids)
        if actual != expected:
            raise ValueError(
                f"Unexpected duplicate case ID pattern: actual={sorted(actual)}, "
                f"expected={sorted(expected)}"
            )


def write_parquet(frame, parquet_path):
    parquet_path = Path(parquet_path)
    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = parquet_path.with_name(
        f".{parquet_path.name}.{uuid.uuid4().hex}.tmp"
    )
    try:
        frame.to_parquet(temporary_path, engine="pyarrow", index=False)
        os.replace(temporary_path, parquet_path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def ingest_parquet(parquet_path, database_path):
    parquet_path = Path(parquet_path).resolve()
    database_path = Path(database_path)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_database = database_path.with_name(
        f".{database_path.name}.{uuid.uuid4().hex}.tmp"
    )
    column_definitions = ", ".join(
        f'"{name}" {data_type}' for name, data_type in DUCKDB_SCHEMA
    )
    selected_columns = ", ".join(
        f'CAST("{name}" AS {data_type}) AS "{name}"'
        for name, data_type in DUCKDB_SCHEMA
    )
    connection = None
    try:
        connection = duckdb.connect(str(temporary_database))
        connection.execute(f"CREATE TABLE collisions ({column_definitions})")
        connection.execute(
            f"INSERT INTO collisions SELECT {selected_columns} "
            "FROM read_parquet(?)",
            [str(parquet_path)],
        )
        connection.close()
        connection = None
        os.replace(temporary_database, database_path)
    finally:
        if connection is not None:
            connection.close()
        if temporary_database.exists():
            temporary_database.unlink()


def validate_database(database_path, expected_rows):
    connection = duckdb.connect(str(database_path), read_only=True)
    try:
        row_count = connection.execute("SELECT count(*) FROM collisions").fetchone()[0]
        if row_count != expected_rows:
            raise ValueError(
                f"DuckDB row count is {row_count}; expected {expected_rows}"
            )
        schema = dict(
            connection.execute(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_name = 'collisions' ORDER BY ordinal_position"
            ).fetchall()
        )
        if schema != dict(DUCKDB_SCHEMA):
            raise ValueError("DuckDB schema does not match the explicit schema")
        return {
            "row_count": row_count,
            "year_min": connection.execute(
                "SELECT min(collision_year) FROM collisions"
            ).fetchone()[0],
            "year_max": connection.execute(
                "SELECT max(collision_year) FROM collisions"
            ).fetchone()[0],
            "number_killed": connection.execute(
                "SELECT sum(number_killed) FROM collisions"
            ).fetchone()[0],
            "number_injured": connection.execute(
                "SELECT sum(number_injured) FROM collisions"
            ).fetchone()[0],
            "duplicate_case_rows": connection.execute(
                "SELECT count(*) FROM collisions WHERE sandag_case_id = '6820212021'"
            ).fetchone()[0],
        }
    finally:
        connection.close()


def write_eda_report(cleaned, database_results, report_path):
    important_columns = [
        "collision_time",
        "distance",
        "state_route",
        "postmile",
        "control_device",
        "stwd_vehtype_at_fault",
        "location_sandag",
        "reservation_sandag",
    ]
    missing = cleaned[important_columns].isna().sum()
    severity = cleaned["severity_normalized"].value_counts()
    missing_text = ", ".join(
        f"`{column}` ({int(count):,})" for column, count in missing.items()
    )
    severity_text = ", ".join(
        f"{label} ({int(count):,})" for label, count in severity.items()
    )
    report = f"""# Collision Data EDA

## Summary

- {database_results['row_count']:,} collision records covering {database_results['year_min']}–{database_results['year_max']} were retained.
- The source has {len(ORIGINAL_COLUMNS)} columns; {len(DERIVED_COLUMNS)} analytical columns were added.
- The dataset records {database_results['number_killed']:,} fatalities and {database_results['number_injured']:,} injuries.
- The cleaned data is stored in `data/processed/collisions.parquet` and `data/collisions.duckdb`.

## Main observations

- Missing values are concentrated in contextual fields: {missing_text}.
- All 2023 records are missing `distance`, `location_sandag`, and `reservation_sandag`.
- Case ID `6820212021` appears {database_results['duplicate_case_rows']} times, but the records are not exact duplicates.
- Normalized severity counts are: {severity_text}.
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
"""
    report_path = Path(report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")


def run_pipeline(csv_path, parquet_path, database_path, report_path):
    source = read_source(csv_path)
    validate_source_schema(source)
    if len(source) != 239_588:
        raise ValueError(f"Unexpected source row count: {len(source)}")
    if source.duplicated().any():
        raise ValueError(f"Unexpected exact duplicate rows: {int(source.duplicated().sum())}")

    cleaned = clean_collisions(source)
    validate_cleaned_data(
        cleaned,
        expected_rows=239_588,
        expected_duplicate_case_ids={"6820212021"},
    )
    write_parquet(cleaned, parquet_path)
    ingest_parquet(parquet_path, database_path)
    results = validate_database(database_path, 239_588)
    if results["year_min"] != 2014 or results["year_max"] != 2023:
        raise ValueError(f"Unexpected database year range: {results}")
    if results["number_killed"] != 2_479 or results["number_injured"] != 181_254:
        raise ValueError(f"Unexpected casualty aggregates: {results}")
    if results["duplicate_case_rows"] != 2:
        raise ValueError(f"Duplicated case ID was not retained twice: {results}")
    write_eda_report(cleaned, results, report_path)
    return results


def main():
    parser = argparse.ArgumentParser(description="Clean and ingest SANDAG collisions")
    parser.add_argument("--csv", default="sandag_collisions_full.csv")
    parser.add_argument(
        "--parquet", default="data/processed/collisions.parquet"
    )
    parser.add_argument("--database", default="data/collisions.duckdb")
    parser.add_argument("--report", default="eda.md")
    args = parser.parse_args()
    results = run_pipeline(args.csv, args.parquet, args.database, args.report)
    print(f"Ingested {results['row_count']:,} collision records")


if __name__ == "__main__":
    main()
