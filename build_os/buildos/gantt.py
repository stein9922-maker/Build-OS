"""Gantt chart support.

* `gantt_dataframe` prepares everything the chart needs (pandas only, fully unit-tested).
* `build_gantt_figure` hands that data to Plotly. Plotly is imported inside the function, so
  the rest of the application (and the test suite) works even where Plotly is not installed.

Finish-exclusive reminder: a bar runs from the activity's early-start date up to (not
including) its early-finish date, so a 5-day activity starting Monday 2 Nov covers Nov 2-6
and its bar ends at the start of Sat Nov 7. Milestones (0 days) are drawn as diamonds.
"""
from __future__ import annotations

import html
from datetime import date

import pandas as pd

from .scheduling.cpm import ActivitySchedule, ScheduleResult

MS_PER_DAY = 86_400_000  # Plotly measures bar length on a date axis in milliseconds

CRITICAL_COLOR = "#d62728"
NON_CRITICAL_COLOR = "#1f77b4"
MILESTONE_COLOR = "#555555"

# (is_critical, is_milestone, legend name, colour) - one Plotly trace per combination present
TRACE_SPECS = (
    (True, False, "Critical activity", CRITICAL_COLOR),
    (False, False, "Non-critical activity", NON_CRITICAL_COLOR),
    (True, True, "Critical milestone", CRITICAL_COLOR),
    (False, True, "Milestone", MILESTONE_COLOR),
)

GANTT_COLUMNS = [
    "Label",
    "Code",
    "Name",
    "Start",
    "Finish",
    "Duration (days)",
    "Total float (days)",
    "Critical",
    "Milestone",
    "Hover",
]


def _pretty(day: date) -> str:
    return day.strftime("%a %d %b %Y")


def _hover_text(a: ActivitySchedule) -> str:
    duration = "Milestone (0 days)" if a.is_milestone else f"Duration: {a.duration_days} days"
    return "<br>".join(
        [
            f"<b>{html.escape(a.code)} - {html.escape(a.name)}</b>",
            duration,
            f"Early start: {_pretty(a.es_date)} (day {a.es})",
            f"Early finish: {_pretty(a.ef_date)} (day {a.ef}, finish-exclusive)",
            f"Late start: {_pretty(a.ls_date)} (day {a.ls})",
            f"Late finish: {_pretty(a.lf_date)} (day {a.lf}, finish-exclusive)",
            f"Total float: {a.total_float} days",
            "CRITICAL" if a.is_critical else "Not critical",
        ]
    )


def gantt_dataframe(result: ScheduleResult) -> pd.DataFrame:
    """One row per activity, in schedule order (the order bars appear top to bottom)."""
    rows = [
        [
            f"{a.code} - {a.name}",
            a.code,
            a.name,
            a.es_date.isoformat(),
            a.ef_date.isoformat(),
            a.duration_days,
            a.total_float,
            a.is_critical,
            a.is_milestone,
            _hover_text(a),
        ]
        for a in result.activities
    ]
    return pd.DataFrame(rows, columns=GANTT_COLUMNS)


def build_gantt_figure(result: ScheduleResult):
    """Return an interactive Plotly Gantt figure for a calculated schedule."""
    import plotly.graph_objects as go  # imported here on purpose (see module docstring)

    rows = gantt_dataframe(result)
    labels = [html.escape(label) for label in rows["Label"]]
    rows = rows.assign(Y=labels)

    figure = go.Figure()
    for is_critical, is_milestone, name, color in TRACE_SPECS:
        part = rows[(rows["Critical"] == is_critical) & (rows["Milestone"] == is_milestone)]
        if part.empty:
            continue
        if is_milestone:
            figure.add_trace(
                go.Scatter(
                    x=part["Start"].tolist(),
                    y=part["Y"].tolist(),
                    mode="markers",
                    marker={"symbol": "diamond", "size": 14, "color": color,
                            "line": {"width": 1, "color": "#222222"}},
                    name=name,
                    hovertext=part["Hover"].tolist(),
                    hoverinfo="text",
                )
            )
        else:
            figure.add_trace(
                go.Bar(
                    base=part["Start"].tolist(),
                    x=[int(days) * MS_PER_DAY for days in part["Duration (days)"]],
                    y=part["Y"].tolist(),
                    orientation="h",
                    marker={"color": color, "line": {"width": 0.5, "color": "#222222"}},
                    name=name,
                    hovertext=part["Hover"].tolist(),
                    hoverinfo="text",
                )
            )

    completion = result.completion_date.isoformat()
    figure.update_layout(
        height=max(320, 30 * len(rows) + 160),
        barmode="overlay",
        bargap=0.25,
        margin={"l": 10, "r": 20, "t": 90, "b": 40},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.10, "xanchor": "left", "x": 0},
        xaxis={
            "type": "date",
            "title": {"text": "Calendar date (a bar ends at the start of the day after its last working day)"},
        },
        yaxis={"autorange": "reversed", "categoryorder": "array", "categoryarray": labels,
               "automargin": True},
        shapes=[
            {"type": "line", "xref": "x", "yref": "paper", "x0": completion, "x1": completion,
             "y0": 0, "y1": 1, "line": {"dash": "dot", "width": 2, "color": "#555555"}}
        ],
        annotations=[
            {"x": completion, "xref": "x", "y": 1, "yref": "paper", "text": "Projected completion",
             "showarrow": False, "xanchor": "right", "yanchor": "bottom"}
        ],
    )
    return figure
