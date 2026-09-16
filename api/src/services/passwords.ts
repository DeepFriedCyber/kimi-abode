/**
 * Password hashing utilities — argon2 for production.
 */

import crypto from "crypto";


export async function hashPassword(password: string): Promise<{ hash: string; salt: string }> {
  const salt = crypto.randomBytes(16).toString("hex");

  try {
    const argon2 = await import("argon2");
    const hash = await argon2.default.hash(password, { salt: Buffer.from(salt, "hex") });
    return { hash, salt };
  } catch {
    throw new Error(
      "argon2 is required for password hashing. Install it via 'npm install argon2' " +
      "or set NODE_ENV=development and ensure argon2 is available."
    );
  }
}

export async function verifyPassword(
  password: string,
  hash: string,
  salt: string,
): Promise<boolean> {
  try {
    const argon2 = await import("argon2");
    return await argon2.default.verify(hash, password);
  } catch {
    throw new Error(
      "argon2 is required for password verification. Install it via 'npm install argon2'."
    );
  }
}

/** Generate a random token for password reset / API keys. */
export function generateToken(length: number = 32): string {
  return crypto.randomBytes(length).toString("hex");
}
