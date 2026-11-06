import unittest
from datetime import date

from buildos.db import Database
from buildos.errors import CircularDependencyError, NotFoundError, ValidationError
from buildos.services import ActivityService, ProjectService
from tests.helpers import TempDatabaseTestCase


class ProjectServiceTests(TempDatabaseTestCase):
    def test_create_and_get(self):
        p = self.projects.create_project("  Tower A ", date(2026, 11, 2), "desc")
        self.assertEqual(self.projects.get_project(p.id), p)
        self.assertEqual((p.name, p.start_date, p.description), ("Tower A", date(2026, 11, 2), "desc"))

    def test_invalid_input_is_not_saved(self):
        with self.assertRaises(ValidationError):
            self.projects.create_project("", date(2026, 11, 2))
        self.assertEqual(self.projects.list_projects(), [])

    def test_duplicate_name_rejected_case_insensitively(self):
        self.make_project("Tower A")
        with self.assertRaises(ValidationError):
            self.projects.create_project("tower a", date(2026, 11, 2))

    def test_list_is_sorted_by_name(self):
        for name in ("beta", "Alpha", "gamma"):
            self.make_project(name)
        self.assertEqual([p.name for p in self.projects.list_projects()], ["Alpha", "beta", "gamma"])

    def test_update(self):
        p = self.make_project("Old")
        updated = self.projects.update_project(p.id, "New", date(2027, 1, 4), "d")
        self.assertEqual((updated.name, updated.start_date), ("New", date(2027, 1, 4)))

    def test_update_keeping_own_name_is_allowed(self):
        p = self.make_project("Same")
        self.projects.update_project(p.id, "Same", date(2027, 1, 4))

    def test_update_to_another_projects_name_rejected(self):
        self.make_project("One")
        two = self.make_project("Two")
        with self.assertRaises(ValidationError):
            self.projects.update_project(two.id, "ONE", date(2026, 11, 2))

    def test_missing_project_raises_not_found(self):
        for call in (
            lambda: self.projects.get_project(999),
            lambda: self.projects.update_project(999, "x", date(2026, 1, 1)),
            lambda: self.projects.delete_project(999),
        ):
            with self.assertRaises(NotFoundError):
                call()

    def test_delete(self):
        p = self.make_project()
        self.projects.delete_project(p.id)
        self.assertEqual(self.projects.list_projects(), [])


class ActivityServiceTests(TempDatabaseTestCase):
    def setUp(self):
        super().setUp()
        self.p = self.make_project()

    def test_add_and_list_in_creation_order(self):
        self.make_activity(self.p.id, "B")
        self.make_activity(self.p.id, "A")
        self.assertEqual([a.code for a in self.activities.list_activities(self.p.id)], ["B", "A"])

    def test_code_is_normalised(self):
        self.assertEqual(self.activities.add_activity(self.p.id, " a1 ", "x", 2).code, "A1")

    def test_duplicate_code_rejected_even_with_different_case(self):
        self.make_activity(self.p.id, "A1")
        with self.assertRaises(ValidationError):
            self.activities.add_activity(self.p.id, "a1", "other", 1)

    def test_invalid_input_not_saved(self):
        with self.assertRaises(ValidationError):
            self.activities.add_activity(self.p.id, "A1", "x", -5)
        self.assertEqual(self.activities.list_activities(self.p.id), [])

    def test_unknown_project_raises_not_found(self):
        with self.assertRaises(NotFoundError):
            self.activities.add_activity(999, "A1", "x", 1)

    def test_update(self):
        a = self.make_activity(self.p.id, "A1", 3)
        updated = self.activities.update_activity(a.id, "a9", "Renamed", 7, "note")
        self.assertEqual((updated.code, updated.name, updated.duration_days, updated.notes),
                         ("A9", "Renamed", 7, "note"))
        self.assertEqual(updated.project_id, self.p.id)

    def test_update_to_existing_code_rejected_but_own_code_allowed(self):
        a = self.make_activity(self.p.id, "A1")
        b = self.make_activity(self.p.id, "A2")
        with self.assertRaises(ValidationError):
            self.activities.update_activity(b.id, "A1", "x", 1)
        self.activities.update_activity(a.id, "A1", "Renamed", 2)

    def test_update_missing_activity(self):
        with self.assertRaises(NotFoundError):
            self.activities.update_activity(999, "A1", "x", 1)

    def test_delete_reports_removed_links_and_removes_them(self):
        a, b, c = (self.make_activity(self.p.id, code) for code in ("A", "B", "C"))
        self.activities.add_dependency(self.p.id, a.id, b.id)
        self.activities.add_dependency(self.p.id, b.id, c.id)
        self.assertEqual(self.activities.delete_activity(b.id), 2)
        self.assertEqual(self.activities.list_dependencies(self.p.id), [])
        self.assertEqual([x.code for x in self.activities.list_activities(self.p.id)], ["A", "C"])

    def test_delete_missing_activity(self):
        with self.assertRaises(NotFoundError):
            self.activities.delete_activity(999)


