"""Headless UI smoke tests (see tests/fakes.py for what this does and does NOT prove).

They execute the real app.py and the real Schedule tab against a real temporary SQLite
database, with a stand-in for Streamlit that never presses buttons. A pass means the Python
wiring runs and shows the expected numbers - NOT that the page looks right in a browser.
"""
import runpy
import unittest
from unittest import mock

from buildos.sample_data import load_sample_project
from buildos.services import ScheduleService
from tests.fakes import PROJECT_ROOT, headless_streamlit
from tests.helpers import TempDatabaseTestCase


class SmokeBase(TempDatabaseTestCase):
    def _services(self, common):
        return common.Services(self.projects, self.activities, ScheduleService(self.db))

    def render_schedule(self, project_id, plotly="fake"):
        with headless_streamlit(plotly) as st:
            import webui.common as common
            from webui.schedule_tab import render_schedule_tab

            render_schedule_tab(self._services(common), self.projects.get_project(project_id))
        return st

    def run_app(self, plotly="fake"):
        with headless_streamlit(plotly) as st:
            import webui.common as common

            with mock.patch.object(common, "get_services", return_value=self._services(common)):
                runpy.run_path(str(PROJECT_ROOT / "app.py"), run_name="__main__")
        return st


class ScheduleTabSmokeTests(SmokeBase):
    def test_demo_project_shows_summary_table_chart_and_critical_path(self):
        project = load_sample_project(self.projects, self.activities)
        st = self.render_schedule(project.id)

        metrics = {args[0]: args[1] for args, _kw in st.of("metric")}
        self.assertEqual(metrics["Project start"], "2026-11-02 (Mon)")
        self.assertEqual(metrics["Projected completion"], "2027-02-12 (Fri)")
        self.assertEqual(metrics["Project duration"], "102 days")
        self.assertEqual(metrics["Critical activities"], "14 of 17")

        (table_args, _), = st.of("dataframe")
        table = table_args[0]
        self.assertEqual(len(table), 17)
        for column in ("Duration (days)", "ES", "EF", "LS", "LF", "Total float (days)", "Critical"):
            self.assertIn(column, table.columns)
        self.assertEqual(table[table["Code"] == "A180"]["Total float (days)"].iloc[0], 38)

        self.assertEqual(len(st.of("plotly_chart")), 1)
        self.assertEqual(st.of("error"), [])

        path_line, = [t for t in st.texts("markdown") if t.startswith("**Critical path:**")]
        self.assertIn("A100 → A110 → A120 → A130 → A140 → A160", path_line)
        self.assertTrue(path_line.endswith("A250 → A260"))

    def test_finish_exclusive_convention_is_explained_with_a_concrete_example(self):
        project = load_sample_project(self.projects, self.activities)
        st = self.render_schedule(project.id)
        note, = [t for t in st.texts("info") if "finish-exclusive" in t]
        for phrase in ("EF = ES + duration", "first day *after*", "2026-11-02", "2026-11-06", "2026-11-07"):
            self.assertIn(phrase, note)

    def test_parallel_critical_paths_are_announced(self):
        p = self.make_project()
        a, b, c, d = (self.make_activity(p.id, code, dur) for code, dur in (("A", 2), ("B", 3), ("C", 3), ("D", 1)))
        for pred, succ in ((a, b), (a, c), (b, d), (c, d)):
            self.activities.add_dependency(p.id, pred.id, succ.id)
        st = self.render_schedule(p.id)
        warning, = st.texts("warning")
        self.assertIn("2 parallel critical paths", warning)

    def test_empty_project_shows_guidance_and_no_chart(self):
        st = self.render_schedule(self.make_project().id)
        self.assertTrue(any("Add activities" in t for t in st.texts("info")))
        self.assertEqual((st.of("plotly_chart"), st.of("dataframe"), st.of("metric")), ([], [], []))

    def test_stored_cycle_shows_an_error_instead_of_crashing(self):
        p = self.make_project()
        a, b = self.make_activity(p.id, "A"), self.make_activity(p.id, "B")
        self.activities.add_dependency(p.id, a.id, b.id)
        with self.db.connect() as conn:
            conn.execute("INSERT INTO dependencies (project_id, predecessor_id, successor_id) VALUES (?,?,?)",
                         (p.id, b.id, a.id))
        st = self.render_schedule(p.id)
        self.assertTrue(any("circular dependency" in t for t in st.texts("error")))
        self.assertEqual((st.of("plotly_chart"), st.of("dataframe")), ([], []))

    def test_missing_plotly_shows_a_helpful_error_but_keeps_the_table(self):
        project = load_sample_project(self.projects, self.activities)
        st = self.render_schedule(project.id, plotly="missing")
        self.assertTrue(any("Plotly is not installed" in t for t in st.texts("error")))
        self.assertEqual(len(st.of("dataframe")), 1)
        self.assertEqual(st.of("plotly_chart"), [])


class WholeAppSmokeTests(SmokeBase):
    def test_app_runs_with_the_demo_project(self):
        load_sample_project(self.projects, self.activities)
        st = self.run_app()
        args, _ = st.of("tabs")[0]
        self.assertEqual(list(args[0]), ["Project", "Activities", "Dependencies", "Schedule", "Procurement"])
        self.assertEqual(len(st.of("set_page_config")), 1)
        self.assertEqual(st.of("error"), [])
        self.assertEqual(len(st.of("plotly_chart")), 1)
        self.assertEqual(len(st.of("dataframe")), 3)  # activities, dependencies, schedule
        self.assertIn("2027-02-12 (Fri)", [a[1] for a, _ in st.of("metric")])

    def test_app_runs_with_no_projects_and_asks_the_user_to_create_one(self):
        st = self.run_app()
        self.assertTrue(any("No projects yet" in t for t in st.texts("info")))
        self.assertEqual(st.texts("info").count("Select or create a project first."), 4)
        self.assertEqual((st.of("error"), st.of("plotly_chart")), ([], []))

    def test_app_runs_with_an_empty_project(self):
        self.make_project()
        st = self.run_app()
        self.assertEqual(st.of("error"), [])
        self.assertTrue(any("Add activities" in t for t in st.texts("info")))

    def test_app_survives_plotly_being_unavailable(self):
        load_sample_project(self.projects, self.activities)
        st = self.run_app(plotly="missing")
        self.assertTrue(any("Plotly is not installed" in t for t in st.texts("error")))


if __name__ == "__main__":
    unittest.main()
