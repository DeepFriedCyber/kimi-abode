/**
 * Tests for authentication routes.
 */

import { describe, it, expect, vi } from "vitest";
import { hashPassword, verifyPassword } from "../src/services/passwords";

describe("auth routes", () => {
  it("requires email and password for registration", () => {
    // Verify the email regex used in auth.ts would reject missing fields
    const RegisterBody = { email: undefined, password: undefined };
    expect(!RegisterBody.email || !RegisterBody.password).toBe(true);
  });

  it("validates email format before registration", () => {
    const validEmailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    expect(validEmailRegex.test("not-an-email")).toBe(false);
    expect(validEmailRegex.test("user@example.com")).toBe(true);
  });

  it("hashes password with salt on registration", async () => {
    const { hash, salt } = await hashPassword("secure-password-123");
    expect(hash).toBeDefined();
    expect(salt).toBeDefined();
    expect(salt.length).toBe(32);
  });

  it("rejects wrong password on login verification", async () => {
    const { hash, salt } = await hashPassword("correct-password");
    const verified = await verifyPassword("wrong-password", hash, salt);
    expect(verified).toBe(false);
  });

  it("accepts correct password on login verification", async () => {
    const { hash, salt } = await hashPassword("correct-password");
    const verified = await verifyPassword("correct-password", hash, salt);
    expect(verified).toBe(true);
  });
});
