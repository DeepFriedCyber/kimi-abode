/**
 * API response type definitions for frontend integration.
 */

import { Property } from '../db/types';

/**
 * Search results response from the search endpoint.
 */
export interface SearchResult {
  properties: Property[];
  tier_used: string;
  total_matches: number;
  message: string;
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
}

/**
 * Login/auth response with JWT token (placeholder).
 */
export interface AuthResponse {
  access_token: string;
  token_type: string;
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
}
