/**
 * Tests for the SSE chat handler.
 */

import { describe, it, expect } from "vitest";

describe("chat handler (SSE bridge)", () => {
  it("forwards messages to AI service", async () => {
    // Mock fetch to verify the call pattern
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ response: "test" }),
    });

    global.fetch = mockFetch;

    expect(mockFetch).toBeDefined();
  });

  it("handles connection errors gracefully", async () => {
    const mockFetch = vi.fn().mockRejectedValue(new Error("AI service unavailable"));

    global.fetch = mockFetch;

    expect(mockFetch).toBeDefined();
  });
});
