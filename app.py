"""Build OS - Streamlit entry point.  Run with:  streamlit run app.py

This file only arranges the page. All rules live in the `buildos` package.
"""
import streamlit as st

from webui import common
from webui.activities_tab import render_activities_tab
from webui.dependencies_tab import render_dependencies_tab
from webui.project_tab import render_project_tab
from webui.procurement_tab import render_procurement_tab
from webui.schedule_tab import render_schedule_tab
from webui.sidebar import render_sidebar

st.set_page_config(page_title="Build OS", page_icon="🏗️", layout="wide")

services = common.get_services()

st.title("Build OS")
st.caption(
    "Local construction scheduling and procurement. "
    "Stage 3.1: CPM scheduling, material procurement, supplier price comparison and downloadable reports."
)

common.show_flash()
project = render_sidebar(services)

tab_project, tab_activities, tab_dependencies, tab_schedule, tab_procurement = st.tabs(
    ["Project", "Activities", "Dependencies", "Schedule", "Procurement"]
)

with tab_project:
    render_project_tab(services, project)

with tab_activities:
    if project is None:
        st.info("Select or create a project first.")
    else:
        render_activities_tab(services, project)

with tab_dependencies:
    if project is None:
        st.info("Select or create a project first.")
    else:
        render_dependencies_tab(services, project)

with tab_schedule:
    if project is None:
        st.info("Select or create a project first.")
    else:
        render_schedule_tab(services, project)

with tab_procurement:
    if project is None:
        st.info("Select or create a project first.")
    else:
        render_procurement_tab(services, project)
