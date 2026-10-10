/**
 * API response type definitions for frontend integration.
 */

import { Property } from '../db/types';

/**
 * Search results response from the search endpoint.
 * @openapi
 * components/schemas/SearchResult:
 *   type: object
 *   properties:
 *     properties: { $ref: '#/components/schemas/Property[]' }
 *     tier_used: { type: string, enum: [semantic, deterministic, keyword] }
 *     total_matches: { type: integer }
 *     message: { type: string }
 *     timestamp: { type: string, format: date-time }
 */
export interface SearchResult {
  properties: Property[];
  tier_used: string;
  total_matches: number;
  message: string;
  timestamp?: string; // ISO 8601 datetime for caching invalidation
}

/**
 * Parse query response from the AI service proxy.
 */
export interface ParseResult {
  intent: string;
  entities: any[];
  original_query: string;
}

/**
 * Auth registration response.
 */
export interface RegisterResponse {
  id: number;
  email: string;
  name?: string;
  message: string;
  timestamp?: string; // For rate limiting tracking
}

/**
 * Login/auth response with JWT token.
 */
export interface AuthResponse {
  access_token: string;
  token_type: "Bearer";
  user: {
    id: number;
    email: string;
    name: string;
  };
  timestamp?: string; // For cache invalidation
}

/**
 * Property entity from the AI service.
 */
export interface AIProperty {
  id?: number;
  title: string;
  description?: string;
  location?: string;
  price?: number;
  bedrooms?: number;
  bathrooms?: number;
  sqft?: number;
  amenities?: string[];
  images?: string[];
  status?: 'available' | 'sold' | 'pending';
}

/**
 * Property type for frontend.
 */
export interface FrontendProperty extends AIProperty {
  id: number;
}

/**
 * Error response standard format.
 */
export interface ErrorResponse {
  error: string;
  status?: number;
  code?: string;
  message?: string;
  details?: unknown;
  timestamp?: string; // For API version tracking and caching
}

/**
 * Property entity from database.
 */
export interface DatabaseProperty extends AIProperty {
  address_line1: string;
  address_line2?: string | null;
  town?: string | null;
  postcode?: string | null;
  outcode?: string | null;
  property_type: string;
  num_beds: number;
  price_paid: number;
  date_sold?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  source?: string;
}

/**
 * Health check response.
 */
export interface HealthResponse {
  status: "healthy" | "unhealthy";
  db?: boolean;
  mode: "read-write" | "read-only" | "fallback";
  timestamp?: string;
}
