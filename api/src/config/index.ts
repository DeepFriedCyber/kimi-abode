/**
 * Configuration module for the API server.
 * Validates and loads environment variables at startup.
 */

export const config = {
  port: parseInt(process.env.PORT || "3001", 10),
  aiServiceUrl: process.env.AI_SERVICE_URL || "http://localhost:8001",
  databaseUrl: process.env.DATABASE_URL,
  corsOrigin: process.env.CORS_ORIGIN || "http://localhost:3000",
  nodeEnv: (process.env.NODE_ENV as "development" | "production" | "test") || "development",
};

export function validateConfig(): void {
  if (!process.env.AI_SERVICE_URL) {
    throw new Error("AI_SERVICE_URL is required");
  }
  if (!process.env.JWT_SECRET) {
    throw new Error("JWT_SECRET is required");
  }
}
