/**
 * ResultsList — responsive grid of property cards.
 */

"use client";

import PropertyCard from "./PropertyCard";
import type { Property } from "../lib/types";

interface ResultsListProps {
  properties: Property[];
}

export default function ResultsList({ properties }: ResultsListProps) {
  if (!properties || properties.length === 0) {
    return (
      <div className="text-center py-8 text-gray-400">
        <p>No properties to display.</p>
      </div>
    );
  }

  return (
    <div className="property-grid">
      {properties.map((property) => (
        <PropertyCard key={property.id} property={property} />
      ))}
    </div>
  );
}
