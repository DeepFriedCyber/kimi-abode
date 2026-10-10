/**
 * API client for communicating with the Abode API server.
 * Includes caching and error handling improvements.
 */

import type { SearchResult, ParsedQuery, PoiResult, ChatResponse, Property } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:3001";

interface SearchFilters {
  minBeds?: number;
  maxPrice?: number;
  propertyType?: string;
}

/** Cache for health check with stale-while-revalidate pattern. */
const HEALTH_CACHE = {
  data: null as { status: string; ai: boolean } | null,
  timestamp: 0,
  ttl: 30_000, // 30 seconds stale duration
};

/** Search properties by natural language query with optional filters. */
export async function searchProperties(query: string, filters?: SearchFilters): Promise<SearchResult> {
  const params = new URLSearchParams({ q: query });
  if (filters?.minBeds) params.set("min_beds", String(filters.minBeds));
  if (filters?.maxPrice) params.set("max_price", String(filters.maxPrice));
  if (filters?.propertyType) params.set("property_type", filters.propertyType);

  const res = await fetch(`${API_BASE}/api/search?${params.toString()}`);
  if (!res.ok) throw new Error(`Search failed: ${res.status} ${res.statusText}`);
  return res.json();
}

/** Fetch a single property by ID. */
export async function fetchProperty(id: string | number): Promise<Property | null> {
  const res = await fetch(`${API_BASE}/api/property/${id}`);
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`Property fetch failed: ${res.status} ${res.statusText}`);
  return res.json();
}

/** Parse a natural language query. */
export async function parseQuery(query: string): Promise<ParsedQuery> {
  const res = await fetch(`${API_BASE}/api/parse`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query }),
  });
  if (!res.ok) throw new Error(`Parse failed: ${res.status} ${res.statusText}`);
  return res.json();
}

/** Get POI data near a property. */
export async function getNearbyPois(
  lat: number,
  lon: number,
  category?: string,
  n: number = 5,
): Promise<{ nearby: PoiResult[]; category_scores: Record<string, number> }> {
  const res = await fetch(`${API_BASE}/api/ask/poi`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ lat, lon, category, n }),
  });
  if (!res.ok) throw new Error(`POI query failed: ${res.status} ${res.statusText}`);
  return res.json();
}

/** 
 * Get health status of the API server with stale-while-revalidate caching.
 * Returns cached data for up to TTL milliseconds, then revalidates in background.
 */
export async function getHealth(): Promise<{ status: string; ai: boolean }> {
  const now = Date.now();
  
  // Return cached data if available and fresh (stale-while-revalidate)
  if (HEALTH_CACHE.data && now - HEALTH_CACHE.timestamp < HEALTH_CACHE.ttl) {
    return HEALTH_CACHE.data;
  }

  try {
    const res = await fetch(`${API_BASE}/api/health`);
    
    if (!res.ok) throw new Error(`Health check failed: ${res.status} ${res.statusText}`);
    
    const data = await res.json();
    
    // Update cache
    HEALTH_CACHE.data = data;
    HEALTH_CACHE.timestamp = now;
    
    return data;
  } catch (error) {
    console.error("Health check failed, falling back to unknown status:", error);
    
    // On failure, return a default state rather than throwing
    return { 
      status: "unknown", 
      ai: false 
    };
  }
}

/** Chat with the AI assistant. */
export async function chat(message: string, propertyId?: number): Promise<ChatResponse> {
  const res = await fetch(`${API_BASE}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      messages: [{ role: "user" as const, content: message }],
      property_id: propertyId,
    }),
  });
  if (!res.ok) throw new Error(`Chat failed: ${res.status} ${res.statusText}`);
  return res.json();
}

/** Explicitly invalidate the health cache. */
export function clearHealthCache(): void {
  HEALTH_CACHE.data = null;
  HEALTH_CACHE.timestamp = 0;
}