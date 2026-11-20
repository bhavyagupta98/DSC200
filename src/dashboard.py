import argparse

import streamlit as st
import pandas as pd

from src.analytics import (
    summary_statistics,
    temporal_trends,
    severity_distribution,
    geographic_hotspots,
)


def render_dashboard():
    st.title("San Diego Traffic Collision Dashboard")
    st.write("Explore historical SANDAG collision data from 2014–2023.")

    st.sidebar.header("Filters")
    year_range = st.sidebar.slider(
        "Select years",
        min_value=2014,
        max_value=2023,
        value=(2014, 2023),
    )

    filters = {
        "start_year": year_range[0],
        "end_year": year_range[1],
    }

    summary = summary_statistics(filters)
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Collisions", f"{summary['total_collisions']:,}")
    col2.metric("Fatalities", f"{summary['total_fatalities']:,}")
    col3.metric("Injuries", f"{summary['total_injuries']:,}")

    st.header("Collision Trends by Year")
    yearly_df = pd.DataFrame(temporal_trends("year", filters))
    if not yearly_df.empty:
        st.line_chart(yearly_df.set_index("year")["collision_count"])

    st.header("Collisions by Hour")
    hourly_df = pd.DataFrame(temporal_trends("hour", filters))
    if not hourly_df.empty:
        st.bar_chart(hourly_df.set_index("hour")["collision_count"])

    st.header("Collision Severity")
    severity_df = pd.DataFrame(severity_distribution(filters))
    if not severity_df.empty:
        st.bar_chart(severity_df.set_index("severity")["collision_count"])

    st.header("Collision Hotspots")
    hotspot_df = pd.DataFrame(
        geographic_hotspots(filters=filters, grid_size=0.01, limit=100)
    )
    if not hotspot_df.empty:
        map_df = hotspot_df.rename(
            columns={
                "latitude_cell": "lat",
                "longitude_cell": "lon",
            }
        )
        st.map(map_df, size="collision_count")

    st.caption(
        "Hotspots represent historical collision counts, "
        "not traffic-adjusted accident risk."
    )


def chat_enabled():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--chat", action="store_true")
    arguments, _ = parser.parse_known_args()
    return arguments.chat


if __name__ == "__main__":
    st.set_page_config(
        page_title="SANDAG Traffic Dashboard",
        page_icon="🚗",
        layout="wide",
    )

    if chat_enabled():
        from src.chat import render_chat

        navigation = st.navigation(
            [
                st.Page(render_dashboard, title="Visual Analytics", icon="📊"),
                st.Page(render_chat, title="Chat", icon="💬"),
            ]
        )
        navigation.run()
    else:
        render_dashboard()
