/**
 * Password hashing and policy tests.
 */

import { describe, expect, it } from "vitest";
import {
  hashPassword,
  validatePassword,
  verifyPassword,
} from "../src/services/passwords";

describe("passwords", () => {
  it("hashes and verifies a password", async () => {
    const hash = await hashPassword("correct horse battery staple");
    expect(hash).toMatch(/^\$2[aby]\$12\$/);

    await expect(verifyPassword("correct horse battery staple", hash)).resolves.toBe(true);
    await expect(verifyPassword("wrong password entirely", hash)).resolves.toBe(false);
  });

  it("returns false for a malformed hash instead of throwing", async () => {
    await expect(verifyPassword("anything", "not-a-hash")).resolves.toBe(false);
  });

  it("rejects passwords shorter than 12 characters", () => {
    const result = validatePassword("short1234");
    expect(result.valid).toBe(false);
    expect(result.message).toMatch(/at least 12/);
  });

  it("allows long passphrases without composition rules", () => {
    expect(validatePassword("this is a long passphrase").valid).toBe(true);
  });

  it("rejects common passwords", () => {
    expect(validatePassword("password123").valid).toBe(false);
  });

  it("rejects passwords containing the user's email local part", () => {
    const result = validatePassword("alice-in-wonderland", { email: "alice@example.com" });
    expect(result.valid).toBe(false);
  });

  it("enforces the bcrypt 72-byte limit", () => {
    const result = validatePassword("a".repeat(73));
    expect(result.valid).toBe(false);
    expect(result.message).toMatch(/at most 72/);
  });
});
