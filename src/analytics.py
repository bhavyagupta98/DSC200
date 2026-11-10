from math import isfinite

from src.db import DEFAULT_DATABASE_PATH, build_where_clause, execute_query


GROUPINGS = {
    "year": ("collision_year", "year"),
    "month": ("collision_month", "month"),
    "weekday": ("collision_weekday", "weekday"),
    "hour": ("collision_hour", "hour"),
    "severity": ("severity_normalized", "severity"),
    "weather": ("weather_1", "weather"),
    "collision_type": ("type_of_collision", "collision_type"),
}

TEMPORAL_PERIODS = {"year", "month", "weekday", "hour"}

FILTER_OPTION_COLUMNS = {
    "severity": "severity_normalized",
    "weather": "weather_1",
    "collision_type": "type_of_collision",
    "weekday": "collision_weekday",
    "location": "location_sandag",
}


def _database_path(db_path):
    return db_path if db_path is not None else DEFAULT_DATABASE_PATH


def summary_statistics(filters=None, db_path=None):
    where_clause, parameters = build_where_clause(filters)
    rows = execute_query(
        "SELECT COUNT(*) AS total_collisions, "
        "COALESCE(SUM(number_killed), 0) AS total_fatalities, "
        "COALESCE(SUM(number_injured), 0) AS total_injuries "
        f"FROM collisions{where_clause}",
        parameters,
        _database_path(db_path),
    )
    return rows[0]


def aggregate_collisions(group_by, filters=None, db_path=None):
    if group_by not in GROUPINGS:
        raise ValueError(f"Unsupported group_by: {group_by}")
    column, result_name = GROUPINGS[group_by]
    where_clause, parameters = build_where_clause(filters)
    null_condition = " AND " if where_clause else " WHERE "
    sql = (
        f"SELECT {column} AS {result_name}, COUNT(*) AS collision_count, "
        "COALESCE(SUM(number_killed), 0) AS total_fatalities, "
        "COALESCE(SUM(number_injured), 0) AS total_injuries "
        f"FROM collisions{where_clause}{null_condition}{column} IS NOT NULL "
        f"GROUP BY {column} ORDER BY {column}"
    )
    return execute_query(sql, parameters, _database_path(db_path))


def temporal_trends(period, filters=None, db_path=None):
    if period not in TEMPORAL_PERIODS:
        raise ValueError(f"Unsupported temporal period: {period}")
    return aggregate_collisions(period, filters, db_path)


def severity_distribution(filters=None, db_path=None):
    return aggregate_collisions("severity", filters, db_path)


def geographic_hotspots(filters=None, grid_size=0.01, limit=10, db_path=None):
    if (
        isinstance(grid_size, bool)
        or not isinstance(grid_size, (int, float))
        or not isfinite(grid_size)
        or grid_size <= 0
    ):
        raise ValueError("grid_size must be a positive finite number")
    if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
        raise ValueError("limit must be a positive integer")

    where_clause, filter_parameters = build_where_clause(filters)
    coordinate_condition = " AND " if where_clause else " WHERE "
    sql = (
        "WITH grid AS ("
        "SELECT ROUND(FLOOR(latitude_sandag / ?) * ?, 10) AS latitude_cell, "
        "ROUND(FLOOR(longitude_sandag / ?) * ?, 10) AS longitude_cell, "
        "number_killed, number_injured "
        f"FROM collisions{where_clause}{coordinate_condition}"
        "latitude_sandag IS NOT NULL AND longitude_sandag IS NOT NULL"
        ") "
        "SELECT latitude_cell, longitude_cell, COUNT(*) AS collision_count, "
        "COALESCE(SUM(number_killed), 0) AS total_fatalities, "
        "COALESCE(SUM(number_injured), 0) AS total_injuries "
        "FROM grid GROUP BY latitude_cell, longitude_cell "
        "ORDER BY collision_count DESC, latitude_cell, longitude_cell LIMIT ?"
    )
    parameters = [grid_size, grid_size, grid_size, grid_size]
    parameters.extend(filter_parameters)
    parameters.append(limit)
    return execute_query(sql, parameters, _database_path(db_path))


def filter_options(db_path=None):
    options = {}
    for name, column in FILTER_OPTION_COLUMNS.items():
        rows = execute_query(
            f"SELECT DISTINCT {column} AS value FROM collisions "
            f"WHERE {column} IS NOT NULL ORDER BY {column}",
            db_path=_database_path(db_path),
        )
        options[name] = [row["value"] for row in rows]
    return options
