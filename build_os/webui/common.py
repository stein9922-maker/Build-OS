"""Small Streamlit helpers shared by every page. All business logic stays in `buildos`."""
from __future__ import annotations

from typing import NamedTuple

import streamlit as st

from buildos.config import DEFAULT_DB_PATH
from buildos.db import Database
from buildos.errors import BuildOSError, ValidationError
from buildos.services import ActivityService, ProjectService, ScheduleService


class Services(NamedTuple):
    projects: ProjectService
    activities: ActivityService
    schedule: ScheduleService

    @property
    def db(self) -> Database:
        # All services share the same Database instance.
        return self.projects._db


@st.cache_resource
def get_services() -> Services:
    """Create the database (once per server process) and the services that use it."""
    db = Database(DEFAULT_DB_PATH)
    db.initialize()
    return Services(ProjectService(db), ActivityService(db), ScheduleService(db))


# ---------- one-shot messages that survive st.rerun() ----------
_FLASH_KEY = "_flash_message"


def flash(kind: str, message: str) -> None:
    """Queue a message to show on the next run. kind: 'success', 'warning' or 'info'."""
    st.session_state[_FLASH_KEY] = (kind, message)


def show_flash() -> None:
    item = st.session_state.pop(_FLASH_KEY, None)
    if item is None:
        return
    kind, message = item
    {"success": st.success, "warning": st.warning}.get(kind, st.info)(message)


def show_error(exc: BuildOSError) -> None:
    messages = exc.messages if isinstance(exc, ValidationError) else [str(exc)]
    for message in messages:
        st.error(message)


# ---------- clearing "add" forms after a successful save ----------
# Changing a widget's key makes Streamlit treat it as a brand-new, empty widget.
def form_nonce(name: str) -> int:
    return st.session_state.get(f"_nonce_{name}", 0)


def reset_form(name: str) -> None:
    st.session_state[f"_nonce_{name}"] = form_nonce(name) + 1
