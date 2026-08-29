"""
Unit and integration tests for the financial data normalizer layer.
"""

import io
import json
import os
import tempfile
import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.normalizer import (
    GenericCSVNormalizer,
    IBMAMLNormalizer,
    get_normalizer,
    list_normalizers,
)
from src.normalizer.schemas import ColumnMappingConfig

client = TestClient(app)

SAMPLE_IBM_AML_CSV = """tran_id,orig_acct,bene_acct,tx_type,base_amt,tran_timestamp
TX_IBM_001,ACC_ORIG_101,ACC_BENE_201,TRANSFER,9357.50,2026-08-20
TX_IBM_002,ACC_ORIG_102,ACC_BENE_202,PAYMENT,150.00,2026-08-20
TX_IBM_003,ACC_ORIG_103,ACC_BENE_203,TRANSFER,49.99,2026-08-21
"""

SAMPLE_GENERIC_CSV = """custom_id,customer_ref,transaction_value,settlement_date
CUST_TX_1001,REF_A,1250.75,2026-08-19
CUST_TX_1002,REF_B,3400.00,2026-08-20
"""


def test_registry_lookup_and_listing():
    """Test registry functions for normalizers."""
    normalizers = list_normalizers()
    names = [n["name"] for n in normalizers]
    assert "ibm_aml" in names
    assert "generic_csv" in names

    ibm = get_normalizer("ibm_aml")
    assert isinstance(ibm, IBMAMLNormalizer)
    assert ibm.source_type == "synthetic_public_dataset"

    generic = get_normalizer("generic_csv")
    assert isinstance(generic, GenericCSVNormalizer)

    with pytest.raises(ValueError, match="Unknown normalizer"):
        get_normalizer("non_existent_normalizer")


def test_ibm_aml_normalizer_success():
    """Test standard normalization of IBM AML transactions."""
    normalizer = IBMAMLNormalizer()
    dataset = normalizer.normalize(
        source_input=SAMPLE_IBM_AML_CSV,
        filename="ibm_aml_sample.csv",
        derive_reconciliation_sources=True,
    )

    assert len(dataset.payments) == 3
    assert len(dataset.ledger) == 3
    assert len(dataset.bank) == 3
    assert len(dataset.errors) == 0

    # Verify first payment record
    p1 = dataset.payments[0]
    assert p1.transaction_id == "TX_IBM_001"
    assert p1.amount == 9357.50
    assert p1.merchant_id == "ACC_ORIG_101"
    assert p1.date == "2026-08-20"
    assert p1.provenance.source_dataset == "IBM AML"
    assert p1.provenance.raw_amount == "9357.50"

    # Verify ledger record derived fee
    l1 = dataset.ledger[0]
    assert l1.transaction_id == "TX_IBM_001"
    assert l1.gross_amount == 9357.50
    assert l1.fee == 20.00
    assert l1.net_amount == 9337.50

    # Verify manifest metadata
    assert dataset.manifest.source_dataset == "IBM AML"
    assert dataset.manifest.source_type == "synthetic_public_dataset"
    assert dataset.manifest.is_derived_test_data is True


def test_ibm_aml_normalizer_validation_errors():
    """Test error handling on malformed amounts, missing IDs, or duplicates."""
    malformed_csv = """tran_id,orig_acct,bene_acct,tx_type,base_amt,tran_timestamp
TX_VAL_001,ACC_1,ACC_2,TRANSFER,invalid_number,2026-08-20
,ACC_1,ACC_2,TRANSFER,100.00,2026-08-20
TX_VAL_003,ACC_1,ACC_2,TRANSFER,250.00,2026-08-20
TX_VAL_003,ACC_1,ACC_2,TRANSFER,250.00,2026-08-20
"""
    normalizer = IBMAMLNormalizer()
    dataset = normalizer.normalize(malformed_csv, filename="malformed.csv")

    assert len(dataset.payments) == 1
    assert dataset.payments[0].transaction_id == "TX_VAL_003"
    assert len(dataset.errors) == 3
    assert any("Malformed numeric base_amt" in e for e in dataset.errors)
    assert any("Empty tran_id" in e for e in dataset.errors)
    assert any("Duplicate tran_id" in e for e in dataset.errors)


def test_generic_csv_normalizer():
    """Test generic CSV normalizer with explicit mapping."""
    normalizer = GenericCSVNormalizer()
    mapping = {
        "transaction_id": "custom_id",
        "amount": "transaction_value",
        "date": "settlement_date",
        "merchant_id": "customer_ref",
    }

    dataset = normalizer.normalize(
        SAMPLE_GENERIC_CSV,
        filename="custom.csv",
        mapping=mapping,
        derive_reconciliation_sources=True,
    )

    assert len(dataset.payments) == 2
    assert dataset.payments[0].transaction_id == "CUST_TX_1001"
    assert dataset.payments[0].amount == 1250.75
    assert dataset.payments[0].merchant_id == "REF_A"
    assert dataset.payments[0].date == "2026-08-19"
    assert len(dataset.errors) == 0


def test_generic_csv_missing_mapping():
    """Test that generic CSV fails without explicit mapping."""
    normalizer = GenericCSVNormalizer()
    with pytest.raises(ValueError, match="requires an explicit column mapping"):
        normalizer.normalize(SAMPLE_GENERIC_CSV)


def test_export_to_directory():
    """Test CSV file generation and manifest export."""
    normalizer = IBMAMLNormalizer()
    dataset = normalizer.normalize(SAMPLE_IBM_AML_CSV, filename="test.csv")

    with tempfile.TemporaryDirectory() as tmpdir:
        exported = normalizer.export_to_directory(dataset, tmpdir)
        assert os.path.exists(exported["payments"])
        assert os.path.exists(exported["ledger"])
        assert os.path.exists(exported["bank"])
        assert os.path.exists(exported["adjustments"])
        assert os.path.exists(exported["manifest"])

        with open(exported["manifest"], "r", encoding="utf-8") as f:
            manifest_json = json.load(f)
            assert manifest_json["source_dataset"] == "IBM AML"
            assert manifest_json["record_count"] == 3


def test_api_normalizer_preview():
    """Test POST /api/normalizer/preview endpoint."""
    response = client.post(
        "/api/normalizer/preview",
        data={"source_type": "ibm_aml"},
        files={"file": ("ibm_test.csv", SAMPLE_IBM_AML_CSV.encode("utf-8"), "text/csv")},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["normalizer"] == "ibm_aml"
    assert data["source_dataset"] == "IBM AML"
    assert data["source_type"] == "synthetic_public_dataset"
    assert data["total_source_rows"] == 3
    assert data["normalized_payments_count"] == 3
    assert data["valid"] is True
    assert len(data["sample_normalized_rows"]) == 3
    assert data["sample_normalized_rows"][0]["transaction_id"] == "TX_IBM_001"
    assert data["sample_normalized_rows"][0]["amount"] == 9357.50
