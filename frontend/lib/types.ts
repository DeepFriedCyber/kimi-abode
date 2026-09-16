/**
 * Shared TypeScript types for the frontend.
 */

export interface Property {
  id?: number;
  address_line1: string;
  address_line2?: string;
  town?: string;
  postcode?: string;
  outcode?: string;
  property_type?: string;
  num_beds?: number;
  price_paid?: number;
  date_sold?: string;
  latitude?: number;
  longitude?: number;
  nearest_stations?: PoiResult[];
  poi_scores?: Record<string, number>;
}

export interface ParsedQuery {
  tier: string;
  min_beds?: number;
  max_price?: number;
  property_types: string[];
  location?: string;
  district?: string;
  outcode?: string;
  semantic_remainder?: string;
  has_location: boolean;
  has_price: boolean;
  raw: string;
}

export interface SearchResult {
  properties: Property[];
  tier_used: string;
  total_matches: number;
  message: string;
}

export interface PoiResult {
  name: string;
  category: string;
  distance_m: number;
  walk_time_min: number;
  decay_score: number;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface ChatResponse {
  response: string;
  has_llm: boolean;
}
