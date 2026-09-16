/**
 * FilterChips — display and modify search filters as interactive chips.
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
const PRICE_OPTIONS = ["Under £100k", "£100k-£200k", "£200k-£300k", "£300k+", "No limit"];
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

  const updateFilter = (key: keyof Filters, value: any) => {
    onChange({ ...filters, [key]: value });
    setOpenFilter(null);
  };

  return (
    <div className="flex flex-wrap gap-2 items-center justify-center">
      {/* Beds filter */}
      <div className="relative">
        <button
          onClick={() => setOpenFilter(openFilter === "beds" ? null : "beds")}
          className={`px-4 py-2 rounded-full border text-sm font-medium transition-colors ${
            filters.minBeds
              ? "bg-blue-100 border-blue-300 text-blue-700"
              : "bg-white border-gray-300 text-gray-700 hover:border-gray-400"
          }`}
        >
          {filters.minBeds ? `${filters.minBeds}+ bed` : "Beds"}
        </button>
        {openFilter === "beds" && (
          <div className="absolute top-full left-0 mt-1 bg-white border rounded-lg shadow-lg p-2 z-10 min-w-[120px]">
            {BED_OPTIONS.map((n) => (
              <button
                key={n}
                onClick={() => updateFilter("minBeds", n)}
                className="w-full text-left px-3 py-1.5 text-sm hover:bg-gray-100 rounded"
              >
                {n}+ beds
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Price filter */}
      <div className="relative">
        <button
          onClick={() => setOpenFilter(openFilter === "price" ? null : "price")}
          className={`px-4 py-2 rounded-full border text-sm font-medium transition-colors ${
            filters.maxPrice
              ? "bg-blue-100 border-blue-300 text-blue-700"
              : "bg-white border-gray-300 text-gray-700 hover:border-gray-400"
          }`}
        >
          Price
        </button>
        {openFilter === "price" && (
          <div className="absolute top-full left-0 mt-1 bg-white border rounded-lg shadow-lg p-2 z-10 min-w-[160px]">
            {PRICE_OPTIONS.map((opt) => (
              <button
                key={opt}
                onClick={() => updateFilter("maxPrice", opt === "No limit" ? undefined : parseFloat(opt.replace(/[^0-9]/g, "")) * 1000)}
                className="w-full text-left px-3 py-1.5 text-sm hover:bg-gray-100 rounded"
              >
                {opt}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Type filter */}
      <div className="relative">
        <button
          onClick={() => setOpenFilter(openFilter === "type" ? null : "type")}
          className={`px-4 py-2 rounded-full border text-sm font-medium transition-colors ${
            filters.propertyType
              ? "bg-blue-100 border-blue-300 text-blue-700"
              : "bg-white border-gray-300 text-gray-700 hover:border-gray-400"
          }`}
        >
          {TYPE_OPTIONS.find((t) => t.value === filters.propertyType)?.label || "Type"}
        </button>
        {openFilter === "type" && (
          <div className="absolute top-full left-0 mt-1 bg-white border rounded-lg shadow-lg p-2 z-10 min-w-[160px]">
            {TYPE_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                onClick={() => updateFilter("propertyType", opt.value)}
                className="w-full text-left px-3 py-1.5 text-sm hover:bg-gray-100 rounded"
              >
                {opt.label}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Clear all */}
      {(filters.minBeds || filters.maxPrice || filters.propertyType) && (
        <button
          onClick={() => onChange({ minBeds: undefined, maxPrice: undefined, propertyType: "" })}
          className="px-4 py-2 rounded-full border text-sm font-medium text-red-600 hover:bg-red-50 border-red-300 transition-colors"
        >
          Clear all
        </button>
      )}
    </div>
  );
}
