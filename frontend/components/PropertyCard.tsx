/**
 * PropertyCard — individual property listing card component.
 * Includes type safety guards and error handling for numeric fields.
 */

"use client";

import Link from "next/link";

interface PropertyCardProps {
  property: {
    id?: number | string;
    address_line1: string;
    address_line2?: string;
    town?: string;
    postcode?: string;
    property_type?: string;
    num_beds?: number;
    price_paid?: number;
    latitude?: number;
    longitude?: number;
  };
}

/** Type-safe numeric sanitizer to prevent NaN/Infinity display issues. */
export function sanitizeNumber(value: number | null | undefined): string | "—" {
  if (value == null) return "—";
  const num = Number(value);
  if (!Number.isFinite(num)) return "—";
  return String(num);
}

/** Safe price formatter with error handling. */
function formatPrice(price: number | null | undefined): string {
  if (price == null) return "Price on request";
  const num = Number(price);
  if (!Number.isFinite(num)) return "Price unavailable";
  return `£${num.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

const typeIcons: Record<string, string> = {
  detached: "🏡",
  "semi-detached": "🏠",
  terraced: "🏘️",
  bungalow: "🏚️",
  flat: "🏢",
  unknown: "🏠",
};

/** Safe type label formatter. */
function formatType(type?: string): string {
  if (!type) return "";
  const formatted = type.replace("-", " ");
  // Capitalize first letter of each word
  return formatted
    .split(" ")
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

export default function PropertyCard({ property }: PropertyCardProps) {
  const price = formatPrice(property.price_paid);
  const beds = sanitizeNumber(property.num_beds);
  const typeLabel = formatType(property.property_type);
  
  // Safe location construction with fallback
  const locationParts: string[] = [];
  if (property.town) locationParts.push(property.town);
  if (property.postcode) locationParts.push(property.postcode);
  const location = locationParts.length > 0 ? locationParts.join(", ") : "Location not available";

  // Safe icon lookup with fallback
  const icon = typeIcons[property.property_type || "unknown"] || "🏠";

  return (
    <Link
      href={`/property/${property.id || "detail"}`}
      className="block bg-white rounded-xl border hover:shadow-md transition-shadow overflow-hidden group focus:outline-none focus:ring-2 focus:ring-blue-500"
    >
      {/* Image placeholder with safe icon */}
      <div className="h-48 bg-gradient-to-br from-gray-200 to-gray-300 flex items-center justify-center">
        <span className="text-5xl opacity-50">{icon}</span>
      </div>

      <div className="p-4 space-y-2">
        <div className="flex items-start justify-between gap-2">
          <h3 className="font-semibold text-gray-900 group-hover:text-blue-600 transition-colors truncate" title={property.address_line1}>
            {property.address_line1}
          </h3>
        </div>

        {/* Address line 2 if available */}
        {property.address_line2 && (
          <p className="text-sm text-gray-600 truncate" title={property.address_line2}>
            {property.address_line2}
          </p>
        )}

        <p className="text-lg font-bold text-green-700">{price}</p>

        <div className="flex flex-wrap gap-2 text-sm text-gray-600">
          {beds && beds !== "—" && (
            <span>{beds === 1 ? `${beds} bed` : `${beds} beds`}</span>
          )}
          {typeLabel && <span className="capitalize">{typeLabel}</span>}
        </div>

        {location !== "Location not available" && (
          <p className="text-sm text-gray-500 truncate">
            {location}
          </p>
        )}
      </div>
    </Link>
  );
}