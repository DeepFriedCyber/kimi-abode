/**
 * Shared TypeScript types for the frontend.
 */

export interface Property {
  id: number;
  address_line1: string;
  address_line2?: string | null;
  town?: string | null;
  postcode?: string | null;
  outcode?: string | null;
  property_type?: string | null;
  num_beds?: number | null;
  price_paid?: number | null;
  date_sold?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  asking_price?: number | null;
  price_qualifier?: string | null;
  price_period?: string | null;
  listing_status?: string | null;
  listed_at?: string | null;
  num_bathrooms?: number | null;
  description?: string | null;
  features?: string[] | null;
  agent_id?: string | null;
  agent_ref?: string | null;
  floor_area_sqm?: number | null;
  plot_size_sqm?: number | null;
  price_per_sqm?: number | null;
  tenure?: string | null;
  ward?: string | null;
  district?: string | null;
  source_url?: string | null;
  geo_precision?: string | null;
  sold_precision?: string | null;
  has_embedding?: number;
  source?: string | null;
  nearest_stations?: PoiResult[];
  poi_scores?: Record<string, number>;
  photos?: Photo[];
}

export interface Photo {
  id: string;
  url: string;
  thumb_url: string;
  width: number;
  height: number;
  bytes?: number;
  is_cover: boolean;
  position?: number;
}

export interface ParsedQuery {
  tier: string;
  min_beds?: number | null;
  max_beds?: number | null;
  min_price?: number | null;
  max_price?: number | null;
  property_types: string[];
  location?: string | null;
  district?: string | null;
  outcode?: string | null;
  semantic_remainder?: string | null;
  has_location: boolean;
  has_price: boolean;
  raw: string;
}

export interface SearchResult {
  properties: Property[];
  tier_used: string;
  total_matches: number;
  message?: string;
  limit?: number;
}

export interface PoiResult {
  name: string;
  category: string;
  distance_m: number;
  walk_time_min: number;
  decay_score: number;
}

export interface PoiResponse {
  nearby: PoiResult[];
  category_scores: Record<string, number>;
  message?: string;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface ChatResponse {
  response: string;
  has_llm?: boolean;
}

export interface AreaPlace {
  name: string;
  brand?: string | null;
  category: string;
  subtype?: string | null;
  street?: string | null;
  distance_m: number;
  walk_time_min: number;
  opening_hours?: string | null;
  map_url: string;
}

export interface AreaAnswer {
  answer: string;
  intent: {
    category?: string | null;
    brand?: string | null;
    radius_m: number;
    limit: number;
  };
  results: AreaPlace[];
  total_matches: number;
  fallback?: string | null;
  distance_type: string;
  walk_assumption?: string;
  attribution: string;
  source: string;
  property_id?: number;
}

export interface HealthResponse {
  status: string;
  services?: {
    database: { status: string };
    ai_service: { status: string };
  };
  timestamp?: string;
}
