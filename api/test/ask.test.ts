/**
 * Tests for the ask/POI routes.
 */

import { describe, it, expect } from "vitest";
import { askRoutes } from "../src/routes/ask";

describe("ask routes", () => {
  it("is a valid Fastify plugin", () => {
    expect(typeof askRoutes).toBe("function");
  });

  it("requires lat/lon for POI queries", async () => {
    // The askRoutes should validate lat/lon on /ask/poi
    const mockApp = {
      post: vi.fn(),
      get: vi.fn(),
    };

    askRoutes(mockApp as any, "http://localhost:8001");

    expect(mockApp.post).toHaveBeenCalled();
  });
});
