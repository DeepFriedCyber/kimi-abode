/**
 * PropertyCard — individual property listing card component.
 */

"use client";

import Link from "next/link";

interface PropertyCardProps {
  property: {
    id?: number | string;
    address_line1: string;
    town?: string;
    postcode?: string;
    property_type?: string;
    num_beds?: number;
    price_paid?: number;
    latitude?: number;
    longitude?: number;
  };
}

const typeIcons: Record<string, string> = {
  detached: "🏡",
  "semi-detached": "🏠",
  terraced: "🏘️",
  bungalow: "🏚️",
  flat: "🏢",
};

export default function PropertyCard({ property }: PropertyCardProps) {
  const price = property.price_paid != null ? `£${property.price_paid.toLocaleString()}` : "Price on request";
  const beds = property.num_beds ? `${property.num_beds} bed` : "";
  const typeLabel = (property.property_type || "").replace("-", " ");
  const location = [property.town, property.postcode].filter(Boolean).join(", ");

  return (
    <Link
      href={`/property/${property.id || "detail"}`}
      className="block bg-white rounded-xl border hover:shadow-md transition-shadow overflow-hidden group"
    >
      {/* Image placeholder */}
      <div className="h-48 bg-gradient-to-br from-gray-200 to-gray-300 flex items-center justify-center">
        <span className="text-4xl opacity-50">{typeIcons[property.property_type || ""] || "🏠"}</span>
      </div>

      <div className="p-4 space-y-2">
        <div className="flex items-start justify-between gap-2">
          <h3 className="font-semibold text-gray-900 group-hover:text-blue-600 transition-colors line-clamp-1">
            {property.address_line1}
          </h3>
        </div>

        <p className="text-lg font-bold text-green-700">{price}</p>

        <div className="flex gap-3 text-sm text-gray-600">
          {beds && <span>{beds}</span>}
          {typeLabel && <span className="capitalize">{typeLabel}</span>}
        </div>

        {location && (
          <p className="text-sm text-gray-500 truncate">
            {location}
          </p>
        )}
      </div>
    </Link>
  );
}
