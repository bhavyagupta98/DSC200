import argparse
import math
import os
import random
import sys
import time
import uuid
from pathlib import Path

import duckdb
import matplotlib


PROJECT_ROOT = Path(__file__).resolve().parents[1]
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(PROJECT_ROOT))

from collision_pipeline import DUCKDB_SCHEMA
from src.analytics import (
    collision_type_distribution,
    geographic_hotspots,
    severity_distribution,
    summary_statistics,
    temporal_trends,
)


DEFAULT_PARQUET_PATH = PROJECT_ROOT / "data" / "processed" / "collisions.parquet"
DEFAULT_SNAPSHOT_DIR = PROJECT_ROOT / "evaluation" / "snapshots"
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "evaluation" / "filter_latency_summary.md"
DEFAULT_PLOT_PATH = PROJECT_ROOT / "evaluation" / "filter_latency_trends.png"

SCALES = (
    (25, 59_897),
    (50, 119_794),
    (75, 179_691),
    (100, 239_588),
)

QUERY_CASES = (
    {
        "id": "summary_simple",
        "function": "summary_statistics",
        "query_type": "simple",
        "arguments": {"filters": {"start_year": 2022, "end_year": 2022}},
    },
    {
        "id": "summary_compound",
        "function": "summary_statistics",
        "query_type": "compound",
        "arguments": {
            "filters": {
                "start_year": 2019,
                "end_year": 2023,
                "severity": "Fatal",
                "alcohol_involved": True,
            }
        },
    },
    {
        "id": "temporal_simple",
        "function": "temporal_trends",
        "query_type": "simple",
        "arguments": {"period": "year", "filters": {"severity": "Fatal"}},
    },
    {
        "id": "temporal_compound",
        "function": "temporal_trends",
        "query_type": "compound",
        "arguments": {
            "period": "hour",
            "filters": {
                "start_year": 2019,
                "end_year": 2023,
                "highway_type": "State Highway",
                "weather": ["Clear", "Raining"],
            },
        },
    },
    {
        "id": "severity_simple",
        "function": "severity_distribution",
        "query_type": "simple",
        "arguments": {"filters": {"start_year": 2022, "end_year": 2022}},
    },
    {
        "id": "severity_compound",
        "function": "severity_distribution",
        "query_type": "compound",
        "arguments": {
            "filters": {
                "start_date": "2019-01-01",
                "end_date": "2023-12-31",
                "alcohol_involved": True,
                "highway_type": "Not State Highway",
            }
        },
    },
    {
        "id": "collision_type_simple",
        "function": "collision_type_distribution",
        "query_type": "simple",
        "arguments": {
            "filters": {"start_year": 2022, "end_year": 2022},
            "limit": 5,
        },
    },
    {
        "id": "collision_type_compound",
        "function": "collision_type_distribution",
        "query_type": "compound",
        "arguments": {
            "filters": {
                "start_year": 2019,
                "end_year": 2022,
                "severity": ["Fatal", "Injury (Severe)"],
                "weather": ["Clear", "Raining"],
                "location": "San Diego",
            },
            "limit": 5,
        },
    },
    {
        "id": "hotspots_simple",
        "function": "geographic_hotspots",
        "query_type": "simple",
        "arguments": {
            "filters": {"alcohol_involved": True},
            "grid_size": 0.01,
            "limit": 10,
        },
    },
    {
        "id": "hotspots_compound",
        "function": "geographic_hotspots",
        "query_type": "compound",
        "arguments": {
            "filters": {
                "start_year": 2019,
                "end_year": 2023,
                "severity": ["Fatal", "Injury (Severe)"],
                "min_latitude": 32.70,
                "max_latitude": 32.90,
                "min_longitude": -117.30,
                "max_longitude": -117.00,
            },
            "grid_size": 0.01,
            "limit": 10,
        },
    },
)

QUERY_FUNCTIONS = {
    "summary_statistics": summary_statistics,
    "temporal_trends": temporal_trends,
    "severity_distribution": severity_distribution,
    "collision_type_distribution": collision_type_distribution,
    "geographic_hotspots": geographic_hotspots,
}

