"""Pure calculation helpers for PVPC Plug Cost."""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

ZERO = Decimal(0)
SECONDS_PER_HOUR = Decimal(3600)


@dataclass(frozen=True)
class EnergyCost:
    """Energy and cost accumulated during a time segment."""

    energy_kwh: Decimal
    cost_eur: Decimal


def to_decimal(value: Any) -> Decimal | None:
    """Convert a value to a finite Decimal, returning None otherwise."""

    if isinstance(value, Decimal):
        return value if value.is_finite() else None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not result.is_finite():
        return None
    return result


def accumulate_segment(
    power_kw: Decimal,
    price_eur_kwh: Decimal,
    start: datetime,
    end: datetime,
) -> EnergyCost:
    """Integrate the power at the start of a segment over that segment."""

    seconds = Decimal(str((end - start).total_seconds()))
    if seconds <= ZERO:
        return EnergyCost(ZERO, ZERO)

    energy_kwh = power_kw * seconds / SECONDS_PER_HOUR
    return EnergyCost(energy_kwh, energy_kwh * price_eur_kwh)


def start_of_hour(value: datetime) -> datetime:
    """Return the start of the clock hour for a local datetime."""

    return value.replace(minute=0, second=0, microsecond=0)


def next_hour_start(value: datetime) -> datetime:
    """Return the start of the next clock hour in the value's time zone."""

    value_utc = value.astimezone(timezone.utc)
    start = start_of_hour(value)
    start_utc = start.astimezone(timezone.utc)
    if start_utc > value_utc:
        return start

    next_wall = start + timedelta(hours=1)
    next_wall_utc = next_wall.astimezone(timezone.utc)

    if value.fold == 0:
        repeated = start.replace(fold=1)
        repeated_utc = repeated.astimezone(timezone.utc)
        if value_utc < repeated_utc < next_wall_utc:
            return repeated

    return next_wall_utc.astimezone(value.tzinfo)


def start_of_year(value: datetime) -> datetime:
    """Return the start of the calendar year for a local datetime."""

    return value.replace(
        month=1, day=1, hour=0, minute=0, second=0, microsecond=0
    )


def start_of_day(value: datetime) -> datetime:
    """Return the start of the calendar day for a local datetime."""

    return value.replace(hour=0, minute=0, second=0, microsecond=0)


def next_day_start(value: datetime) -> datetime:
    """Return the start of the next calendar day."""

    return datetime.combine(
        value.date() + timedelta(days=1), time.min, tzinfo=value.tzinfo
    )


def clamp_billing_day(year: int, month: int, billing_day: int) -> int:
    """Clamp the configured billing day to the last day of the month."""

    last_day = calendar.monthrange(year, month)[1]
    return min(max(billing_day, 1), last_day)


def _billing_start_for_month(
    year: int, month: int, billing_day: int, tzinfo
) -> datetime:
    day = clamp_billing_day(year, month, billing_day)
    return datetime(year, month, day, tzinfo=tzinfo)


def billing_period_start(value: datetime, billing_day: int) -> datetime:
    """Return the start of the billing period containing the given datetime."""

    current = _billing_start_for_month(
        value.year, value.month, billing_day, value.tzinfo
    )
    if value >= current:
        return current

    if value.month == 1:
        year, month = value.year - 1, 12
    else:
        year, month = value.year, value.month - 1
    return _billing_start_for_month(year, month, billing_day, value.tzinfo)


def next_billing_period_start(value: datetime, billing_day: int) -> datetime:
    """Return the start of the billing period after the one containing value."""

    current = billing_period_start(value, billing_day)
    if current.month == 12:
        year, month = current.year + 1, 1
    else:
        year, month = current.year, current.month + 1
    return _billing_start_for_month(year, month, billing_day, current.tzinfo)


def period_boundaries(
    start: datetime, end: datetime, billing_day: int
) -> list[datetime]:
    """Return all hour, day and billing-period boundaries between start and end."""

    start_utc = start.astimezone(timezone.utc)
    end_utc = end.astimezone(timezone.utc)
    if end_utc <= start_utc:
        return []

    boundaries: dict[datetime, datetime] = {}

    def add(boundary: datetime) -> bool:
        boundary_utc = boundary.astimezone(timezone.utc)
        if boundary_utc >= end_utc:
            return False
        if boundary_utc > start_utc:
            boundaries[boundary_utc] = boundary
        return True

    cursor = start
    while True:
        boundary = next_hour_start(cursor)
        if not add(boundary):
            break
        cursor = boundary

    cursor = start
    while True:
        boundary = next_day_start(cursor)
        if not add(boundary):
            break
        cursor = boundary

    cursor = start
    while True:
        boundary = next_billing_period_start(cursor, billing_day)
        if not add(boundary):
            break
        cursor = boundary

    return [boundaries[key] for key in sorted(boundaries)]
