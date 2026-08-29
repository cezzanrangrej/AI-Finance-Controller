"""
Financial Dataset Normalizer package.

Provides normalizers for third-party and custom transaction schemas to produce
canonical 4-source reconciliation datasets.
"""

from src.normalizer.base import DatasetNormalizer
from src.normalizer.generic_csv import GenericCSVNormalizer
from src.normalizer.ibm_aml import IBMAMLNormalizer
from src.normalizer.registry import (
    get_normalizer,
    list_normalizers,
    register_normalizer,
)
from src.normalizer.schemas import (
    CanonicalAdjustmentRecord,
    CanonicalBankRecord,
    CanonicalLedgerRecord,
    CanonicalPaymentRecord,
    ColumnMappingConfig,
    DatasetManifest,
    NormalizationPreviewResponse,
    NormalizedDataset,
    ProvenanceRecord,
)

__all__ = [
    "DatasetNormalizer",
    "GenericCSVNormalizer",
    "IBMAMLNormalizer",
    "get_normalizer",
    "list_normalizers",
    "register_normalizer",
    "CanonicalPaymentRecord",
    "CanonicalLedgerRecord",
    "CanonicalBankRecord",
    "CanonicalAdjustmentRecord",
    "ColumnMappingConfig",
    "DatasetManifest",
    "NormalizedDataset",
    "NormalizationPreviewResponse",
    "ProvenanceRecord",
]
