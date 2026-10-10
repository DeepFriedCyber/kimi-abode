import type { Property } from './Property';
export interface SearchResult {
  properties: Property[];
  tier_used: string;
  total_matches: number;
  message: string;
}
export type ApiResponse = {
  success: boolean;
  data?: SearchResult;
  error: string;
}
