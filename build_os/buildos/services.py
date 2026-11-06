"""Business rules for projects, activities and dependencies.

Services validate input, enforce rules (unique codes, no cycles, same-project links)
and call the repository inside a single transaction. They never touch Streamlit.
"""
from __future__ import annotations

import functools
import sqlite3
from datetime import date

from . import repository as repo
from . import validation
from .errors import (
    CircularDependencyError,
    NotFoundError,
    ValidationError,
    format_cycle,
)
from .db import Database
from .models import Activity, Dependency, Project
from .scheduling.cpm import ScheduleResult, compute_schedule
from .scheduling.graph import build_graph, find_cycle, find_cycle_through_new_link


def _translate_integrity_errors(func):
    """Backstop: if a database constraint trips despite our checks, surface a clean error."""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except sqlite3.IntegrityError as exc:
            raise ValidationError(
                "The change conflicts with existing data and was not saved."
            ) from exc

    return wrapper


class ProjectService:
    def __init__(self, db: Database):
        self._db = db

    @_translate_integrity_errors
    def create_project(self, name: str, start_date: date, description: str = "") -> Project:
        name, start_date, description = validation.clean_project_input(name, start_date, description)
        with self._db.connect() as conn:
            if repo.find_project_by_name(conn, name) is not None:
                raise ValidationError(f"A project named '{name}' already exists.")
            project_id = repo.insert_project(conn, name, start_date, description)
            return repo.get_project(conn, project_id)

    def get_project(self, project_id: int) -> Project:
        with self._db.connect() as conn:
            project = repo.get_project(conn, project_id)
        if project is None:
            raise NotFoundError(f"Project {project_id} does not exist.")
        return project

    def list_projects(self) -> list[Project]:
        with self._db.connect() as conn:
            return repo.list_projects(conn)

    @_translate_integrity_errors
    def update_project(
        self, project_id: int, name: str, start_date: date, description: str = ""
    ) -> Project:
        name, start_date, description = validation.clean_project_input(name, start_date, description)
        with self._db.connect() as conn:
            if repo.get_project(conn, project_id) is None:
                raise NotFoundError(f"Project {project_id} does not exist.")
            clash = repo.find_project_by_name(conn, name)
            if clash is not None and clash.id != project_id:
                raise ValidationError(f"A project named '{name}' already exists.")
            repo.update_project(conn, project_id, name, start_date, description)
            return repo.get_project(conn, project_id)

    def delete_project(self, project_id: int) -> None:
        """Deletes the project together with its activities and dependencies."""
        with self._db.connect() as conn:
            if not repo.delete_project(conn, project_id):
                raise NotFoundError(f"Project {project_id} does not exist.")


