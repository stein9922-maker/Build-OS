"""Turn model objects into pandas DataFrames for display. No Streamlit here, so it is testable."""
from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

from .models import Activity, Dependency
from .scheduling.cpm import ScheduleResult

ACTIVITY_COLUMNS = ["Code", "Name", "Duration (days)", "Predecessors (FS)", "Notes"]
DEPENDENCY_COLUMNS = ["Predecessor", "Successor", "Type"]


def activities_to_dataframe(
    activities: Sequence[Activity], dependencies: Sequence[Dependency]
) -> pd.DataFrame:
    code_by_id = {a.id: a.code for a in activities}
    predecessors: dict[int, list[str]] = {a.id: [] for a in activities}
    for dep in dependencies:
        if dep.successor_id in predecessors and dep.predecessor_id in code_by_id:
            predecessors[dep.successor_id].append(code_by_id[dep.predecessor_id])
    rows = [
        [a.code, a.name, a.duration_days, ", ".join(sorted(predecessors[a.id])), a.notes]
        for a in activities
    ]
    return pd.DataFrame(rows, columns=ACTIVITY_COLUMNS)


def dependencies_to_dataframe(
    activities: Sequence[Activity], dependencies: Sequence[Dependency]
) -> pd.DataFrame:
    by_id = {a.id: a for a in activities}
    rows = []
    for dep in dependencies:
        pred, succ = by_id[dep.predecessor_id], by_id[dep.successor_id]
        rows.append([f"{pred.code} - {pred.name}", f"{succ.code} - {succ.name}", "FS"])
    return pd.DataFrame(rows, columns=DEPENDENCY_COLUMNS)


SCHEDULE_COLUMNS = [
    "Code",
    "Name",
    "Duration (days)",
    "ES",
    "EF",
    "LS",
    "LF",
    "Total float (days)",
    "Critical",
    "Early start date",
    "Early finish date",
    "Late start date",
    "Late finish date",
]


def schedule_to_dataframe(result: ScheduleResult) -> pd.DataFrame:
    """One row per activity in schedule order. ES/EF/LS/LF are day numbers (day 0 = project
    start). All dates follow the finish-exclusive convention, so a 'finish date' is the first
    day AFTER the activity. Dates are ISO text (yyyy-mm-dd) so they display and sort reliably."""
    rows = [
        [
            a.code,
            a.name,
            a.duration_days,
            a.es,
            a.ef,
            a.ls,
            a.lf,
            a.total_float,
            "Yes" if a.is_critical else "No",
            a.es_date.isoformat(),
            a.ef_date.isoformat(),
            a.ls_date.isoformat(),
            a.lf_date.isoformat(),
        ]
        for a in result.activities
    ]
    return pd.DataFrame(rows, columns=SCHEDULE_COLUMNS)
