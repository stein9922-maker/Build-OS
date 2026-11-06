import unittest

from buildos.tables import (
    ACTIVITY_COLUMNS,
    DEPENDENCY_COLUMNS,
    activities_to_dataframe,
    dependencies_to_dataframe,
)
from tests.helpers import TempDatabaseTestCase


class TableTests(TempDatabaseTestCase):
    def setUp(self):
        super().setUp()
        self.p = self.make_project()
        self.a = self.make_activity(self.p.id, "A", 3)
        self.b = self.make_activity(self.p.id, "B", 5)
        self.c = self.make_activity(self.p.id, "C", 0)
        self.activities.add_dependency(self.p.id, self.a.id, self.c.id)
        self.activities.add_dependency(self.p.id, self.b.id, self.c.id)

    def _load(self):
        return (self.activities.list_activities(self.p.id), self.activities.list_dependencies(self.p.id))

    def test_activity_table_shows_predecessor_codes(self):
        df = activities_to_dataframe(*self._load())
        self.assertEqual(list(df.columns), ACTIVITY_COLUMNS)
        self.assertEqual(df["Code"].tolist(), ["A", "B", "C"])
        self.assertEqual(df["Duration (days)"].tolist(), [3, 5, 0])
        self.assertEqual(df["Predecessors (FS)"].tolist(), ["", "", "A, B"])

    def test_dependency_table_lists_fs_links(self):
        df = dependencies_to_dataframe(*self._load())
        self.assertEqual(list(df.columns), DEPENDENCY_COLUMNS)
        self.assertEqual(len(df), 2)
        self.assertEqual(set(df["Type"]), {"FS"})
        self.assertEqual(df.iloc[0]["Predecessor"], "A - Activity A")

    def test_empty_inputs_still_have_columns(self):
        self.assertEqual(list(activities_to_dataframe([], []).columns), ACTIVITY_COLUMNS)
        self.assertEqual(list(dependencies_to_dataframe([], []).columns), DEPENDENCY_COLUMNS)


if __name__ == "__main__":
    unittest.main()