class ActivityService:
    def __init__(self, db: Database):
        self._db = db

    # ---------- helpers ----------
    @staticmethod
    def _require_project(conn: sqlite3.Connection, project_id: int) -> None:
        if repo.get_project(conn, project_id) is None:
            raise NotFoundError(f"Project {project_id} does not exist.")

    @staticmethod
    def _require_activity(conn: sqlite3.Connection, activity_id: int) -> Activity:
        activity = repo.get_activity(conn, activity_id)
        if activity is None:
            raise NotFoundError(f"Activity {activity_id} does not exist.")
        return activity

    # ---------- activities ----------
    @_translate_integrity_errors
    def add_activity(
        self, project_id: int, code: str, name: str, duration_days: int, notes: str = ""
    ) -> Activity:
        code, name, duration_days, notes = validation.clean_activity_input(
            code, name, duration_days, notes
        )
        with self._db.connect() as conn:
            self._require_project(conn, project_id)
            if repo.find_activity_by_code(conn, project_id, code) is not None:
                raise ValidationError(f"Activity code '{code}' is already used in this project.")
            new_id = repo.insert_activity(conn, project_id, code, name, duration_days, notes)
            return repo.get_activity(conn, new_id)

    @_translate_integrity_errors
    def update_activity(
        self, activity_id: int, code: str, name: str, duration_days: int, notes: str = ""
    ) -> Activity:
        code, name, duration_days, notes = validation.clean_activity_input(
            code, name, duration_days, notes
        )
        with self._db.connect() as conn:
            existing = self._require_activity(conn, activity_id)
            clash = repo.find_activity_by_code(conn, existing.project_id, code)
            if clash is not None and clash.id != activity_id:
                raise ValidationError(f"Activity code '{code}' is already used in this project.")
            repo.update_activity(conn, activity_id, code, name, duration_days, notes)
            return repo.get_activity(conn, activity_id)

    def delete_activity(self, activity_id: int) -> int:
        """Delete an activity and every dependency link attached to it.

        Returns the number of links that were removed so the UI can tell the user.
        """
        with self._db.connect() as conn:
            self._require_activity(conn, activity_id)
            removed_links = repo.count_dependencies_for_activity(conn, activity_id)
            repo.delete_activity(conn, activity_id)
            return removed_links

    def get_activity(self, activity_id: int) -> Activity:
        with self._db.connect() as conn:
            return self._require_activity(conn, activity_id)

    def list_activities(self, project_id: int) -> list[Activity]:
        with self._db.connect() as conn:
            return repo.list_activities(conn, project_id)

    # ---------- dependencies ----------
    @_translate_integrity_errors
    def add_dependency(self, project_id: int, predecessor_id: int, successor_id: int) -> Dependency:
        """Add a finish-to-start link, rejecting self-links, duplicates and cycles."""
        with self._db.connect() as conn:
            self._require_project(conn, project_id)
            predecessor = repo.get_activity(conn, predecessor_id)
            successor = repo.get_activity(conn, successor_id)

            problems = []
            if predecessor is None or predecessor.project_id != project_id:
                problems.append("The predecessor activity does not belong to this project.")
            if successor is None or successor.project_id != project_id:
                problems.append("The successor activity does not belong to this project.")
            if problems:
                raise ValidationError(problems)

            if predecessor_id == successor_id:
                raise ValidationError("An activity cannot depend on itself.")
            if repo.dependency_exists(conn, predecessor_id, successor_id):
                raise ValidationError(
                    f"{predecessor.code} is already a predecessor of {successor.code}."
                )

            activities = repo.list_activities(conn, project_id)
            links = [
                (d.predecessor_id, d.successor_id) for d in repo.list_dependencies(conn, project_id)
            ]
            graph = build_graph([a.id for a in activities], links)
            cycle_ids = find_cycle_through_new_link(graph, predecessor_id, successor_id)
            if cycle_ids is not None:
                code_by_id = {a.id: a.code for a in activities}
                raise CircularDependencyError([code_by_id[i] for i in cycle_ids])

            new_id = repo.insert_dependency(conn, project_id, predecessor_id, successor_id)
            return repo.get_dependency(conn, new_id)

    def remove_dependency(self, dependency_id: int) -> None:
        with self._db.connect() as conn:
            if not repo.delete_dependency(conn, dependency_id):
                raise NotFoundError(f"Dependency {dependency_id} does not exist.")

    def list_dependencies(self, project_id: int) -> list[Dependency]:
        with self._db.connect() as conn:
            return repo.list_dependencies(conn, project_id)

    # ---------- whole-network check ----------
    def check_project_network(self, project_id: int) -> list[str]:
        """Return a list of problems found in the stored network (empty list = healthy).

        add_dependency already prevents cycles, so this is a safety net for data that was
        edited outside the app or imported in a future stage.
        """
        with self._db.connect() as conn:
            self._require_project(conn, project_id)
            activities = repo.list_activities(conn, project_id)
            links = [
                (d.predecessor_id, d.successor_id) for d in repo.list_dependencies(conn, project_id)
            ]
        graph = build_graph([a.id for a in activities], links)
        cycle_ids = find_cycle(graph)
        if cycle_ids is None:
            return []
        code_by_id = {a.id: a.code for a in activities}
        return [f"Circular dependency detected: {format_cycle(code_by_id[i] for i in cycle_ids)}."]


class ScheduleService:
    """Calculates the CPM schedule on demand from the stored project data.

    Nothing is written to the database: a schedule is *derived* from durations, dependencies
    and the project start date, so storing it would only let it go stale after an edit.
    """

    def __init__(self, db: Database):
        self._db = db

    def calculate_schedule(self, project_id: int) -> ScheduleResult:
        """Raises NotFoundError for an unknown project and CircularDependencyError if the
        stored dependencies contain a loop (the app prevents loops, so that would mean the
        database was edited by hand)."""
        with self._db.connect() as conn:  # one connection = one consistent snapshot
            project = repo.get_project(conn, project_id)
            if project is None:
                raise NotFoundError(f"Project {project_id} does not exist.")
            activities = repo.list_activities(conn, project_id)
            dependencies = repo.list_dependencies(conn, project_id)
        return compute_schedule(project.start_date, activities, dependencies)
