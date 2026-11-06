"""Central configuration and the explicit modelling assumptions for version one."""
from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Override with the BUILDOS_DB_PATH environment variable if you want the
# database somewhere else (tests and demos do this).
DEFAULT_DB_PATH = Path(os.environ.get("BUILDOS_DB_PATH") or PROJECT_ROOT / "data" / "buildos.db")

# Shown in the UI and documented in the README. Keep these honest.
ASSUMPTIONS = (
    "Durations are whole calendar days (weekends and holidays count).",
    "A duration of 0 days is allowed and represents a milestone.",
    "All dependencies are finish-to-start (FS) with no lag or lead.",
    "Activity codes are unique within a project and stored in upper case.",
    "Dates are finish-exclusive: day 0 is the project start, EF = ES + duration, and a "
    "successor may start on the day its predecessor's EF falls on.",
    "Activities with no successor may finish as late as the project end, so short "
    "disconnected activities show positive float.",
)
