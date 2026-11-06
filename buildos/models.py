"""Plain, immutable data records. No behaviour, no database code."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Project:
    id: int
    name: str
    start_date: date
    description: str = ""


@dataclass(frozen=True)
class Activity:
    id: int
    project_id: int
    code: str
    name: str
    duration_days: int  # whole calendar days; 0 = milestone
    notes: str = ""


@dataclass(frozen=True)
class Dependency:
    """Finish-to-start link: `successor` cannot start until `predecessor` has finished."""

    id: int
    project_id: int
    predecessor_id: int
    successor_id: int
