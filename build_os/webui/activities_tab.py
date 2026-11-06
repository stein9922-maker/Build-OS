"""Activities tab: list, add, edit and delete activities."""
from __future__ import annotations

import streamlit as st

from buildos.errors import BuildOSError
from buildos.models import Activity, Project
from buildos.tables import activities_to_dataframe
from buildos.validation import (
    MAX_ACTIVITY_NAME_LEN,
    MAX_CODE_LEN,
    MAX_DURATION_DAYS,
    MAX_NOTES_LEN,
)

from .common import Services, flash, form_nonce, reset_form, show_error


def _label(activity: Activity) -> str:
    return f"{activity.code} - {activity.name}"


def render_activities_tab(services: Services, project: Project) -> None:
    activities = services.activities.list_activities(project.id)
    dependencies = services.activities.list_dependencies(project.id)

    st.subheader(f"Activities in '{project.name}'")
    st.caption("Durations are whole calendar days. A duration of 0 is a milestone.")
    if activities:
        st.dataframe(activities_to_dataframe(activities, dependencies), hide_index=True)
    else:
        st.info("No activities yet. Add the first one below.")

    _render_add_form(services, project)
    if activities:
        st.divider()
        _render_edit_and_delete(services, activities)


def _render_add_form(services: Services, project: Project) -> None:
    st.markdown("#### Add an activity")
    nonce = form_nonce(f"add_activity_{project.id}")
    suffix = f"{project.id}_{nonce}"
    with st.form(f"add_activity_form_{suffix}"):
        col_code, col_name, col_duration = st.columns([1, 3, 1])
        code = col_code.text_input(
            "Code", placeholder="A100", max_chars=MAX_CODE_LEN, key=f"aa_code_{suffix}"
        )
        name = col_name.text_input(
            "Name", max_chars=MAX_ACTIVITY_NAME_LEN, key=f"aa_name_{suffix}"
        )
        duration = col_duration.number_input(
            "Duration (days)", min_value=0, max_value=MAX_DURATION_DAYS, value=1, step=1,
            key=f"aa_dur_{suffix}",
        )
        notes = st.text_area("Notes (optional)", max_chars=MAX_NOTES_LEN, key=f"aa_notes_{suffix}")
        submitted = st.form_submit_button("Add activity")
    if submitted:
        try:
            created = services.activities.add_activity(project.id, code, name, int(duration), notes)
        except BuildOSError as exc:
            show_error(exc)
        else:
            reset_form(f"add_activity_{project.id}")
            flash("success", f"Added activity {created.code}.")
            st.rerun()


def _render_edit_and_delete(services: Services, activities: list[Activity]) -> None:
    st.markdown("#### Edit or delete an activity")
    by_id = {a.id: a for a in activities}
    chosen_id = st.selectbox(
        "Choose an activity", options=list(by_id), format_func=lambda i: _label(by_id[i])
    )
    activity = by_id[chosen_id]

    with st.form(f"edit_activity_form_{activity.id}"):
        col_code, col_name, col_duration = st.columns([1, 3, 1])
        code = col_code.text_input(
            "Code", value=activity.code, max_chars=MAX_CODE_LEN, key=f"ea_code_{activity.id}"
        )
        name = col_name.text_input(
            "Name", value=activity.name, max_chars=MAX_ACTIVITY_NAME_LEN, key=f"ea_name_{activity.id}"
        )
        duration = col_duration.number_input(
            "Duration (days)", min_value=0, max_value=MAX_DURATION_DAYS,
            value=activity.duration_days, step=1, key=f"ea_dur_{activity.id}",
        )
        notes = st.text_area(
            "Notes", value=activity.notes, max_chars=MAX_NOTES_LEN, key=f"ea_notes_{activity.id}"
        )
        submitted = st.form_submit_button("Save activity")
    if submitted:
        try:
            services.activities.update_activity(activity.id, code, name, int(duration), notes)
        except BuildOSError as exc:
            show_error(exc)
        else:
            flash("success", f"Saved activity {code.strip().upper()}.")
            st.rerun()

    confirmed = st.checkbox(
        f"Yes, delete {activity.code} and every dependency link attached to it",
        key=f"confirm_delete_activity_{activity.id}",
    )
    if st.button("Delete activity", disabled=not confirmed, key=f"delete_activity_{activity.id}"):
        try:
            removed_links = services.activities.delete_activity(activity.id)
        except BuildOSError as exc:
            show_error(exc)
        else:
            flash("success", f"Deleted {activity.code} (and {removed_links} dependency link(s)).")
            st.rerun()
