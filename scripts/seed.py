from __future__ import annotations

from decimal import Decimal
from datetime import datetime

from sqlalchemy import select

from app.database import db_session, init_db
from app.models import Customer, Order, OrderItem, Product
from app.services.credit import CreditService


CUSTOMERS = [
    {"name": "Acme Corp", "email": "ap@acme.example", "credit_limit": Decimal("10000.00")},
    {"name": "Globex", "email": "billing@globex.example", "credit_limit": Decimal("5000.00")},
]

PRODUCTS = [
    {"sku": "WIDGET-RED", "name": "Widget (Red)", "unit_price": Decimal("25.00")},
    {"sku": "WIDGET-BLU", "name": "Widget (Blue)", "unit_price": Decimal("20.00")},
    {"sku": "GADGET-STD", "name": "Standard Gadget", "unit_price": Decimal("40.00")},
]


def main() -> None:
    init_db()
    with db_session() as session:
        if session.execute(select(Customer)).first() is None:
            for payload in CUSTOMERS:
                session.add(Customer(**payload))

        if session.execute(select(Product)).first() is None:
            for payload in PRODUCTS:
                session.add(Product(**payload))

        session.flush()

        customer = session.execute(select(Customer).where(Customer.email == "ap@acme.example")).scalar_one()
        product = session.execute(select(Product).where(Product.sku == "WIDGET-RED")).scalar_one()
        if session.execute(select(Order).limit(1)).first() is None:
            order = Order(customer=customer, notes="Sample unshipped order")
            item = OrderItem(product=product, quantity=5, unit_price=product.unit_price, amount=product.unit_price * 5)
            order.items.append(item)
            order.update_amount_total()
            session.add(order)

        shipped_exists = session.execute(
            select(Order).where(Order.date_shipped.is_not(None)).limit(1)
        ).first()
        if not shipped_exists:
            other_customer = session.execute(select(Customer).where(Customer.email == "billing@globex.example")).scalar_one()
            other_product = session.execute(select(Product).where(Product.sku == "GADGET-STD")).scalar_one()
            order = Order(customer=other_customer, notes="Shipped sample", date_shipped=datetime.utcnow())
            item = OrderItem(
                product=other_product,
                quantity=2,
                unit_price=other_product.unit_price,
                amount=other_product.unit_price * 2,
            )
            order.items.append(item)
            order.update_amount_total()
            session.add(order)

        session.flush()
        credit_service = CreditService(session)
        for customer in session.execute(select(Customer)).scalars():
            credit_service.balance(customer.id)  # Warm cache / ensure logic executes


if __name__ == "__main__":
    main()
