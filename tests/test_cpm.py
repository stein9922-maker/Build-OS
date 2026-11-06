"""CPM engine tests. Every expected number below was worked out BY HAND (see the comments),
not copied from the engine's output.

Table format:  code -> (ES, EF, LS, LF, total float), all in days from project start (day 0).
"""
import unittest
from datetime import date, timedelta

from buildos.errors import CircularDependencyError, ValidationError
from buildos.models import Activity, Dependency
from buildos.sample_data import SAMPLE_ACTIVITIES, SAMPLE_DEPENDENCIES
from buildos.scheduling.cpm import compute_schedule

START = date(2026, 11, 2)  # a Monday


def run(spec, links=(), start=START):
    """spec: {code: duration}; links: [(predecessor_code, successor_code)]."""
    activities = [
        Activity(id=i, project_id=1, code=code, name=f"Activity {code}", duration_days=days)
        for i, (code, days) in enumerate(spec.items(), start=1)
    ]
    id_of = {a.code: a.id for a in activities}
    dependencies = [
        Dependency(id=i, project_id=1, predecessor_id=id_of[p], successor_id=id_of[s])
        for i, (p, s) in enumerate(links, start=1)
    ]
    return compute_schedule(start, activities, dependencies)


class CpmTestCase(unittest.TestCase):
    def assertTable(self, result, expected):
        got = {a.code: (a.es, a.ef, a.ls, a.lf, a.total_float) for a in result.activities}
        self.assertEqual(got, expected)
        for a in result.activities:  # internal consistency that must always hold
            self.assertEqual(a.ef, a.es + a.duration_days)
            self.assertEqual(a.lf, a.ls + a.duration_days)
            self.assertEqual(a.total_float, a.ls - a.es)
            self.assertEqual(a.total_float, a.lf - a.ef)
            self.assertEqual(a.is_critical, a.total_float == 0)

    def assertValidDependencyOrder(self, result, links):
        position = {a.code: i for i, a in enumerate(result.activities)}
        for pred, succ in links:
            self.assertLess(position[pred], position[succ], f"{pred} must come before {succ}")


class LinearChainTests(CpmTestCase):
    # A(3) -> B(2) -> C(4)
    # Forward : A 0-3 | B 3-5 | C 5-9            D = 9
    # Backward: C LF9 LS5 | B LF5 LS3 | A LF3 LS0  -> float 0 everywhere
    LINKS = [("A", "B"), ("B", "C")]

    def setUp(self):
        self.result = run({"A": 3, "B": 2, "C": 4}, self.LINKS)

    def test_table(self):
        self.assertTable(self.result, {"A": (0, 3, 0, 3, 0), "B": (3, 5, 3, 5, 0), "C": (5, 9, 5, 9, 0)})

    def test_everything_is_critical_and_path_is_unique(self):
        self.assertEqual([a.code for a in self.result.critical_activities], ["A", "B", "C"])
        self.assertEqual(self.result.critical_path_count, 1)

    def test_duration_and_completion_date(self):
        self.assertEqual(self.result.project_duration_days, 9)
        self.assertEqual(self.result.project_start, START)
        self.assertEqual(self.result.completion_date, date(2026, 11, 11))  # Nov 2 + 9 days

    def test_schedule_order_respects_dependencies(self):
        self.assertValidDependencyOrder(self.result, self.LINKS)


