"""Illustrative demo project so the app can be explored immediately.

IMPORTANT: every duration and every link below is a made-up placeholder chosen to give a
realistic-looking network with parallel paths. They are NOT estimates for a real job, and
this file deliberately contains no material quantities.

Run `python -m buildos.sample_data` to load it into the default database from the command line.
"""
from __future__ import annotations

from datetime import date

from .config import DEFAULT_DB_PATH
from .db import Database
from .errors import ValidationError
from .models import Project
from .services import ActivityService, ProjectService
from .tables import activities_to_dataframe

SAMPLE_PROJECT_NAME = "DEMO - Single-Storey Commercial Building (illustrative)"
SAMPLE_DESCRIPTION = (
    "Illustrative demo project. Durations and logic are made-up placeholders for exploring "
    "the app, not estimates for any real job. Contains no material quantities."
)
SAMPLE_START_DATE = date(2026, 11, 2)  # fixed so demos and tests are reproducible

# (code, name, duration in calendar days)
SAMPLE_ACTIVITIES: tuple[tuple[str, str, int], ...] = (
    ("A100", "Mobilization and site setup", 5),
    ("A110", "Site clearing and earthworks", 8),
    ("A120", "Foundation excavation", 6),
    ("A130", "Footing formwork and reinforcement", 7),
    ("A140", "Footing concrete pour and curing", 10),
    ("A150", "Underground utilities", 6),
    ("A160", "Slab on grade", 5),
    ("A170", "Structural frame erection", 12),
    ("A180", "Roofing", 8),
    ("A190", "Exterior walls and envelope", 14),
    ("A200", "Windows and doors installation", 6),
    ("A210", "MEP rough-in", 10),
    ("A220", "Interior partitions and drywall", 9),
    ("A230", "Interior finishes", 10),
    ("A240", "Fixtures and MEP trim-out", 7),
    ("A250", "Final inspection and handover", 3),
    ("A260", "Substantial completion (milestone)", 0),
)

# (predecessor code, successor code); all finish-to-start
SAMPLE_DEPENDENCIES: tuple[tuple[str, str], ...] = (
    ("A100", "A110"),
    ("A110", "A120"),
    ("A120", "A130"),
    ("A130", "A140"),
    ("A120", "A150"),
    ("A140", "A160"),
    ("A150", "A160"),
    ("A160", "A170"),
    ("A170", "A180"),
    ("A170", "A190"),
    ("A190", "A200"),
    ("A170", "A210"),
    ("A200", "A220"),
    ("A210", "A220"),
    ("A220", "A230"),
    ("A230", "A240"),
    ("A180", "A250"),
    ("A240", "A250"),
    ("A250", "A260"),
)


def load_sample_project(
    projects: ProjectService, activities: ActivityService, start_date: date = SAMPLE_START_DATE
) -> Project:
    """Create the demo project. Raises ValidationError if it already exists.

    If anything fails part-way, the half-built project is removed so no partial data is left.
    """
    project = projects.create_project(SAMPLE_PROJECT_NAME, start_date, SAMPLE_DESCRIPTION)
    try:
        ids: dict[str, int] = {}
        for code, name, duration in SAMPLE_ACTIVITIES:
            ids[code] = activities.add_activity(project.id, code, name, duration).id
        for predecessor, successor in SAMPLE_DEPENDENCIES:
            activities.add_dependency(project.id, ids[predecessor], ids[successor])
    except Exception:
        projects.delete_project(project.id)
        raise
    return project


def main() -> int:
    db = Database(DEFAULT_DB_PATH)
    db.initialize()
    projects, activities = ProjectService(db), ActivityService(db)
    try:
        project = load_sample_project(projects, activities)
    except ValidationError as exc:
        print(f"Nothing loaded: {exc}")
        return 1
    table = activities_to_dataframe(
        activities.list_activities(project.id), activities.list_dependencies(project.id)
    )
    print(f"Loaded '{project.name}' into {DEFAULT_DB_PATH}\n")
    print(table.drop(columns=["Notes"]).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
