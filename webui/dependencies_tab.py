"""Dependencies tab: add and remove finish-to-start links, and show the network check."""
from __future__ import annotations

import streamlit as st

from buildos.errors import BuildOSError
from buildos.models import Activity, Project
from buildos.tables import dependencies_to_dataframe

from .common import Services, flash, show_error


def _label(activity: Activity) -> str:
    return f"{activity.code} - {activity.name}"


def render_dependencies_tab(services: Services, project: Project) -> None:
    activities = services.activities.list_activities(project.id)
    dependencies = services.activities.list_dependencies(project.id)

    st.subheader(f"Dependencies in '{project.name}'")
    st.caption(
        "Every link is finish-to-start (FS): the successor cannot start until the "
        "predecessor has finished. Lag and lead are not supported in version one."
    )

    problems = services.activities.check_project_network(project.id)
    if problems:
        for problem in problems:
            st.error(problem)
    elif activities:
        st.success("Network check passed: no circular dependencies.")

    if len(activities) < 2:
        st.info("Add at least two activities before creating dependencies.")
        return

    by_id = {a.id: a for a in activities}
    ids = list(by_id)

    st.markdown("#### Add a dependency")
    with st.form(f"add_dependency_form_{project.id}"):
        predecessor_id = st.selectbox(
            "Predecessor (finishes first)", options=ids, format_func=lambda i: _label(by_id[i])
        )
        successor_id = st.selectbox(
            "Successor (starts after)", options=ids, index=1, format_func=lambda i: _label(by_id[i])
        )
        submitted = st.form_submit_button("Add dependency")
    if submitted:
        try:
            services.activities.add_dependency(project.id, predecessor_id, successor_id)
        except BuildOSError as exc:
            show_error(exc)
        else:
            flash("success", f"{by_id[predecessor_id].code} -> {by_id[successor_id].code} added.")
            st.rerun()

    st.markdown("#### Existing dependencies")
    if not dependencies:
        st.info("No dependencies yet.")
        return
    st.dataframe(dependencies_to_dataframe(activities, dependencies), hide_index=True)

    dep_by_id = {d.id: d for d in dependencies}

    def _dep_label(dep_id: int) -> str:
        dep = dep_by_id[dep_id]
        return f"{by_id[dep.predecessor_id].code} -> {by_id[dep.successor_id].code}"

    remove_id = st.selectbox("Dependency to remove", options=list(dep_by_id), format_func=_dep_label)
    if st.button("Remove selected dependency"):
        try:
            services.activities.remove_dependency(remove_id)
        except BuildOSError as exc:
            show_error(exc)
        else:
            flash("success", f"Removed {_dep_label(remove_id)}.")
            st.rerun()
