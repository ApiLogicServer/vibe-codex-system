from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol

from ..models import Order


class ProducerProtocol(Protocol):
    def produce(self, topic: str, value: bytes) -> Any: ...

    def flush(self, timeout: float | None = None) -> Any: ...


@dataclass
class KafkaMessage:
    topic: str
    payload: dict[str, Any]


class KafkaService:
    """Minimal Kafka publisher with fallback to filesystem storage."""

    def __init__(self, topic: str, producer: ProducerProtocol | None = None, storage_dir: str = "data"):
        self.topic = topic
        self.producer = producer
        self.storage_path = Path(storage_dir) / f"{topic}.jsonl"
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

    def publish(self, payload: dict[str, Any]) -> KafkaMessage:
        message = KafkaMessage(topic=self.topic, payload=payload)
        if self.producer:
            self.producer.produce(self.topic, json.dumps(payload, default=self._serialize).encode("utf-8"))
            self.producer.flush()
        else:
            with self.storage_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, default=self._serialize) + "\n")
        return message

    def publish_order(self, order: Order) -> KafkaMessage:
        payload = {
            "order_id": order.id,
            "customer_id": order.customer_id,
            "amount_total": self._decimal_to_str(order.amount_total),
            "notes": order.notes,
            "date_created": self._datetime_to_str(order.date_created),
            "date_shipped": self._datetime_to_str(order.date_shipped),
            "items": [
                {
                    "product_id": item.product_id,
                    "quantity": item.quantity,
                    "unit_price": self._decimal_to_str(item.unit_price),
                    "amount": self._decimal_to_str(item.amount),
                }
                for item in order.items
            ],
        }
        return self.publish(payload)

    @staticmethod
    def _decimal_to_str(value: Decimal | None) -> str | None:
        return format(value, "f") if value is not None else None

    @staticmethod
    def _datetime_to_str(value: datetime | None) -> str | None:
        return value.isoformat() if value else None

    @staticmethod
    def _serialize(value: Any) -> Any:
        if isinstance(value, datetime):
            return KafkaService._datetime_to_str(value)
        if isinstance(value, Decimal):
            return KafkaService._decimal_to_str(value)
        return value
