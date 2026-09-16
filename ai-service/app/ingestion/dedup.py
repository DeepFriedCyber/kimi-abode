"""Deduplication logic for property listings — prevents false merges."""

from __future__ import annotations

import re
from typing import Any


def normalise_address(addr: str) -> str:
    """Normalise an address for comparison — strip numbers, punctuation, lower-case."""
    s = addr.lower().strip()
    # Remove house numbers but keep road names
    s = re.sub(r"^\d+\s*", "", s)  # leading number
    s = re.sub(r"[.,;:!?&\/\\]", " ", s)  # punctuation → space
    return " ".join(s.split())


def addresses_match(addr1: str, addr2: str) -> bool:
    """Check if two addresses refer to the same property."""
    n1 = normalise_address(addr1)
    n2 = normalise_address(addr2)
    if n1 == n2:
        return True
    # Also check without "road"/"rd", "street"/"st" etc.
    s1 = re.sub(r"\b(road|rd|street|st|lane|ln|drive|dr|avenue|ave|way)\b", "", n1, flags=re.I).strip()
    s2 = re.sub(r"\b(road|rd|street|st|lane|ln|drive|dr|avenue|ave|way)\b", "", n2, flags=re.I).strip()
    return s1 == s2


def deduplicate_listings(listings: list[dict[str, Any]], *, threshold: float = 0.9) -> list[dict[str, Any]]:
    """Deduplicate a list of property listings.

    Groups addresses that refer to the same property and keeps the one with
    the most complete data.
    """
    groups: dict[int, list[dict[str, Any]]] = {}
    next_group_id = 0

    for listing in listings:
        addr = listing.get("address_line1", "")
        if not addr:
            continue

        best_match_id: int | None = None
        best_score = 0.0

        for gid, members in groups.items():
            for member in members:
                # Skip — conflicting house numbers can't be the same property
                if _number_conflict(addr, member.get("address_line1", "")):
                    continue
                score = _address_similarity(addr, member.get("address_line1", ""))
                if score > best_score and score >= threshold:
                    best_score = score
                    best_match_id = gid

        if best_match_id is not None:
            # Merge into existing group — keep the most complete listing
            groups[best_match_id].append(listing)
        else:
            groups[next_group_id] = [listing]
            next_group_id += 1

    # Keep the best listing from each group
    result = []
    for members in groups.values():
        best = max(members, key=lambda m: _completeness_score(m))
        result.append(best)

    return result


def _address_similarity(a: str, b: str) -> float:
    """Compute similarity between two addresses (0-1)."""
    na = normalise_address(a)
    nb = normalise_address(b)
    if na == nb:
        return 1.0

    tokens_a = set(na.split())
    tokens_b = set(nb.split())
    if not tokens_a or not tokens_b:
        return 0.0

    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    jaccard = len(intersection) / len(union)

    # Bonus for shared long substrings (catches "23 Station Road" vs "25 Station Road")
    common_substr = _longest_common_substring(na, nb)
    length_bonus = len(common_substr) / max(len(na), len(nb)) * 0.3

    return min(1.0, jaccard + length_bonus)


def _number_conflict(addr1: str, addr2: str) -> bool:
    """Check if two addresses have conflicting house numbers."""
    nums1 = re.findall(r"\d+", addr1)
    nums2 = re.findall(r"\d+", addr2)
    if nums1 and nums2:
        # If both start with different numbers, they likely differ
        n1_first = int(nums1[0]) if nums1[0].isdigit() else 0
        n2_first = int(nums2[0]) if nums2[0].isdigit() else 0
        if abs(n1_first - n2_first) > 5:  # heuristic threshold
            return True
    return False


def _longest_common_substring(a: str, b: str) -> str:
    """Find the longest common substring (efficient enough for addresses)."""
    if not a or not b:
        return ""
    m = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    longest = 0
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            if a[i - 1] == b[j - 1]:
                m[i][j] = m[i - 1][j - 1] + 1
                if m[i][j] > longest:
                    longest = m[i][j]
    return a[max(0, i - longest):i]


def _completeness_score(item: dict[str, Any]) -> int:
    """Score how complete a listing is (higher = better)."""
    score = 0
    for field in ("address_line1", "town", "postcode", "num_beds", "price_paid"):
        if item.get(field):
            score += 1
    return score
