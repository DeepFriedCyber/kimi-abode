"""BLM (Basic Listing Model) mapping — standardises agent feeds."""

from __future__ import annotations

from .schemas import BlmListing, CsvListing


# Standard field mappings for different estate-agent systems.
SYSTEM_MAPS: dict[str, dict[str, str]] = {
    "alto": {
        "address": "full_address",
        "town": "town",
        "postcode": "postcode_outcode",
        "price": "asking_price",
        "beds": "num_bedrooms",
        "property_type": "property_subtype",
    },
    "jupix": {
        "address": "address_line1",
        "town": "town",
        "postcode": "postcode",
        "price": "sale_price",
        "beds": "bedrooms",
        "property_type": "prop_type",
    },
    "reapit": {
        "address": "full_address",
        "town": "town_name",
        "postcode": "outward_code",
        "price": "price",
        "beds": "bedroom_count",
        "property_type": "property_type_desc",
    },
}


def resolve_mapping(system: str) -> dict[str, str]:
    """Get the standard column mapping for a given estate-agent CRM system."""
    return SYSTEM_MAPS.get(system, SYSTEM_MAPS["reapit"])  # default to REAPIT


def map_blm_to_standard(blm: BlmListing) -> CsvListing:
    """Convert a BLM listing to the standard CSV format."""
    return CsvListing(
        address=blm.address,
        town=blm.town,
        postcode=blm.postcode,
        price=blm.price,
        beds=blm.beds,
        property_type=blm.property_type,
        tenure=blm.tenure,
    )


def standard_to_blm(standard: CsvListing) -> BlmListing:
    """Convert a standard listing to BLM format."""
    return BlmListing(
        address=standard.address,
        town=standard.town,
        postcode=standard.postcode,
        price=standard.price,
        beds=standard.beds,
        property_type=standard.property_type,
        tenure=standard.tenure,
    )
