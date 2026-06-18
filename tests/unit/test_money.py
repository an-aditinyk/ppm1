from decimal import Decimal

import pytest

from tallyimporter.contracts.errors import MoneyError
from tallyimporter.core.money import parse_money, render_amount


class TestParseMoney:
    def test_parses_plain_string(self) -> None:
        assert parse_money("12000") == Decimal("12000")

    def test_parses_decimal_string(self) -> None:
        assert parse_money("12000.50") == Decimal("12000.50")

    def test_parses_int(self) -> None:
        assert parse_money(12000) == Decimal("12000")

    def test_passes_through_decimal(self) -> None:
        assert parse_money(Decimal("1.23")) == Decimal("1.23")

    def test_rejects_float(self) -> None:
        with pytest.raises(MoneyError):
            parse_money(1.23)  # type: ignore[arg-type]

    def test_rejects_non_numeric_string(self) -> None:
        with pytest.raises(MoneyError):
            parse_money("not-a-number")

    def test_rejects_nan(self) -> None:
        with pytest.raises(MoneyError):
            parse_money("NaN")

    def test_rejects_infinity(self) -> None:
        with pytest.raises(MoneyError):
            parse_money("Infinity")


class TestRenderAmount:
    def test_two_decimal_places(self) -> None:
        assert render_amount(Decimal("12000")) == "12000.00"

    def test_negative(self) -> None:
        assert render_amount(Decimal("-12000")) == "-12000.00"

    def test_rounds_half_up(self) -> None:
        assert render_amount(Decimal("1.005")) == "1.01"

    def test_rounds_half_up_negative(self) -> None:
        # round-half-up on magnitude: -1.005 -> -1.01
        assert render_amount(Decimal("-1.005")) == "-1.01"

    def test_truncates_extra_precision_with_rounding(self) -> None:
        assert render_amount(Decimal("1.014")) == "1.01"
        assert render_amount(Decimal("1.016")) == "1.02"

    def test_zero(self) -> None:
        assert render_amount(Decimal("0")) == "0.00"

    def test_rejects_float(self) -> None:
        with pytest.raises(MoneyError):
            render_amount(1.23)  # type: ignore[arg-type]

    def test_rejects_non_finite(self) -> None:
        with pytest.raises(MoneyError):
            render_amount(Decimal("NaN"))
