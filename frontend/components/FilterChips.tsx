/**
 * FilterChips — beds / price / property-type filters.
 *
 * Each price option maps to an explicit value; parsing the label ("£100k-£200k"
 * used to become £100,200,000) was a bug.
 */

"use client";

import { useState } from "react";

interface Filters {
  minBeds?: number;
  maxPrice?: number;
  propertyType: string;
}

interface FilterChipsProps {
  filters: Filters;
  onChange: (filters: Filters) => void;
}

const BED_OPTIONS = [1, 2, 3, 4, 5];

const PRICE_OPTIONS: Array<{ label: string; value?: number }> = [
  { label: "Under £100k", value: 100_000 },
  { label: "Under £200k", value: 200_000 },
  { label: "Under £300k", value: 300_000 },
  { label: "Under £400k", value: 400_000 },
  { label: "Under £500k", value: 500_000 },
  { label: "No limit", value: undefined },
];

const TYPE_OPTIONS = [
  { value: "", label: "All types" },
  { value: "detached", label: "Detached" },
  { value: "semi-detached", label: "Semi-detached" },
  { value: "terraced", label: "Terraced" },
  { value: "bungalow", label: "Bungalow" },
  { value: "flat", label: "Flat" },
];

export default function FilterChips({ filters, onChange }: FilterChipsProps) {
  const [openFilter, setOpenFilter] = useState<string | null>(null);

  const toggle = (name: string) =>
    setOpenFilter((current) => (current === name ? null : name));

  const update = (patch: Partial<Filters>) => {
    onChange({ ...filters, ...patch });
    setOpenFilter(null);
  };

  return (
    <div className="flex flex-wrap gap-2 items-center">
      {/* Beds */}
      <div className="relative">
        <button
          type="button"
          aria-expanded={openFilter === "beds"}
          onClick={() => toggle("beds")}
          className={`px-4 py-2 rounded-full border text-sm font-medium transition-colors ${
            filters.minBeds
              ? "bg-blue-100 border-blue-300 text-blue-700"
              : "bg-white border-gray-300 text-gray-700 hover:border-gray-400"
          }`}
        >
          {filters.minBeds ? `${filters.minBeds}+ beds` : "Beds"}
        </button>
        {openFilter === "beds" && (
          <div className="absolute top-full left-0 mt-1 bg-white border rounded-lg shadow-lg p-2 z-20 min-w-[130px]">
            {BED_OPTIONS.map((count) => (
              <button
                key={count}
                type="button"
                onClick={() => update({ minBeds: count })}
                className="w-full text-left px-3 py-1.5 text-sm hover:bg-gray-100 rounded"
              >
                {count}+ beds
              </button>
            ))}
            <button
              type="button"
              onClick={() => update({ minBeds: undefined })}
              className="w-full text-left px-3 py-1.5 text-sm text-gray-500 hover:bg-gray-100 rounded"
            >
              Any
            </button>
          </div>
        )}
      </div>

      {/* Price */}
      <div className="relative">
        <button
          type="button"
          aria-expanded={openFilter === "price"}
          onClick={() => toggle("price")}
          className={`px-4 py-2 rounded-full border text-sm font-medium transition-colors ${
            filters.maxPrice
              ? "bg-blue-100 border-blue-300 text-blue-700"
              : "bg-white border-gray-300 text-gray-700 hover:border-gray-400"
          }`}
        >
          {filters.maxPrice
            ? `Under £${Math.round(filters.maxPrice / 1000)}k`
            : "Price"}
        </button>
        {openFilter === "price" && (
          <div className="absolute top-full left-0 mt-1 bg-white border rounded-lg shadow-lg p-2 z-20 min-w-[170px]">
            {PRICE_OPTIONS.map((option) => (
              <button
                key={option.label}
                type="button"
                onClick={() => update({ maxPrice: option.value })}
                className="w-full text-left px-3 py-1.5 text-sm hover:bg-gray-100 rounded"
              >
                {option.label}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Type */}
      <div className="relative">
        <button
          type="button"
          aria-expanded={openFilter === "type"}
          onClick={() => toggle("type")}
          className={`px-4 py-2 rounded-full border text-sm font-medium transition-colors ${
            filters.propertyType
              ? "bg-blue-100 border-blue-300 text-blue-700"
              : "bg-white border-gray-300 text-gray-700 hover:border-gray-400"
          }`}
        >
          {TYPE_OPTIONS.find((option) => option.value === filters.propertyType)?.label ??
            "Type"}
        </button>
        {openFilter === "type" && (
          <div className="absolute top-full left-0 mt-1 bg-white border rounded-lg shadow-lg p-2 z-20 min-w-[170px]">
            {TYPE_OPTIONS.map((option) => (
              <button
                key={option.value || "all"}
                type="button"
                onClick={() => update({ propertyType: option.value })}
                className="w-full text-left px-3 py-1.5 text-sm hover:bg-gray-100 rounded"
              >
                {option.label}
              </button>
            ))}
          </div>
        )}
      </div>

      {(filters.minBeds !== undefined ||
        filters.maxPrice !== undefined ||
        filters.propertyType) && (
        <button
          type="button"
          onClick={() =>
            onChange({ minBeds: undefined, maxPrice: undefined, propertyType: "" })
          }
          className="px-4 py-2 rounded-full border text-sm font-medium text-red-600 hover:bg-red-50 border-red-300 transition-colors"
        >
          Clear all
        </button>
      )}
    </div>
  );
}