def snapshot_path(snapshot_dir, scale_percent):
    return snapshot_dir / f"collisions_{scale_percent}.duckdb"


def validate_source_parquet(parquet_path):
    connection = duckdb.connect()
    try:
        row_count = connection.execute(
            "SELECT COUNT(*) FROM read_parquet(?)", [str(parquet_path)]
        ).fetchone()[0]
    finally:
        connection.close()
    if row_count != SCALES[-1][1]:
        raise ValueError(
            f"Parquet contains {row_count} rows; expected {SCALES[-1][1]}"
        )


def create_snapshot(parquet_path, database_path, row_count):
    database_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = database_path.with_name(
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
        connection = duckdb.connect(str(temporary_path))
        connection.execute(f"CREATE TABLE collisions ({column_definitions})")
        connection.execute(
            f"INSERT INTO collisions SELECT {selected_columns} "
            "FROM read_parquet(?) "
            "ORDER BY hash(sandag_case_id, collision_date, collision_time, "
            "latitude_sandag, longitude_sandag, shape) LIMIT ?",
            [str(parquet_path), row_count],
        )
        connection.close()
        connection = None
        os.replace(temporary_path, database_path)
    finally:
        if connection is not None:
            connection.close()
        if temporary_path.exists():
            temporary_path.unlink()


def validate_snapshot(database_path, expected_rows):
    connection = duckdb.connect(str(database_path), read_only=True)
    try:
        row_count = connection.execute("SELECT COUNT(*) FROM collisions").fetchone()[0]
        schema = connection.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name = 'collisions' ORDER BY ordinal_position"
        ).fetchall()
    finally:
        connection.close()
    if row_count != expected_rows:
        raise ValueError(
            f"{database_path} contains {row_count} rows; expected {expected_rows}"
        )
    if schema != DUCKDB_SCHEMA:
        raise ValueError(f"{database_path} does not match the production schema")


def prepare_snapshots(parquet_path, snapshot_dir, rebuild):
    validate_source_parquet(parquet_path)
    snapshots = []
    for scale_percent, row_count in SCALES:
        database_path = snapshot_path(snapshot_dir, scale_percent)
        if rebuild or not database_path.exists():
            create_snapshot(parquet_path, database_path, row_count)
        validate_snapshot(database_path, row_count)
        snapshots.append((scale_percent, row_count, database_path))
    return snapshots


def percentile_95(values):
    ordered = sorted(values)
    index = max(0, math.ceil(0.95 * len(ordered)) - 1)
    return ordered[index]


def execute_case(case, database_path):
    function = QUERY_FUNCTIONS[case["function"]]
    return function(db_path=database_path, **case["arguments"])


def summarize_timings(scale_percent, database_rows, case, timings):
    return {
        "scale": f"{scale_percent}%",
        "rows": database_rows,
        "query": case["function"],
        "query_type": case["query_type"],
        "p95_ms": round(percentile_95(timings), 3),
        "max_ms": round(max(timings), 3),
    }


def benchmark_snapshot(
    scale_percent,
    database_rows,
    database_path,
    repetitions,
    warmups,
    seed,
):
    baselines = {}
    timings = {case["id"]: [] for case in QUERY_CASES}

    for case in QUERY_CASES:
        query_id = case["id"]
        baseline = execute_case(case, database_path)
        baselines[query_id] = baseline
        for _ in range(warmups):
            result = execute_case(case, database_path)
            if result != baseline:
                raise ValueError(f"Warm-up result changed for {query_id}")

    schedule = [
        case
        for case in QUERY_CASES
        for _ in range(repetitions)
    ]
    random.Random(seed + scale_percent).shuffle(schedule)

    for case in schedule:
        query_id = case["id"]
        started = time.perf_counter_ns()
        result = execute_case(case, database_path)
        elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
        if result != baselines[query_id]:
            raise ValueError(f"Measured result changed for {query_id}")
        timings[query_id].append(elapsed_ms)

    return [
        summarize_timings(
            scale_percent=scale_percent,
            database_rows=database_rows,
            case=case,
            timings=timings[case["id"]],
        )
        for case in QUERY_CASES
    ]


