from __future__ import annotations

from decimal import Decimal, InvalidOperation

from flask import Blueprint, flash, redirect, render_template, request, url_for

from .database import db_session
from .services import CreditLimitExceededError, DomainError, KafkaService, OrderService
from .services.credit import CreditService

web_bp = Blueprint("web", __name__)


def _service_factory(session) -> OrderService:
    credit = CreditService(session)
    kafka = KafkaService(topic="order_shipping")
    return OrderService(session, credit, kafka)


@web_bp.route("/")
def index():
    return redirect(url_for("web.list_orders"))


@web_bp.route("/customers")
def list_customers():
    with db_session() as session:
        service = _service_factory(session)
        customers = service.list_customers()
        credit = service.credit_service
        enriched = []
        for customer in customers:
            balance = credit.balance(customer.id)
            enriched.append(
                {
                    "base": customer,
                    "balance": balance,
                    "available_credit": customer.credit_limit - balance,
                }
            )
        return render_template("customers.html", customers=enriched)


@web_bp.route("/customers/new", methods=["GET", "POST"])
def create_customer():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        credit_limit_raw = request.form.get("credit_limit", "0").strip()
        try:
            credit_limit = Decimal(credit_limit_raw)
        except InvalidOperation:
            flash("Credit limit must be a valid decimal amount.", "error")
        else:
            try:
                with db_session() as session:
                    service = _service_factory(session)
                    customer = service.create_customer(name, email, credit_limit)
                    flash(f"Customer '{customer.name}' created.", "success")
                    return redirect(url_for("web.list_customers"))
            except DomainError as exc:
                flash(str(exc), "error")

    return render_template("customer_form.html")


@web_bp.route("/products")
def list_products():
    with db_session() as session:
        service = _service_factory(session)
        products = service.list_products()
        return render_template("products.html", products=products)


@web_bp.route("/products/new", methods=["GET", "POST"])
def create_product():
    if request.method == "POST":
        sku = request.form.get("sku", "").strip()
        name = request.form.get("name", "").strip()
        price_raw = request.form.get("unit_price", "0").strip()
        is_active = bool(request.form.get("is_active"))
        try:
            unit_price = Decimal(price_raw)
        except InvalidOperation:
            flash("Unit price must be a valid decimal amount.", "error")
        else:
            try:
                with db_session() as session:
                    service = _service_factory(session)
                    product = service.create_product(sku, name, unit_price, is_active)
                    flash(f"Product '{product.name}' created.", "success")
                    return redirect(url_for("web.list_products"))
            except DomainError as exc:
                flash(str(exc), "error")

    return render_template("product_form.html")


@web_bp.route("/orders")
def list_orders():
    with db_session() as session:
        service = _service_factory(session)
        orders = service.list_orders()
        return render_template("orders.html", orders=orders)


@web_bp.route("/orders/<int:order_id>")
def order_detail(order_id: int):
    with db_session() as session:
        service = _service_factory(session)
        order = service.get_order(order_id)
        return render_template("order_detail.html", order=order)


@web_bp.route("/orders/<int:order_id>/ship", methods=["POST"])
def ship_order(order_id: int):
    with db_session() as session:
        service = _service_factory(session)
        service.ship_order(order_id)
        flash("Order shipped and forwarded to integration queue.", "success")
    return redirect(url_for("web.order_detail", order_id=order_id))


@web_bp.route("/orders/new", methods=["GET", "POST"])
def create_order():
    if request.method == "POST":
        customer_id = request.form.get("customer_id")
        notes = request.form.get("notes")
        product_ids = request.form.getlist("product_id")
        quantities = request.form.getlist("quantity")
        items = []
        for product_id, quantity in zip(product_ids, quantities):
            if product_id and quantity:
                try:
                    items.append({"product_id": int(product_id), "quantity": int(quantity)})
                except ValueError:
                    flash("Invalid quantity provided.", "error")
                    items = []
                    break

        if not customer_id:
            flash("Customer is required.", "error")
        elif not items:
            flash("Please provide at least one item.", "error")
        else:
            try:
                with db_session() as session:
                    service = _service_factory(session)
                    order = service.create_order(int(customer_id), items, notes)
                    flash(f"Order #{order.id} created.", "success")
                    return redirect(url_for("web.order_detail", order_id=order.id))
            except CreditLimitExceededError as exc:
                flash(str(exc), "error")
            except DomainError as exc:
                flash(str(exc), "error")

    with db_session() as session:
        service = _service_factory(session)
        customers = service.list_customers()
        products = service.list_products()
        return render_template("order_form.html", customers=customers, products=products)
