/**
 * API client for the Abode gateway.
 *
 * Every call goes through `request()` so timeouts, error shapes and JSON
 * parsing behave consistently. Components should never call `fetch` directly.
 */

import type {
  AreaAnswer,
  ChatResponse,
  HealthResponse,
  ParsedQuery,
  PoiResponse,
  Property,
  SearchResult,
} from "./types";

export type { AreaAnswer, AreaPlace } from "./types";

export const API_BASE = (
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:3001"
).replace(/\/+$/, "");

/** Absolute URL for a media path returned by the API (e.g. "/media/..."). */
export function mediaUrl(path: string | null | undefined): string | null {
  if (!path) return null;
  if (/^https?:\/\//i.test(path)) return path;
  return `${API_BASE}/api${path.startsWith("/") ? "" : "/"}${path}`;
}

const DEFAULT_TIMEOUT_MS = 15_000;

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly correlationId?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

interface ApiErrorBody {
  error?: string;
  correlation_id?: string;
}

export async function request<T>(
  path: string,
  init: RequestInit = {},
  timeoutMs: number = DEFAULT_TIMEOUT_MS,
): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(`${API_BASE}${path}`, {
      ...init,
      signal: controller.signal,
      headers: { Accept: "application/json", ...(init.headers ?? {}) },
    });

    if (!response.ok) {
      let body: ApiErrorBody = {};
      try {
        body = (await response.json()) as ApiErrorBody;
      } catch {
        // Non-JSON error body — keep the generic message.
      }
      throw new ApiError(
        body.error ?? `Request failed (${response.status})`,
        response.status,
        body.correlation_id,
      );
    }

    return (await response.json()) as T;
  } finally {
    clearTimeout(timeout);
  }
}

export interface SearchFilters {
  minBeds?: number;
  maxPrice?: number;
  propertyType?: string;
  location?: string;
  limit?: number;
}

/** Search properties by natural-language query with optional filters. */
export async function searchProperties(
  query: string,
  filters: SearchFilters = {},
): Promise<SearchResult> {
  const params = new URLSearchParams({ q: query });
  if (filters.minBeds !== undefined) params.set("min_beds", String(filters.minBeds));
  if (filters.maxPrice !== undefined) params.set("max_price", String(filters.maxPrice));
  if (filters.propertyType) params.set("property_type", filters.propertyType);
  if (filters.location) params.set("location", filters.location);
  if (filters.limit !== undefined) params.set("limit", String(filters.limit));

  return request<SearchResult>(`/api/search?${params.toString()}`);
}

/** Fetch a single property by id. Returns null for a 404. */
export async function fetchProperty(id: string | number): Promise<Property | null> {
  try {
    return await request<Property>(`/api/property/${encodeURIComponent(String(id))}`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

/** Parse a natural-language query without searching. */
export async function parseQuery(query: string): Promise<ParsedQuery> {
  return request<ParsedQuery>("/api/parse", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query }),
  });
}

/** Get POI data near a property. */
export async function getNearbyPois(
  lat: number,
  lon: number,
  category?: string,
  n = 5,
): Promise<PoiResponse> {
  return request<PoiResponse>("/api/ask/poi", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ lat, lon, category, n }),
  });
}

interface HealthCacheEntry {
  data: HealthResponse | null;
  timestamp: number;
}

const HEALTH_TTL_MS = 30_000;
let healthCache: HealthCacheEntry = { data: null, timestamp: 0 };

/** Health status with a short client-side cache. */
export async function getHealth(): Promise<HealthResponse> {
  const now = Date.now();
  if (healthCache.data && now - healthCache.timestamp < HEALTH_TTL_MS) {
    return healthCache.data;
  }

  try {
    const data = await request<HealthResponse>("/api/health", {}, 5_000);
    healthCache = { data, timestamp: now };
    return data;
  } catch {
    return { status: "unknown" };
  }
}

/** Explicitly invalidate the health cache (used after errors). */
export function clearHealthCache(): void {
  healthCache = { data: null, timestamp: 0 };
}

/** Chat with the AI assistant. */
export async function chat(message: string, propertyId?: number): Promise<ChatResponse> {
  return request<ChatResponse>("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      messages: [{ role: "user", content: message }],
      property_id: propertyId,
    }),
  }, 30_000);
}

/**
 * Stream a chat response. Yields text chunks as they arrive.
 * The gateway forwards SSE frames: `data: {"chunk": "..."}` and `data: [DONE]`.
 */
export async function* streamChat(
  message: string,
  propertyId?: number,
): AsyncGenerator<string> {
  const response = await fetch(`${API_BASE}/api/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify({
      messages: [{ role: "user", content: message }],
      property_id: propertyId,
    }),
  });

  if (!response.ok || !response.body) {
    throw new ApiError("Chat is unavailable", response.status);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      const raw = line.slice(6).trim();
      if (!raw) continue;
      if (raw === "[DONE]") return;

      try {
        const payload = JSON.parse(raw) as { chunk?: string; error?: string };
        if (payload.error) throw new ApiError(payload.error, 502);
        if (payload.chunk) yield payload.chunk;
      } catch (error) {
        if (error instanceof ApiError) throw error;
        // Ignore malformed frames.
      }
    }
  }
}

/**
 * Ask a question about the area around a property.
 * Deterministic answers come from OSM data, not the LLM.
 */
export async function askAboutArea(
  propertyId: number | string,
  question: string,
): Promise<AreaAnswer> {
  return request<AreaAnswer>(
    `/api/property/${encodeURIComponent(String(propertyId))}/nearby?q=${encodeURIComponent(question)}`,
  );
}
