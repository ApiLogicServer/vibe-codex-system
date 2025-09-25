from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Iterable, Sequence

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from ..models import Customer, Order, OrderItem, Product
from .exceptions import DomainError, ResourceNotFoundError
from .credit import CreditService


class OrderService:
    """Application service encapsulating order workflows."""

    def __init__(self, session: Session, credit_service: CreditService, kafka_service: "KafkaService | None" = None):
        self.session = session
        self.credit_service = credit_service
        self.kafka_service = kafka_service

    # -------- Retrieval helpers ---------
    def _order_query(self, order_id: int) -> Select[tuple[Order]]:
        return select(Order).where(Order.id == order_id)

    def get_order(self, order_id: int) -> Order:
        order = self.session.execute(self._order_query(order_id)).unique().scalar_one_or_none()
        if not order:
            raise ResourceNotFoundError("Order", order_id)
        return order

    def list_orders(self) -> Sequence[Order]:
        return (
            self.session.execute(select(Order).order_by(Order.date_created.desc()))
            .unique()
            .scalars()
            .all()
        )

    def list_customers(self) -> Sequence[Customer]:
        return self.session.execute(select(Customer).order_by(Customer.name)).scalars().all()

    def list_products(self) -> Sequence[Product]:
        return self.session.execute(select(Product).where(Product.is_active.is_(True)).order_by(Product.name)).scalars().all()

    # -------- Commands ---------
    def create_product(self, sku: str, name: str, unit_price: Decimal, is_active: bool = True) -> Product:
        sku = sku.strip()
        name = name.strip()
        if not sku or not name:
            raise DomainError("Product SKU and name are required")
        if unit_price <= Decimal("0"):
            raise DomainError("Unit price must be greater than zero")

        existing = self.session.execute(
            select(Product).where(Product.sku == sku)
        ).scalar_one_or_none()
        if existing:
            raise DomainError("A product with this SKU already exists")

        product = Product(sku=sku, name=name, unit_price=unit_price, is_active=is_active)
        self.session.add(product)
        self.session.flush()
        return product

    def create_customer(self, name: str, email: str, credit_limit: Decimal) -> Customer:
        name = name.strip()
        email = email.strip().lower()
        if not name or not email:
            raise DomainError("Customer name and email are required")
        if credit_limit <= Decimal("0"):
            raise DomainError("Credit limit must be greater than zero")

        existing = self.session.execute(
            select(Customer).where(Customer.email == email)
        ).scalar_one_or_none()
        if existing:
            raise DomainError("A customer with this email already exists")

        customer = Customer(name=name, email=email, credit_limit=credit_limit)
        self.session.add(customer)
        self.session.flush()
        return customer

    def create_order(self, customer_id: int, items_data: Iterable[dict], notes: str | None = None) -> Order:
        items_payload = list(items_data)
        if not items_payload:
            raise DomainError("Cannot create an order without items")

        customer = self.credit_service.get_customer(customer_id)
        product_ids = {int(item["product_id"]) for item in items_payload}
        products = {
            product.id: product
            for product in self.session.execute(select(Product).where(Product.id.in_(product_ids))).scalars().all()
        }
        missing = product_ids - products.keys()
        if missing:
            raise ResourceNotFoundError("Product", next(iter(missing)))

        order = Order(customer=customer, notes=notes)
        total = Decimal("0")
        order_items: list[OrderItem] = []
        for item in items_payload:
            quantity = int(item.get("quantity", 0))
            if quantity <= 0:
                raise DomainError("Item quantity must be greater than zero")
            product = products[int(item["product_id"])]
            unit_price: Decimal = product.unit_price
            amount = unit_price * Decimal(quantity)
            total += amount
            order_items.append(
                OrderItem(product=product, quantity=quantity, unit_price=unit_price, amount=amount)
            )

        self.credit_service.ensure_credit(customer.id, total)
        order.items = order_items
        order.update_amount_total()
        self.session.add(order)
        self.session.flush()
        return order

    def add_items(self, order_id: int, items_data: Iterable[dict]) -> Order:
        order = self.get_order(order_id)
        for item in items_data:
            product_id = int(item["product_id"])
            quantity = int(item.get("quantity", 0))
            if quantity <= 0:
                raise DomainError("Item quantity must be greater than zero")
            product = self.session.get(Product, product_id)
            if not product:
                raise ResourceNotFoundError("Product", product_id)
            unit_price = product.unit_price
            amount = unit_price * Decimal(quantity)
            order.items.append(OrderItem(product=product, quantity=quantity, unit_price=unit_price, amount=amount))

        order.update_amount_total()
        self.credit_service.ensure_credit(order.customer_id, order.amount_total)
        self.session.flush()
        return order

    def ship_order(self, order_id: int, shipped_at: datetime | None = None) -> Order:
        order = self.get_order(order_id)
        order.date_shipped = shipped_at or datetime.utcnow()
        self.session.flush()
        if self.kafka_service:
            self.kafka_service.publish_order(order)
        return order


# Import at bottom to avoid circular imports
from .kafka import KafkaService  # noqa: E402  # pylint: disable=wrong-import-position
