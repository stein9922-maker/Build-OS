"""ScheduleService: CPM on real (temporary) SQLite data, including the read-only guarantee."""
import unittest
from datetime import date

from buildos.errors import CircularDependencyError, NotFoundError
from buildos.sample_data import load_sample_project
from buildos.db import SCHEMA_VERSION
from buildos.services import ScheduleService
from tests.helpers import TempDatabaseTestCase


class ScheduleServiceTests(TempDatabaseTestCase):
    def setUp(self):
        super().setUp()
        self.schedules = ScheduleService(self.db)

    def _chain(self, durations=(3, 2, 4)):
        p = self.make_project()
        made = [self.make_activity(p.id, code, d) for code, d in zip("ABC", durations)]
        self.activities.add_dependency(p.id, made[0].id, made[1].id)
        self.activities.add_dependency(p.id, made[1].id, made[2].id)
        return p, made

    def test_schedule_from_stored_data(self):
        p, _ = self._chain()
        result = self.schedules.calculate_schedule(p.id)
        self.assertEqual(result.project_start, date(2026, 11, 2))
        self.assertEqual(result.project_duration_days, 9)
        self.assertEqual(result.completion_date, date(2026, 11, 11))
        self.assertEqual([(a.code, a.es, a.ef) for a in result.activities],
                         [("A", 0, 3), ("B", 3, 5), ("C", 5, 9)])

    def test_demo_project_matches_the_hand_calculation(self):
        project = load_sample_project(self.projects, self.activities)
        result = self.schedules.calculate_schedule(project.id)
        self.assertEqual(result.project_duration_days, 102)
        self.assertEqual(result.completion_date, date(2027, 2, 12))
        by_code = result.by_code()
        self.assertEqual((by_code["A150"].total_float, by_code["A180"].total_float,
                          by_code["A210"].total_float), (11, 38, 10))
        self.assertEqual(len(result.critical_activities), 14)
        self.assertEqual(result.critical_path_count, 1)

    def test_empty_project(self):
        p = self.make_project()
        result = self.schedules.calculate_schedule(p.id)
        self.assertEqual((result.activities, result.project_duration_days), ((), 0))
        self.assertEqual(result.completion_date, p.start_date)

    def test_unknown_project(self):
        with self.assertRaises(NotFoundError):
            self.schedules.calculate_schedule(999)

    def test_schedule_is_never_stale_after_edits(self):
        p, made = self._chain()
        self.assertEqual(self.schedules.calculate_schedule(p.id).project_duration_days, 9)
        self.activities.update_activity(made[1].id, "B", "Activity B", 10)  # B: 2 -> 10 days
        self.assertEqual(self.schedules.calculate_schedule(p.id).project_duration_days, 17)
        deps = self.activities.list_dependencies(p.id)
        self.activities.remove_dependency(deps[1].id)  # cut B -> C: C becomes disconnected
        result = self.schedules.calculate_schedule(p.id)
        self.assertEqual(result.project_duration_days, 13)  # A(3)+B(10); C(4) has float 9
        self.assertEqual(result.by_code()["C"].total_float, 9)

    def test_changing_the_project_start_shifts_dates_but_not_day_numbers(self):
        p, _ = self._chain()
        self.projects.update_project(p.id, p.name, date(2027, 1, 4))
        result = self.schedules.calculate_schedule(p.id)
        self.assertEqual(result.completion_date, date(2027, 1, 13))  # Jan 4 + 9 days
        self.assertEqual(result.by_code()["C"].es, 5)

    def test_projects_do_not_leak_into_each_other(self):
        p, _ = self._chain()
        other = self.make_project("Other")
        self.make_activity(other.id, "X", 50)
        self.assertEqual(self.schedules.calculate_schedule(p.id).project_duration_days, 9)
        self.assertEqual(self.schedules.calculate_schedule(other.id).project_duration_days, 50)

    def test_stored_cycle_is_rejected(self):
        p, made = self._chain()
        with self.db.connect() as conn:  # simulate a hand-edited database
            conn.execute(
                "INSERT INTO dependencies (project_id, predecessor_id, successor_id) VALUES (?,?,?)",
                (p.id, made[2].id, made[0].id),
            )
        with self.assertRaises(CircularDependencyError) as ctx:
            self.schedules.calculate_schedule(p.id)
        self.assertEqual(sorted(ctx.exception.cycle), ["A", "B", "C"])

    def test_calculating_a_schedule_does_not_modify_the_database(self):
        project = load_sample_project(self.projects, self.activities)

        def snapshot():
            with self.db.connect() as conn:
                tables = {
                    t: [tuple(r) for r in conn.execute(f"SELECT * FROM {t} ORDER BY id")]
                    for t in ("projects", "activities", "dependencies")
                }
                tables["_user_version"] = conn.execute("PRAGMA user_version").fetchone()[0]
                tables["_schema"] = [
                    tuple(r) for r in conn.execute("SELECT name, sql FROM sqlite_master ORDER BY name")
                ]
                return tables

        before = snapshot()
        for _ in range(3):
            self.schedules.calculate_schedule(project.id)
        self.assertEqual(snapshot(), before)
        self.assertEqual(before["_user_version"], SCHEMA_VERSION)  # schedule calculation does not migrate


if __name__ == "__main__":
    unittest.main()
