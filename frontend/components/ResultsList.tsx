/**
 * ResultsList — renders a grid of property cards.
 */

"use client";

import PropertyCard from "./PropertyCard";

interface ResultsListProps {
  properties: Array<{
    id?: number;
    address_line1: string;
    town?: string;
    postcode?: string;
    property_type?: string;
    num_beds?: number;
    price_paid?: number;
    latitude?: number;
    longitude?: number;
  }>;
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
      {properties.map((prop) => (
        <PropertyCard key={prop.id || prop.address_line1} property={prop} />
      ))}
    </div>
  );
}
