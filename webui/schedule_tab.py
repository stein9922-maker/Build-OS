"""Schedule tab: CPM results, critical path, Gantt chart and the full schedule table."""
from __future__ import annotations

from datetime import timedelta

import streamlit as st

from buildos.errors import BuildOSError
from buildos.gantt import build_gantt_figure
from buildos.models import Project
from buildos.scheduling.cpm import ScheduleResult
from buildos.tables import schedule_to_dataframe

from .common import Services, show_error


def _day(value) -> str:
    return f"{value:%Y-%m-%d} ({value:%a})"


def render_schedule_tab(services: Services, project: Project) -> None:
    st.subheader(f"Schedule for '{project.name}'")
    st.caption(
        "Calculated with the Critical Path Method from the activities, durations and "
        "finish-to-start dependencies. It is recalculated every time you open this tab, "
        "so it always reflects your latest edits."
    )

    try:
        result = services.schedule.calculate_schedule(project.id)
    except BuildOSError as exc:
        show_error(exc)
        return

    if not result.activities:
        st.info("Add activities (and dependencies) first. The schedule is calculated from them.")
        return

    _render_summary(result)
    _render_convention_note(result)
    _render_critical_path(result)

    st.markdown("#### Gantt chart")
    try:
        figure = build_gantt_figure(result)
    except ImportError:
        st.error("Plotly is not installed, so the chart cannot be drawn. "
                 "Run: pip install -r requirements.txt")
    else:
        st.plotly_chart(figure, key=f"gantt_chart_{project.id}")
        st.caption(
            "Red = critical (zero float). Blue = has float. Diamonds = zero-day milestones. "
            "The dotted line is the projected completion date. Hover a bar for details."
        )

    st.markdown("#### Schedule table")
    st.dataframe(schedule_to_dataframe(result), hide_index=True)
    st.caption(
        "ES/EF = earliest start/finish, LS/LF = latest start/finish (day numbers; day 0 = project "
        "start). Total float = days an activity can slip without delaying the project completion."
    )


def _render_summary(result: ScheduleResult) -> None:
    total = len(result.activities)
    critical = len(result.critical_activities)
    col_start, col_end, col_duration, col_critical = st.columns(4)
    col_start.metric("Project start", _day(result.project_start))
    col_end.metric("Projected completion", _day(result.completion_date))
    col_duration.metric("Project duration", f"{result.project_duration_days} days")
    col_critical.metric("Critical activities", f"{critical} of {total}")


def _render_convention_note(result: ScheduleResult) -> None:
    start = result.project_start
    day0, day4, day5 = start, start + timedelta(days=4), start + timedelta(days=5)
    st.info(
        "**How dates work (finish-exclusive convention)**\n\n"
        f"- Day 0 is the project start date ({start:%Y-%m-%d}). ES, EF, LS and LF are day numbers "
        "counted from it, and every date is simply the start date plus that many days.\n"
        "- An activity occupies the days from its start up to, but **not including**, its finish: "
        "**EF = ES + duration**. So EF is the first day *after* the activity, and it is the day a "
        "successor is allowed to start.\n"
        f"- Example: an activity with ES = 0 and a 5-day duration works on {day0:%Y-%m-%d} through "
        f"{day4:%Y-%m-%d}. Its EF is day 5 ({day5:%Y-%m-%d}), which is when its successor starts.\n"
        "- The projected completion date is finish-exclusive too: the last day of work is the day "
        "*before* it.\n"
        "- Durations are calendar days (weekends and holidays count); dependencies are "
        "finish-to-start with no lag."
    )


def _render_critical_path(result: ScheduleResult) -> None:
    critical = result.critical_activities
    codes = [a.code for a in critical]
    if result.critical_path_count == 1:
        st.markdown("**Critical path:** " + " → ".join(codes))
    else:
        st.warning(
            f"There are **{result.critical_path_count} parallel critical paths** (separate "
            f"zero-float chains of equal length). All {len(critical)} critical activities are "
            "highlighted: " + ", ".join(codes) + ". A delay on any of them delays the project."
        )