class ParallelActivitiesTests(CpmTestCase):
    def test_parallel_branches_without_a_join(self):
        # S(2) -> A(5) and S(2) -> B(3); A and B have no successors.
        # Forward : S 0-2 | A 2-7 | B 2-5            D = 7
        # Backward: A LF7 LS2 (TF0) | B LF7 LS4 (TF2: may slip 2 days)
        #           S LF = min(LS_A 2, LS_B 4) = 2, LS0 (TF0)
        result = run({"S": 2, "A": 5, "B": 3}, [("S", "A"), ("S", "B")])
        self.assertTable(result, {"S": (0, 2, 0, 2, 0), "A": (2, 7, 2, 7, 0), "B": (2, 5, 4, 7, 2)})
        self.assertEqual({a.code for a in result.critical_activities}, {"S", "A"})
        self.assertEqual(result.critical_path_count, 1)
        self.assertEqual(result.project_duration_days, 7)

    def test_parallel_branches_that_rejoin(self):
        # S(2) -> A(5), S -> B(3); A -> E(1), B -> E
        # Forward : S 0-2 | A 2-7 | B 2-5 | E max(7,5)=7 -> 7-8      D = 8
        # Backward: E LF8 LS7 | A LF7 LS2 | B LF7 LS4 (TF2) | S LF=min(2,4)=2 LS0
        result = run(
            {"S": 2, "A": 5, "B": 3, "E": 1},
            [("S", "A"), ("S", "B"), ("A", "E"), ("B", "E")],
        )
        self.assertTable(
            result,
            {"S": (0, 2, 0, 2, 0), "A": (2, 7, 2, 7, 0), "B": (2, 5, 4, 7, 2), "E": (7, 8, 7, 8, 0)},
        )
        self.assertEqual(result.critical_path_count, 1)


class DiamondTests(CpmTestCase):
    LINKS = [("A", "B"), ("A", "C"), ("B", "D"), ("C", "D")]

    def test_diamond_with_one_longer_branch(self):
        # A(2) -> B(4) -> D(3) and A(2) -> C(1) -> D(3)
        # Forward : A 0-2 | B 2-6 | C 2-3 | D max(6,3)=6 -> 6-9            D = 9
        # Backward: D LF9 LS6 | B LF6 LS2 (TF0) | C LF6 LS5 (TF3) | A LF=min(2,5)=2 LS0
        result = run({"A": 2, "B": 4, "C": 1, "D": 3}, self.LINKS)
        self.assertTable(
            result,
            {"A": (0, 2, 0, 2, 0), "B": (2, 6, 2, 6, 0), "C": (2, 3, 5, 6, 3), "D": (6, 9, 6, 9, 0)},
        )
        self.assertEqual([a.code for a in result.critical_activities], ["A", "B", "D"])
        self.assertEqual(result.critical_path_count, 1)
        self.assertEqual(result.completion_date, date(2026, 11, 11))
        self.assertValidDependencyOrder(result, self.LINKS)

    def test_diamond_with_two_equal_branches_has_two_critical_paths(self):
        # A(2) -> B(3) -> D(1) and A(2) -> C(3) -> D(1)
        # Forward : A 0-2 | B 2-5 | C 2-5 | D 5-6                          D = 6
        # Backward: D LF6 LS5 | B LF5 LS2 | C LF5 LS2 | A LF2 LS0 -> all float 0
        result = run({"A": 2, "B": 3, "C": 3, "D": 1}, self.LINKS)
        self.assertTable(
            result,
            {"A": (0, 2, 0, 2, 0), "B": (2, 5, 2, 5, 0), "C": (2, 5, 2, 5, 0), "D": (5, 6, 5, 6, 0)},
        )
        self.assertEqual(len(result.critical_activities), 4)
        self.assertEqual(result.critical_path_count, 2)  # A-B-D and A-C-D


