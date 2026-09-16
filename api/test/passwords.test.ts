/**
 * Tests for password hashing utilities.
 */

import { describe, it, expect } from "vitest";
import { hashPassword, verifyPassword, generateToken } from "../src/services/passwords";

describe("passwords", () => {
  it("hashes and verifies a password", async () => {
    const { hash, salt } = await hashPassword("test-password-123");
    expect(hash).toBeDefined();
    expect(salt).toBeDefined();
    expect(salt.length).toBe(32); // 16 bytes hex

    const verified = await verifyPassword("test-password-123", hash, salt);
    expect(verified).toBe(true);
  });

  it("rejects wrong password", async () => {
    const { hash, salt } = await hashPassword("correct-password");
    const verified = await verifyPassword("wrong-password", hash, salt);
    expect(verified).toBe(false);
  });

  it("generates a token of the correct length", () => {
    const token = generateToken(32);
    expect(token.length).toBe(64); // 32 bytes → 64 hex chars
  });
});
