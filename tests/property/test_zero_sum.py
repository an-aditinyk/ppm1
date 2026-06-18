"""Property tests (§6.4).

Hypothesis generates balanced canonical vouchers, serializes them, re-parses, and
asserts the signed AMOUNTs sum to exactly 0 and that ledger names / amounts survive
XML escaping round-trip (including names with ``& < > "``).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st
from lxml import etree

from tallyimporter.contracts.canonical import (
    CanonicalBatch,
    CanonicalLedgerEntry,
    CanonicalVoucher,
)
from tallyimporter.core.money import render_amount
from tallyimporter.stages.s12_emit.mapper import canonical_to_tally
from tallyimporter.stages.s12_emit.serializer import serialize_envelope
from tallyimporter.stages.s12_emit.validator import validate_tally_xml

# Names that exercise XML escaping plus ordinary text.
_NAME_ALPHABET = st.text(
    alphabet=st.characters(
        min_codepoint=0x20,
        max_codepoint=0x7E,
        blacklist_characters="\x7f",
    ),
    min_size=1,
    max_size=20,
).map(lambda s: s.strip() or "L")

# Positive magnitudes with at most 2dp so rounding never perturbs the balance.
_AMOUNTS = st.integers(min_value=1, max_value=10_000_000).map(
    lambda cents: Decimal(cents) / Decimal(100)
)


@st.composite
def balanced_voucher(draw: st.DrawFn, number: str) -> CanonicalVoucher:
    # One credit line balancing N debit lines keeps construction always balanced.
    n_debits = draw(st.integers(min_value=1, max_value=4))
    debit_amounts = [draw(_AMOUNTS) for _ in range(n_debits)]
    total = sum(debit_amounts, start=Decimal("0"))
    debit_names = draw(st.lists(_NAME_ALPHABET, min_size=n_debits, max_size=n_debits))
    credit_name = draw(_NAME_ALPHABET)
    entries = (
        *(
            CanonicalLedgerEntry(ledger_name=name, is_debit=True, amount=amt)
            for name, amt in zip(debit_names, debit_amounts, strict=True)
        ),
        CanonicalLedgerEntry(ledger_name=credit_name, is_debit=False, amount=total),
    )
    return CanonicalVoucher(
        voucher_type=draw(st.sampled_from(["Payment", "Receipt", "Sales"])),
        date=draw(st.dates(min_value=date(2000, 1, 1), max_value=date(2099, 12, 31))),
        voucher_number=number,
        narration=draw(st.none() | _NAME_ALPHABET),
        entries=entries,
    )


@st.composite
def balanced_batch(draw: st.DrawFn) -> CanonicalBatch:
    n = draw(st.integers(min_value=1, max_value=4))
    vouchers = tuple(draw(balanced_voucher(number=f"V-{i}")) for i in range(n))
    return CanonicalBatch(
        company_name=draw(_NAME_ALPHABET),
        source_system=draw(st.sampled_from(["zoho", "busy"])),
        vouchers=vouchers,
    )


@settings(max_examples=200)
@given(batch=balanced_batch())
def test_serialized_amounts_zero_sum_and_roundtrip(batch: CanonicalBatch) -> None:
    xml = serialize_envelope(canonical_to_tally(batch))
    # The serialized document satisfies the full §2.2 contract.
    validate_tally_xml(xml)

    root = etree.fromstring(xml)
    vouchers = root.findall("BODY/DATA/TALLYMESSAGE/VOUCHER")
    assert len(vouchers) == len(batch.vouchers)

    for voucher_xml, canonical in zip(vouchers, batch.vouchers, strict=True):
        amounts = [
            Decimal(a.text or "") for a in voucher_xml.findall("ALLLEDGERENTRIES.LIST/AMOUNT")
        ]
        assert sum(amounts, start=Decimal("0")) == Decimal("0")

        names = [n.text for n in voucher_xml.findall("ALLLEDGERENTRIES.LIST/LEDGERNAME")]
        assert names == [e.ledger_name for e in canonical.entries]

        for amount_el, entry in zip(
            voucher_xml.findall("ALLLEDGERENTRIES.LIST/AMOUNT"),
            canonical.entries,
            strict=True,
        ):
            signed = -entry.amount if entry.is_debit else entry.amount
            assert amount_el.text == render_amount(signed)
