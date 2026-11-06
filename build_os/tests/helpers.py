"""Shared test fixture: every test gets its own throwaway SQLite file."""
from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from buildos.db import Database
from buildos.services import ActivityService, ProjectService


class TempDatabaseTestCase(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db_path = Path(tmp.name) / "test.db"
        self.db = Database(self.db_path)
        self.db.initialize()
        self.projects = ProjectService(self.db)
        self.activities = ActivityService(self.db)

    # convenience builders -------------------------------------------------
    def make_project(self, name: str = "Test Project"):
        return self.projects.create_project(name, date(2026, 11, 2))

    def make_activity(self, project_id: int, code: str, duration: int = 1):
        return self.activities.add_activity(project_id, code, f"Activity {code}", duration)
