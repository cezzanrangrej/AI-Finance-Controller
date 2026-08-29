"""
Generic CSV normalizer with explicit column mapping.

Transforms arbitrary CSV files into the canonical 4-source reconciliation format
based on an explicit mapping dictionary. Does NOT guess mappings silently.
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
    ColumnMappingConfig,
    DatasetManifest,
    NormalizedDataset,
    ProvenanceRecord,
)
from src.utils.formatters import safe_decimal, safe_numeric


@register_normalizer("generic_csv")
class GenericCSVNormalizer(DatasetNormalizer):
    """Normalizes arbitrary CSV data using an explicit column mapping."""

    name: str = "generic_csv"
    source_dataset_name: str = "Generic CSV"
    source_type: str = "user_uploaded_dataset"

    def normalize(
        self,
        source_input: Union[str, bytes, Any],
        filename: Optional[str] = None,
        derive_reconciliation_sources: bool = True,
        mapping: Optional[Union[Dict[str, str], ColumnMappingConfig]] = None,
        **kwargs,
    ) -> NormalizedDataset:
        rows, resolved_filename = self.read_csv_rows(source_input, filename)

        # Parse mapping
        if mapping is None:
            raise ValueError(
                "Generic CSV normalization requires an explicit column mapping. "
                "Provide a dictionary specifying at least 'transaction_id' and 'amount' source columns."
            )

        if isinstance(mapping, ColumnMappingConfig):
            map_dict = mapping.model_dump()
        else:
            map_dict = dict(mapping)

        txn_col = map_dict.get("transaction_id")
        amt_col = map_dict.get("amount")
        date_col = map_dict.get("date")
        status_col = map_dict.get("status")
        merchant_col = map_dict.get("merchant_id")

        if not txn_col or not amt_col:
            raise ValueError(
                f"Column mapping must specify both 'transaction_id' and 'amount'. Provided mapping: {map_dict}"
            )

        # Check required columns exist in input rows
        if rows:
            sample_keys = {k.lower(): k for k in rows[0].keys()}
            if txn_col.lower() not in sample_keys:
                raise ValueError(
                    f"Mapped transaction ID column '{txn_col}' was not found in CSV. "
                    f"Available headers: {', '.join(rows[0].keys())}"
                )
            if amt_col.lower() not in sample_keys:
                raise ValueError(
                    f"Mapped amount column '{amt_col}' was not found in CSV. "
                    f"Available headers: {', '.join(rows[0].keys())}"
                )

        payments: List[CanonicalPaymentRecord] = []
        ledger: List[CanonicalLedgerRecord] = []
        bank: List[CanonicalBankRecord] = []
        adjustments: List[CanonicalAdjustmentRecord] = []
        provenance_list: List[ProvenanceRecord] = []
        warnings: List[str] = []
        errors: List[str] = []

        seen_txn_ids: Set[str] = set()

        for idx, row in enumerate(rows):
            row_num = idx + 1
            raw_id = row.get(txn_col)
            raw_amt = row.get(amt_col)

            # 1. Validate Transaction ID
            if raw_id is None or str(raw_id).strip() == "":
                errors.append(f"Row {row_num}: Empty transaction ID in column '{txn_col}'.")
                continue

            clean_id = str(raw_id).strip()

            # 2. Check Uniqueness
            if clean_id in seen_txn_ids:
                errors.append(f"Row {row_num}: Duplicate transaction ID '{clean_id}' encountered.")
                continue
            seen_txn_ids.add(clean_id)

            # 3. Validate and Parse Amount with Decimal
            if raw_amt is None or str(raw_amt).strip() == "":
                errors.append(f"Row {row_num} (ID '{clean_id}'): Empty amount in column '{amt_col}'.")
                continue

            dec_amt = safe_decimal(raw_amt)
            if dec_amt is None:
                errors.append(f"Row {row_num} (ID '{clean_id}'): Malformed numeric amount '{raw_amt}'.")
                continue

            num_amt = safe_numeric(dec_amt)

            # 4. Optional Fields
            clean_date = str(row.get(date_col, "2026-08-20")).strip() if date_col and row.get(date_col) else "2026-08-20"
            clean_status = str(row.get(status_col, "CAPTURED")).strip().upper() if status_col and row.get(status_col) else "CAPTURED"
            clean_merchant = str(row.get(merchant_col, "MERCHANT_DEFAULT")).strip() if merchant_col and row.get(merchant_col) else "MERCHANT_DEFAULT"

            # 5. Provenance Record
            prov = ProvenanceRecord(
                source_file=resolved_filename,
                source_row=row_num,
                source_dataset=self.source_dataset_name,
                raw_transaction_id=str(raw_id),
                raw_amount=str(raw_amt),
                normalized_transaction_id=clean_id,
                normalized_amount=num_amt,
                metadata={k: v for k, v in row.items() if k not in [txn_col, amt_col]},
            )
            provenance_list.append(prov)

            # 6. Canonical Payment Record
            payment_record = CanonicalPaymentRecord(
                transaction_id=clean_id,
                amount=num_amt,
                merchant_id=clean_merchant,
                date=clean_date,
                status=clean_status,
                provenance=prov,
            )
            payments.append(payment_record)

            # 7. Controlled Reconciliation Derivation (if requested)
            if derive_reconciliation_sources:
                # Controlled fee calculation
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
            column_mapping=map_dict,
            provenance_notes="Normalized via Generic CSV Normalizer with explicit column mappings.",
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
