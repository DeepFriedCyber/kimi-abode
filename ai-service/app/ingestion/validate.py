"""Validation for listings — ensures data quality before database insertion."""

from __future__ import annotations

from typing import Any


# Minimum thresholds
MIN_PRICE = 10_000
MAX_PRICE = 50_000_000
REQUIRED_FIELDS = {"address_line1"}


def validate_listing(data: dict[str, Any]) -> tuple[bool, list[str]]:
    """Validate a property listing. Returns (is_valid, errors)."""
    errors = []

    if not data.get("address_line1"):
        errors.append("missing address")

    price = data.get("price_paid")
    if price is not None and (price < MIN_PRICE or price > MAX_PRICE):
        errors.append(f"price {price} out of range [{MIN_PRICE}, {MAX_PRICE}]")

    beds = data.get("num_beds")
    if beds is not None and (beds < 0 or beds > 20):
        errors.append(f"suspicious bed count: {beds}")

    postcode = data.get("postcode")
    if postcode and len(postcode) < 5:
        errors.append(f"postcode too short: {postcode}")

    return (len(errors) == 0, errors)


def validate_sold_record(data: dict[str, Any]) -> tuple[bool, list[str]]:
    """Validate a sold-price record."""
    errors = []

    price = data.get("price_paid", 0)
    if not isinstance(price, (int, float)) or price <= 0:
        errors.append(f"invalid price: {price}")

    date_sold = data.get("date_sold")
    if date_sold and hasattr(date_sold, "year"):
        if date_sold.year < 1995:
            errors.append(f"suspicious date: {date_sold.year} (Land Registry data starts ~1995)")

    return (len(errors) == 0, errors)


class ValidationReport:
    """Track validation results across a batch."""

    def __init__(self):
        self.total = 0
        self.valid = 0
        self.invalid = 0
        self.errors_by_type: dict[str, int] = {}

    def record(self, valid: bool, data: dict[str, Any], errors: list[str]):
        self.total += 1
        if valid:
            self.valid += 1
        else:
            self.invalid += 1
            for err in errors:
                self.errors_by_type[err] = self.errors_by_type.get(err, 0) + 1

    def summary(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "valid": self.valid,
            "invalid": self.invalid,
            "error_distribution": self.errors_by_type,
        }
