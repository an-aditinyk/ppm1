"""Typed boundary errors.

Every boundary in TallyImporter validates its input and raises one of these on
violation. Nothing is silently coerced or dropped.
"""

from __future__ import annotations


class TallyImporterError(Exception):
    """Base class for all typed boundary errors."""


class MoneyError(TallyImporterError):
    """Raised when a money value is not a valid finite Decimal-representable number."""


class BalanceError(TallyImporterError):
    """Raised when a voucher's entries do not net to zero."""


class ValidationError(TallyImporterError):
    """Raised when a model or document violates a structural/business rule."""


class XmlContractError(TallyImporterError):
    """Raised when generated/parsed Tally XML violates the §2 contract."""
