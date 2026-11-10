from typing import Any

from mcp.server.fastmcp import FastMCP

from src import analytics


mcp = FastMCP("Collision Analytics")


@mcp.tool()
def get_summary_statistics(filters: dict[str, Any] | None = None) -> dict:
    """Return totals; put year, severity, and other filters inside `filters`."""
    return analytics.summary_statistics(filters)


@mcp.tool()
def get_temporal_trends(
    period: str, filters: dict[str, Any] | None = None
) -> list[dict]:
    """Return collision and casualty trends by year, month, weekday, or hour."""
    return analytics.temporal_trends(period, filters)


@mcp.tool()
def get_severity_distribution(filters: dict[str, Any] | None = None) -> list[dict]:
    """Return collision and casualty totals by normalized severity."""
    return analytics.severity_distribution(filters)


@mcp.tool()
def get_geographic_hotspots(
    filters: dict[str, Any] | None = None,
    grid_size: float = 0.01,
    limit: int = 10,
) -> list[dict]:
    """Rank coordinate grid cells by collisions; normally use grid_size 0.01."""
    return analytics.geographic_hotspots(filters, grid_size, limit)


@mcp.tool()
def get_filter_options() -> dict[str, list]:
    """Return available values for supported categorical filters."""
    return analytics.filter_options()


if __name__ == "__main__":
    mcp.run()
