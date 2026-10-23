/** Shared display formatting (used by cards and the detail page). */

import type { Property } from "./types";

export function formatPrice(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return "Price unavailable";
  }
  return `£${value.toLocaleString("en-GB", { maximumFractionDigits: 0 })}`;
}

export function formatArea(value: number | null | undefined): string | null {
  if (value === null || value === undefined || !Number.isFinite(value)) return null;
  return `${Math.round(value)} m²`;
}

export function formatPerSqm(value: number | null | undefined): string | null {
  if (value === null || value === undefined || !Number.isFinite(value)) return null;
  return `£${Math.round(value).toLocaleString("en-GB")}/m²`;
}

export function formatNumber(value: number | null | undefined): string {
  return value === null || value === undefined || !Number.isFinite(value)
    ? "—"
    : String(value);
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleDateString("en-GB", { year: "numeric", month: "long" });
}

export function formatType(type: string | null | undefined): string {
  if (!type) return "";
  return type.replace(/-/g, " ");
}

/** Live agent listings carry an asking price; sold records carry price_paid. */
export function effectivePrice(property: Property): number | null {
  if (property.asking_price !== null && property.asking_price !== undefined) {
    return property.asking_price;
  }
  return property.price_paid ?? null;
}

export function priceKind(property: Property): "Asking" | "Sold" {
  return property.asking_price !== null && property.asking_price !== undefined
    ? "Asking"
    : "Sold";
}

export function formatStatus(status: string | null | undefined): string {
  if (!status) return "";
  return status.replace(/_/g, " ");
}

const METRES_PER_MILE = 1_609.344;
const METRES_PER_YARD = 0.9144;

/**
 * UK imperial display, mirroring `format_distance` in the AI service so the
 * chat prose and the UI rows never disagree: yards up close, then miles.
 */
export function formatDistance(metres: number | null | undefined): string {
  if (metres === null || metres === undefined || !Number.isFinite(metres)) {
    return "—";
  }
  const miles = metres / METRES_PER_MILE;
  if (miles < 0.1) {
    const yards = Math.max(10, Math.round(metres / METRES_PER_YARD / 10) * 10);
    return `${yards.toLocaleString("en-GB")} yards`;
  }
  if (miles < 10) {
    const rounded = Math.round(miles * 10) / 10;
    if (rounded === 1) return "1 mile";
    if (Number.isInteger(rounded)) return `${rounded} miles`;
    return `${rounded.toFixed(1)} miles`;
  }
  return `${Math.round(miles)} miles`;
}
