"""Print sample amenity answers for a property (uses data/poi_cache.json)."""

from __future__ import annotations

import json
from pathlib import Path

from app.poi.query import answer_poi_question

PROPERTY = {"address": "51 Cloverfields, CW1 5AL", "lat": 53.097675, "lon": -2.405048}
QUESTIONS = [
    "How far is the nearest Tesco superstore?",
    "What gyms are nearby?",
    "Nearest supermarket",
    "Primary schools within 2 miles",
    "Nearest train station",
    "Is there a park nearby?",
    "Pharmacy near me",
    "Nearest Waitrose",
]


def main() -> None:
    payload = json.loads(Path("data/poi_cache.json").read_text(encoding="utf-8"))
    pois = payload["pois"]
    print(f"{len(pois)} cached POIs; property: {PROPERTY['address']}\n")

    for question in QUESTIONS:
        result = answer_poi_question(pois, PROPERTY["lat"], PROPERTY["lon"], question)
        print(f"Q: {question}")
        if result is None:
            print("   (not an amenity question)\n")
            continue
        print(f"   {result['answer']}")
        for item in result["results"]:
            print(
                f"   - {item['name']} | {item['distance_m']:.0f} m | "
                f"{item['walk_time_min']} min | {item.get('brand') or '-'}"
            )
        print()


if __name__ == "__main__":
    main()
