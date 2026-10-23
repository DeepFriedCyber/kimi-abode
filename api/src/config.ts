/**
 * Single source of truth for API configuration.
 *
 * Loads environment variables once, validates them, and exports a frozen,
 * typed object. Fails fast on missing/insecure settings in production instead
 * of silently falling back to a hard-coded secret.
 */

import { randomBytes } from "node:crypto";
import { fileURLToPath } from "node:url";
import { config as loadEnv } from "dotenv";

// Load service-local .env first, then the repo-root .env. dotenv keeps the
// first value it sees, so api/.env wins over shared defaults.
loadEnv({
  path: [
    fileURLToPath(new URL("../.env", import.meta.url)),
    fileURLToPath(new URL("../../.env", import.meta.url)),
  ],
});

const DEFAULT_PORT = 3001;
const DEFAULT_AI_SERVICE_URL = "http://localhost:8001";
const DEFAULT_CORS_ORIGINS = ["http://localhost:3000"];
const MIN_SECRET_LENGTH = 32;

export type NodeEnv = "development" | "production" | "test";

function parseNodeEnv(raw: string | undefined): NodeEnv {
  if (raw === "production" || raw === "test") return raw;
  return "development";
}

function parsePort(raw: string | undefined): number {
  const parsed = Number.parseInt(raw ?? "", 10);
  if (!Number.isInteger(parsed) || parsed < 1 || parsed > 65_535) {
    return DEFAULT_PORT;
  }
  return parsed;
}

function parseOrigins(raw: string | undefined): string[] {
  const origins = (raw ?? "")
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);

  if (origins.includes("*")) {
    // Wildcard + credentials is rejected by browsers and unsafe with cookies.
    if (process.env.NODE_ENV === "production") {
      throw new Error(
        "CORS_ORIGIN cannot be '*' — list explicit origins (comma separated).",
      );
    }
    console.warn("[Config] CORS_ORIGIN='*' is not allowed — falling back to localhost defaults.");
    return DEFAULT_CORS_ORIGINS;
  }

  return origins.length > 0 ? origins : DEFAULT_CORS_ORIGINS;
}

function resolveJwtSecret(nodeEnv: NodeEnv, raw: string | undefined): string {
  const secret = raw?.trim() ?? "";

  if (secret.length >= MIN_SECRET_LENGTH) {
    return secret;
  }

  if (nodeEnv === "production") {
    throw new Error(
      `JWT_SECRET must be set and at least ${MIN_SECRET_LENGTH} characters in production.`,
    );
  }

  // Dev/test: never ship a literal fallback. An ephemeral secret means tokens
  // are invalidated on restart, which is the correct trade-off for local work.
  console.warn(
    "[Config] JWT_SECRET missing or too short — using an ephemeral development secret.",
  );
  return randomBytes(48).toString("hex");
}

function normaliseUrl(url: string): string {
  return url.replace(/\/+$/, "");
}

const nodeEnv = parseNodeEnv(process.env.NODE_ENV);

export const config = Object.freeze({
  nodeEnv,
  isProduction: nodeEnv === "production",
  port: parsePort(process.env.PORT),
  host: process.env.HOST ?? "0.0.0.0",

  /** Base URL of the Python AI service (no trailing slash, no /api prefix). */
  aiServiceUrl: normaliseUrl(process.env.AI_SERVICE_URL ?? DEFAULT_AI_SERVICE_URL),

  corsOrigins: parseOrigins(process.env.CORS_ORIGIN),

  jwt: Object.freeze({
    secret: resolveJwtSecret(nodeEnv, process.env.JWT_SECRET),
    issuer: process.env.JWT_ISSUER ?? "abode-api",
    audience: process.env.JWT_AUDIENCE ?? "abode-frontend",
    expiresIn: process.env.JWT_EXPIRES_IN ?? "1h",
  }),

  /** Maximum accepted request body (bytes). */
  bodyLimit: Number.parseInt(process.env.BODY_LIMIT_BYTES ?? "1000000", 10),

  /** Upstream AI request timeout (ms). */
  upstreamTimeoutMs: Number.parseInt(process.env.UPSTREAM_TIMEOUT_MS ?? "10000", 10),

  /** Listing upload limits (multipart passthrough). */
  uploadLimitBytes: Number.parseInt(process.env.UPLOAD_LIMIT_BYTES ?? "8388608", 10),
  uploadTimeoutMs: Number.parseInt(process.env.UPLOAD_TIMEOUT_MS ?? "60000", 10),
  /** Photo batches are larger than listing files. */
  photoLimitBytes: Number.parseInt(process.env.PHOTO_LIMIT_BYTES ?? "41943040", 10),

  /**
   * Trust X-Forwarded-* headers. Only enable when the app is behind a proxy you
   * control — otherwise clients can spoof their IP and defeat rate limiting.
   */
  trustProxy: process.env.TRUST_PROXY === "true" || process.env.TRUST_PROXY === "1",

  /** Optional SQLite file. When unset the API uses the in-memory property store. */
  sqlitePath: process.env.SQLITE_PATH?.trim() || undefined,

  version: "1.0.0",
});

/** Validate config that can only be checked at runtime. Called during boot. */
export function validateConfig(): void {
  if (config.isProduction && !process.env.AI_SERVICE_URL) {
    throw new Error("AI_SERVICE_URL must be set in production.");
  }

  if (!Number.isInteger(config.bodyLimit) || config.bodyLimit < 1024) {
    throw new Error("BODY_LIMIT_BYTES must be an integer >= 1024.");
  }

  if (!Number.isInteger(config.upstreamTimeoutMs) || config.upstreamTimeoutMs < 100) {
    throw new Error("UPSTREAM_TIMEOUT_MS must be an integer >= 100.");
  }

  if (!Number.isInteger(config.uploadLimitBytes) || config.uploadLimitBytes < 1024) {
    throw new Error("UPLOAD_LIMIT_BYTES must be an integer >= 1024.");
  }

  if (!Number.isInteger(config.uploadTimeoutMs) || config.uploadTimeoutMs < 1_000) {
    throw new Error("UPLOAD_TIMEOUT_MS must be an integer >= 1000.");
  }

  if (!Number.isInteger(config.photoLimitBytes) || config.photoLimitBytes < 1_048_576) {
    throw new Error("PHOTO_LIMIT_BYTES must be an integer >= 1048576.");
  }

  if (config.isProduction && config.corsOrigins.some((o) => !o.startsWith("https://"))) {
    throw new Error("Production CORS origins must use https://.");
  }
}

export default config;
