"""Thin SQL layer. One function per query; no business rules live here.

Every function takes an open connection so a service can group several calls
into one transaction. Rules such as "codes must be unique" are enforced by the
services (friendly messages) and backed up by database constraints.
"""
from __future__ import annotations

import sqlite3
from datetime import date

from .models import Activity, Dependency, Project


# ---------- row mappers ----------
def _project(row: sqlite3.Row) -> Project:
    return Project(
        id=row["id"],
        name=row["name"],
        start_date=date.fromisoformat(row["start_date"]),
        description=row["description"],
    )


def _activity(row: sqlite3.Row) -> Activity:
    return Activity(
        id=row["id"],
        project_id=row["project_id"],
        code=row["code"],
        name=row["name"],
        duration_days=row["duration_days"],
        notes=row["notes"],
    )


def _dependency(row: sqlite3.Row) -> Dependency:
    return Dependency(
        id=row["id"],
        project_id=row["project_id"],
        predecessor_id=row["predecessor_id"],
        successor_id=row["successor_id"],
    )


# ---------- projects ----------
def insert_project(conn: sqlite3.Connection, name: str, start_date: date, description: str) -> int:
    cur = conn.execute(
        "INSERT INTO projects (name, start_date, description) VALUES (?, ?, ?)",
        (name, start_date.isoformat(), description),
    )
    return int(cur.lastrowid)


def get_project(conn: sqlite3.Connection, project_id: int) -> Project | None:
    row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    return _project(row) if row else None


def find_project_by_name(conn: sqlite3.Connection, name: str) -> Project | None:
    row = conn.execute("SELECT * FROM projects WHERE name = ?", (name,)).fetchone()  # NOCASE column
    return _project(row) if row else None


def list_projects(conn: sqlite3.Connection) -> list[Project]:
    rows = conn.execute("SELECT * FROM projects ORDER BY name COLLATE NOCASE").fetchall()
    return [_project(r) for r in rows]


def update_project(
    conn: sqlite3.Connection, project_id: int, name: str, start_date: date, description: str
) -> None:
    conn.execute(
        "UPDATE projects SET name = ?, start_date = ?, description = ? WHERE id = ?",
        (name, start_date.isoformat(), description, project_id),
    )


def delete_project(conn: sqlite3.Connection, project_id: int) -> bool:
    return conn.execute("DELETE FROM projects WHERE id = ?", (project_id,)).rowcount > 0


# ---------- activities ----------
def insert_activity(
    conn: sqlite3.Connection, project_id: int, code: str, name: str, duration_days: int, notes: str
) -> int:
    cur = conn.execute(
        "INSERT INTO activities (project_id, code, name, duration_days, notes) VALUES (?, ?, ?, ?, ?)",
        (project_id, code, name, duration_days, notes),
    )
    return int(cur.lastrowid)


def get_activity(conn: sqlite3.Connection, activity_id: int) -> Activity | None:
    row = conn.execute("SELECT * FROM activities WHERE id = ?", (activity_id,)).fetchone()
    return _activity(row) if row else None


def find_activity_by_code(conn: sqlite3.Connection, project_id: int, code: str) -> Activity | None:
    row = conn.execute(
        "SELECT * FROM activities WHERE project_id = ? AND code = ?", (project_id, code)
    ).fetchone()
    return _activity(row) if row else None


def list_activities(conn: sqlite3.Connection, project_id: int) -> list[Activity]:
    rows = conn.execute(
        "SELECT * FROM activities WHERE project_id = ? ORDER BY id", (project_id,)
    ).fetchall()
    return [_activity(r) for r in rows]


def update_activity(
    conn: sqlite3.Connection, activity_id: int, code: str, name: str, duration_days: int, notes: str
) -> None:
    conn.execute(
        "UPDATE activities SET code = ?, name = ?, duration_days = ?, notes = ? WHERE id = ?",
        (code, name, duration_days, notes, activity_id),
    )


def delete_activity(conn: sqlite3.Connection, activity_id: int) -> bool:
    return conn.execute("DELETE FROM activities WHERE id = ?", (activity_id,)).rowcount > 0


# ---------- dependencies ----------
def insert_dependency(
    conn: sqlite3.Connection, project_id: int, predecessor_id: int, successor_id: int
) -> int:
    cur = conn.execute(
        "INSERT INTO dependencies (project_id, predecessor_id, successor_id) VALUES (?, ?, ?)",
        (project_id, predecessor_id, successor_id),
    )
    return int(cur.lastrowid)


def get_dependency(conn: sqlite3.Connection, dependency_id: int) -> Dependency | None:
    row = conn.execute("SELECT * FROM dependencies WHERE id = ?", (dependency_id,)).fetchone()
    return _dependency(row) if row else None


def dependency_exists(conn: sqlite3.Connection, predecessor_id: int, successor_id: int) -> bool:
    row = conn.execute(
        "SELECT 1 FROM dependencies WHERE predecessor_id = ? AND successor_id = ?",
        (predecessor_id, successor_id),
    ).fetchone()
    return row is not None


def list_dependencies(conn: sqlite3.Connection, project_id: int) -> list[Dependency]:
    rows = conn.execute(
        "SELECT * FROM dependencies WHERE project_id = ? ORDER BY id", (project_id,)
    ).fetchall()
    return [_dependency(r) for r in rows]


def count_dependencies_for_activity(conn: sqlite3.Connection, activity_id: int) -> int:
    row = conn.execute(
        "SELECT COUNT(*) FROM dependencies WHERE predecessor_id = ? OR successor_id = ?",
        (activity_id, activity_id),
    ).fetchone()
    return int(row[0])


def delete_dependency(conn: sqlite3.Connection, dependency_id: int) -> bool:
    return conn.execute("DELETE FROM dependencies WHERE id = ?", (dependency_id,)).rowcount > 0
