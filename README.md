# Order Management System

A minimal Python + SQLite system exposing REST and HTML interfaces for customers, orders, items, and products. Core business logic covers credit checking, order totals, and shipping integration to a Kafka topic (emulated via append-only log).

## Original Request
> in this directory, Using Python and sqlite, Create a system with customers, orders, items and products.
>
> Include a notes field for orders.
>
> System means API, Web App, and business logic
>
> Use case: Check Credit
> 1. The Customer's balance is less than the credit limit
> 2. The Customer's balance is the sum of the Order amount_total where date_shipped is null
> 3. The Order's amount_total is the sum of the Item amount
> 4. The Item amount is the quantity * unit_price
> 5. The Item unit_price is copied from the Product unit_price
>
> Use case: App Integration
> 1. Send the Order to Kafka topic 'order_shipping' if the date_shipped is not None.

## Features
- Customers, products, orders, and order items persisted in SQLite via SQLAlchemy 2.0.
- Business rules enforced for credit utilisation, order amount rollups, and product pricing.
- REST API built with Flask for listing, creating, and shipping orders.
- Web UI for browsing customers, creating customers, creating orders, and marking shipments.
- Web UI for browsing products, creating products, and managing availability.
- Kafka integration stub that records shipped orders to `data/order_shipping.jsonl`.

## Status Notes
- Verified that product creation via `/products/new` succeeds and items become available for order entry.
- An attempted order that exceeded the customer's credit limit was correctly rejected with the expected credit exceeded message.
- Subsequent orders within the limit now complete successfully—the earlier `sqlalchemy.exc.InvalidRequestError` (missing `.unique()`) has been fixed, and balances update as expected after order creation.

## Tests & Scenarios
- **Increase quantity on a pending order:** Not directly supported in the current UI/API. The service layer exposes `add_items`, which appends new items and rechecks credit, but it does not edit existing item quantities. Manually bumping a quantity (e.g., via SQLAlchemy session tweaks) would bypass `ensure_credit` unless you also call `order.update_amount_total()` and `CreditService.ensure_credit(...)` yourself. A full update workflow would require an additional service method that recalculates item amounts and revalidates credit after quantity changes.
- **Swap item for a different product/price:** The current flows always copy unit price from the selected product when the item is created and recalculate totals. However, editing an existing item to point at a different product isn’t exposed; you would need to remove and re-add the item via `add_items`. An update feature should ensure the new product’s unit price is copied, the amount is recalculated, and credit is rechecked before committing.

## Prototype Assessment
- Significant scope gaps existed in the first delivery (no product navigation, no creation flows, missing secret key configuration). Those were addressed iteratively, but highlight that the prototype should be treated as a work in progress.
- Core business logic surfaced defects—order retrieval crashed until `.unique()` was added and credit checks could be bypassed by manual quantity edits. These issues illustrate limited initial testing and the need for regression coverage.
- There are still no automated tests, no item-edit workflow, and no audit of negative paths (e.g., deleting products, handling duplicate submissions). Use this system for demonstrations only until those areas are hardened.
- Documentation now records the known gaps and fixes; maintainers should review it carefully before claiming feature completeness.
- see the next section on a broader perspective on this assessment

## Comparison: Declarative vs Procedural Logic
- The sibling `basic_demo` project (in `basic_demo/logic/logic_discovery/check_credit.py`) uses LogicBank to declare the credit rules. Those spreadsheet-like formulas automatically recompute order totals, customer balances, and enforce credit limits on any insert/update/delete.
- Our Flask prototype implements the same requirements imperatively within service methods, so only the explicit flows we coded (order creation, adding items, shipping) trigger recalculations. Editing existing items or quantities is unsupported and would require extra code to maintain correctness.
- In similar projects, covering every CRUD pathway procedurally tends to consume a few hundred lines of service code, whereas the declarative rules remain concise. That trade-off should inform future enhancements—either adopt a rule engine for completeness or expand the service layer with comprehensive update/delete logic and tests.
- Training materials such as `basic_demo/docs/training/logic_bank_api.prompt` show how to author those declarative rules. With equivalent guidance, this project could emit LogicBank rule modules (e.g., a generated `check_credit.py`) instead of the hand-written service logic.
- For broader context on these trade-offs, see Val Huber’s Medium article [*The Missing Half of GenAI — and Why Microsoft’s CEO Says It’s the Future*](https://medium.com/@valjhuber/the-missing-half-of-genai-and-why-microsofts-ceo-says-it-s-the-future-c6fc05d93640), which argues that declarative rule engines supply the enterprise-ready business logic layer missing from UI-focused GenAI tooling.


## Getting Started

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/seed.py  # bootstrap customers, products, sample orders
python -m app.main      # run the development server on http://127.0.0.1:5000/
```

### Seeding Notes
- The seed script is optional; the app auto-creates empty tables on startup. Run the seed only if you want demo data.
- Initial failures were caused by missing dependencies (`ModuleNotFoundError: No module named 'sqlalchemy'`). Installing from `requirements.txt` resolves this.
- On Python 3.13 the older SQLAlchemy build (2.0.28) raised an assertion error during import. Updating to a 3.13-compatible release such as `SQLAlchemy>=2.0.31` fixes the issue. If an upgrade is not possible, use Python 3.12.

### Web UI
- `http://127.0.0.1:5000/orders` — browse and manage orders.
- `http://127.0.0.1:5000/orders/new` — create a new order.
- `http://127.0.0.1:5000/customers` — view customer credit exposure.
- `http://127.0.0.1:5000/customers/new` — create a customer with name, email, and credit limit.
- `http://127.0.0.1:5000/products` — browse active products.
- `http://127.0.0.1:5000/products/new` — create a product with SKU, name, and unit price.
- The initial navigation menu omitted the Products link; the current version adds it to the header so the products UI is discoverable.
- Order items are immutable via the current UI/API; editing or swapping products on existing line items would require additional endpoints.

### REST API Highlights
- `GET /api/customers` — list customers with balances and available credit.
- `GET /api/orders` — list orders and their items.
- `POST /api/orders` — create an order. Example payload:

  ```json
  {
    "customer_id": 1,
    "notes": "PO-1001",
    "items": [
      {"product_id": 1, "quantity": 3},
      {"product_id": 2, "quantity": 1}
    ]
  }
  ```

- `POST /api/orders/<id>/ship` — mark an order as shipped; triggers Kafka stub output to `data/order_shipping.jsonl`.

### Configuration
- Set a custom database location with the `DATABASE_URL` environment variable (defaults to `sqlite:///app.db`).
- Configure session security by setting `SECRET_KEY`; the app falls back to a development-only value (`dev-secret-key`). Without a secret key, flashing messages (e.g., after inserts) fails with Flask's "session is unavailable" runtime error.
- Provide a real Kafka producer by instantiating `KafkaService` with a producer implementation in `app/services/kafka.py`.

## Project Layout
- `app/` — Flask application, SQLAlchemy models, and business services.
- `templates/` — HTML templates for the web UI.
- `scripts/seed.py` — database bootstrapper.
- `data/order_shipping.jsonl` — shipping events written by the Kafka stub (created on demand).

## Running Tests
No automated tests are provided yet. For production use, consider adding unit tests for credit validation and API contracts.
