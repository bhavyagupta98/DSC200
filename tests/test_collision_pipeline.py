from pathlib import Path

import duckdb
import pandas as pd
import pytest

from collision_pipeline import (
    DERIVED_COLUMNS,
    DUCKDB_SCHEMA,
    ORIGINAL_COLUMNS,
    clean_collisions,
    ingest_parquet,
    validate_cleaned_data,
    validate_source_schema,
    write_parquet,
)


def sample_row(**overrides):
    row = {
        "accident_year": "2021",
        "collision_date": "2021-06-08 00:00:00.0000000",
        "collision_time": "1900-01-01 17:42:00.0000000",
        "day_of_week": "Tuesday",
        "primary_rd": "EAST PLAZA BL",
        "secondary_rd": "E PLAZA BL 1645",
        "distance": "0.00000000",
        "direction": "Not Stated",
        "intersection": "Intersection",
        "weather_1": "Clear",
        "state_hwy_ind": "No",
        "state_route": "NULL",
        "postmile": "",
        "location_type": "No State Highway",
        "ramp_intersection": "Not Stated",
        "collision_severity": "PDO",
        "number_killed": "0",
        "number_injured": "0",
        "party_count": "2",
        "pcf_viol_category": "Unsafe Speed",
        "hit_and_run": "Not Hit and Run",
        "type_of_collision": "Rear End",
        "mviw": "Other Motor Vehicle",
        "ped_action": "No Pedestrian Involved",
        "road_surface": "Dry",
        "road_cond_1": "No Unusual Condition",
        "lighting": "Daylight",
        "control_device": "None",
        "chp_road_type": "0",
        "pedestrian_accident": "false",
        "bicycle_accident": "false",
        "motorcycle_accident": "false",
        "truck_accident": "false",
        "alcohol_involved": "false",
        "stwd_vehtype_at_fault": "Passenger Car/Station Wagon",
        "count_severe_inj": "0",
        "count_visible_inj": "0",
        "count_complaint_pain": "0",
        "count_ped_killed": "0",
        "count_ped_injured": "0",
        "count_bicyclist_killed": "0",
        "count_bicyclist_injured": "0",
        "count_mc_killed": "0",
        "count_mc_injured": "0",
        "sandag_case_id": "6820212021",
        "latitude_sandag": "32.67412186",
        "longitude_sandag": "-117.10619350",
        "x": "6280000.25",
        "y": "1830000.75",
        "location_sandag": "National City",
        "reservation_sandag": "Not Reservation Land",
        "shape": "0xABC",
    }
    row.update(overrides)
    return row


def test_schema_requires_exact_original_columns():
    frame = pd.DataFrame([sample_row()])
    validate_source_schema(frame)

    with pytest.raises(ValueError, match="Source columns do not match"):
        validate_source_schema(frame.drop(columns=["shape"]))


def test_cleaning_preserves_missing_and_categorical_values():
    frame = pd.DataFrame(
        [
            sample_row(
                state_route="NULL",
                postmile="",
                control_device="None",
                direction="Not Stated",
            )
        ]
    )

    cleaned = clean_collisions(frame)

    assert pd.isna(cleaned.loc[0, "state_route"])
    assert pd.isna(cleaned.loc[0, "postmile"])
    assert cleaned.loc[0, "control_device"] == "None"
    assert cleaned.loc[0, "direction"] == "Not Stated"


def test_severity_date_and_time_transformations():
    frame = pd.DataFrame(
        [
            sample_row(),
            sample_row(
                sandag_case_id="2",
                collision_severity="Injury (Severe)",
                collision_date="2020-02-29 00:00:00.0000000",
                collision_time=None,
                accident_year="2020",
                number_injured="1",
                count_severe_inj="1",
            ),
        ]
    )

    cleaned = clean_collisions(frame)

    assert cleaned["severity_normalized"].tolist() == [
        "Property Damage Only",
        "Injury (Severe)",
    ]
    assert cleaned.loc[0, "collision_date"] == pd.Timestamp("2021-06-08")
    assert cleaned.loc[0, "collision_year"] == 2021
    assert cleaned.loc[0, "collision_month"] == 6
    assert cleaned.loc[0, "collision_weekday"] == "Tuesday"
    assert cleaned.loc[0, "collision_hour"] == 17
    assert cleaned.loc[0, "collision_time"].hour == 17
    assert pd.isna(cleaned.loc[1, "collision_time"])
    assert pd.isna(cleaned.loc[1, "collision_hour"])


def test_numeric_conversion_coordinates_and_duplicate_ids():
    frame = pd.DataFrame(
        [
            sample_row(),
            sample_row(
                latitude_sandag="32.67410169",
                longitude_sandag="-117.10625671",
                distance=None,
            ),
        ]
    )

    cleaned = clean_collisions(frame)
    validate_cleaned_data(cleaned)

    assert len(cleaned) == 2
    assert cleaned["sandag_case_id"].tolist() == ["6820212021", "6820212021"]
    assert cleaned.loc[0, "latitude_sandag"] == pytest.approx(32.67412186)
    assert pd.isna(cleaned.loc[1, "distance"])
    assert str(cleaned["party_count"].dtype) == "Int64"


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"collision_severity": "New Severity"}, "Unexpected collision_severity"),
        ({"collision_date": "not-a-date"}, "Invalid collision_date"),
        ({"collision_time": "25:00:00"}, "Invalid collision_time"),
        ({"latitude_sandag": "35.0"}, "latitude_sandag outside"),
        ({"number_injured": "unknown"}, "Invalid numeric values"),
        ({"number_killed": "-1"}, "Negative casualty"),
        (
            {"number_injured": "2", "count_complaint_pain": "1"},
            "Injury total mismatch",
        ),
    ],
)
def test_unexpected_values_fail_validation(overrides, message):
    with pytest.raises(ValueError, match=message):
        clean_collisions(pd.DataFrame([sample_row(**overrides)]))


def test_parquet_and_duckdb_persistence_is_idempotent(tmp_path):
    frame = pd.DataFrame(
        [
            sample_row(),
            sample_row(
                latitude_sandag="32.67410169",
                collision_time=None,
                postmile="NULL",
            ),
        ]
    )
    cleaned = clean_collisions(frame)
    parquet_path = tmp_path / "processed" / "collisions.parquet"
    database_path = tmp_path / "collisions.duckdb"

    write_parquet(cleaned, parquet_path)
    ingest_parquet(parquet_path, database_path)
    ingest_parquet(parquet_path, database_path)

    connection = duckdb.connect(str(database_path), read_only=True)
    try:
        assert connection.execute("SELECT count(*) FROM collisions").fetchone()[0] == 2
        assert connection.execute(
            "SELECT count(*) FROM collisions WHERE sandag_case_id = '6820212021'"
        ).fetchone()[0] == 2
        assert connection.execute(
            "SELECT count(*) FROM collisions WHERE collision_time IS NULL"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT count(*) FROM collisions WHERE severity_normalized = "
            "'Property Damage Only'"
        ).fetchone()[0] == 2
        actual_types = dict(
            connection.execute(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_name = 'collisions'"
            ).fetchall()
        )
        assert actual_types == dict(DUCKDB_SCHEMA)
        assert len(actual_types) == len(ORIGINAL_COLUMNS) + len(DERIVED_COLUMNS)
    finally:
        connection.close()

