from datetime import date

import duckdb
import pytest

from src import analytics
from src.db import build_where_clause
from src.mcp_server import (
    get_filter_options,
    get_geographic_hotspots,
    get_severity_distribution,
    get_summary_statistics,
    get_temporal_trends,
    mcp,
)


@pytest.fixture
def database_path(tmp_path):
    path = tmp_path / "collisions.duckdb"
    connection = duckdb.connect(str(path))
    connection.execute(
        """
        CREATE TABLE collisions (
            collision_date DATE,
            collision_year INTEGER,
            collision_month INTEGER,
            collision_weekday VARCHAR,
            collision_hour INTEGER,
            severity_normalized VARCHAR,
            weather_1 VARCHAR,
            type_of_collision VARCHAR,
            location_sandag VARCHAR,
            pedestrian_accident BOOLEAN,
            bicycle_accident BOOLEAN,
            motorcycle_accident BOOLEAN,
            truck_accident BOOLEAN,
            alcohol_involved BOOLEAN,
            latitude_sandag DOUBLE,
            longitude_sandag DOUBLE,
            number_killed INTEGER,
            number_injured INTEGER,
            sandag_case_id VARCHAR
        )
        """
    )
    rows = [
        (date(2020, 1, 1), 2020, 1, "Wednesday", 8, "Fatal", "Clear", "Rear End", "San Diego", True, False, False, False, True, 32.701, -117.101, 1, 2, "duplicate"),
        (date(2020, 1, 2), 2020, 1, "Thursday", None, "Property Damage Only", "Cloudy", "Hit Object", "San Diego", False, False, False, False, False, 32.702, -117.102, 0, 0, "duplicate"),
        (date(2021, 6, 10), 2021, 6, "Thursday", 17, "Injury (Severe)", "Clear", "Rear End", "Chula Vista", False, False, True, False, False, 32.751, -117.051, 0, 3, "case-3"),
        (date(2021, 6, 11), 2021, 6, "Friday", 17, "Injury (Complaint of Pain)", None, "Vehicle/Pedestrian", None, True, False, False, False, False, None, None, 0, 1, "case-4"),
        (date(2022, 12, 3), 2022, 12, "Saturday", 22, "Property Damage Only", "Not Stated", "None", "Unincorporated", False, False, False, True, False, 32.801, -117.201, 0, 0, "case-5"),
        (date(2023, 7, 4), 2023, 7, "Tuesday", 21, "Fatal", "Raining", "Head-On", "San Diego", False, False, False, False, False, 32.901, -117.301, 2, 1, "case-6"),
    ]
    connection.executemany(
        "INSERT INTO collisions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    connection.close()
    return path


def test_where_clause_uses_parameters_and_combines_filters():
    sql, parameters = build_where_clause(
        {
            "start_date": "2020-01-01",
            "end_date": date(2021, 12, 31),
            "severity": ["Fatal", "Injury (Severe)"],
            "weather": "Clear",
            "alcohol_involved": True,
            "min_latitude": 32.5,
        }
    )

    assert " WHERE " in sql
    assert "severity_normalized IN (?, ?)" in sql
    assert "Fatal" not in sql
    assert " AND " in sql
    assert parameters == [
        date(2020, 1, 1),
        date(2021, 12, 31),
        "Fatal",
        "Injury (Severe)",
        "Clear",
        True,
        32.5,
    ]


@pytest.mark.parametrize(
    ("filters", "message"),
    [
        ({"unknown": "value"}, "Unsupported filters"),
        ({"severity": []}, "cannot be empty"),
        ({"severity": ["Fatal", 3]}, "must contain strings"),
        ({"alcohol_involved": "true"}, "must be a boolean"),
        ({"start_date": "bad-date"}, "valid ISO date"),
        ({"start_year": 2024}, "between 2014 and 2023"),
        ({"start_year": 2022, "end_year": 2020}, "start_year cannot exceed"),
        ({"min_latitude": 40.0, "max_latitude": 30.0}, "min_latitude cannot exceed"),
    ],
)
def test_invalid_filters_are_rejected(filters, message):
    with pytest.raises(ValueError, match=message):
        build_where_clause(filters)


def test_summary_statistics_and_combined_filters(database_path):
    assert analytics.summary_statistics(db_path=database_path) == {
        "total_collisions": 6,
        "total_fatalities": 3,
        "total_injuries": 7,
    }

    result = analytics.summary_statistics(
        {
            "start_year": 2020,
            "end_year": 2021,
            "severity": ["Fatal", "Injury (Severe)"],
            "weather": "Clear",
        },
        db_path=database_path,
    )
    assert result == {
        "total_collisions": 2,
        "total_fatalities": 1,
        "total_injuries": 5,
    }


def test_boolean_location_and_bounding_box_filters(database_path):
    assert analytics.summary_statistics(
        {"pedestrian_accident": True}, db_path=database_path
    )["total_collisions"] == 2
    assert analytics.summary_statistics(
        {"location": "San Diego", "alcohol_involved": False},
        db_path=database_path,
    )["total_collisions"] == 2
    assert analytics.summary_statistics(
        {
            "min_latitude": 32.70,
            "max_latitude": 32.71,
            "min_longitude": -117.11,
            "max_longitude": -117.10,
        },
        db_path=database_path,
    )["total_collisions"] == 2


def test_generic_grouping_and_temporal_trends(database_path):
    grouped = analytics.aggregate_collisions(
        "severity", {"start_year": 2020, "end_year": 2021}, db_path=database_path
    )
    assert grouped == [
        {
            "severity": "Fatal",
            "collision_count": 1,
            "total_fatalities": 1,
            "total_injuries": 2,
        },
        {
            "severity": "Injury (Complaint of Pain)",
            "collision_count": 1,
            "total_fatalities": 0,
            "total_injuries": 1,
        },
        {
            "severity": "Injury (Severe)",
            "collision_count": 1,
            "total_fatalities": 0,
            "total_injuries": 3,
        },
        {
            "severity": "Property Damage Only",
            "collision_count": 1,
            "total_fatalities": 0,
            "total_injuries": 0,
        },
    ]

    hourly = analytics.temporal_trends("hour", db_path=database_path)
    assert sum(item["collision_count"] for item in hourly) == 5
    assert all(item["hour"] is not None for item in hourly)

    with pytest.raises(ValueError, match="Unsupported group_by"):
        analytics.aggregate_collisions("primary_rd", db_path=database_path)
    with pytest.raises(ValueError, match="Unsupported temporal period"):
        analytics.temporal_trends("minute", db_path=database_path)


def test_severity_distribution_reuses_generic_aggregation(database_path):
    result = analytics.severity_distribution(
        {"start_year": 2020, "end_year": 2020}, db_path=database_path
    )
    counts = {item["severity"]: item["collision_count"] for item in result}
    assert counts == {"Fatal": 1, "Property Damage Only": 1}


def test_hotspots_exclude_missing_coordinates_and_rank_cells(database_path):
    result = analytics.geographic_hotspots(
        grid_size=0.01, limit=2, db_path=database_path
    )

    assert len(result) == 2
    assert result[0]["collision_count"] == 2
    assert sum(item["collision_count"] for item in result) == 3
    assert set(result[0]) == {
        "latitude_cell",
        "longitude_cell",
        "collision_count",
        "total_fatalities",
        "total_injuries",
    }

    with pytest.raises(ValueError, match="grid_size must be"):
        analytics.geographic_hotspots(grid_size=0, db_path=database_path)
    with pytest.raises(ValueError, match="limit must be"):
        analytics.geographic_hotspots(limit=True, db_path=database_path)


def test_filter_options_preserve_valid_categories_and_exclude_null(database_path):
    options = analytics.filter_options(db_path=database_path)

    assert "Not Stated" in options["weather"]
    assert None not in options["weather"]
    assert "None" in options["collision_type"]
    assert None not in options["location"]
    assert options["severity"] == sorted(options["severity"])


def test_empty_results(database_path):
    filters = {"start_date": "2019-01-01", "end_date": "2019-12-31"}
    assert analytics.summary_statistics(filters, db_path=database_path) == {
        "total_collisions": 0,
        "total_fatalities": 0,
        "total_injuries": 0,
    }
    assert analytics.aggregate_collisions(
        "year", filters, db_path=database_path
    ) == []
    assert analytics.geographic_hotspots(
        filters, db_path=database_path
    ) == []


def test_mcp_tools_delegate_to_shared_analytics(database_path, monkeypatch):
    monkeypatch.setattr(analytics, "DEFAULT_DATABASE_PATH", database_path)
    filters = {"start_year": 2021, "end_year": 2022}

    assert get_summary_statistics(filters) == analytics.summary_statistics(filters)
    assert get_temporal_trends("year", filters) == analytics.temporal_trends(
        "year", filters
    )
    assert get_severity_distribution(filters) == analytics.severity_distribution(
        filters
    )
    assert get_geographic_hotspots(filters, 0.01, 5) == analytics.geographic_hotspots(
        filters, 0.01, 5
    )
    assert get_filter_options() == analytics.filter_options()

    tool_names = {tool.name for tool in mcp._tool_manager.list_tools()}
    assert tool_names == {
        "get_summary_statistics",
        "get_temporal_trends",
        "get_severity_distribution",
        "get_geographic_hotspots",
        "get_filter_options",
    }
