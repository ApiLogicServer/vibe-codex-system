from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from ..models import Customer, Order
from .exceptions import CreditLimitExceededError, ResourceNotFoundError


class CreditService:
    """Provide credit-related operations for customers."""

    def __init__(self, session: Session):
        self.session = session

    def _customer_query(self, customer_id: int) -> Select[tuple[Customer]]:
        return select(Customer).where(Customer.id == customer_id)

    def get_customer(self, customer_id: int) -> Customer:
        customer = self.session.execute(self._customer_query(customer_id)).scalar_one_or_none()
        if not customer:
            raise ResourceNotFoundError("Customer", customer_id)
        return customer

    def balance(self, customer_id: int) -> Decimal:
        balance_value = (
            self.session.execute(
                select(func.coalesce(func.sum(Order.amount_total), 0))
                .where(Order.customer_id == customer_id)
                .where(Order.date_shipped.is_(None))
            ).scalar_one()
        )
        if isinstance(balance_value, Decimal):
            return balance_value
        return Decimal(balance_value)

    def can_place_order(self, customer_id: int, new_order_total: Decimal) -> bool:
        customer = self.get_customer(customer_id)
        current_balance = self.balance(customer_id)
        attempted_balance = current_balance + new_order_total
        if attempted_balance > customer.credit_limit:
            raise CreditLimitExceededError(customer.id, customer.credit_limit, attempted_balance)
        return True

    def ensure_credit(self, customer_id: int, new_order_total: Decimal) -> None:
        self.can_place_order(customer_id, new_order_total)

    def open_credit(self, customer_id: int) -> Decimal:
        customer = self.get_customer(customer_id)
        return customer.credit_limit - self.balance(customer_id)

    def mark_credit(self, customer_id: int, delta: Decimal) -> Decimal:
        """Utility helper kept for completeness; recompute using persisted data."""
        return self.balance(customer_id) + delta
