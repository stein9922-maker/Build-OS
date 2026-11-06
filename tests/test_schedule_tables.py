import unittest
from datetime import date

from buildos.sample_data import load_sample_project
from buildos.services import ScheduleService
from buildos.tables import SCHEDULE_COLUMNS, schedule_to_dataframe
from tests.helpers import TempDatabaseTestCase


class ScheduleTableTests(TempDatabaseTestCase):
    def setUp(self):
        super().setUp()
        p = self.make_project()
        self.p = p
        s = self.activities.add_activity(p.id, "S", "Start", 2)
        a = self.activities.add_activity(p.id, "A", "Long branch", 5)
        b = self.activities.add_activity(p.id, "B", "Short branch", 3)
        m = self.activities.add_activity(p.id, "M", "Milestone", 0)
        for pred, succ in ((s, a), (s, b), (a, m)):
            self.activities.add_dependency(p.id, pred.id, succ.id)
        self.df = schedule_to_dataframe(ScheduleService(self.db).calculate_schedule(p.id))

    def row(self, code):
        return self.df[self.df["Code"] == code].iloc[0]

    def test_columns(self):
        self.assertEqual(list(self.df.columns), SCHEDULE_COLUMNS)
        for needed in ("Duration (days)", "ES", "EF", "LS", "LF", "Total float (days)", "Critical"):
            self.assertIn(needed, self.df.columns)

    def test_values_match_hand_calculation(self):
        # S 0-2 | A 2-7 | M 7-7 | B 2-5 with LF = D = 7  -> LS 4, float 2        D = 7
        self.assertEqual(self.row("S")[["ES", "EF", "LS", "LF", "Total float (days)"]].tolist(), [0, 2, 0, 2, 0])
        self.assertEqual(self.row("A")[["ES", "EF", "LS", "LF", "Total float (days)"]].tolist(), [2, 7, 2, 7, 0])
        self.assertEqual(self.row("B")[["ES", "EF", "LS", "LF", "Total float (days)"]].tolist(), [2, 5, 4, 7, 2])
        self.assertEqual(self.row("M")[["ES", "EF", "LS", "LF", "Total float (days)"]].tolist(), [7, 7, 7, 7, 0])

    def test_critical_status_is_yes_or_no(self):
        self.assertEqual(self.df.set_index("Code")["Critical"].to_dict(),
                         {"S": "Yes", "A": "Yes", "M": "Yes", "B": "No"})

    def test_dates_are_iso_text_and_finish_exclusive(self):
        a = self.row("A")  # start 2026-11-02; ES 2, EF 7
        self.assertEqual(a["Early start date"], "2026-11-04")
        self.assertEqual(a["Early finish date"], "2026-11-09")
        self.assertEqual(self.row("B")["Late start date"], "2026-11-06")
        self.assertEqual(self.row("B")["Late finish date"], "2026-11-09")

    def test_rows_are_in_schedule_order(self):
        # S(0,2) -> B(2,5) -> A(2,7) -> M(7,7): ties on ES are broken by EF
        self.assertEqual(self.df["Code"].tolist(), ["S", "B", "A", "M"])

    def test_empty_schedule_has_columns_and_no_rows(self):
        empty = schedule_to_dataframe(ScheduleService(self.db).calculate_schedule(self.make_project("Empty").id))
        self.assertEqual(list(empty.columns), SCHEDULE_COLUMNS)
        self.assertEqual(len(empty), 0)


if __name__ == "__main__":
    unittest.main()
