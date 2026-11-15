"""Shared text keys for matching Power BI names."""

from __future__ import annotations

from functools import lru_cache
from typing import Any


@lru_cache(maxsize=65536)
def _alnum_text(value: str) -> str:
    return "".join(char for char in value.casefold() if char.isalnum())


def alnum_key(value: Any) -> str:
    """Case-insensitive key made of letters and digits only (``"Sales Amount"`` and ``"sales_amount"`` match)."""
    # Object names are matched millions of times during a scan, so the key is memoized per text.
    return _alnum_text(value if isinstance(value, str) else str(value))
