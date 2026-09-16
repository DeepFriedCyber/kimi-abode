"""Ingestion schemas — unified property listing models."""

from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel


class ListingInput(BaseModel):
    """Base model for any estate-agent listing format."""
    address: str
    town: Optional[str] = None
    postcode: Optional[str] = None
    price: float
    beds: Optional[int] = None
    property_type: Optional[str] = None
    tenure: Optional[str] = None


class BlmListing(ListingInput):
    """Rightmove / Zoopla BLM CSV format."""
    source: str = "blm"
    estate_agent: Optional[str] = None
    listing_date: Optional[date] = None
    status: str = "active"
    description: Optional[str] = None


class CsvListing(ListingInput):
    """Generic CSV with column mapping."""
    source: str = "csv"
    column_map: dict[str, str] = {}
    encoding: str = "utf-8-sig"  # handles BOM


class SoldListing(BaseModel):
    """Land Registry sold-price record."""
    price_paid: float
    date_sold: date
    property_type: str
    is_multi_property: bool = False
    unique_property_reference_number: Optional[str] = None
