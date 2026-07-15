"""Order domain model.

Imports `customer` at module level, completing the `order` <-> `customer` cycle.
"""

from __future__ import annotations

from . import customer
from .utils import format_currency

PRICE_PER_ITEM = 9.99


class Order:
    """An order placed by a customer for a list of items."""

    def __init__(self, customer: "customer.Customer", items: list[str]) -> None:
        self.customer = customer
        self.items = items

    def total(self) -> float:
        """Return the order total as a float."""
        return len(self.items) * PRICE_PER_ITEM

    def receipt(self) -> str:
        """Return a human-readable receipt string."""
        return f"{self.customer.name}: {format_currency(self.total())}"