class MilestoneTests(CpmTestCase):
    def test_milestones_at_start_middle_and_end_of_a_chain(self):
        # M0(0) -> A(3) -> M1(0) -> B(2) -> M2(0)
        # Forward : M0 0-0 | A 0-3 | M1 3-3 | B 3-5 | M2 5-5               D = 5
        # Backward gives the same numbers -> everything critical
        links = [("M0", "A"), ("A", "M1"), ("M1", "B"), ("B", "M2")]
        result = run({"M0": 0, "A": 3, "M1": 0, "B": 2, "M2": 0}, links)
        self.assertTable(
            result,
            {
                "M0": (0, 0, 0, 0, 0),
                "A": (0, 3, 0, 3, 0),
                "M1": (3, 3, 3, 3, 0),
                "B": (3, 5, 3, 5, 0),
                "M2": (5, 5, 5, 5, 0),
            },
        )
        self.assertEqual([a.code for a in result.critical_activities], ["M0", "A", "M1", "B", "M2"])
        self.assertEqual(result.critical_path_count, 1)
        self.assertTrue(all(a.is_milestone for a in result.activities if a.code.startswith("M")))
        self.assertValidDependencyOrder(result, links)

    def test_join_milestone_waits_for_the_slowest_predecessor(self):
        # A(3) -> M(0), B(5) -> M(0), M -> C(2)
        # Forward : A 0-3 | B 0-5 | M max(3,5)=5 -> 5-5 | C 5-7           D = 7
        # Backward: C LF7 LS5 | M LF5 LS5 | A LF5 LS2 (TF2) | B LF5 LS0 (TF0)
        result = run(
            {"A": 3, "B": 5, "M": 0, "C": 2}, [("A", "M"), ("B", "M"), ("M", "C")]
        )
        self.assertTable(
            result,
            {"A": (0, 3, 2, 5, 2), "B": (0, 5, 0, 5, 0), "M": (5, 5, 5, 5, 0), "C": (5, 7, 5, 7, 0)},
        )
        self.assertEqual([a.code for a in result.critical_activities], ["B", "M", "C"])
        self.assertEqual(result.critical_path_count, 1)

    def test_project_made_only_of_a_milestone(self):
        result = run({"M": 0})
        self.assertTable(result, {"M": (0, 0, 0, 0, 0)})
        self.assertEqual(result.project_duration_days, 0)
        self.assertEqual(result.completion_date, START)
        self.assertEqual(result.critical_path_count, 1)

    def test_milestones_chained_at_day_zero(self):
        # M1(0) -> M2(0): D = 0, everything critical, one path
        result = run({"M1": 0, "M2": 0}, [("M1", "M2")])
        self.assertTable(result, {"M1": (0, 0, 0, 0, 0), "M2": (0, 0, 0, 0, 0)})
        self.assertEqual(result.critical_path_count, 1)
        self.assertEqual([a.code for a in result.activities], ["M1", "M2"])  # dependency order kept


class DisconnectedActivityTests(CpmTestCase):
    def test_short_isolated_activity_and_isolated_milestone_get_float(self):
        # Chain X(4) -> Y(6): X 0-4, Y 4-10, D = 10, both critical.
        # Z(3) alone: ES0 EF3; no successor so LF = D = 10, LS 7, TF 7.
        # W(0) alone: ES0 EF0; LF = 10, LS 10, TF 10.
        result = run({"X": 4, "Y": 6, "Z": 3, "W": 0}, [("X", "Y")])
        self.assertTable(
            result,
            {
                "X": (0, 4, 0, 4, 0),
                "Y": (4, 10, 4, 10, 0),
                "Z": (0, 3, 7, 10, 7),
                "W": (0, 0, 10, 10, 10),
            },
        )
        self.assertEqual([a.code for a in result.critical_activities], ["X", "Y"])
        self.assertEqual(result.critical_path_count, 1)
        self.assertEqual(result.project_duration_days, 10)

    def test_isolated_activity_as_long_as_the_project_is_a_second_critical_path(self):
        # Chain X(4) -> Y(6) and isolated P(10): both reach day 10.
        result = run({"X": 4, "Y": 6, "P": 10}, [("X", "Y")])
        self.assertTable(
            result,
            {"X": (0, 4, 0, 4, 0), "Y": (4, 10, 4, 10, 0), "P": (0, 10, 0, 10, 0)},
        )
        self.assertEqual(result.critical_path_count, 2)
        self.assertEqual(len(result.critical_activities), 3)

    def test_two_disconnected_networks_are_scheduled_independently(self):
        # Network 1: A(2) -> B(2)  (D1 = 4).  Network 2: C(5) -> D(1) (D2 = 6).  D = 6.
        # Network 1 ends at 4 but may finish as late as 6 -> float 2 for both A and B.
        result = run({"A": 2, "B": 2, "C": 5, "D": 1}, [("A", "B"), ("C", "D")])
        self.assertTable(
            result,
            {"A": (0, 2, 2, 4, 2), "B": (2, 4, 4, 6, 2), "C": (0, 5, 0, 5, 0), "D": (5, 6, 5, 6, 0)},
        )
        self.assertEqual([a.code for a in result.critical_activities], ["C", "D"])


