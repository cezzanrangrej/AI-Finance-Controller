"""
Base abstract interface for dataset normalizers.

Provides standard normalization, provenance generation, validation routines,
and multi-source CSV export.
"""

import abc
import csv
import io
import json
import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple, Union

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


class DatasetNormalizer(abc.ABC):
    """Abstract base class for all financial dataset normalizers."""

    name: str = "base"
    source_dataset_name: str = "Generic Source"
    source_type: str = "synthetic_public_dataset"

    @abc.abstractmethod
    def normalize(
        self,
        source_input: Union[str, bytes, io.IOBase, List[Dict[str, Any]]],
        filename: Optional[str] = None,
        derive_reconciliation_sources: bool = True,
        **kwargs,
    ) -> NormalizedDataset:
        """
        Normalizes raw source records into a canonical NormalizedDataset.

        Args:
            source_input: File path, file bytes, file stream, or list of raw dicts.
            filename: Source file name for provenance tracking.
            derive_reconciliation_sources: When true and source contains single-sided transactions,
                produces controlled ledger/bank/adjustment test data for 4-source reconciliation.
            **kwargs: Extra parameters such as column mapping configurations.

        Returns:
            NormalizedDataset containing canonical payments, ledger, bank, adjustments, and manifest.
        """
        raise NotImplementedError

    def export_to_directory(
        self,
        dataset: NormalizedDataset,
        output_dir: str,
    ) -> Dict[str, str]:
        """
        Exports the normalized dataset into standard CSV files and manifest.json.

        Files exported:
        - payments.csv
        - ledger.csv
        - bank.csv
        - adjustments.csv
        - manifest.json
        """
        os.makedirs(output_dir, exist_ok=True)
        exported_paths = {}

        # 1. Export Payments
        p_path = os.path.join(output_dir, "payments.csv")
        with open(p_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["transaction_id", "amount", "merchant_id", "date", "status"])
            for p in dataset.payments:
                writer.writerow([p.transaction_id, p.amount, p.merchant_id, p.date, p.status])
        exported_paths["payments"] = p_path

        # 2. Export Ledger
        l_path = os.path.join(output_dir, "ledger.csv")
        with open(l_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["transaction_id", "gross_amount", "fee", "net_amount", "date", "status"])
            for l in dataset.ledger:
                writer.writerow([l.transaction_id, l.gross_amount, l.fee, l.net_amount, l.date, l.status])
        exported_paths["ledger"] = l_path

        # 3. Export Bank
        b_path = os.path.join(output_dir, "bank.csv")
        with open(b_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["bank_reference", "transaction_id", "credited_amount", "date"])
            for b in dataset.bank:
                writer.writerow([b.bank_reference, b.transaction_id, b.credited_amount, b.date])
        exported_paths["bank"] = b_path

        # 4. Export Adjustments
        a_path = os.path.join(output_dir, "adjustments.csv")
        with open(a_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["transaction_id", "adjustment_type", "amount", "reason", "date", "reference"])
            for a in dataset.adjustments:
                writer.writerow([a.transaction_id, a.adjustment_type, a.amount, a.reason, a.date, a.reference or ""])
        exported_paths["adjustments"] = a_path

        # 5. Export Manifest
        m_path = os.path.join(output_dir, "manifest.json")
        with open(m_path, "w", encoding="utf-8") as f:
            json.dump(dataset.manifest.model_dump(), f, indent=2)
        exported_paths["manifest"] = m_path

        return exported_paths

    @staticmethod
    def read_csv_rows(
        source_input: Union[str, bytes, io.IOBase, List[Dict[str, Any]]],
        filename: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], str]:
        """Helper to parse varied input representations into a uniform list of dicts."""
        resolved_filename = filename or "source.csv"

        if isinstance(source_input, list):
            return source_input, resolved_filename

        if isinstance(source_input, str):
            if os.path.exists(source_input):
                resolved_filename = os.path.basename(source_input)
                with open(source_input, "rb") as f:
                    content_bytes = f.read()
            else:
                content_bytes = source_input.encode("utf-8")
        elif isinstance(source_input, bytes):
            content_bytes = source_input
        elif hasattr(source_input, "read"):
            content = source_input.read()
            if isinstance(content, str):
                content_bytes = content.encode("utf-8")
            else:
                content_bytes = content
        else:
            raise ValueError(f"Unsupported source input type: {type(source_input)}")

        try:
            text = content_bytes.decode("utf-8-sig")
        except UnicodeDecodeError:
            try:
                text = content_bytes.decode("latin-1")
            except Exception as e:
                raise ValueError(f"Encoding error decoding {resolved_filename}: {str(e)}")

        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            raise ValueError(f"{resolved_filename} contains no header or is empty.")

        rows = []
        for row in reader:
            clean_row = {k.strip(): (v.strip() if v is not None else "") for k, v in row.items() if k}
            rows.append(clean_row)

        return rows, resolved_filename
