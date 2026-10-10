/**
 * Configuration module for the API server.
 * Validates and loads environment variables at startup.
 */

const DEFAULT_PORT = 3001;
const DEFAULT_AI_SERVICE_URL = "http://localhost:8001";
const DEFAULT_CORS_ORIGIN = "http://localhost:3000";

/** Default allowed origins for development (single origin). */
export const DEV_CORS_ORIGIN = process.env.CORS_ORIGIN || DEFAULT_CORS_ORIGIN;

/** Whitelisted production origins (must use HTTPS in production). */
export const PROD_CORS_ORIGINS = [
  "https://app.abode-ai.local",
  "https://kimi-abode.local",
].map(o => o.replace("//", "//")) || [];

export const config = {
  port: parseInt(process.env.PORT || DEFAULT_PORT.toString(), 10),
  aiServiceUrl: process.env.AI_SERVICE_URL || DEFAULT_AI_SERVICE_URL,
  databaseUrl: process.env.DATABASE_URL,
  /** Use whitelisted origins in production, single origin otherwise. */
  corsOrigin: 
    (process.env.NODE_ENV === "production" && PROD_CORS_ORIGINS.length > 0)
      ? PROD_CORS_ORIGINS.join(", ")
      : DEV_CORS_ORIGIN,
  nodeEnv: (process.env.NODE_ENV as "development" | "production" | "test") || "development",
};

/** Validate configuration at application startup. */
export function validateConfig(): void {
  // AI_SERVICE_URL and JWT_SECRET are required in production
  if (process.env.NODE_ENV === "production") {
    const required: Record<string, string> = {};
    if (!process.env.AI_SERVICE_URL) required.AI_SERVICE_URL = "AI_SERVICE_URL";
    if (!process.env.JWT_SECRET) required.JWT_SECRET = "JWT_SECRET";
    
    if (Object.keys(required).length > 0) {
      const names = Object.values(required).join(", ");
      throw new Error(`Missing required environment variables: ${names}`);
    }
  }

  // Validate database URL format when provided
  if (process.env.DATABASE_URL) {
    const dbUrl = process.env.DATABASE_URL;
    if (!/^postgres(:\/\/)?/.test(dbUrl)) {
      console.warn(
        `WARNING: DATABASE_URL may have unexpected format. ` +
        `Expected: postgres://... Found: ${dbUrl}`
      );
    }
  }

  // Warn in development about missing database URL
  if (process.env.NODE_ENV === "development" && !process.env.DATABASE_URL) {
    console.warn(
      "WARNING: DATABASE_URL not set. Using mock data store for development only."
    );
  }

  // Validate JWT_SECRET minimum length in production
  if (process.env.NODE_ENV === "production" && process.env.JWT_SECRET) {
    if (process.env.JWT_SECRET.length < 32) {
      throw new Error(
        "JWT_SECRET must be at least 32 characters long for security"
      );
    }
  }
}