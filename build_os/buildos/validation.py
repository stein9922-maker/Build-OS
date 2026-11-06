"""Input validation and cleaning. Pure functions: no database, no Streamlit.

Every function collects *all* problems and raises a single ValidationError, so the
user can fix everything in one pass instead of one error at a time.
"""
from __future__ import annotations

import math
import re
from datetime import date, datetime
from numbers import Integral, Real

from .errors import ValidationError

MAX_PROJECT_NAME_LEN = 100
MAX_DESCRIPTION_LEN = 1000
MAX_ACTIVITY_NAME_LEN = 120
MAX_CODE_LEN = 20
MAX_NOTES_LEN = 1000
MAX_DURATION_DAYS = 3650  # ten years: a sanity cap that catches typos like 99999
MIN_PROJECT_YEAR = 1990
MAX_PROJECT_YEAR = 2100

_CODE_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def _clean_text(value, label: str, max_len: int, errors: list[str], required: bool = False) -> str:
    if value is None:
        value = ""
    if not isinstance(value, str):
        errors.append(f"{label} must be text.")
        return ""
    value = value.strip()
    if required and not value:
        errors.append(f"{label} is required.")
    elif len(value) > max_len:
        errors.append(f"{label} must be at most {max_len} characters (got {len(value)}).")
    return value


def _clean_date(value, errors: list[str]) -> date | None:
    if isinstance(value, datetime):  # datetime is a subclass of date; keep only the date part
        value = value.date()
    if not isinstance(value, date):
        errors.append("Start date must be a valid date.")
        return None
    if not (MIN_PROJECT_YEAR <= value.year <= MAX_PROJECT_YEAR):
        errors.append(f"Start date year must be between {MIN_PROJECT_YEAR} and {MAX_PROJECT_YEAR}.")
        return None
    return value


def _clean_duration(value, errors: list[str]) -> int | None:
    message = "Duration must be a whole number of calendar days."
    if isinstance(value, bool) or value is None:
        errors.append(message)
        return None
    if isinstance(value, Integral):
        number = int(value)
    elif isinstance(value, Real):
        as_float = float(value)
        if not math.isfinite(as_float) or not as_float.is_integer():
            errors.append(message)
            return None
        number = int(as_float)
    else:  # strings and everything else are rejected on purpose
        errors.append(message)
        return None
    if number < 0:
        errors.append("Duration cannot be negative.")
        return None
    if number > MAX_DURATION_DAYS:
        errors.append(f"Duration cannot exceed {MAX_DURATION_DAYS} days.")
        return None
    return number


def clean_project_input(name, start_date, description="") -> tuple[str, date, str]:
    """Return (name, start_date, description) cleaned, or raise ValidationError."""
    errors: list[str] = []
    clean_name = _clean_text(name, "Project name", MAX_PROJECT_NAME_LEN, errors, required=True)
    clean_description = _clean_text(description, "Description", MAX_DESCRIPTION_LEN, errors)
    clean_start = _clean_date(start_date, errors)
    if errors:
        raise ValidationError(errors)
    assert clean_start is not None
    return clean_name, clean_start, clean_description


def clean_activity_input(code, name, duration_days, notes="") -> tuple[str, str, int, str]:
    """Return (code, name, duration_days, notes) cleaned, or raise ValidationError.

    The code is upper-cased so 'a100' and 'A100' are the same activity.
    """
    errors: list[str] = []
    clean_code = _clean_text(code, "Activity code", MAX_CODE_LEN, errors, required=True)
    if clean_code and not _CODE_PATTERN.fullmatch(clean_code):
        errors.append(
            "Activity code may contain only letters, numbers, '.', '_' and '-', "
            "and must start with a letter or number (e.g. A100)."
        )
    clean_name = _clean_text(name, "Activity name", MAX_ACTIVITY_NAME_LEN, errors, required=True)
    clean_duration = _clean_duration(duration_days, errors)
    clean_notes = _clean_text(notes, "Notes", MAX_NOTES_LEN, errors)
    if errors:
        raise ValidationError(errors)
    assert clean_duration is not None
    return clean_code.upper(), clean_name, clean_duration, clean_notes
