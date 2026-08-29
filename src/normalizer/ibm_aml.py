"""
IBM AML / AMLSim public synthetic transaction dataset normalizer.

Maps IBM AML published transaction schema fields:
- tran_id: Unique transaction ID
- orig_acct: Originating account (mapped to merchant_id)
- bene_acct: Beneficiary account
- tx_type: Transaction type (mapped to status/type)
- base_amt: Monetary transaction amount
- tran_timestamp: Transaction timestamp

Clearly labels metadata as synthetic public dataset:
- source_dataset = "IBM AML"
- source_type = "synthetic_public_dataset"
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Set, Union

from src.normalizer.base import DatasetNormalizer
from src.normalizer.registry import register_normalizer
from src.normalizer.schemas import (
    CanonicalAdjustmentRecord,
    CanonicalBankRecord,
    CanonicalLedgerRecord,
    CanonicalPaymentRecord,
    DatasetManifest,
    NormalizedDataset,
    ProvenanceRecord,
)
from src.utils.formatters import safe_decimal, safe_numeric


@register_normalizer("ibm_aml")
class IBMAMLNormalizer(DatasetNormalizer):
    """Normalizes public synthetic IBM AML/AMLSim transaction datasets into canonical finance schema."""

    name: str = "ibm_aml"
    source_dataset_name: str = "IBM AML"
    source_type: str = "synthetic_public_dataset"

    # Default IBM AML schema field mapping
    DEFAULT_COLUMN_MAPPING = {
        "transaction_id": "tran_id",
        "amount": "base_amt",
        "date": "tran_timestamp",
        "merchant_id": "orig_acct",
        "beneficiary_account": "bene_acct",
        "tx_type": "tx_type",
    }

    def normalize(
        self,
        source_input: Union[str, bytes, Any],
        filename: Optional[str] = None,
        derive_reconciliation_sources: bool = True,
        **kwargs,
    ) -> NormalizedDataset:
        rows, resolved_filename = self.read_csv_rows(source_input, filename)

        payments: List[CanonicalPaymentRecord] = []
        ledger: List[CanonicalLedgerRecord] = []
        bank: List[CanonicalBankRecord] = []
        adjustments: List[CanonicalAdjustmentRecord] = []
        provenance_list: List[ProvenanceRecord] = []
        warnings: List[str] = []
        errors: List[str] = []

        seen_txn_ids: Set[str] = set()

        if not rows:
            errors.append(f"{resolved_filename} contains 0 data rows.")
            return NormalizedDataset(
                source_dataset=self.source_dataset_name,
                source_type=self.source_type,
                manifest=DatasetManifest(
                    source_dataset=self.source_dataset_name,
                    source_type=self.source_type,
                    source_file=resolved_filename,
                    normalizer=self.name,
                    normalization_timestamp=datetime.now(timezone.utc).isoformat(),
                    record_count=0,
                    column_mapping=self.DEFAULT_COLUMN_MAPPING,
                    provenance_notes="Empty IBM AML dataset.",
                ),
                payments=[],
                ledger=[],
                bank=[],
                adjustments=[],
                provenance=[],
                warnings=warnings,
                errors=errors,
            )

        # Check required columns in source
        sample_keys = {k.lower(): k for k in rows[0].keys()}
        if "tran_id" not in sample_keys:
            errors.append(
                f"Required IBM AML column 'tran_id' missing from {resolved_filename}. "
                f"Found headers: {', '.join(rows[0].keys())}"
            )
            return NormalizedDataset(
                source_dataset=self.source_dataset_name,
                source_type=self.source_type,
                manifest=DatasetManifest(
                    source_dataset=self.source_dataset_name,
                    source_type=self.source_type,
                    source_file=resolved_filename,
                    normalizer=self.name,
                    normalization_timestamp=datetime.now(timezone.utc).isoformat(),
                    record_count=0,
                    column_mapping=self.DEFAULT_COLUMN_MAPPING,
                    provenance_notes="Validation failed: missing tran_id.",
                ),
                payments=[],
                ledger=[],
                bank=[],
                adjustments=[],
                provenance=[],
                warnings=warnings,
                errors=errors,
            )

        if "base_amt" not in sample_keys:
            errors.append(
                f"Required IBM AML column 'base_amt' missing from {resolved_filename}. "
                f"Found headers: {', '.join(rows[0].keys())}"
            )
            return NormalizedDataset(
                source_dataset=self.source_dataset_name,
                source_type=self.source_type,
                manifest=DatasetManifest(
                    source_dataset=self.source_dataset_name,
                    source_type=self.source_type,
                    source_file=resolved_filename,
                    normalizer=self.name,
                    normalization_timestamp=datetime.now(timezone.utc).isoformat(),
                    record_count=0,
                    column_mapping=self.DEFAULT_COLUMN_MAPPING,
                    provenance_notes="Validation failed: missing base_amt.",
                ),
                payments=[],
                ledger=[],
                bank=[],
                adjustments=[],
                provenance=[],
                warnings=warnings,
                errors=errors,
            )

        tran_id_key = sample_keys["tran_id"]
        base_amt_key = sample_keys["base_amt"]
        timestamp_key = sample_keys.get("tran_timestamp")
        orig_acct_key = sample_keys.get("orig_acct")
        bene_acct_key = sample_keys.get("bene_acct")
        tx_type_key = sample_keys.get("tx_type")

        for idx, row in enumerate(rows):
            row_num = idx + 1
            raw_id = row.get(tran_id_key)
            raw_amt = row.get(base_amt_key)

            # 1. Validate Transaction ID
            if raw_id is None or str(raw_id).strip() == "":
                errors.append(f"Row {row_num}: Empty tran_id.")
                continue

            clean_id = str(raw_id).strip()

            # 2. Check Uniqueness
            if clean_id in seen_txn_ids:
                errors.append(f"Row {row_num}: Duplicate tran_id '{clean_id}'.")
                continue
            seen_txn_ids.add(clean_id)

            # 3. Validate and Parse Amount with Decimal
            if raw_amt is None or str(raw_amt).strip() == "":
                errors.append(f"Row {row_num} (ID '{clean_id}'): Empty base_amt.")
                continue

            dec_amt = safe_decimal(raw_amt)
            if dec_amt is None:
                errors.append(f"Row {row_num} (ID '{clean_id}'): Malformed numeric base_amt '{raw_amt}'.")
                continue

            num_amt = safe_numeric(dec_amt)

            # 4. Optional Fields
            clean_date = str(row.get(timestamp_key, "2026-08-20")).strip() if timestamp_key and row.get(timestamp_key) else "2026-08-20"
            clean_merchant = str(row.get(orig_acct_key, "IBM_ORIG_ACCT")).strip() if orig_acct_key and row.get(orig_acct_key) else "IBM_ORIG_ACCT"

            # 5. Provenance Record
            prov = ProvenanceRecord(
                source_file=resolved_filename,
                source_row=row_num,
                source_dataset=self.source_dataset_name,
                raw_transaction_id=str(raw_id),
                raw_amount=str(raw_amt),
                normalized_transaction_id=clean_id,
                normalized_amount=num_amt,
                metadata={
                    "orig_acct": row.get(orig_acct_key),
                    "bene_acct": row.get(bene_acct_key),
                    "tx_type": row.get(tx_type_key),
                },
            )
            provenance_list.append(prov)

            # 6. Canonical Payment Record
            payment_record = CanonicalPaymentRecord(
                transaction_id=clean_id,
                amount=num_amt,
                merchant_id=clean_merchant,
                date=clean_date,
                status="CAPTURED",
                provenance=prov,
            )
            payments.append(payment_record)

            # 7. Controlled Reconciliation Derivation (if requested)
            if derive_reconciliation_sources:
                # Controlled fee derivation
                fee_dec = Decimal("0.00")
                if dec_amt > Decimal("100.00"):
                    fee_dec = Decimal("20.00")
                net_dec = dec_amt - fee_dec

                ledger.append(
                    CanonicalLedgerRecord(
                        transaction_id=clean_id,
                        gross_amount=num_amt,
                        fee=float(safe_numeric(fee_dec)),
                        net_amount=float(safe_numeric(net_dec)),
                        date=clean_date,
                        status="POSTED",
                        provenance=prov,
                    )
                )

                bank.append(
                    CanonicalBankRecord(
                        bank_reference=f"BNK_{clean_id}",
                        transaction_id=clean_id,
                        credited_amount=float(safe_numeric(net_dec)),
                        date=clean_date,
                        provenance=prov,
                    )
                )

        manifest = DatasetManifest(
            source_dataset=self.source_dataset_name,
            source_type=self.source_type,
            source_file=resolved_filename,
            normalizer=self.name,
            normalization_timestamp=datetime.now(timezone.utc).isoformat(),
            record_count=len(payments),
            column_mapping=self.DEFAULT_COLUMN_MAPPING,
            provenance_notes=(
                "Source data normalized from IBM AML synthetic public dataset. "
                "Ledger and bank records are derived test fixtures for 4-source reconciliation verification."
            ),
            is_derived_test_data=derive_reconciliation_sources,
            derived_records_count=len(ledger) if derive_reconciliation_sources else None,
        )

        return NormalizedDataset(
            source_dataset=self.source_dataset_name,
            source_type=self.source_type,
            manifest=manifest,
            payments=payments,
            ledger=ledger,
            bank=bank,
            adjustments=adjustments,
            provenance=provenance_list,
            warnings=warnings,
            errors=errors,
        )
