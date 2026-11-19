"""Tests for the pure PVPC Plug Cost calculator."""

from __future__ import annotations

import importlib.util
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import sys
import unittest
from zoneinfo import ZoneInfo

MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "pvpc_plug_cost"
    / "calculator.py"
)
SPEC = importlib.util.spec_from_file_location("pvpc_plug_cost_calculator", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
calculator = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = calculator
SPEC.loader.exec_module(calculator)


class CalculatorTest(unittest.TestCase):
    def test_constant_power(self) -> None:
        start = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 1, 1, 0, 30, tzinfo=timezone.utc)

        result = calculator.accumulate_segment(
            Decimal("1"), Decimal("0.10"), start, end
        )

        self.assertEqual(result.energy_kwh, Decimal("0.5"))
        self.assertEqual(result.cost_eur, Decimal("0.05"))

    def test_left_power_uses_start_value(self) -> None:
        start = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 1, 1, 1, 0, tzinfo=timezone.utc)

        result = calculator.accumulate_segment(
            Decimal("2"), Decimal("0.20"), start, end
        )

        self.assertEqual(result.energy_kwh, Decimal("2"))
        self.assertEqual(result.cost_eur, Decimal("0.40"))

    def test_invalid_decimal(self) -> None:
        self.assertIsNone(calculator.to_decimal("unavailable"))
        self.assertEqual(calculator.to_decimal("1.25"), Decimal("1.25"))
        self.assertIsNone(calculator.to_decimal("nan"))
        self.assertIsNone(calculator.to_decimal("inf"))
        self.assertIsNone(calculator.to_decimal("-inf"))

    def test_day_boundaries(self) -> None:
        value = datetime(2026, 3, 14, 23, 30, tzinfo=timezone.utc)
        self.assertEqual(
            calculator.start_of_hour(value),
            datetime(2026, 3, 14, 23, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(
            calculator.next_hour_start(value),
            datetime(2026, 3, 15, 0, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(
            calculator.start_of_year(value),
            datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(
            calculator.start_of_day(value),
            datetime(2026, 3, 14, 0, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(
            calculator.next_day_start(value),
            datetime(2026, 3, 15, 0, 0, tzinfo=timezone.utc),
        )

    def test_billing_period_day_31_in_february(self) -> None:
        before = datetime(2026, 2, 27, 12, 0, tzinfo=timezone.utc)
        after = datetime(2026, 2, 28, 12, 0, tzinfo=timezone.utc)

        self.assertEqual(
            calculator.billing_period_start(before, 31),
            datetime(2026, 1, 31, 0, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(
            calculator.billing_period_start(after, 31),
            datetime(2026, 2, 28, 0, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(
            calculator.next_billing_period_start(after, 31),
            datetime(2026, 3, 31, 0, 0, tzinfo=timezone.utc),
        )

    def test_billing_period_with_mid_month_day(self) -> None:
        before = datetime(2026, 3, 14, 12, 0, tzinfo=timezone.utc)
        after = datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc)

        self.assertEqual(
            calculator.billing_period_start(before, 15),
            datetime(2026, 2, 15, 0, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(
            calculator.billing_period_start(after, 15),
            datetime(2026, 3, 15, 0, 0, tzinfo=timezone.utc),
        )

    def test_period_boundaries_are_split_and_deduplicated(self) -> None:
        start = datetime(2026, 3, 14, 22, 30, tzinfo=timezone.utc)
        end = datetime(2026, 3, 15, 1, 30, tzinfo=timezone.utc)

        self.assertEqual(
            calculator.period_boundaries(start, end, 15),
            [
                datetime(2026, 3, 14, 23, 0, tzinfo=timezone.utc),
                datetime(2026, 3, 15, 0, 0, tzinfo=timezone.utc),
                datetime(2026, 3, 15, 1, 0, tzinfo=timezone.utc),
            ],
        )

    def test_period_boundaries_include_new_year(self) -> None:
        start = datetime(2026, 12, 31, 22, 30, tzinfo=timezone.utc)
        end = datetime(2027, 1, 1, 1, 30, tzinfo=timezone.utc)

        self.assertEqual(
            calculator.period_boundaries(start, end, 1),
            [
                datetime(2026, 12, 31, 23, 0, tzinfo=timezone.utc),
                datetime(2027, 1, 1, 0, 0, tzinfo=timezone.utc),
                datetime(2027, 1, 1, 1, 0, tzinfo=timezone.utc),
            ],
        )

    def test_period_boundaries_handle_dst_fall_back(self) -> None:
        tz = ZoneInfo("Europe/Madrid")
        start = datetime(2027, 10, 31, 1, 30, tzinfo=tz)
        end = datetime(2027, 10, 31, 3, 30, tzinfo=tz)

        boundaries = calculator.period_boundaries(start, end, 1)

        self.assertEqual(
            [boundary.astimezone(timezone.utc) for boundary in boundaries],
            [
                datetime(2027, 10, 31, 0, 0, tzinfo=timezone.utc),
                datetime(2027, 10, 31, 1, 0, tzinfo=timezone.utc),
                datetime(2027, 10, 31, 2, 0, tzinfo=timezone.utc),
            ],
        )

    def test_next_hour_start_handles_dst_fold(self) -> None:
        tz = ZoneInfo("Europe/Madrid")
        first = datetime(2027, 10, 31, 2, 0, tzinfo=tz, fold=0)
        second = datetime(2027, 10, 31, 2, 0, tzinfo=tz, fold=1)

        self.assertEqual(
            calculator.next_hour_start(first).astimezone(timezone.utc),
            datetime(2027, 10, 31, 1, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(
            calculator.next_hour_start(second).astimezone(timezone.utc),
            datetime(2027, 10, 31, 2, 0, tzinfo=timezone.utc),
        )

    def test_next_hour_start_handles_half_hour_offset(self) -> None:
        tz = ZoneInfo("Asia/Kolkata")
        value = datetime(2027, 3, 10, 10, 45, tzinfo=tz)

        self.assertEqual(
            calculator.next_hour_start(value),
            datetime(2027, 3, 10, 11, 0, tzinfo=tz),
        )

    def test_next_hour_start_handles_dst_spring_forward(self) -> None:
        tz = ZoneInfo("Europe/Madrid")
        value = datetime(2027, 3, 28, 1, 30, tzinfo=tz)

        self.assertEqual(
            calculator.next_hour_start(value),
            datetime(2027, 3, 28, 3, 0, tzinfo=tz),
        )


if __name__ == "__main__":
    unittest.main()
