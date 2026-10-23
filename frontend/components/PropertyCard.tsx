/**
 * PropertyCard — a single listing card.
 */

"use client";

import Link from "next/link";
import {
  effectivePrice,
  formatArea,
  formatPerSqm,
  formatPrice,
  formatType,
  priceKind,
} from "../lib/format";
import { mediaUrl } from "../lib/api";
import type { Property } from "../lib/types";

interface PropertyCardProps {
  property: Property;
}

const TYPE_ICONS: Record<string, string> = {
  detached: "🏡",
  "semi-detached": "🏠",
  terraced: "🏘️",
  bungalow: "🏚️",
  flat: "🏢",
  maisonette: "🏢",
  other: "🏠",
};

export default function PropertyCard({ property }: PropertyCardProps) {
  const location =
    [property.town, property.postcode].filter(Boolean).join(", ") ||
    "Location unavailable";
  const icon = TYPE_ICONS[property.property_type ?? "unknown"] ?? "🏠";
  const beds = property.num_beds;
  const kind = priceKind(property);
  const sizeFacts = [
    formatArea(property.floor_area_sqm),
    formatPerSqm(property.price_per_sqm),
  ].filter(Boolean);
  const cover = property.photos?.find((photo) => photo.is_cover) ?? property.photos?.[0];
  const coverUrl = cover ? mediaUrl(cover.thumb_url) : null;

  return (
    <Link
      href={`/property/${property.id}`}
      className="block bg-white rounded-xl border hover:shadow-md transition-shadow overflow-hidden group focus:outline-none focus:ring-2 focus:ring-blue-500"
    >
      <div className="h-40 bg-gradient-to-br from-gray-200 to-gray-300 flex items-center justify-center overflow-hidden">
        {coverUrl ? (
          <img
            src={coverUrl}
            alt=""
            className="w-full h-full object-cover"
            loading="lazy"
            width={cover?.width}
            height={cover?.height}
          />
        ) : (
          <span className="text-5xl opacity-50" aria-hidden>
            {icon}
          </span>
        )}
      </div>

      <div className="p-4 space-y-2">
        <h3
          className="font-semibold text-gray-900 group-hover:text-blue-600 transition-colors truncate"
          title={property.address_line1}
        >
          {property.address_line1}
        </h3>

        {property.address_line2 && (
          <p className="text-sm text-gray-600 truncate" title={property.address_line2}>
            {property.address_line2}
          </p>
        )}

        <div className="flex items-baseline justify-between gap-2">
          <p className="text-lg font-bold text-green-700">
            {formatPrice(effectivePrice(property))}
          </p>
          <span className="text-[10px] uppercase tracking-wide text-gray-400">{kind}</span>
        </div>

        <div className="flex flex-wrap gap-2 text-sm text-gray-600">
          {beds !== null && beds !== undefined && (
            <span>
              {beds} {beds === 1 ? "bed" : "beds"}
            </span>
          )}
          {property.property_type && (
            <span className="capitalize">{formatType(property.property_type)}</span>
          )}
        </div>

        {sizeFacts.length > 0 && (
          <p className="text-xs text-gray-500">{sizeFacts.join(" · ")}</p>
        )}

        <p className="text-sm text-gray-500 truncate">{location}</p>
      </div>
    </Link>
  );
}
