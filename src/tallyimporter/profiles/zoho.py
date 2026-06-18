"""The Zoho Books source profile.

This is *data* (per cross-cutting decision X3): all Zoho-specific knowledge — which
export file is which accounting role, which columns hold ids/amounts/parties, and how
each transaction posts as double-entry — lives here, consumed by generic stage logic.
A future Busy adapter ships its own profile; the stages do not change.

Grounded in the real Zoho export (`Contacts/Vendors/Items/Sales_Invoices/...`) and the
posting conventions validated end-to-end against TallyPrime (see smoke_import/).
"""

from __future__ import annotations

from tallyimporter.contracts.source import (
    PARTY_SENTINEL,
    ArtifactRole,
    PartyTable,
    SourceProfile,
    TransactionTemplate,
)

_FILE_ROLES: tuple[tuple[str, ArtifactRole], ...] = (
    ("Contacts.csv", ArtifactRole.CUSTOMERS),
    ("Vendors.csv", ArtifactRole.SUPPLIERS),
    ("Items.csv", ArtifactRole.ITEMS),
    ("Sales_Invoices.csv", ArtifactRole.SALES_INVOICES),
    ("Sales_Invoice_Items.csv", ArtifactRole.SALES_INVOICE_LINES),
    ("Customer_Payments.csv", ArtifactRole.CUSTOMER_RECEIPTS),
    ("Bills.csv", ArtifactRole.BILLS),
    ("Bill_Items.csv", ArtifactRole.BILL_LINES),
    ("Vendor_Payments.csv", ArtifactRole.SUPPLIER_PAYMENTS),
    ("Credit_Notes.csv", ArtifactRole.CREDIT_NOTES),
    ("Journals.csv", ArtifactRole.JOURNALS),
    ("Bank_Transactions.csv", ArtifactRole.BANK_TRANSACTIONS),
    ("GST_Transactions.csv", ArtifactRole.TAX_TRANSACTIONS),
    ("Sales_Orders.csv", ArtifactRole.SALES_ORDERS),
    ("Purchase_Orders.csv", ArtifactRole.PURCHASE_ORDERS),
    ("Inventory_Transactions.csv", ArtifactRole.INVENTORY_MOVEMENTS),
    ("Inventory_Adjustments.csv", ArtifactRole.INVENTORY_ADJUSTMENTS),
    # Projects.csv and Time_Entries.csv are deliberately excluded (S01 D6): not postable
    # accounting documents. If present they are recorded as "extra artifacts", not consumed.
)

# Conservative required set: exactly what the current voucher path consumes (S01 D5).
_REQUIRED: tuple[ArtifactRole, ...] = (
    ArtifactRole.CUSTOMERS,
    ArtifactRole.SALES_INVOICES,
    ArtifactRole.CUSTOMER_RECEIPTS,
    ArtifactRole.SUPPLIER_PAYMENTS,
)

_PARTIES: tuple[PartyTable, ...] = (
    PartyTable(role=ArtifactRole.CUSTOMERS, id_column="contact_id", name_column="contact_name"),
    PartyTable(role=ArtifactRole.SUPPLIERS, id_column="vendor_id", name_column="vendor_name"),
)

# Posting templates (the conventions validated against TallyPrime):
#   Sales invoice  → Dr <customer>            / Cr Sales Account
#   Customer recpt → Dr Bank Account          / Cr Accounts Receivable
#   Vendor payment → Dr Accounts Payable      / Cr Bank Account
_TRANSACTIONS: tuple[TransactionTemplate, ...] = (
    TransactionTemplate(
        role=ArtifactRole.SALES_INVOICES,
        voucher_type="Sales",
        id_column="invoice_id",
        amount_column="total",
        party_column="customer_id",
        party_role=ArtifactRole.CUSTOMERS,
        debit_account=PARTY_SENTINEL,
        credit_account="Sales Account",
    ),
    TransactionTemplate(
        role=ArtifactRole.CUSTOMER_RECEIPTS,
        voucher_type="Receipt",
        id_column="id",
        amount_column="amount",
        debit_account="Bank Account",
        credit_account="Accounts Receivable",
    ),
    TransactionTemplate(
        role=ArtifactRole.SUPPLIER_PAYMENTS,
        voucher_type="Payment",
        id_column="id",
        amount_column="amount",
        debit_account="Accounts Payable",
        credit_account="Bank Account",
    ),
)

# Control-account groups (Tally predefined groups), confirmed by the round-trip. Party
# ledgers fall back to the default (Sundry Debtors): in this dataset only customer
# ledgers appear as named ledgers — vendor payments post to the Accounts Payable control.
_LEDGER_GROUPS: tuple[tuple[str, str], ...] = (
    ("Sales Account", "Sales Accounts"),
    ("Bank Account", "Bank Accounts"),
    ("Accounts Receivable", "Sundry Debtors"),
    ("Accounts Payable", "Sundry Creditors"),
)

ZOHO_PROFILE = SourceProfile(
    source_system="zoho",
    file_roles=_FILE_ROLES,
    required_roles=_REQUIRED,
    parties=_PARTIES,
    transactions=_TRANSACTIONS,
    ledger_overrides=(),
    ledger_groups=_LEDGER_GROUPS,
    default_ledger_group="Sundry Debtors",
)
