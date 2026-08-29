"""
Centralized formatting and safe numeric conversion utilities.

Prevents TypeError and ValueError: Cannot specify ',' with 's' across all
layers (tools, agent, prompts, API, logs).
"""

import re
from decimal import Decimal
from typing import Any, Optional, Union


def safe_int(val: Any) -> Optional[int]:
    """
    Safely converts a value to integer.
    Handles int, float, Decimal, numeric strings (including commas and currency symbols),
    and returns None for invalid or None/empty inputs.
    """
    if val is None or val == "":
        return None
    if isinstance(val, bool):
        return None
    if isinstance(val, int):
        return val
    if isinstance(val, (float, Decimal)):
        return int(val)
    if isinstance(val, str):
        cleaned = val.strip().replace("₹", "").replace(",", "").strip()
        if not cleaned:
            return None
        try:
            return int(float(cleaned))
        except (ValueError, TypeError):
            return None
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None


def safe_decimal(val: Any) -> Optional[Decimal]:
    """
    Safely converts a value to Decimal for exact financial calculations.
    Handles int, float, Decimal, numeric strings (including commas, currency symbols, and spaces),
    and returns None for invalid or empty inputs.
    """
    if val is None or val == "":
        return None
    if isinstance(val, bool):
        return None
    if isinstance(val, Decimal):
        return val
    if isinstance(val, (int, float)):
        return Decimal(str(val))
    if isinstance(val, str):
        cleaned = val.strip().replace("₹", "").replace("$", "").replace(",", "").strip()
        if not cleaned:
            return None
        try:
            return Decimal(cleaned)
        except Exception:
            return None
    try:
        return Decimal(str(val))
    except Exception:
        return None


def safe_numeric(val: Any) -> Optional[Union[int, float]]:
    """
    Safely converts a value to int (if whole number) or float (if fractional).
    Preserves exact decimal monetary representation without truncation.
    """
    d = safe_decimal(val)
    if d is None:
        return None
    if d % 1 == 0:
        return int(d)
    return float(d)


def safe_float(val: Any) -> Optional[float]:
    """
    Safely converts a value to float.
    Handles int, float, Decimal, numeric strings, and returns None for invalid inputs.
    """
    if val is None or val == "":
        return None
    if isinstance(val, bool):
        return None
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, Decimal):
        return float(val)
    if isinstance(val, str):
        cleaned = val.strip().replace("₹", "").replace("$", "").replace(",", "").strip()
        if not cleaned:
            return None
        try:
            return float(cleaned)
        except (ValueError, TypeError):
            return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def format_amount(val: Any, default: str = "N/A") -> str:
    """
    Formats a numeric value with thousands separator commas.
    Safely handles numbers, numeric strings, None, and non-numeric strings.
    """
    if val is None or val == "":
        return default
    num_int = safe_int(val)
    if num_int is not None:
        num_float = safe_float(val)
        if num_float is not None and num_float != num_int:
            return f"{num_float:,.2f}"
        return f"{num_int:,}"
    if isinstance(val, str):
        return val
    return str(val)


def format_currency(
    val: Any,
    symbol: str = "₹",
    default: str = "N/A",
    decimals: Optional[int] = None,
) -> str:
    """
    Formats a numeric value as a currency string with thousands separators.
    Examples:
        3000 -> '₹3,000'
        '3000' -> '₹3,000'
        None -> 'N/A'
    """
    if val is None or val == "":
        return default

    if decimals is not None:
        num_float = safe_float(val)
        if num_float is not None:
            if num_float < 0:
                return f"-{symbol}{abs(num_float):,.{decimals}f}"
            return f"{symbol}{num_float:,.{decimals}f}"
        return str(val)

    num_int = safe_int(val)
    if num_int is not None:
        num_float = safe_float(val)
        if num_float is not None and num_float != num_int:
            return f"{symbol}{num_float:,.2f}"
        return f"{symbol}{num_int:,}"

    if isinstance(val, str):
        return val
    return str(val)


def format_decimal_currency(
    val: Any,
    symbol: str = "₹",
    decimals: int = 2,
    default: str = "N/A",
) -> str:
    """Formats a value as a currency string with fixed decimal places."""
    return format_currency(val, symbol=symbol, default=default, decimals=decimals)
