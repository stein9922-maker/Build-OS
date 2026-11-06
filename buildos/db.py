"""SQLite connection handling and schema migrations.

A fresh connection is opened for every unit of work (cheap for a local SQLite file).
This makes the app safe under Streamlit, which runs each browser session in its own thread.
"""
from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

# Migration 1 (Stage 1). Later stages append new entries to MIGRATIONS; never edit old ones.
_MIGRATION_1 = """
CREATE TABLE projects (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL COLLATE NOCASE UNIQUE,
    start_date  TEXT NOT NULL,                       -- ISO format yyyy-mm-dd
    description TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE activities (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id    INTEGER NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
    code          TEXT NOT NULL COLLATE NOCASE,
    name          TEXT NOT NULL,
    duration_days INTEGER NOT NULL CHECK (duration_days >= 0),
    notes         TEXT NOT NULL DEFAULT '',
    UNIQUE (project_id, code),
    UNIQUE (id, project_id)  -- lets dependencies prove both ends belong to the same project
);

CREATE TABLE dependencies (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id     INTEGER NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
    predecessor_id INTEGER NOT NULL,
    successor_id   INTEGER NOT NULL,
    UNIQUE (predecessor_id, successor_id),
    CHECK (predecessor_id <> successor_id),
    FOREIGN KEY (predecessor_id, project_id) REFERENCES activities (id, project_id) ON DELETE CASCADE,
    FOREIGN KEY (successor_id,   project_id) REFERENCES activities (id, project_id) ON DELETE CASCADE
);

CREATE INDEX idx_dependencies_project ON dependencies (project_id);
"""

_MIGRATION_2 = """
CREATE TABLE materials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name TEXT NOT NULL COLLATE NOCASE,
    category TEXT NOT NULL DEFAULT 'General',
    unit TEXT NOT NULL,
    UNIQUE(project_id, name)
);

CREATE TABLE activity_materials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    activity_id INTEGER NOT NULL,
    material_id INTEGER NOT NULL REFERENCES materials(id) ON DELETE CASCADE,
    required_quantity REAL NOT NULL CHECK(required_quantity > 0),
    notes TEXT NOT NULL DEFAULT '',
    UNIQUE(activity_id, material_id),
    FOREIGN KEY(activity_id, project_id) REFERENCES activities(id, project_id) ON DELETE CASCADE
);

CREATE TABLE inventory (
    material_id INTEGER PRIMARY KEY REFERENCES materials(id) ON DELETE CASCADE,
    available_quantity REAL NOT NULL DEFAULT 0 CHECK(available_quantity >= 0),
    reserved_quantity REAL NOT NULL DEFAULT 0 CHECK(reserved_quantity >= 0),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK(reserved_quantity <= available_quantity)
);

CREATE TABLE suppliers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    contact TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    UNIQUE(project_id, name)
);

CREATE TABLE supplier_materials (
    supplier_id INTEGER NOT NULL REFERENCES suppliers(id) ON DELETE CASCADE,
    material_id INTEGER NOT NULL REFERENCES materials(id) ON DELETE CASCADE,
    lead_time_days INTEGER NOT NULL DEFAULT 7 CHECK(lead_time_days >= 0),
    PRIMARY KEY(supplier_id, material_id)
);

CREATE TABLE purchase_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    material_id INTEGER NOT NULL REFERENCES materials(id) ON DELETE CASCADE,
    supplier_id INTEGER NOT NULL REFERENCES suppliers(id) ON DELETE RESTRICT,
    quantity REAL NOT NULL CHECK(quantity > 0),
    received_quantity REAL NOT NULL DEFAULT 0 CHECK(received_quantity >= 0 AND received_quantity <= quantity),
    order_date TEXT NOT NULL,
    expected_delivery TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'Ordered'
        CHECK(status IN ('Draft','Ordered','Partially delivered','Delivered','Cancelled')),
    notes TEXT NOT NULL DEFAULT '',
    CHECK(expected_delivery >= order_date)
);
CREATE INDEX idx_activity_materials_project ON activity_materials(project_id);
CREATE INDEX idx_purchase_orders_project ON purchase_orders(project_id);
"""


# Migration 3: supplier quotations for material price comparison. Never edit earlier migrations.
_MIGRATION_3 = """
CREATE TABLE supplier_quotes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    material_id INTEGER NOT NULL REFERENCES materials(id) ON DELETE CASCADE,
    supplier_id INTEGER NOT NULL REFERENCES suppliers(id) ON DELETE CASCADE,
    unit_price REAL NOT NULL CHECK(unit_price >= 0),
    currency TEXT NOT NULL DEFAULT 'INR',
    quote_date TEXT NOT NULL,
    valid_until TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    CHECK(valid_until >= quote_date)
);
CREATE INDEX idx_supplier_quotes_project ON supplier_quotes(project_id);
"""

MIGRATIONS: tuple[str, ...] = (_MIGRATION_1, _MIGRATION_2, _MIGRATION_3)
SCHEMA_VERSION = len(MIGRATIONS)


def migrate(conn: sqlite3.Connection) -> None:
    """Apply any migrations newer than the database's `user_version`. Safe to call repeatedly."""
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    for version, sql in enumerate(MIGRATIONS, start=1):
        if version <= current:
            continue
        # Each migration runs in one transaction together with its version bump.
        conn.executescript(f"BEGIN;\n{sql}\nPRAGMA user_version = {version};\nCOMMIT;")


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def initialize(self) -> None:
        """Create the folder and schema if needed."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            migrate(conn)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """Open a connection; commit on success, roll back on any error, always close."""
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")  # SQLite leaves this OFF unless asked
        try:
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()
