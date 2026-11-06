"""Project tab: create, edit and delete projects."""
from __future__ import annotations

from datetime import date

import streamlit as st

from buildos.errors import BuildOSError
from buildos.models import Project
from buildos.validation import MAX_DESCRIPTION_LEN, MAX_PROJECT_NAME_LEN

from .common import Services, flash, form_nonce, reset_form, show_error
from .sidebar import select_project_on_next_run


def render_project_tab(services: Services, project: Project | None) -> None:
    _render_create_form(services)
    if project is not None:
        st.divider()
        _render_edit_form(services, project)
        _render_delete_section(services, project)


def _render_create_form(services: Services) -> None:
    st.subheader("Create a project")
    nonce = form_nonce("create_project")
    with st.form(f"create_project_form_{nonce}"):
        name = st.text_input("Project name", max_chars=MAX_PROJECT_NAME_LEN, key=f"cp_name_{nonce}")
        start = st.date_input("Planned start date", value=date.today(), key=f"cp_start_{nonce}")
        description = st.text_area(
            "Description (optional)", max_chars=MAX_DESCRIPTION_LEN, key=f"cp_desc_{nonce}"
        )
        submitted = st.form_submit_button("Create project")
    if submitted:
        try:
            created = services.projects.create_project(name, start, description)
        except BuildOSError as exc:
            show_error(exc)
        else:
            reset_form("create_project")
            select_project_on_next_run(created.id)
            flash("success", f"Created project '{created.name}'.")
            st.rerun()


def _render_edit_form(services: Services, project: Project) -> None:
    st.subheader(f"Edit project: {project.name}")
    with st.form(f"edit_project_form_{project.id}"):
        name = st.text_input(
            "Project name", value=project.name, max_chars=MAX_PROJECT_NAME_LEN,
            key=f"ep_name_{project.id}",
        )
        start = st.date_input(
            "Planned start date", value=project.start_date, key=f"ep_start_{project.id}"
        )
        description = st.text_area(
            "Description", value=project.description, max_chars=MAX_DESCRIPTION_LEN,
            key=f"ep_desc_{project.id}",
        )
        submitted = st.form_submit_button("Save project")
    if submitted:
        try:
            services.projects.update_project(project.id, name, start, description)
        except BuildOSError as exc:
            show_error(exc)
        else:
            flash("success", "Project saved.")
            st.rerun()


def _render_delete_section(services: Services, project: Project) -> None:
    with st.expander("Danger zone: delete this project"):
        st.warning(
            "Deleting a project permanently removes all of its activities and dependencies."
        )
        confirmed = st.checkbox(
            f"Yes, permanently delete '{project.name}'", key=f"confirm_delete_project_{project.id}"
        )
        if st.button("Delete project", disabled=not confirmed, key=f"delete_project_{project.id}"):
            try:
                services.projects.delete_project(project.id)
            except BuildOSError as exc:
                show_error(exc)
            else:
                flash("success", f"Deleted project '{project.name}'.")
                st.rerun()
