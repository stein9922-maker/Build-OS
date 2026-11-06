"""Sidebar: project picker, demo data loader and the visible list of assumptions."""
from __future__ import annotations

import streamlit as st

from buildos.config import ASSUMPTIONS
from buildos.errors import BuildOSError
from buildos.models import Project
from buildos.sample_data import load_sample_project

from .common import Services, flash

SELECTED_KEY = "selected_project_id"
NEXT_KEY = "_next_project_id"  # set by actions that want a particular project selected next run


def select_project_on_next_run(project_id: int) -> None:
    st.session_state[NEXT_KEY] = project_id


def render_sidebar(services: Services) -> Project | None:
    """Draw the sidebar and return the currently selected project (or None)."""
    st.sidebar.header("Projects")
    projects = services.projects.list_projects()
    by_id = {p.id: p for p in projects}

    # These two session_state edits must happen BEFORE the selectbox below is created.
    pending = st.session_state.pop(NEXT_KEY, None)
    if pending in by_id:
        st.session_state[SELECTED_KEY] = pending
    if st.session_state.get(SELECTED_KEY) not in by_id:
        st.session_state.pop(SELECTED_KEY, None)

    selected: Project | None = None
    if projects:
        selected_id = st.sidebar.selectbox(
            "Active project",
            options=list(by_id),
            format_func=lambda pid: by_id[pid].name,
            key=SELECTED_KEY,
        )
        selected = by_id[selected_id]
    else:
        st.sidebar.info("No projects yet. Create one in the Project tab, or load the demo project.")

    st.sidebar.divider()
    st.sidebar.subheader("Demo data")
    st.sidebar.caption(
        "Loads an ILLUSTRATIVE project with made-up durations so you can explore the app. "
        "It contains no material quantities."
    )
    if st.sidebar.button("Load demo project"):
        try:
            project = load_sample_project(services.projects, services.activities)
        except BuildOSError as exc:
            st.sidebar.error(str(exc))
        else:
            select_project_on_next_run(project.id)
            flash("success", f"Loaded '{project.name}'.")
            st.rerun()

    with st.sidebar.expander("Scheduling assumptions (v1)"):
        for assumption in ASSUMPTIONS:
            st.markdown(f"- {assumption}")

    return selected
