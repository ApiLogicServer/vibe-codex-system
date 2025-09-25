from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal
from http import HTTPStatus
from typing import Any

from flask import Blueprint, Response, jsonify, request

from .database import db_session
from .models import Customer, Order
from .services import (
    CreditLimitExceededError,
    CreditService,
    DomainError,
    KafkaService,
    OrderService,
    ResourceNotFoundError,
)

api_bp = Blueprint("api", __name__)


@dataclass
class ApiError:
    message: str
    code: str
    details: dict[str, Any] | None = None

    def to_response(self, status: HTTPStatus) -> Response:
        payload = {"error": asdict(self)}
        return jsonify(payload), status


def _serialize_decimal(value: Decimal | None) -> str | None:
    return format(value, "f") if value is not None else None


def _serialize_order(order: Order) -> dict[str, Any]:
    return {
        "id": order.id,
        "customer_id": order.customer_id,
        "amount_total": _serialize_decimal(order.amount_total),
        "notes": order.notes,
        "date_created": order.date_created.isoformat() if order.date_created else None,
        "date_shipped": order.date_shipped.isoformat() if order.date_shipped else None,
        "items": [
            {
                "id": item.id,
                "product_id": item.product_id,
                "quantity": item.quantity,
                "unit_price": _serialize_decimal(item.unit_price),
                "amount": _serialize_decimal(item.amount),
            }
            for item in order.items
        ],
    }


def _serialize_customer(customer: Customer, credit_service: CreditService) -> dict[str, Any]:
    balance = credit_service.balance(customer.id)
    available_credit = customer.credit_limit - balance
    return {
        "id": customer.id,
        "name": customer.name,
        "email": customer.email,
        "credit_limit": _serialize_decimal(customer.credit_limit),
        "balance": _serialize_decimal(balance),
        "available_credit": _serialize_decimal(available_credit),
    }


def _service_factory(session) -> OrderService:
    credit = CreditService(session)
    kafka = KafkaService(topic="order_shipping")
    return OrderService(session, credit, kafka)


@api_bp.errorhandler(DomainError)
def handle_domain_error(error: DomainError):  # type: ignore[override]
    status = HTTPStatus.BAD_REQUEST
    if isinstance(error, ResourceNotFoundError):
        status = HTTPStatus.NOT_FOUND
    if isinstance(error, CreditLimitExceededError):
        status = HTTPStatus.CONFLICT
    api_error = ApiError(message=str(error), code=error.__class__.__name__)
    return api_error.to_response(status)


@api_bp.route("/customers", methods=["GET"])
def list_customers():
    with db_session() as session:
        service = _service_factory(session)
        customers = service.list_customers()
        credit = service.credit_service
        return jsonify([_serialize_customer(customer, credit) for customer in customers])


@api_bp.route("/orders", methods=["GET"])
def list_orders():
    with db_session() as session:
        service = _service_factory(session)
        orders = service.list_orders()
        return jsonify([_serialize_order(order) for order in orders])


@api_bp.route("/orders", methods=["POST"])
def create_order():
    payload = request.get_json(force=True) or {}
    customer_id = payload.get("customer_id")
    items = payload.get("items", [])
    notes = payload.get("notes")

    if not customer_id:
        return ApiError("customer_id is required", "ValidationError").to_response(HTTPStatus.BAD_REQUEST)

    with db_session() as session:
        service = _service_factory(session)
        order = service.create_order(int(customer_id), items, notes)
        return jsonify(_serialize_order(order)), HTTPStatus.CREATED


@api_bp.route("/orders/<int:order_id>", methods=["GET"])
def get_order(order_id: int):
    with db_session() as session:
        service = _service_factory(session)
        order = service.get_order(order_id)
        return jsonify(_serialize_order(order))


@api_bp.route("/orders/<int:order_id>/ship", methods=["POST"])
def ship_order(order_id: int):
    with db_session() as session:
        service = _service_factory(session)
        order = service.ship_order(order_id)
        return jsonify(_serialize_order(order))