class EdgeCaseTests(CpmTestCase):
    def test_empty_project(self):
        result = run({})
        self.assertEqual(result.activities, ())
        self.assertEqual(result.project_duration_days, 0)
        self.assertEqual(result.completion_date, START)
        self.assertEqual(result.critical_path_count, 0)
        self.assertEqual(result.critical_activities, ())

    def test_single_activity(self):
        result = run({"A": 7})
        self.assertTable(result, {"A": (0, 7, 0, 7, 0)})
        self.assertEqual(result.critical_path_count, 1)

    def test_lookup_helpers(self):
        result = run({"A": 1, "B": 2}, [("A", "B")])
        a = result.by_code()["A"]
        self.assertEqual(result.by_id()[a.activity_id], a)


class FinishExclusiveDateTests(CpmTestCase):
    def test_successor_starts_on_the_predecessors_finish_date(self):
        # A: 5 days from Monday 2 Nov. It occupies Nov 2..6; EF date is Sat Nov 7.
        result = run({"A": 5, "B": 2}, [("A", "B")])
        a, b = result.by_code()["A"], result.by_code()["B"]
        self.assertEqual(a.es_date, date(2026, 11, 2))
        self.assertEqual(a.ef_date, date(2026, 11, 7))
        self.assertEqual(b.es_date, a.ef_date)  # the successor starts the day EF falls on
        self.assertEqual(b.ef_date, date(2026, 11, 9))
        self.assertEqual(result.completion_date, date(2026, 11, 9))

    def test_milestone_has_equal_start_and_finish_dates(self):
        result = run({"A": 3, "M": 0}, [("A", "M")])
        m = result.by_code()["M"]
        self.assertEqual(m.es_date, m.ef_date)
        self.assertEqual(m.es_date, date(2026, 11, 5))

    def test_late_dates_for_a_float_activity(self):
        # S(2) -> A(5), S -> B(3): B has ES 2, LS 4, LF 7  => dates Nov 4, Nov 6, Nov 9
        result = run({"S": 2, "A": 5, "B": 3}, [("S", "A"), ("S", "B")])
        b = result.by_code()["B"]
        self.assertEqual((b.es_date, b.ef_date), (date(2026, 11, 4), date(2026, 11, 7)))
        self.assertEqual((b.ls_date, b.lf_date), (date(2026, 11, 6), date(2026, 11, 9)))

    def test_leap_day_is_counted(self):
        result = run({"A": 3}, start=date(2028, 2, 27))
        self.assertEqual(result.completion_date, date(2028, 3, 1))  # Feb 28, Feb 29, Mar 1

    def test_year_boundary(self):
        result = run({"A": 5}, start=date(2026, 12, 30))
        self.assertEqual(result.completion_date, date(2027, 1, 4))


class CircularDependencyTests(unittest.TestCase):
    def test_three_node_cycle_is_rejected_with_codes(self):
        with self.assertRaises(CircularDependencyError) as ctx:
            run({"A": 1, "B": 1, "C": 1, "D": 1}, [("A", "B"), ("B", "C"), ("C", "A"), ("C", "D")])
        self.assertEqual(sorted(ctx.exception.cycle), ["A", "B", "C"])
        self.assertIn("schedule cannot be calculated", str(ctx.exception))
        self.assertIsInstance(ctx.exception, ValidationError)  # so the UI's error handling shows it

    def test_two_node_cycle_is_rejected(self):
        with self.assertRaises(CircularDependencyError):
            run({"A": 1, "B": 1}, [("A", "B"), ("B", "A")])

    def test_self_link_is_rejected(self):
        with self.assertRaises(CircularDependencyError):
            run({"A": 1}, [("A", "A")])

    def test_cycle_in_a_disconnected_part_is_still_rejected(self):
        with self.assertRaises(CircularDependencyError):
            run({"A": 1, "B": 1, "C": 1}, [("B", "C"), ("C", "B")])


class InvalidInputTests(unittest.TestCase):
    def test_negative_duration_rejected(self):
        with self.assertRaises(ValidationError):
            compute_schedule(START, [Activity(1, 1, "A", "A", -1)], [])

    def test_non_integer_duration_rejected(self):
        for bad in (2.5, "3", None, True):
            with self.subTest(duration=bad), self.assertRaises(ValidationError):
                compute_schedule(START, [Activity(1, 1, "A", "A", bad)], [])

    def test_link_to_unknown_activity_is_a_value_error(self):
        with self.assertRaises(ValueError):
            compute_schedule(START, [Activity(1, 1, "A", "A", 1)], [Dependency(1, 1, 1, 99)])

    def test_duplicate_activity_ids_are_a_value_error(self):
        twin = [Activity(1, 1, "A", "A", 1), Activity(1, 1, "B", "B", 1)]
        with self.assertRaises(ValueError):
            compute_schedule(START, twin, [])


