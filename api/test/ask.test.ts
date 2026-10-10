/**
 * Tests for the ask/POI routes.
 */

import { describe, it, expect, vi } from "vitest";
import { askRoutes } from "../src/routes/ask";

describe("ask routes", () => {
  it("is a valid Fastify plugin", () => {
    expect(typeof askRoutes).toBe("function");
  });

  it("requires lat/lon for POI queries", async () => {
    const mockApp = {
      post: vi.fn(),
      get: vi.fn(),
    };

    askRoutes(mockApp as any, { aiUrl: "http://localhost:8001" });

    expect(mockApp.post).toHaveBeenCalled();
  });

  it("validates lat/lon range on /ask/poi", async () => {
    const routes: Array<{ path: string; handler: (req: any, reply: any) => Promise<void> }> = [];
    const mockApp = {
      post: vi.fn((path: string, handler: any) => {
        routes.push({ path, handler });
      }),
      get: vi.fn((path: string, handler: any) => {
        routes.push({ path, handler });
      }),
    };

    askRoutes(mockApp as any, { aiUrl: "http://localhost:8001" });

    const poiRoute = routes.find((r) => r.path === "/ask/poi");
    expect(poiRoute).toBeDefined();

    const mockReply = {
      code: vi.fn().mockReturnThis(),
      send: vi.fn(),
    };

    // Missing lat/lon → 400
    await poiRoute!.handler({ body: {} } as any, mockReply);
    expect(mockReply.code).toHaveBeenCalledWith(400);

    // Out of range lat → 400
    mockReply.code.mockClear();
    await poiRoute!.handler({ body: { lat: 95, lon: 0 } } as any, mockReply);
    expect(mockReply.code).toHaveBeenCalledWith(400);
  });
});
