"""Stateless helper functions with no internal dependencies (a clean leaf)."""

from __future__ import annotations


def format_currency(amount: float, symbol: str = "$") -> str:
    """Format a numeric amount as a currency string with two decimals."""
    return f"{symbol}{amount:,.2f}"


def slugify(text: str) -> str:
    """Convert arbitrary text into a lowercase, hyphenated slug."""
    return "-".join(text.lower().split())
