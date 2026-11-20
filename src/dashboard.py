
import streamlit as st
import pandas as pd

from src.analytics import (
    summary_statistics,
    temporal_trends,
    severity_distribution,
    geographic_hotspots,
    filter_options
)

st.set_page_config(
    page_title="SANDAG Traffic Dashboard",
    page_icon="🚗",
    layout="wide"
)

st.title("San Diego Traffic Collision Dashboard")
st.write("Explore historical SANDAG collision data from 2014–2023.")

# Sidebar filters
st.sidebar.header("Filters")

options = filter_options()

year_range = st.sidebar.slider(
    "Select years",
    min_value=2014,
    max_value=2023,
    value=(2014, 2023)
)

st.sidebar.subheader("Road Type")

state_hwy = st.sidebar.checkbox("State Highway", value=True)
not_state_hwy = st.sidebar.checkbox("Not State Highway", value=True)
not_stated = st.sidebar.checkbox("Unstated Road Type", value=True)


st.sidebar.subheader("Locality")

region_options = ["All Cities"] + options["location"]

selected_region = st.sidebar.selectbox(
    "Specific city, town, or reservation in the San Diego area.",
    options=region_options
)


st.sidebar.subheader("Collision Factors")

pcf_options = ["All Factors"] + options["pcf"]

selected_pcf = st.sidebar.selectbox(
    "Main contributor to collision.",
    options=pcf_options
)


filters = {
    "start_year": year_range[0],
    "end_year": year_range[1],
    "highway_type": [
        value for value, selected in [
            ("State Highway", state_hwy),
            ("Not State Highway", not_state_hwy),
            ("Not Stated", not_stated)
        ]
        if selected
    ],
}

if selected_region != "All Cities":
    filters["location"] = [selected_region]
if selected_pcf != "All Factors":
    filters["pcf"] = [selected_pcf]


# Error catching
if not filters["highway_type"]:
    st.warning("Please select at least one road type.")
    st.stop()



# Summary statistics
summary = summary_statistics(filters)

if summary['total_collisions'] == 0:
    st.warning("There are no documented collisions with this set of filters. "\
               "To resolve this, input a different combination in the sidebar.")
    st.stop()

col1, col2, col3 = st.columns(3)

col1.metric("Total Collisions", f"{summary['total_collisions']:,}")
col2.metric("Fatalities", f"{summary['total_fatalities']:,}")
col3.metric("Injuries", f"{summary['total_injuries']:,}")

# Collision trends
st.header("Collision Trends by Year")

yearly_data = temporal_trends("year", filters)
yearly_df = pd.DataFrame(yearly_data)

if not yearly_df.empty:
    st.line_chart(
        yearly_df.set_index("year")["collision_count"]
    )

# Hourly collisions
st.header("Collisions by Hour")

st.write("Labels are chronological, such that 0 corresponds to 12 A.M. and 23 corresponds to 11 P.M.")

hourly_data = temporal_trends("hour", filters)
hourly_df = pd.DataFrame(hourly_data)

if not hourly_df.empty:
    st.bar_chart(
        hourly_df.set_index("hour")["collision_count"]
    )

# Severity distribution
st.header("Collision Severity")

severity_data = severity_distribution(filters)
severity_df = pd.DataFrame(severity_data)

if not severity_df.empty:
    st.bar_chart(
        severity_df.set_index("severity")["collision_count"]
    )

# Geographic hotspots
st.header("Collision Hotspots")

hotspots = geographic_hotspots(
    filters=filters,
    grid_size=0.01,
    limit=100
)

hotspot_df = pd.DataFrame(hotspots)

if not hotspot_df.empty:
    map_df = hotspot_df.rename(
        columns={
            "latitude_cell": "lat",
            "longitude_cell": "lon"
        }
    )

    st.map(map_df, size="collision_count")

st.caption(
    "Hotspots represent historical collision counts, "
    "not traffic-adjusted accident risk."
)
