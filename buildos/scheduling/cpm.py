"""Critical Path Method (CPM) engine. Pure logic: no database, no Streamlit.

Conventions (version one, deliberately explicit)
------------------------------------------------
* Time is measured in whole CALENDAR DAYS from the project start. Day 0 is the start date.
* FINISH-EXCLUSIVE: an activity with early start ES and duration d occupies the days
  [ES, EF) where EF = ES + d. EF is the first day AFTER the activity, which is also the
  earliest day a finish-to-start successor may start. Dates are start_date + N days.
  Example: start Mon 2 Nov, ES = 0, d = 5 -> works Nov 2..6, EF = 5 = Sat 7 Nov.
* All dependencies are finish-to-start with no lag:  ES = max(EF of predecessors), or 0.
* Project duration D = max(EF). Projected completion date = start_date + D days.
* Backward pass: LF = min(LS of successors), or D when there are none. LS = LF - d.
  So an activity with no successors may finish as late as the project end. This is why a
  short, disconnected activity gets positive float.
* Total float TF = LS - ES (= LF - EF). An activity is critical when TF == 0.
* Zero-duration activities (milestones) have ES == EF and take part in everything normally.

Everything is integer arithmetic, so "float == 0" is an exact test.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta

import networkx as nx

from ..errors import CircularDependencyError, ValidationError, format_cycle
from ..models import Activity, Dependency
from .graph import build_graph, find_cycle


@dataclass(frozen=True)
class ActivitySchedule:
    """CPM results for one activity. es/ef/ls/lf are day offsets from the project start."""

    activity_id: int
    code: str
    name: str
    duration_days: int
    es: int
    ef: int
    ls: int
    lf: int
    total_float: int
    is_critical: bool
    es_date: date  # = project start + es
    ef_date: date  # finish-exclusive: the first day after the activity
    ls_date: date
    lf_date: date

    @property
    def is_milestone(self) -> bool:
        return self.duration_days == 0


@dataclass(frozen=True)
class ScheduleResult:
    """Full CPM result.

    `activities` is in schedule order: sorted by (ES, EF) with ties broken topologically,
    so it is always a valid dependency order (every predecessor appears before its successors).
    """

    project_start: date
    project_duration_days: int
    completion_date: date  # project_start + duration (finish-exclusive)
    activities: tuple[ActivitySchedule, ...]
    # Number of distinct start-to-finish paths whose length equals the project duration.
    # 0 for an empty project; 1 means "the" critical path is unique.
    critical_path_count: int

    @property
    def critical_activities(self) -> tuple[ActivitySchedule, ...]:
        """Every zero-float activity, in schedule order. Equals the critical path when
        `critical_path_count == 1`; with several parallel critical paths it is their union."""
        return tuple(a for a in self.activities if a.is_critical)

    def by_id(self) -> dict[int, ActivitySchedule]:
        return {a.activity_id: a for a in self.activities}

    def by_code(self) -> dict[str, ActivitySchedule]:
        return {a.code: a for a in self.activities}


def _check_inputs(activities: Sequence[Activity]) -> None:
    seen: set[int] = set()
    for activity in activities:
        if activity.id in seen:
            raise ValueError(f"Duplicate activity id {activity.id}.")
        seen.add(activity.id)
        duration = activity.duration_days
        if isinstance(duration, bool) or not isinstance(duration, int) or duration < 0:
            raise ValidationError(
                f"Activity {activity.code} has an invalid duration ({duration!r}); "
                "it must be a whole number of days, 0 or more."
            )


def compute_schedule(
    project_start: date,
    activities: Sequence[Activity],
    dependencies: Sequence[Dependency],
) -> ScheduleResult:
    """Run the CPM forward and backward passes.

    Raises CircularDependencyError if the dependencies contain a loop, ValidationError for
    an invalid duration, and ValueError for structurally broken input (duplicate ids or a
    link to an unknown activity).
    """
    _check_inputs(activities)
    position = {a.id: index for index, a in enumerate(activities)}
    by_id = {a.id: a for a in activities}
    graph = build_graph(position, [(d.predecessor_id, d.successor_id) for d in dependencies])

    cycle_ids = find_cycle(graph)
    if cycle_ids is not None:
        codes = [by_id[i].code for i in cycle_ids]
        raise CircularDependencyError(
            codes,
            message=(
                "The schedule cannot be calculated because the dependencies contain a "
                f"circular dependency: {format_cycle(codes)}."
            ),
        )

    # Deterministic topological order (ties broken by the order the activities were given).
    topo = list(nx.lexicographical_topological_sort(graph, key=position.__getitem__))

    # ---- forward pass ----
    es: dict[int, int] = {}
    ef: dict[int, int] = {}
    for node in topo:
        es[node] = max((ef[p] for p in graph.predecessors(node)), default=0)
        ef[node] = es[node] + by_id[node].duration_days
    project_duration = max(ef.values(), default=0)

    # ---- backward pass ----
    ls: dict[int, int] = {}
    lf: dict[int, int] = {}
    for node in reversed(topo):
        lf[node] = min((ls[s] for s in graph.successors(node)), default=project_duration)
        ls[node] = lf[node] - by_id[node].duration_days

    total_float = {n: ls[n] - es[n] for n in topo}
    critical = {n for n in topo if total_float[n] == 0}

    # ---- count critical paths ----
    # A "driving" link joins two critical activities with no gap (EF of predecessor == ES of
    # successor). Critical paths are exactly the start-to-finish paths made of driving links.
    ways: dict[int, int] = {}
    for node in topo:
        if node not in critical:
            continue
        driving_preds = [p for p in graph.predecessors(node) if p in critical and ef[p] == es[node]]
        ways[node] = sum(ways[p] for p in driving_preds) if driving_preds else 1
    path_count = sum(
        ways[n]
        for n in critical
        if not any(s in critical and ef[n] == es[s] for s in graph.successors(n))
    )

    # ---- assemble results in schedule order ----
    topo_index = {n: i for i, n in enumerate(topo)}
    ordered = sorted(topo, key=lambda n: (es[n], ef[n], topo_index[n]))

    def on(day: int) -> date:
        return project_start + timedelta(days=day)

    rows = tuple(
        ActivitySchedule(
            activity_id=n,
            code=by_id[n].code,
            name=by_id[n].name,
            duration_days=by_id[n].duration_days,
            es=es[n],
            ef=ef[n],
            ls=ls[n],
            lf=lf[n],
            total_float=total_float[n],
            is_critical=n in critical,
            es_date=on(es[n]),
            ef_date=on(ef[n]),
            ls_date=on(ls[n]),
            lf_date=on(lf[n]),
        )
        for n in ordered
    )
    return ScheduleResult(
        project_start=project_start,
        project_duration_days=project_duration,
        completion_date=on(project_duration),
        activities=rows,
        critical_path_count=path_count,
    )
