/**
 * Password hashing, verification and policy.
 *
 * Policy follows NIST SP 800-63B: favour length and blocklist screening over
 * composition rules ("must contain a symbol"), which push users toward
 * predictable patterns. bcrypt silently truncates at 72 bytes, so that is the
 * enforced upper bound.
 */

import bcrypt from "bcryptjs";

const BCRYPT_COST = 12;
const MIN_LENGTH = 12;
const MAX_BYTES = 72; // bcrypt input limit

/**
 * A valid bcrypt hash used only to equalise timing when an account does not
 * exist (prevents user enumeration via response time).
 */
export const DUMMY_PASSWORD_HASH =
  "$2a$12$gIQ4d7QYZTPSBv6e3q3nSOs7qpPOBRF1VivSDECcPKFoSfgaPAEte";

// Small local blocklist. In production, prefer a breached-password service
// (HIBP k-anonymity) over a static list.
const COMMON_PASSWORDS = new Set([
  "password", "password1", "password123", "123456789012", "qwertyuiop",
  "letmein123", "welcome123", "admin1234567", "iloveyou123", "changeme123",
  "trustno1", "abc123456789", "monkey123456", "dragon123456",
]);

export async function hashPassword(password: string): Promise<string> {
  return bcrypt.hash(password, BCRYPT_COST);
}

export async function verifyPassword(
  password: string,
  passwordHash: string,
): Promise<boolean> {
  try {
    return await bcrypt.compare(password, passwordHash);
  } catch {
    // Malformed hash: treat as a failed login rather than a 500.
    return false;
  }
}

/** Kept for backwards compatibility with earlier call sites. */
export const comparePassword = verifyPassword;

export interface PasswordValidation {
  valid: boolean;
  message?: string;
}

/**
 * Validate a candidate password.
 *
 * @param password - plaintext candidate
 * @param context  - optional user-supplied values (email, name) that must not
 *                   be contained in the password
 */
export function validatePassword(
  password: string,
  context: { email?: string; name?: string } = {},
): PasswordValidation {
  if (typeof password !== "string" || password.length < MIN_LENGTH) {
    return {
      valid: false,
      message: `Password must be at least ${MIN_LENGTH} characters.`,
    };
  }

  if (password.length > MAX_BYTES || Buffer.byteLength(password, "utf8") > MAX_BYTES) {
    return {
      valid: false,
      message: `Password must be at most ${MAX_BYTES} bytes.`,
    };
  }

  const normalised = password.trim().toLowerCase();

  if (COMMON_PASSWORDS.has(normalised)) {
    return {
      valid: false,
      message: "Password is too common. Choose something less predictable.",
    };
  }

  const localPart = context.email?.split("@")[0]?.toLowerCase();
  if (localPart && localPart.length >= 3 && containsToken(normalised, localPart)) {
    return {
      valid: false,
      message: "Password must not contain your email address.",
    };
  }

  if (context.name) {
    const name = context.name.trim().toLowerCase();
    if (name.length >= 4 && containsToken(normalised, name)) {
      return {
        valid: false,
        message: "Password must not contain your name.",
      };
    }
  }

  return { valid: true };
}

/**
 * Whole-token containment check. Avoids false positives such as a user named
 * "Test" being rejected for the password "…for testing".
 */
function containsToken(haystack: string, needle: string): boolean {
  const escaped = needle.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`(^|[^a-z0-9])${escaped}([^a-z0-9]|$)`, "i").test(haystack);
}
