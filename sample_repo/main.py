"""Entry point that wires the demo store together."""

from __future__ import annotations

from .customer import Customer


def run_demo() -> str:
    """Create a customer, place an order, and return its receipt."""
    alice = Customer(name="Alice Smith", email="alice@example.com")
    order = alice.place_order(items=["widget", "gadget", "gizmo"])
    return order.receipt()


if __name__ == "__main__":
    print(run_demo())
