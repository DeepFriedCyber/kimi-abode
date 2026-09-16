/**
 * API client for communicating with the Abode API server.
 */

import type { SearchResult, ParsedQuery, PoiResult, ChatResponse } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:3001";

/** Search properties by natural language query. */
export async function searchProperties(query: string): Promise<SearchResult> {
  const res = await fetch(`${API_BASE}/api/search?q=${encodeURIComponent(query)}`);
  if (!res.ok) throw new Error(`Search failed: ${res.statusText}`);
  return res.json();
}

/** Parse a natural language query. */
export async function parseQuery(query: string): Promise<ParsedQuery> {
  const res = await fetch(`${API_BASE}/api/parse`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query }),
  });
  if (!res.ok) throw new Error(`Parse failed: ${res.statusText}`);
  return res.json();
}

/** Get POI data near a property. */
export async function getNearbyPois(lat: number, lon: number, category?: string): Promise<{ nearby: PoiResult[]; category_scores: Record<string, number> }> {
  const params = new URLSearchParams({ lat: String(lat), lon: String(lon) });
  if (category) params.set("category", category);
  const res = await fetch(`${API_BASE}/api/ask/poi?${params}`);
  if (!res.ok) throw new Error(`POI query failed: ${res.statusText}`);
  return res.json();
}

/** Get health status of the API server. */
export async function getHealth(): Promise<{ status: string; ai: boolean }> {
  const res = await fetch(`${API_BASE}/api/health`);
  if (!res.ok) throw new Error(`Health check failed: ${res.statusText}`);
  return res.json();
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
  if (!res.ok) throw new Error(`Chat failed: ${res.statusText}`);
  return res.json();
}
