"""Shared text keys for matching Power BI names."""

from __future__ import annotations

from typing import Any


def alnum_key(value: Any) -> str:
    """Case-insensitive key made of letters and digits only (``"Sales Amount"`` and ``"sales_amount"`` match)."""
    return "".join(char for char in str(value).casefold() if char.isalnum())
