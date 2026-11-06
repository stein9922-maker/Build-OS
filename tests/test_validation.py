import math
import unittest
from datetime import date, datetime

from buildos.errors import ValidationError
from buildos.validation import (
    MAX_CODE_LEN,
    MAX_DURATION_DAYS,
    clean_activity_input,
    clean_project_input,
)


class ProjectValidationTests(unittest.TestCase):
    def test_valid_input_is_trimmed(self):
        name, start, desc = clean_project_input("  Tower A  ", date(2026, 11, 2), "  note ")
        self.assertEqual((name, start, desc), ("Tower A", date(2026, 11, 2), "note"))

    def test_blank_name_rejected(self):
        with self.assertRaises(ValidationError):
            clean_project_input("   ", date(2026, 11, 2))

    def test_none_name_rejected(self):
        with self.assertRaises(ValidationError):
            clean_project_input(None, date(2026, 11, 2))

    def test_name_too_long_rejected(self):
        with self.assertRaises(ValidationError):
            clean_project_input("x" * 101, date(2026, 11, 2))

    def test_non_date_rejected(self):
        for bad in ("2026-11-02", None, 20261102):
            with self.subTest(bad=bad), self.assertRaises(ValidationError):
                clean_project_input("P", bad)

    def test_datetime_is_reduced_to_date(self):
        _, start, _ = clean_project_input("P", datetime(2026, 11, 2, 15, 30))
        self.assertEqual(start, date(2026, 11, 2))

    def test_year_out_of_range_rejected(self):
        for bad in (date(1900, 1, 1), date(2500, 1, 1)):
            with self.subTest(bad=bad), self.assertRaises(ValidationError):
                clean_project_input("P", bad)

    def test_all_problems_reported_together(self):
        with self.assertRaises(ValidationError) as ctx:
            clean_project_input("", "not a date")
        self.assertEqual(len(ctx.exception.messages), 2)


class ActivityValidationTests(unittest.TestCase):
    def test_valid_input_and_code_uppercased(self):
        self.assertEqual(
            clean_activity_input(" a100 ", " Excavate ", 5, " n "), ("A100", "Excavate", 5, "n")
        )

    def test_bad_codes_rejected(self):
        for bad in ("", "  ", "A 100", "A/100", "-A1", ".A1", "ÄÖ1", "A" * (MAX_CODE_LEN + 1), None):
            with self.subTest(code=bad), self.assertRaises(ValidationError):
                clean_activity_input(bad, "Name", 1)

    def test_good_codes_accepted(self):
        for good in ("A1", "1", "A.1", "A_1", "A-1", "a100"):
            with self.subTest(code=good):
                self.assertEqual(clean_activity_input(good, "N", 1)[0], good.upper())

    def test_blank_name_rejected(self):
        with self.assertRaises(ValidationError):
            clean_activity_input("A1", "  ", 1)

    def test_zero_duration_allowed_as_milestone(self):
        self.assertEqual(clean_activity_input("M1", "Milestone", 0)[2], 0)

    def test_integer_valued_float_accepted(self):
        self.assertEqual(clean_activity_input("A1", "N", 3.0)[2], 3)

    def test_max_duration_boundary(self):
        self.assertEqual(clean_activity_input("A1", "N", MAX_DURATION_DAYS)[2], MAX_DURATION_DAYS)
        with self.assertRaises(ValidationError):
            clean_activity_input("A1", "N", MAX_DURATION_DAYS + 1)

    def test_bad_durations_rejected(self):
        for bad in (-1, 2.5, True, False, None, "5", float("nan"), math.inf, -0.5):
            with self.subTest(duration=bad), self.assertRaises(ValidationError):
                clean_activity_input("A1", "N", bad)

    def test_all_problems_reported_together(self):
        with self.assertRaises(ValidationError) as ctx:
            clean_activity_input("", "", -3)
        self.assertEqual(len(ctx.exception.messages), 3)


if __name__ == "__main__":
    unittest.main()
