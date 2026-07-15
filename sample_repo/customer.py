"""Customer domain model.

Imports `order` at module level, which in turn imports this module — the
intentional cyclic dependency in this demo package.
"""

from __future__ import annotations

from . import order
from .utils import slugify


class Customer:
    """A store customer who can place orders."""

    def __init__(self, name: str, email: str) -> None:
        self.name = name
        self.email = email
        self.handle = slugify(name)

    def place_order(self, items: list[str]) -> "order.Order":
        """Create and return a new Order for this customer."""
        return order.Order(customer=self, items=items)
