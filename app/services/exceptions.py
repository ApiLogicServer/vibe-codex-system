from decimal import Decimal


class DomainError(Exception):
    """Base class for domain-specific exceptions."""


class CreditLimitExceededError(DomainError):
    def __init__(self, customer_id: int, credit_limit: Decimal, attempted: Decimal):
        message = (
            f"Customer {customer_id} credit limit {credit_limit} exceeded by attempted balance {attempted}."
        )
        super().__init__(message)
        self.customer_id = customer_id
        self.credit_limit = credit_limit
        self.attempted = attempted


class ResourceNotFoundError(DomainError):
    def __init__(self, resource: str, identifier: str | int):
        super().__init__(f"{resource} '{identifier}' was not found")
        self.resource = resource
        self.identifier = identifier
