/**
 * Property detail page — displays full property info with POI intelligence.
 */

"use client";

import { useParams } from "next/navigation";
import AskLocation from "../../../components/AskLocation";

// Mock property data for development (replace with API call in production)
const MOCK_PROPERTY = {
  id: 1,
  address_line1: "1 High Street",
  town: "Sandbach",
  postcode: "CW11 1AA",
  property_type: "semi-detached",
  num_beds: 3,
  price_paid: 245000,
  latitude: 53.13,
  longitude: -2.43,
};

export default function PropertyDetailPage() {
  const params = useParams();
  const propertyId = params.id;

  const typeLabels: Record<string, string> = {
    detached: "Detached House",
    "semi-detached": "Semi-Detached House",
    terraced: "Terraced House",
    bungalow: "Bungalow",
    flat: "Flat",
  };

  const typeIcons: Record<string, string> = {
    detached: "🏡",
    "semi-detached": "🏠",
    terraced: "🏘️",
    bungalow: "🏚️",
    flat: "🏢",
  };

  // In production: fetch from API
  const property = MOCK_PROPERTY;
  const typeLabel = typeLabels[property.property_type || ""] || "Property";

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Back button */}
      <a href="/" className="text-sm text-blue-600 hover:underline">
        ← Back to search
      </a>

      {/* Header */}
      <div className="bg-white rounded-xl border overflow-hidden">
        <div className="h-64 bg-gradient-to-br from-gray-100 to-gray-200 flex items-center justify-center">
          <span className="text-6xl opacity-40">{typeIcons[property.property_type || ""] || "🏠"}</span>
        </div>

        <div className="p-6">
          <div className="flex justify-between items-start mb-2">
            <div>
              <h1 className="text-2xl font-bold">{property.address_line1}</h1>
              <p className="text-gray-500 mt-1">
                {[property.town, property.postcode].filter(Boolean).join(", ")}
              </p>
            </div>
            <div className="text-right">
              <p className="text-3xl font-bold text-green-700">
                £{property.price_paid?.toLocaleString()}
              </p>
              <p className="text-sm text-gray-500 mt-1">{typeLabel}</p>
            </div>
          </div>

          {/* Key facts */}
          <div className="grid grid-cols-3 gap-4 mt-6 py-4 border-t">
            <div className="text-center">
              <p className="text-2xl font-bold">{property.num_beds}</p>
              <p className="text-xs text-gray-500">Bedrooms</p>
            </div>
            <div className="text-center border-x">
              <p className="text-2xl font-bold capitalize">{property.property_type?.replace("-", " ")}</p>
              <p className="text-xs text-gray-500">Type</p>
            </div>
            <div className="text-center">
              <p className="text-2xl font-bold">{property.postcode}</p>
              <p className="text-xs text-gray-500">Postcode</p>
            </div>
          </div>
        </div>
      </div>

      {/* POI Intelligence */}
      {property.latitude && property.longitude && (
        <AskLocation propertyId={String(propertyId) || ""} />
      )}
    </div>
  );
}