def write_report(rows, output_path, plot_path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_name(
        f".{output_path.name}.{uuid.uuid4().hex}.tmp"
    )
    try:
        with temporary_path.open("w", encoding="utf-8") as output:
            output.write("# Filter Query Latency\n\n")
            output.write(f"![Latency trends]({plot_path.name})\n\n")
            output.write(
                "| Scale | Rows | Query | Query Type | P95 (ms) | Max (ms) |\n"
            )
            output.write("|---:|---:|---|---|---:|---:|\n")
            for row in rows:
                output.write(
                    f"| {row['scale']} | {row['rows']:,} | {row['query']} | "
                    f"{row['query_type']} | {row['p95_ms']:.3f} | "
                    f"{row['max_ms']:.3f} |\n"
                )
        os.replace(temporary_path, output_path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def write_plot(rows, plot_path):
    plot_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = plot_path.with_name(
        f".{plot_path.name}.{uuid.uuid4().hex}.tmp"
    )
    colors = plt.get_cmap("tab10").colors
    color_by_query = {
        query: colors[index]
        for index, query in enumerate(QUERY_FUNCTIONS)
    }
    figure, axes = plt.subplots(1, 2, figsize=(13, 5), sharex=True, sharey=True)
    try:
        for axis, query_type in zip(axes, ("simple", "compound")):
            for query in QUERY_FUNCTIONS:
                points = sorted(
                    (
                        row
                        for row in rows
                        if row["query"] == query
                        and row["query_type"] == query_type
                    ),
                    key=lambda row: row["rows"],
                )
                axis.plot(
                    [row["rows"] for row in points],
                    [row["p95_ms"] for row in points],
                    color=color_by_query[query],
                    marker="o",
                    linewidth=2,
                    markersize=5,
                    label=query,
                )
            axis.set_title(f"{query_type.title()} filters")
            axis.set_xlabel("Database rows")
            axis.grid(axis="y", alpha=0.25)
            axis.set_xticks(
                [row_count for _, row_count in SCALES],
                [f"{row_count // 1000}k" for _, row_count in SCALES],
            )

        axes[0].set_ylabel("P95 latency (ms)")
        figure.suptitle("Query latency by dataset size", fontsize=14)
        handles, labels = axes[0].get_legend_handles_labels()
        figure.legend(
            handles,
            labels,
            loc="lower center",
            ncol=3,
            frameon=False,
        )
        figure.tight_layout(rect=(0, 0.14, 1, 0.94))
        figure.savefig(temporary_path, format="png", dpi=180)
        os.replace(temporary_path, plot_path)
    finally:
        plt.close(figure)
        if temporary_path.exists():
            temporary_path.unlink()


def run_benchmark(args):
    snapshots = prepare_snapshots(
        args.parquet,
        args.snapshot_dir,
        args.rebuild_snapshots,
    )
    rows = []
    for scale_percent, database_rows, database_path in snapshots:
        rows.extend(
            benchmark_snapshot(
                scale_percent,
                database_rows,
                database_path,
                args.repetitions,
                args.warmups,
                args.seed,
            )
        )
    write_plot(rows, args.plot_output)
    write_report(rows, args.output, args.plot_output)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Benchmark collision analytics across DuckDB sizes"
    )
    parser.add_argument("--parquet", type=Path, default=DEFAULT_PARQUET_PATH)
    parser.add_argument("--snapshot-dir", type=Path, default=DEFAULT_SNAPSHOT_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--plot-output", type=Path, default=DEFAULT_PLOT_PATH)
    parser.add_argument("--repetitions", type=int, default=100)
    parser.add_argument("--warmups", type=int, default=5)
    parser.add_argument("--seed", type=int, default=200)
    parser.add_argument("--rebuild-snapshots", action="store_true")
    args = parser.parse_args()
    if args.repetitions <= 0:
        parser.error("--repetitions must be positive")
    if args.warmups < 0:
        parser.error("--warmups cannot be negative")
    return args


if __name__ == "__main__":
    run_benchmark(parse_args())
