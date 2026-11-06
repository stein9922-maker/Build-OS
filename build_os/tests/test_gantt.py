"""Gantt tests.

* The data-preparation tests run everywhere.
* The figure tests that use a *stand-in* for Plotly run everywhere too: they check OUR logic
  (which bars, where, how long, what colour) but cannot prove Plotly accepts the arguments.
* The final class uses the REAL Plotly and is skipped when Plotly is not installed.
"""
import unittest
from datetime import date

from buildos.gantt import (
    CRITICAL_COLOR,
    GANTT_COLUMNS,
    MILESTONE_COLOR,
    MS_PER_DAY,
    NON_CRITICAL_COLOR,
    build_gantt_figure,
    gantt_dataframe,
)
from buildos.sample_data import SAMPLE_ACTIVITIES, SAMPLE_DEPENDENCIES
from tests.fakes import Bar as _Bar
from tests.fakes import Scatter as _Scatter
from tests.fakes import fake_plotly
from tests.test_cpm import run

try:
    import plotly.graph_objects  # noqa: F401
    HAVE_PLOTLY = True
except ImportError:
    HAVE_PLOTLY = False


def demo_result():
    return run({c: d for c, _n, d in SAMPLE_ACTIVITIES}, list(SAMPLE_DEPENDENCIES))


def build_with_fake(result):
    with fake_plotly():
        return build_gantt_figure(result)


class GanttDataFrameTests(unittest.TestCase):
    def setUp(self):
        # S(2) -> A(5) -> M(0);  S -> B(3).  Start Mon 2026-11-02.  D = 7
        self.result = run({"S": 2, "A": 5, "B": 3, "M": 0}, [("S", "A"), ("S", "B"), ("A", "M")])
        self.df = gantt_dataframe(self.result)

    def test_columns_and_order(self):
        self.assertEqual(list(self.df.columns), GANTT_COLUMNS)
        self.assertEqual(self.df["Code"].tolist(), ["S", "B", "A", "M"])  # schedule order

    def test_start_and_finish_are_finish_exclusive_iso_dates(self):
        a = self.df[self.df["Code"] == "A"].iloc[0]  # ES 2, EF 7
        self.assertEqual((a["Start"], a["Finish"]), ("2026-11-04", "2026-11-09"))
        self.assertEqual(a["Duration (days)"], 5)

    def test_milestone_and_critical_flags(self):
        flags = {r["Code"]: (bool(r["Critical"]), bool(r["Milestone"])) for _, r in self.df.iterrows()}
        self.assertEqual(flags, {"S": (True, False), "A": (True, False),
                                 "B": (False, False), "M": (True, True)})

    def test_milestone_start_equals_finish(self):
        m = self.df[self.df["Code"] == "M"].iloc[0]
        self.assertEqual(m["Start"], m["Finish"])

    def test_hover_text_is_informative(self):
        hover = self.df[self.df["Code"] == "B"].iloc[0]["Hover"]
        for expected in ("B - Activity B", "Duration: 3 days", "Total float: 2 days",
                         "Not critical", "finish-exclusive"):
            self.assertIn(expected, hover)
        self.assertIn("CRITICAL", self.df[self.df["Code"] == "A"].iloc[0]["Hover"])

    def test_empty_schedule(self):
        self.assertEqual(len(gantt_dataframe(run({}))), 0)


