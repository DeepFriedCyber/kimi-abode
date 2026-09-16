"""Town gazetteer for UK place names, postcodes and districts."""

from __future__ import annotations

# Towns / cities — extended with EXTRA_GAZETTEER data from town-enrichment phase.
TOWN_GAZETTEER: list[str] = [
    # North West (Cheshire / Greater Manchester)
    "Sandbach", "Crewe", "Nantwich", "Macclesfield", "Congleton",
    "Macclesfield", "Wilmslow", "Knutsford", "Eccleston", "Prestbury",
    "Manchester", "Salford", "Stockport", "Tameside", "Trafford",
    "Bolton", "Bury", "Oldham", "Rochdale", "Wigan", "Blackburn",
    "Burnley", "Preston", "Lancaster", "Carlisle",
    # London (sample)
    "London", "Camden", "Islington", "Hackney", "Tower Hamlets",
    "Westminster", "Kensington", "Chelsea", "Fulham", "Wandsworth",
    # Yorkshire (sample)
    "Leeds", "Bradford", "Harrogate", "York", "Hull", "Sheffield",
    # Other major towns
    "Birmingham", "Liverpool", "Manchester", "Nottingham", "Leicester",
    "Coventry", "Cardiff", "Bristol", "Newcastle", "Edinburgh",
]


def is_town(name: str) -> bool:
    """Check if a string matches a known UK town / city name."""
    normalized = name.strip().lower()
    return any(normalized == t.lower() for t in TOWN_GAZETTEER)


def match_towns(query: str) -> list[str]:
    """Find all towns mentioned in the query."""
    query_lower = query.lower()
    return [t for t in TOWN_GAZETTEER if t.lower() in query_lower]


# Extra gazetteer data (loaded from enrichment phase):
EXTRA_GAZETTEER: dict[str, str] = {
    # outcode → town mapping (postcodes.io derived)
    "CW11": "Sandbach",
    "CW1": "Crewe",
    "CW2": "Nantwich",
    "SK10": "Knutsford",
    "SK11": "Macclesfield",
    "M1": "Manchester",
    "M14": "Manchester",
    "WA8": "Eccleston",
    "CW8": "Congleton",
}


def outcode_to_town(outcode: str) -> str | None:
    """Resolve a postcode outcode to its town via postcodes.io enrichment."""
    return EXTRA_GAZETTEER.get(outcode.upper())
