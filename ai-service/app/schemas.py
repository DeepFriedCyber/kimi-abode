"""Data models for the AI service."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class PropertyType(str, Enum):
    DETACHED = "detached"
    SEMI_DETACHED = "semi-detached"
    TERRACED = "terraced"
    BUNGALOW = "bungalow"
    FLAT = "flat"
    MAISONETTE = "maisonette"


class PurchaseType(str, Enum):
    FREEHOLD = "freehold"
    LEASEHOLD = "leasehold"


# ------------------------------------------------------------------ Query
class ParsedQuery(BaseModel):
    """Result of parsing a natural-language property query."""

    tier: str  # deterministic | llm-1 | llm-2 | semantic-cache | forced-deterministic
    min_beds: int | None = None
    max_price: float | None = None
    property_types: list[PropertyType] = Field(default_factory=list)
    location: str | None = None
    district: str | None = None
    outcode: str | None = None
    semantic_remainder: str | None = None
    has_location: bool = False
    has_price: bool = False
    raw: str


class ParseRequest(BaseModel):
    query: str


# ------------------------------------------------------------------ Property
class Property(BaseModel):
    id: int | None = None
    address_line1: str
    address_line2: str | None = None
    town: str | None = None
    postcode: str | None = None
    outcode: str | None = None
    property_type: PropertyType | None = None
    num_beds: int | None = None
    price_paid: float | None = None
    date_sold: datetime | None = None
    latitude: float | None = None
    longitude: float | None = None
    embedding: list[float] | None = None
    source: str = "land-registry"


class PropertyDetail(Property):
    """Property with extra enrichment fields."""

    nearest_stations: list[dict] = Field(default_factory=list)
    nearest_schools: list[dict] = Field(default_factory=list)
    poi_scores: dict[str, float] = Field(default_factory=dict)


# ------------------------------------------------------------------ Search results
class SearchResult(BaseModel):
    properties: list[PropertyDetail]
    tier_used: str
    total_matches: int
    message: str = ""


# ------------------------------------------------------------------ Chat
class ChatMessage(BaseModel):
    role: str  # user | assistant
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    property_id: int | None = None


class ChatResponse(BaseModel):
    response: str
    has_llm: bool


# ------------------------------------------------------------------ POI
class PoiIngestRequest(BaseModel):
    bbox: str  # "lat_min,lon_min,lat_max,lon_max"


class PoiPoint(BaseModel):
    name: str
    osm_id: int
    lat: float
    lon: float
    category: str
    distance_m: float = 0.0
    decay_score: float = 0.0


# ------------------------------------------------------------------ Enrichment review
class EnrichmentReview(BaseModel):
    total_properties: int
    total_sales: int
    trapped_pairs: list[tuple[str, str, str]]
    town_coverage_pct: float
    geo_coverage_pct: float