class DependencyServiceTests(TempDatabaseTestCase):
    def setUp(self):
        super().setUp()
        self.p = self.make_project()
        self.a, self.b, self.c, self.d = (self.make_activity(self.p.id, c) for c in "ABCD")

    def link(self, pred, succ):
        return self.activities.add_dependency(self.p.id, pred.id, succ.id)

    def test_add_and_list(self):
        dep = self.link(self.a, self.b)
        self.assertEqual((dep.predecessor_id, dep.successor_id), (self.a.id, self.b.id))
        self.assertEqual(self.activities.list_dependencies(self.p.id), [dep])

    def test_self_dependency_rejected(self):
        with self.assertRaises(ValidationError):
            self.link(self.a, self.a)

    def test_duplicate_rejected(self):
        self.link(self.a, self.b)
        with self.assertRaises(ValidationError):
            self.link(self.a, self.b)

    def test_direct_cycle_rejected_with_codes_in_message(self):
        self.link(self.a, self.b)
        with self.assertRaises(CircularDependencyError) as ctx:
            self.link(self.b, self.a)
        self.assertEqual(ctx.exception.cycle, ["B", "A"])
        self.assertIn("B -> A -> B", str(ctx.exception))

    def test_indirect_cycle_rejected(self):
        self.link(self.a, self.b)
        self.link(self.b, self.c)
        self.link(self.c, self.d)
        with self.assertRaises(CircularDependencyError) as ctx:
            self.link(self.d, self.a)
        self.assertEqual(ctx.exception.cycle, ["D", "A", "B", "C"])

    def test_rejected_cycle_is_not_persisted(self):
        self.link(self.a, self.b)
        with self.assertRaises(CircularDependencyError):
            self.link(self.b, self.a)
        self.assertEqual(len(self.activities.list_dependencies(self.p.id)), 1)
        self.assertEqual(self.activities.check_project_network(self.p.id), [])

    def test_diamond_and_parallel_paths_are_allowed(self):
        for pred, succ in ((self.a, self.b), (self.a, self.c), (self.b, self.d), (self.c, self.d)):
            self.link(pred, succ)
        self.assertEqual(len(self.activities.list_dependencies(self.p.id)), 4)

    def test_activity_from_another_project_rejected(self):
        other = self.make_project("Other")
        foreign = self.make_activity(other.id, "X")
        with self.assertRaises(ValidationError):
            self.activities.add_dependency(self.p.id, self.a.id, foreign.id)
        with self.assertRaises(ValidationError):
            self.activities.add_dependency(self.p.id, foreign.id, self.a.id)

    def test_unknown_activity_or_project(self):
        with self.assertRaises(ValidationError):
            self.activities.add_dependency(self.p.id, self.a.id, 999)
        with self.assertRaises(NotFoundError):
            self.activities.add_dependency(999, self.a.id, self.b.id)

    def test_remove_dependency_then_reverse_link_becomes_legal(self):
        dep = self.link(self.a, self.b)
        self.activities.remove_dependency(dep.id)
        self.link(self.b, self.a)  # no longer a cycle

    def test_remove_missing_dependency(self):
        with self.assertRaises(NotFoundError):
            self.activities.remove_dependency(999)


class NetworkCheckTests(TempDatabaseTestCase):
    def test_healthy_network_reports_nothing(self):
        p = self.make_project()
        a, b = self.make_activity(p.id, "A"), self.make_activity(p.id, "B")
        self.activities.add_dependency(p.id, a.id, b.id)
        self.assertEqual(self.activities.check_project_network(p.id), [])

    def test_empty_project_is_fine(self):
        self.assertEqual(self.activities.check_project_network(self.make_project().id), [])

    def test_cycle_inserted_behind_the_apps_back_is_detected(self):
        p = self.make_project()
        a, b = self.make_activity(p.id, "A"), self.make_activity(p.id, "B")
        self.activities.add_dependency(p.id, a.id, b.id)
        with self.db.connect() as conn:  # simulate manual database editing
            conn.execute(
                "INSERT INTO dependencies (project_id, predecessor_id, successor_id) VALUES (?,?,?)",
                (p.id, b.id, a.id),
            )
        problems = self.activities.check_project_network(p.id)
        self.assertEqual(len(problems), 1)
        self.assertIn("Circular dependency", problems[0])

    def test_unknown_project(self):
        with self.assertRaises(NotFoundError):
            self.activities.check_project_network(999)


class PersistenceTests(TempDatabaseTestCase):
    def test_data_survives_new_database_and_service_objects(self):
        p = self.make_project("Persistent")
        a, b = self.make_activity(p.id, "A", 4), self.make_activity(p.id, "B", 2)
        self.activities.add_dependency(p.id, a.id, b.id)

        db2 = Database(self.db_path)  # simulates restarting the app
        db2.initialize()
        projects2, activities2 = ProjectService(db2), ActivityService(db2)
        self.assertEqual([x.name for x in projects2.list_projects()], ["Persistent"])
        self.assertEqual([(x.code, x.duration_days) for x in activities2.list_activities(p.id)],
                         [("A", 4), ("B", 2)])
        self.assertEqual(len(activities2.list_dependencies(p.id)), 1)


if __name__ == "__main__":
    unittest.main()
