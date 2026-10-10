/**
 * Environment configuration loader for Abode API server.
 */

import { config as loadConfig } from "dotenv";

// Load .env file from same directory
const result = loadConfig({ path: new URL("../.env", import.meta.url) });

export const config = {
  // Database configuration
  databaseType: process.env.DATABASE_URL?.startsWith("sqlite") ? "sqlite" : 
                process.env.DATABASE_URL?.startsWith("postgresql") ? "postgresql" : "in-memory",
  
  // Environment (development|production|test)
  nodeEnv: process.env.NODE_ENV || "development",
  
  // Server port
  port: parseInt(process.env.PORT || "3001", 10),
  
  // AI service URL
  aiServiceUrl: process.env.AI_SERVICE_URL || "http://localhost:8001/api/parse",
  
  // CORS origins (comma-separated or single value)
  corsOrigin: process.env.CORS_ORIGIN || "*",
  
  // JWT configuration
  jwtSecret: process.env.JWT_SECRET || "dev-secret-for-local-development-only",
  jwtIssuer: process.env.JWT_ISSUER || "abode-api",
} as const;

// Validate required environment variables
export function validateConfig() {
  if (!config.aiServiceUrl) {
    console.warn("[Config] AI_SERVICE_URL not set, using default");
  }
  
  // Always allow in-memory mode for development
  if (config.nodeEnv !== "production" && !config.databaseType) {
    console.log("[Config] Database type auto-detected as in-memory fallback");
  }
}

export function validateDatabaseUrl() {
  const url = process.env.DATABASE_URL || "";
  
  if (!url) {
    console.warn("[Config] DATABASE_URL is empty, using in-memory store");
    return true;
  }
  
  // Accept sqlite://, sqlite:, or postgresql:// URLs
  const validPrefixes = ["sqlite", "postgresql"];
  const hasValidPrefix = validPrefixes.some(prefix => url.startsWith(prefix));
  
  if (!hasValidPrefix) {
    console.warn(`[Config] DATABASE_URL has unexpected format: ${url.substring(0, 30)}...`);
  }
  
  return true;
}