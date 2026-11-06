"""Database-level guarantees: these must hold even if a service forgets to check."""
import sqlite3
import unittest
from datetime import date

from buildos import repository as repo
from buildos.db import SCHEMA_VERSION, Database
from tests.helpers import TempDatabaseTestCase


class SchemaTests(TempDatabaseTestCase):
    def test_schema_version_is_recorded(self):
        with self.db.connect() as conn:
            self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION)

    def test_initialize_twice_is_harmless_and_keeps_data(self):
        self.make_project("Keep me")
        self.db.initialize()
        self.assertEqual([p.name for p in self.projects.list_projects()], ["Keep me"])

    def test_foreign_keys_are_enabled(self):
        with self.db.connect() as conn:
            self.assertEqual(conn.execute("PRAGMA foreign_keys").fetchone()[0], 1)

    def test_expected_tables_exist(self):
        with self.db.connect() as conn:
            names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertTrue({"projects", "activities", "dependencies"} <= names)

    def test_initialize_creates_missing_parent_folder(self):
        nested = self.db_path.parent / "a" / "b" / "x.db"
        Database(nested).initialize()
        self.assertTrue(nested.exists())


class ConstraintTests(TempDatabaseTestCase):
    def setUp(self):
        super().setUp()
        self.p1 = self.make_project("P1")
        self.p2 = self.make_project("P2")

    def test_negative_duration_rejected_by_database(self):
        with self.assertRaises(sqlite3.IntegrityError), self.db.connect() as conn:
            repo.insert_activity(conn, self.p1.id, "A1", "x", -1, "")

    def test_duplicate_code_in_same_project_rejected(self):
        self.make_activity(self.p1.id, "A1")
        with self.assertRaises(sqlite3.IntegrityError), self.db.connect() as conn:
            repo.insert_activity(conn, self.p1.id, "a1", "x", 1, "")  # NOCASE collation

    def test_same_code_in_different_projects_allowed(self):
        self.make_activity(self.p1.id, "A1")
        self.make_activity(self.p2.id, "A1")

    def test_project_names_unique_ignoring_case(self):
        with self.assertRaises(sqlite3.IntegrityError), self.db.connect() as conn:
            repo.insert_project(conn, "p1", date(2026, 1, 1), "")

    def test_self_dependency_rejected_by_database(self):
        a = self.make_activity(self.p1.id, "A1")
        with self.assertRaises(sqlite3.IntegrityError), self.db.connect() as conn:
            repo.insert_dependency(conn, self.p1.id, a.id, a.id)

    def test_cross_project_dependency_rejected_by_database(self):
        a = self.make_activity(self.p1.id, "A1")
        b = self.make_activity(self.p2.id, "B1")
        with self.assertRaises(sqlite3.IntegrityError), self.db.connect() as conn:
            repo.insert_dependency(conn, self.p1.id, a.id, b.id)

    def test_duplicate_dependency_rejected_by_database(self):
        a = self.make_activity(self.p1.id, "A1")
        b = self.make_activity(self.p1.id, "A2")
        with self.db.connect() as conn:
            repo.insert_dependency(conn, self.p1.id, a.id, b.id)
        with self.assertRaises(sqlite3.IntegrityError), self.db.connect() as conn:
            repo.insert_dependency(conn, self.p1.id, a.id, b.id)


class CascadeTests(TempDatabaseTestCase):
    def _count(self, table):
        with self.db.connect() as conn:
            return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    def test_deleting_project_removes_its_activities_and_dependencies(self):
        p = self.make_project()
        a, b = self.make_activity(p.id, "A1"), self.make_activity(p.id, "A2")
        self.activities.add_dependency(p.id, a.id, b.id)
        self.projects.delete_project(p.id)
        self.assertEqual((self._count("activities"), self._count("dependencies")), (0, 0))

    def test_failed_transaction_rolls_back_everything(self):
        p = self.make_project()
        with self.assertRaises(RuntimeError):
            with self.db.connect() as conn:
                repo.insert_activity(conn, p.id, "A1", "x", 1, "")
                raise RuntimeError("boom")
        self.assertEqual(self._count("activities"), 0)


if __name__ == "__main__":
    unittest.main()