class GanttFigureLogicTests(unittest.TestCase):
    """Uses the stand-in for Plotly - checks our logic, not Plotly's acceptance of it."""

    def setUp(self):
        self.result = demo_result()
        self.fig = build_with_fake(self.result)
        self.by_name = {t.kwargs["name"]: t for t in self.fig.traces}

    def test_one_trace_per_present_category(self):
        # demo: 13 critical bars, 3 non-critical bars (A150, A180, A210), 1 critical milestone
        self.assertEqual(sorted(self.by_name), ["Critical activity", "Critical milestone", "Non-critical activity"])
        self.assertIsInstance(self.by_name["Critical activity"], _Bar)
        self.assertIsInstance(self.by_name["Critical milestone"], _Scatter)

    def test_every_activity_is_drawn_exactly_once(self):
        drawn = sum(len(t.kwargs["y"]) for t in self.fig.traces)
        self.assertEqual(drawn, len(SAMPLE_ACTIVITIES))
        self.assertEqual(len(self.by_name["Critical activity"].kwargs["y"]), 13)
        self.assertEqual(len(self.by_name["Non-critical activity"].kwargs["y"]), 3)

    def test_critical_bars_are_red_and_others_blue(self):
        self.assertEqual(self.by_name["Critical activity"].kwargs["marker"]["color"], CRITICAL_COLOR)
        self.assertEqual(self.by_name["Non-critical activity"].kwargs["marker"]["color"], NON_CRITICAL_COLOR)
        self.assertEqual(self.by_name["Critical milestone"].kwargs["marker"]["color"], CRITICAL_COLOR)

    def test_bar_geometry_matches_the_schedule(self):
        bars = self.by_name["Non-critical activity"].kwargs
        got = {y.split(" - ")[0]: (base, x) for y, base, x in zip(bars["y"], bars["base"], bars["x"])}
        # A150: ES 19, 6 days ; A180: ES 53, 8 days ; A210: ES 53, 10 days (start Nov 2 2026)
        self.assertEqual(got["A150"], ("2026-11-21", 6 * MS_PER_DAY))
        self.assertEqual(got["A180"], ("2026-12-25", 8 * MS_PER_DAY))
        self.assertEqual(got["A210"], ("2026-12-25", 10 * MS_PER_DAY))
        self.assertEqual(bars["orientation"], "h")

    def test_milestone_is_a_diamond_on_its_date(self):
        marker = self.by_name["Critical milestone"].kwargs
        self.assertEqual(marker["x"], ["2027-02-12"])  # day 102
        self.assertEqual(marker["marker"]["symbol"], "diamond")
        self.assertTrue(marker["y"][0].startswith("A260"))

    def test_axis_order_follows_the_schedule_and_is_reversed_so_first_is_on_top(self):
        yaxis = self.fig.layout["yaxis"]
        self.assertEqual(yaxis["autorange"], "reversed")
        self.assertEqual(yaxis["categoryorder"], "array")
        self.assertEqual([c.split(" - ")[0] for c in yaxis["categoryarray"]][:3], ["A100", "A110", "A120"])
        self.assertEqual(len(yaxis["categoryarray"]), len(SAMPLE_ACTIVITIES))
        self.assertEqual(self.fig.layout["xaxis"]["type"], "date")

    def test_projected_completion_marker(self):
        shape = self.fig.layout["shapes"][0]
        self.assertEqual((shape["x0"], shape["x1"]), ("2027-02-12", "2027-02-12"))
        self.assertEqual(self.fig.layout["annotations"][0]["x"], "2027-02-12")

    def test_hover_text_is_attached_to_every_item(self):
        for trace in self.fig.traces:
            self.assertEqual(len(trace.kwargs["hovertext"]), len(trace.kwargs["y"]))
            self.assertEqual(trace.kwargs["hoverinfo"], "text")

    def test_only_milestones_means_only_a_scatter_trace(self):
        fig = build_with_fake(run({"M1": 0, "M2": 0}, [("M1", "M2")]))
        self.assertEqual([type(t) for t in fig.traces], [_Scatter])

    def test_non_critical_milestone_gets_its_own_trace_and_colour(self):
        fig = build_with_fake(run({"X": 5, "M": 0}))  # M is disconnected -> float 5
        names = {t.kwargs["name"]: t for t in fig.traces}
        self.assertEqual(names["Milestone"].kwargs["marker"]["color"], MILESTONE_COLOR)

    def test_html_in_names_is_escaped(self):
        from buildos.models import Activity
        from buildos.scheduling.cpm import compute_schedule
        result = compute_schedule(date(2026, 11, 2), [Activity(1, 1, "A", "<b>x</b> & y", 3)], [])
        fig = build_with_fake(result)
        self.assertEqual(fig.traces[0].kwargs["y"], ["A - &lt;b&gt;x&lt;/b&gt; &amp; y"])


@unittest.skipUnless(HAVE_PLOTLY, "plotly is not installed in this environment")
class GanttRealPlotlyTests(unittest.TestCase):
    """Runs only where Plotly is installed. Real Plotly validates every argument we pass."""

    def test_real_figure_builds_and_serialises(self):
        fig = build_gantt_figure(demo_result())
        self.assertEqual(len(fig.data), 3)
        self.assertEqual(fig.layout.yaxis.autorange, "reversed")
        self.assertEqual(fig.layout.xaxis.type, "date")
        self.assertIn("Critical activity", fig.to_json())

    def test_real_figure_for_milestone_only_project(self):
        fig = build_gantt_figure(run({"M": 0}))
        self.assertEqual(len(fig.data), 1)


if __name__ == "__main__":
    unittest.main()