class OrderIndependenceTests(CpmTestCase):
    def test_input_order_does_not_change_the_numbers(self):
        spec = {"A": 2, "B": 4, "C": 1, "D": 3}
        links = [("A", "B"), ("A", "C"), ("B", "D"), ("C", "D")]
        forward = run(spec, links)
        reordered = run(dict(reversed(list(spec.items()))), list(reversed(links)))
        numbers = lambda r: {a.code: (a.es, a.ef, a.ls, a.lf, a.total_float) for a in r.activities}
        self.assertEqual(numbers(forward), numbers(reordered))
        self.assertEqual(forward.critical_path_count, reordered.critical_path_count)


class DemoProjectTests(CpmTestCase):
    """The demo network, calculated by hand.

    Forward : A100 0-5 | A110 5-13 | A120 13-19 | A130 19-26 | A140 26-36 | A150 19-25
              A160 max(36,25)=36 -> 36-41 | A170 41-53 | A180 53-61 | A190 53-67 | A200 67-73
              A210 53-63 | A220 max(73,63)=73 -> 73-82 | A230 82-92 | A240 92-99
              A250 max(61,99)=99 -> 99-102 | A260 (milestone) 102-102            D = 102
    Backward: A260 LF102 | A250 LF102 LS99 | A240 LF99 LS92 | A230 LF92 LS82 | A220 LF82 LS73
              A200 LF73 LS67 | A210 LF73 LS63 (TF 10) | A190 LF67 LS53
              A180 LF=LS(A250)=99 LS91 (TF 38) | A170 LF=min(91,53,63)=53 LS41 | A160 LF41 LS36
              A150 LF=LS(A160)=36 LS30 (TF 11) | A140 LF36 LS26 | A130 LF26 LS19
              A120 LF=min(19,30)=19 LS13 | A110 LF13 LS5 | A100 LF5 LS0
    Completion: Nov 2 2026 + 102 days = Feb 12 2027
    """

    EXPECTED = {
        "A100": (0, 5, 0, 5, 0),
        "A110": (5, 13, 5, 13, 0),
        "A120": (13, 19, 13, 19, 0),
        "A130": (19, 26, 19, 26, 0),
        "A140": (26, 36, 26, 36, 0),
        "A150": (19, 25, 30, 36, 11),
        "A160": (36, 41, 36, 41, 0),
        "A170": (41, 53, 41, 53, 0),
        "A180": (53, 61, 91, 99, 38),
        "A190": (53, 67, 53, 67, 0),
        "A200": (67, 73, 67, 73, 0),
        "A210": (53, 63, 63, 73, 10),
        "A220": (73, 82, 73, 82, 0),
        "A230": (82, 92, 82, 92, 0),
        "A240": (92, 99, 92, 99, 0),
        "A250": (99, 102, 99, 102, 0),
        "A260": (102, 102, 102, 102, 0),
    }

    def setUp(self):
        self.result = run(
            {code: days for code, _name, days in SAMPLE_ACTIVITIES}, list(SAMPLE_DEPENDENCIES)
        )

    def test_every_number_matches_the_hand_calculation(self):
        self.assertTable(self.result, self.EXPECTED)

    def test_duration_completion_and_critical_path(self):
        self.assertEqual(self.result.project_duration_days, 102)
        self.assertEqual(self.result.completion_date, date(2027, 2, 12))
        self.assertEqual(
            [a.code for a in self.result.critical_activities],
            ["A100", "A110", "A120", "A130", "A140", "A160", "A170",
             "A190", "A200", "A220", "A230", "A240", "A250", "A260"],
        )
        self.assertEqual(self.result.critical_path_count, 1)

    def test_schedule_order_respects_dependencies(self):
        self.assertValidDependencyOrder(self.result, SAMPLE_DEPENDENCIES)


if __name__ == "__main__":
    unittest.main()
