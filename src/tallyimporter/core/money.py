"""Decimal money helpers.

Money is always ``Decimal``. ``float`` is rejected at every entry point: a float in
a money path is a defect. Rounding to 2 decimal places (round-half-up) happens only
here, at the serialization boundary.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from tallyimporter.contracts.errors import MoneyError

TWO_PLACES = Decimal("0.01")


def parse_money(value: str | int | Decimal) -> Decimal:
    """Parse a money value into a finite ``Decimal``.

    Accepts ``str``, ``int`` or ``Decimal``. Rejects ``float`` (binary floating point
    is never exact for money) and any non-finite or unparseable value.
    """
    if isinstance(value, bool):
        raise MoneyError(f"bool is not a valid money value: {value!r}")
    if isinstance(value, float):
        raise MoneyError(
            f"float is not a valid money value; use str/int/Decimal instead: {value!r}"
        )
    if isinstance(value, Decimal):
        result = value
    else:
        try:
            result = Decimal(value)
        except (InvalidOperation, ValueError) as exc:
            raise MoneyError(f"cannot parse money value: {value!r}") from exc
    if not result.is_finite():
        raise MoneyError(f"money value is not finite: {value!r}")
    return result


def render_amount(amount: Decimal) -> str:
    """Render a ``Decimal`` amount as a fixed 2-decimal string, round-half-up.

    This is the only place rounding to 2dp occurs. Ties round away from zero
    (``1.005`` -> ``1.01``, ``-1.005`` -> ``-1.01``).
    """
    if not isinstance(amount, Decimal):
        raise MoneyError(f"render_amount requires Decimal, got {type(amount).__name__}")
    if not amount.is_finite():
        raise MoneyError(f"cannot render non-finite amount: {amount!r}")
    quantized = amount.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    # Normalize negative zero to positive zero for byte-stable output.
    if quantized == 0:
        quantized = Decimal("0.00")
    return f"{quantized:.2f}"
