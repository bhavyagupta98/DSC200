from datetime import date, datetime
from math import isfinite
from pathlib import Path

import duckdb


DEFAULT_DATABASE_PATH = Path(__file__).resolve().parents[1] / "data" / "collisions.duckdb"

CATEGORICAL_FILTERS = {
    "severity": "severity_normalized",
    "weather": "weather_1",
    "collision_type": "type_of_collision",
    "weekday": "collision_weekday",
    "location": "location_sandag",
}

BOOLEAN_FILTERS = {
    "pedestrian_accident": "pedestrian_accident",
    "bicycle_accident": "bicycle_accident",
    "motorcycle_accident": "motorcycle_accident",
    "truck_accident": "truck_accident",
    "alcohol_involved": "alcohol_involved",
}

RANGE_FILTERS = {
    "start_date": ("collision_date", ">="),
    "end_date": ("collision_date", "<="),
    "start_year": ("collision_year", ">="),
    "end_year": ("collision_year", "<="),
    "min_latitude": ("latitude_sandag", ">="),
    "max_latitude": ("latitude_sandag", "<="),
    "min_longitude": ("longitude_sandag", ">="),
    "max_longitude": ("longitude_sandag", "<="),
}

SUPPORTED_FILTERS = set(CATEGORICAL_FILTERS) | set(BOOLEAN_FILTERS) | set(
    RANGE_FILTERS
)

FILTER_ORDER = [
    "start_date",
    "end_date",
    "start_year",
    "end_year",
    "severity",
    "weather",
    "collision_type",
    "weekday",
    "location",
    "pedestrian_accident",
    "bicycle_accident",
    "motorcycle_accident",
    "truck_accident",
    "alcohol_involved",
    "min_latitude",
    "max_latitude",
    "min_longitude",
    "max_longitude",
]


def _parse_date(value, name):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as error:
            raise ValueError(f"{name} must be a valid ISO date") from error
    raise ValueError(f"{name} must be a valid ISO date")


def _validate_filters(filters):
    if filters is None:
        return {}
    if not isinstance(filters, dict):
        raise ValueError("filters must be a dictionary")

    unsupported = sorted(set(filters) - SUPPORTED_FILTERS)
    if unsupported:
        raise ValueError(f"Unsupported filters: {unsupported}")

    validated = {}
    for name, value in filters.items():
        if name in CATEGORICAL_FILTERS:
            values = value if isinstance(value, (list, tuple)) else [value]
            if not values:
                raise ValueError(f"{name} cannot be empty")
            if any(not isinstance(item, str) for item in values):
                raise ValueError(f"{name} must contain strings")
            validated[name] = list(values)
        elif name in BOOLEAN_FILTERS:
            if not isinstance(value, bool):
                raise ValueError(f"{name} must be a boolean")
            validated[name] = value
        elif name in ("start_date", "end_date"):
            validated[name] = _parse_date(value, name)
        elif name in ("start_year", "end_year"):
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{name} must be an integer")
            if not 2014 <= value <= 2023:
                raise ValueError(f"{name} must be between 2014 and 2023")
            validated[name] = value
        else:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{name} must be numeric")
            value = float(value)
            if not isfinite(value):
                raise ValueError(f"{name} must be finite")
            if "latitude" in name and not -90 <= value <= 90:
                raise ValueError(f"{name} must be between -90 and 90")
            if "longitude" in name and not -180 <= value <= 180:
                raise ValueError(f"{name} must be between -180 and 180")
            validated[name] = value

    if validated.get("start_date") and validated.get("end_date"):
        if validated["start_date"] > validated["end_date"]:
            raise ValueError("start_date cannot exceed end_date")
    if validated.get("start_year") and validated.get("end_year"):
        if validated["start_year"] > validated["end_year"]:
            raise ValueError("start_year cannot exceed end_year")
    for minimum, maximum in (
        ("min_latitude", "max_latitude"),
        ("min_longitude", "max_longitude"),
    ):
        if minimum in validated and maximum in validated:
            if validated[minimum] > validated[maximum]:
                raise ValueError(f"{minimum} cannot exceed {maximum}")
    return validated


def build_where_clause(filters=None):
    validated = _validate_filters(filters)
    conditions = []
    parameters = []

    for name in FILTER_ORDER:
        if name not in validated:
            continue
        value = validated[name]
        if name in CATEGORICAL_FILTERS:
            column = CATEGORICAL_FILTERS[name]
            placeholders = ", ".join("?" for _ in value)
            conditions.append(f"{column} IN ({placeholders})")
            parameters.extend(value)
        elif name in BOOLEAN_FILTERS:
            conditions.append(f"{BOOLEAN_FILTERS[name]} = ?")
            parameters.append(value)
        else:
            column, operator = RANGE_FILTERS[name]
            conditions.append(f"{column} {operator} ?")
            parameters.append(value)

    if not conditions:
        return "", []
    return " WHERE " + " AND ".join(conditions), parameters


def execute_query(sql, parameters=None, db_path=None):
    path = Path(db_path or DEFAULT_DATABASE_PATH)
    connection = duckdb.connect(str(path), read_only=True)
    try:
        cursor = connection.execute(sql, parameters or [])
        columns = [item[0] for item in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    finally:
        connection.close()
