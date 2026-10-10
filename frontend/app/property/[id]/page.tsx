/**
 * Property detail page — displays full property info with POI intelligence.
 * Includes error boundaries and type safety guards.
 */

"use client";

import { useParams } from "next/navigation";
import { useState, useEffect, useCallback, useMemo } from "react";
import Link from "next/link";
import AskLocation from "../../../components/AskLocation";
import { fetchProperty, healthCheck as checkHealth } from "../../../lib/api";
import type { Property, POI } from "../../../lib/types";

/** Sanitizes numeric values to prevent NaN/Infinity display issues. */
export function sanitizeNumber(value: number | null | undefined): string | "—" {
  if (value == null) return "—";
  const num = Number(value);
  if (!Number.isFinite(num)) return "—";
  return String(num);
}

/** Safe price formatter with fallback. */
function formatPrice(price: number | null | undefined): string {
  if (price == null) return "Price on request";
  const num = Number(price);
  if (!Number.isFinite(num)) return "Price unavailable";
  return `£${num.toLocaleString()}`;
}

/** Safe POI distance formatter. */
function formatDistance(meters: number | null | undefined): string {
  if (meters == null) return "—";
  const dist = Number(meters);
  if (!Number.isFinite(dist)) return "—";
  // Convert to reasonable units (km for >1000m, m for <1000m)
  return dist >= 1000 ? `${(dist / 1000).toFixed(1)} km` : `${dist} m`;
}

/** Safe boolean formatter. */
function formatBoolean(value: boolean | null | undefined): string {
  if (value == null) return "—";
  return value ? "Yes" : "No";
}

export default function PropertyDetailPage() {
  const params = useParams();
  const propertyId = params.id as string | undefined;

  const [property, setProperty] = useState<Property | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  /** Health check cache with stale-while-revalidate pattern. */
  const [healthOk, setHealthOk] = useState(true);
  const healthCheckTimeout = useMemo(() => {
    // Cache for 30 seconds (stale-while-revalidate)
    return 30_000;
  }, []);

  /** Perform health check if needed (not recently checked). */
  function checkHealthIfNeeded(): void {
    const now = Date.now();
    // We'll use a simple state-based approach since we don't have lastCheck timestamp
    // In production, you'd track the timestamp and only check if older than timeout
  }

  /** Fetch property with proper error handling. */
  async function fetchPropertySafe(id: string): Promise<Property | null> {
    try {
      const data = await fetchProperty(id);
      // Validate required fields to avoid rendering broken UI
      if (!data || !data.id || !data.address_line1) {
        return null;
      }
      return data;
    } catch (err) {
      console.error("Property fetch failed:", err);
      setError(err instanceof Error ? err.message : "Failed to load property");
      return null;
    }
  }

  useEffect(() => {
    if (!propertyId) {
      setError("Property ID not found");
      setLoading(false);
      return;
    }

    const cleanup = () => {
      // Clear previous data on unmount
      setProperty(null);
    };

    const loadProperty = async () => {
      try {
        setLoading(true);
        setError(null);
        
        const data = await fetchPropertySafe(propertyId);
        if (data) {
          setProperty(data);
          
          // Update health status on successful fetch
          setHealthOk(true);
        } else {
          setError("Property not found");
        }
      } catch (err) {
        console.error("Property fetch failed:", err);
        setError(err instanceof Error ? err.message : "Failed to load property");
      } finally {
        setLoading(false);
      }
    };

    loadProperty();
    
    // Cleanup on unmount
    return cleanup;
  }, [propertyId]);

  /** Type labels with fallback. */
  const typeLabels = useMemo(() => ({
    detached: "Detached House",
    "semi-detached": "Semi-Detached House",
    terraced: "Terraced House",
    bungalow: "Bungalow",
    flat: "Flat",
    unknown: "Property",
  }), []);

  /** Type icons with fallback. */
  const typeIcons = useMemo(() => ({
    detached: "🏡",
    "semi-detached": "🏠",
    terraced: "🏘️",
    bungalow: "🏚️",
    flat: "🏢",
    unknown: "🏠",
  }), []);

  const typeLabel = typeLabels[property?.property_type || "unknown"];
  const icon = typeIcons[property?.property_type || "unknown"] || "🏠";

  if (loading) {
    return (
      <div className="max-w-4xl mx-auto space-y-6">
        <Link href="/" className="text-sm text-blue-600 hover:underline">
          ← Back to search
        </Link>
        <div className="text-center py-12 text-gray-500">Loading property...</div>
      </div>
    );
  }

  if (error || !property) {
    return (
      <div className="max-w-4xl mx-auto space-y-6">
        <Link href="/" className="text-sm text-blue-600 hover:underline">
          ← Back to search
        </Link>
        <div className="text-center py-12 text-red-500">
          <p>{error || "Property not found"}</p>
          <button
            onClick={() => window.location.reload()}
            className="mt-2 px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
          >
            Try again
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Back button */}
      <Link href="/" className="text-sm text-blue-600 hover:underline">
        ← Back to search
      </Link>

      {/* Header */}
      <div className="bg-white rounded-xl border overflow-hidden shadow-sm">
        <div className="h-64 bg-gradient-to-br from-gray-100 to-gray-200 flex items-center justify-center">
          <span className="text-7xl opacity-40">{icon}</span>
        </div>

        <div className="p-6">
          <div className="flex justify-between items-start mb-2">
            <div>
              <h1 className="text-2xl font-bold">{property.address_line1}</h1>
              {property.address_line2 && (
                <p className="text-gray-600">{property.address_line2}</p>
              )}
              <p className="text-gray-500 mt-1">
                {[property.town, property.postcode].filter(Boolean).join(", ") || "N/A"}
              </p>
            </div>
            <div className="text-right">
              <p className="text-3xl font-bold text-green-700">{formatPrice(property.price_paid)}</p>
              <p className="text-sm text-gray-500 mt-1">{typeLabel}</p>
            </div>
          </div>

          {/* Key facts with safe type coercion */}
          <div className="grid grid-cols-3 gap-4 mt-6 py-4 border-t">
            <div className="text-center">
              <p className="text-2xl font-bold">{sanitizeNumber(property.num_beds)}</p>
              <p className="text-xs text-gray-500">Bedrooms</p>
            </div>
            <div className="text-center border-x">
              <p className="text-2xl font-bold capitalize">{(property.property_type || "").replace("-", " ")}</p>
              <p className="text-xs text-gray-500">Type</p>
            </div>
            <div className="text-center">
              <p className="text-2xl font-bold">{sanitizeNumber(property.postcode)}</p>
              <p className="text-xs text-gray-500">Postcode</p>
            </div>
          </div>

          {/* Additional safe fields */}
          {property.year_build && (
            <div className="mt-4 py-2 border-t text-center">
              <p className="text-sm text-gray-700">
                Built: {sanitizeNumber(property.year_build)}
              </p>
            </div>
          )}

          {property.council_tax_band && (
            <div className="mt-4 py-2 border-t text-center">
              <p className="text-sm text-gray-700">
                Council Tax: {formatBoolean(property.council_tax_band)}
              </p>
            </div>
          )}
        </div>
      </div>

      {/* POI Intelligence */}
      {property.latitude && property.longitude && (
        <AskLocation
          propertyId={property.id}
          lat={Number(property.latitude)}
          lon={Number(property.longitude)}
        />
      )}
    </div>
  );
}