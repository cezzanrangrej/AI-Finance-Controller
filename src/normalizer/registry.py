"""
Normalizer registry for looking up and registering dataset normalizers.
"""

from typing import Dict, List, Type
from src.normalizer.base import DatasetNormalizer

_REGISTRY: Dict[str, Type[DatasetNormalizer]] = {}


def register_normalizer(name: str):
    """Decorator to register a DatasetNormalizer subclass."""
    def decorator(cls: Type[DatasetNormalizer]):
        _REGISTRY[name.lower()] = cls
        cls.name = name.lower()
        return cls
    return decorator


def get_normalizer(name: str) -> DatasetNormalizer:
    """Instantiates a normalizer by its registered name."""
    normalizer_cls = _REGISTRY.get(name.lower())
    if not normalizer_cls:
        available = ", ".join(sorted(_REGISTRY.keys())) or "none"
        raise ValueError(f"Unknown normalizer '{name}'. Available normalizers: {available}")
    return normalizer_cls()


def list_normalizers() -> List[Dict[str, str]]:
    """Returns a list of all registered normalizers with their metadata."""
    result = []
    for key, cls in _REGISTRY.items():
        result.append({
            "name": key,
            "source_dataset_name": getattr(cls, "source_dataset_name", key),
            "source_type": getattr(cls, "source_type", "synthetic_public_dataset"),
            "description": cls.__doc__.strip().split("\n")[0] if cls.__doc__ else "Dataset normalizer",
        })
    return result
