"""Exceptions raised by the Build OS core. The UI catches BuildOSError and shows the message."""
from __future__ import annotations

from collections.abc import Iterable


def format_cycle(codes: Iterable[str]) -> str:
    """Render a cycle such as ['A', 'B', 'C'] as 'A -> B -> C -> A'."""
    codes = list(codes)
    if not codes:
        return ""
    return " -> ".join([*codes, codes[0]])


class BuildOSError(Exception):
    """Base class for every error the application raises on purpose."""


class ValidationError(BuildOSError):
    """Input or business-rule problem. Carries one or more human-readable messages."""

    def __init__(self, messages: str | Iterable[str]):
        if isinstance(messages, str):
            messages = [messages]
        self.messages: list[str] = list(messages)
        super().__init__("; ".join(self.messages))


class NotFoundError(BuildOSError):
    """A requested record does not exist."""


class CircularDependencyError(ValidationError):
    """Adding a dependency would create a loop. `cycle` holds activity codes in order."""

    def __init__(self, cycle_codes: Iterable[str], message: str | None = None):
        self.cycle: list[str] = list(cycle_codes)
        super().__init__(
            message
            or (
                "Cannot add this dependency because it would create a circular "
                f"dependency: {format_cycle(self.cycle)}."
            )
        )
