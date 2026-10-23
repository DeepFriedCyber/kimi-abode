/**
 * Property detail page — full property information plus POI intelligence.
 */

"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import AskLocation from "../../../components/AskLocation";
import AskAboutArea from "../../../components/AskAboutArea";
import PhotoGallery from "../../../components/PhotoGallery";
import { ApiError, fetchProperty } from "../../../lib/api";
import {
  effectivePrice,
  formatArea,
  formatDate,
  formatNumber,
  formatPerSqm,
  formatPrice,
  formatStatus,
  formatType,
  priceKind,
} from "../../../lib/format";
import type { Property } from "../../../lib/types";

const TYPE_LABELS: Record<string, string> = {
  detached: "Detached house",
  "semi-detached": "Semi-detached house",
  terraced: "Terraced house",
  bungalow: "Bungalow",
  flat: "Flat",
  maisonette: "Maisonette",
  other: "Property",
};


export default function PropertyDetailPage() {
  const params = useParams();
  const propertyId = typeof params?.id === "string" ? params.id : undefined;

  const [property, setProperty] = useState<Property | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!propertyId) {
      setError("Property id is missing");
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);

    fetchProperty(propertyId)
      .then((data) => {
        if (cancelled) return;
        if (!data) {
          setError("Property not found");
          setProperty(null);
          return;
        }
        setProperty(data);
      })
      .catch((err) => {
        if (cancelled) return;
        setProperty(null);
        setError(
          err instanceof ApiError ? err.message : "Failed to load this property",
        );
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [propertyId]);

  if (loading) {
    return (
      <div className="max-w-4xl mx-auto space-y-6">
        <BackLink />
        <p className="text-center py-12 text-gray-500">Loading property…</p>
      </div>
    );
  }

  if (error || !property) {
    return (
      <div className="max-w-4xl mx-auto space-y-6">
        <BackLink />
        <div className="text-center py-12 text-red-600">
          <p>{error ?? "Property not found"}</p>
        </div>
      </div>
    );
  }

  const typeKey = property.property_type ?? "other";
  const typeLabel = TYPE_LABELS[typeKey] ?? formatType(typeKey);
  const hasCoordinates =
    typeof property.latitude === "number" && typeof property.longitude === "number";

  const facts = [
    { label: "Bedrooms", value: formatNumber(property.num_beds) },
    { label: "Type", value: typeLabel.replace(" house", "") },
    { label: "Floor area", value: formatArea(property.floor_area_sqm) ?? "—" },
    { label: "Plot size", value: formatArea(property.plot_size_sqm) ?? "—" },
    { label: "Price / m²", value: formatPerSqm(property.price_per_sqm) ?? "—" },
    { label: "Tenure", value: property.tenure ?? "—" },
    { label: "Outcode", value: property.outcode ?? "—" },
    {
      label: property.asking_price ? "Listed" : "Last sold",
      value: formatDate(property.asking_price ? property.listed_at : property.date_sold),
    },
  ];

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <BackLink />

      <article className="bg-white rounded-xl border overflow-hidden shadow-sm">
        <PhotoGallery
          photos={property.photos ?? []}
          address={property.address_line1}
        />

        <div className="p-6">
          <div className="flex flex-col sm:flex-row sm:justify-between sm:items-start gap-3">
            <div>
              <h1 className="text-2xl font-bold">{property.address_line1}</h1>
              {property.address_line2 && (
                <p className="text-gray-600">{property.address_line2}</p>
              )}
              <p className="text-gray-500 mt-1">
                {[property.town, property.postcode].filter(Boolean).join(", ") ||
                  "Location unavailable"}
              </p>
              {property.ward && property.ward !== property.town && (
                <p className="text-xs text-gray-400 mt-1">
                  {property.ward}
                  {property.district ? ` · ${property.district}` : ""}
                </p>
              )}
            </div>
            <div className="sm:text-right">
              <p className="text-3xl font-bold text-green-700">
                {formatPrice(effectivePrice(property))}
              </p>
              <p className="text-sm text-gray-500 mt-1">
                {priceKind(property)} price · {typeLabel}
              </p>
              {property.listing_status && (
                <span className="inline-block mt-2 px-2 py-1 rounded-full text-xs bg-blue-50 text-blue-800 capitalize">
                  {formatStatus(property.listing_status)}
                </span>
              )}
            </div>
          </div>

          <dl className="grid grid-cols-2 sm:grid-cols-4 gap-4 mt-6 py-4 border-t text-center">
            {facts.map((fact) => (
              <div key={fact.label}>
                <dt className="text-xs text-gray-500">{fact.label}</dt>
                <dd className="text-lg font-semibold">{fact.value}</dd>
              </div>
            ))}
          </dl>

          {(property.description || property.features?.length) && (
            <section className="mt-4 pt-4 border-t">
              <h2 className="text-sm font-semibold text-gray-700 mb-2">Description</h2>
              {property.description && (
                <p className="text-sm text-gray-600 whitespace-pre-line">{property.description}</p>
              )}
              {property.features && property.features.length > 0 && (
                <ul className="mt-3 grid sm:grid-cols-2 gap-1 text-sm text-gray-600 list-disc list-inside">
                  {property.features.map((feature) => (
                    <li key={feature}>{feature}</li>
                  ))}
                </ul>
              )}
            </section>
          )}

          {(property.agent_id || property.agent_ref) && (
            <p className="text-xs text-gray-400 mt-3">
              Listed by {property.agent_id ?? "agent"}
              {property.agent_ref ? ` · ref ${property.agent_ref}` : ""}
            </p>
          )}

          <div className="pt-2 border-t flex flex-wrap items-center justify-between gap-2 text-xs text-gray-400">
            <span>
              Source: {property.source ?? "unknown"}
              {property.geo_precision ? ` · location: ${property.geo_precision}` : ""}
            </span>
            {property.source_url && (
              <a
                href={property.source_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-600 hover:underline"
              >
                View original record ↗
              </a>
            )}
          </div>
        </div>
      </article>

      <AskAboutArea propertyId={property.id} />

      {hasCoordinates ? (
        <AskLocation
          lat={property.latitude as number}
          lon={property.longitude as number}
        />
      ) : (
        <div className="bg-white rounded-xl border p-4 text-sm text-gray-500">
          📍 Amenity data is unavailable because this property has no coordinates.
        </div>
      )}
    </div>
  );
}

function BackLink() {
  return (
    <Link href="/" className="text-sm text-blue-600 hover:underline">
      ← Back to search
    </Link>
  );
}
