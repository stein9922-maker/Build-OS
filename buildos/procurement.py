"""Deterministic procurement calculations; no UI or database dependencies."""
from __future__ import annotations

from datetime import date, timedelta


INCOMING_STATUSES = {"Ordered", "Partially delivered"}


def usable_stock(available_quantity: float, reserved_quantity: float) -> float:
    """Stock available for new requirements after existing reservations."""
    return max(0.0, float(available_quantity) - float(reserved_quantity))


def outstanding_order_quantity(quantity: float, received_quantity: float, status: str) -> float:
    """Only active orders count as incoming; delivered/cancelled/draft orders do not."""
    if status not in INCOMING_STATUSES:
        return 0.0
    return max(0.0, float(quantity) - float(received_quantity))


def net_purchase_quantity(
    required_quantity: float,
    available_quantity: float,
    reserved_quantity: float,
    eligible_incoming_quantity: float = 0.0,
) -> float:
    """Calculate uncovered quantity; quantities are assumed to use the same unit."""
    return max(
        0.0,
        float(required_quantity)
        - usable_stock(available_quantity, reserved_quantity)
        - max(0.0, float(eligible_incoming_quantity)),
    )


def recommended_order_date(need_date: date, lead_time_days: int, buffer_days: int = 0) -> date:
    """Order date = need date minus supplier lead time and procurement buffer."""
    if lead_time_days < 0 or buffer_days < 0:
        raise ValueError("Lead time and buffer must be zero or more days.")
    return need_date - timedelta(days=lead_time_days + buffer_days)
