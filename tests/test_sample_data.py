import unittest
from unittest import mock

from buildos.errors import ValidationError
from buildos.sample_data import (
    SAMPLE_ACTIVITIES,
    SAMPLE_DEPENDENCIES,
    SAMPLE_PROJECT_NAME,
    load_sample_project,
)
from tests.helpers import TempDatabaseTestCase


class SampleDataDefinitionTests(unittest.TestCase):
    def test_codes_are_unique_and_links_refer_to_known_codes(self):
        codes = [code for code, _name, _dur in SAMPLE_ACTIVITIES]
        self.assertEqual(len(codes), len(set(codes)))
        for pred, succ in SAMPLE_DEPENDENCIES:
            self.assertIn(pred, codes)
            self.assertIn(succ, codes)

    def test_sample_durations_are_whole_non_negative_numbers(self):
        for _code, _name, duration in SAMPLE_ACTIVITIES:
            self.assertIsInstance(duration, int)
            self.assertGreaterEqual(duration, 0)


class LoadSampleProjectTests(TempDatabaseTestCase):
    def test_loads_every_activity_and_dependency(self):
        project = load_sample_project(self.projects, self.activities)
        self.assertEqual(project.name, SAMPLE_PROJECT_NAME)
        self.assertEqual(len(self.activities.list_activities(project.id)), len(SAMPLE_ACTIVITIES))
        self.assertEqual(len(self.activities.list_dependencies(project.id)), len(SAMPLE_DEPENDENCIES))

    def test_loaded_network_has_no_cycles(self):
        project = load_sample_project(self.projects, self.activities)
        self.assertEqual(self.activities.check_project_network(project.id), [])

    def test_sample_contains_a_zero_day_milestone(self):
        project = load_sample_project(self.projects, self.activities)
        durations = [a.duration_days for a in self.activities.list_activities(project.id)]
        self.assertIn(0, durations)

    def test_loading_twice_is_rejected_and_leaves_one_project(self):
        load_sample_project(self.projects, self.activities)
        with self.assertRaises(ValidationError):
            load_sample_project(self.projects, self.activities)
        self.assertEqual(len(self.projects.list_projects()), 1)

    def test_failure_midway_leaves_no_partial_project(self):
        with mock.patch.object(
            self.activities.__class__, "add_dependency", side_effect=RuntimeError("boom")
        ):
            with self.assertRaises(RuntimeError):
                load_sample_project(self.projects, self.activities)
        self.assertEqual(self.projects.list_projects(), [])


if __name__ == "__main__":
    unittest.main()
