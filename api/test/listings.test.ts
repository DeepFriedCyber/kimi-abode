/**
 * Gateway tests for the listing upload proxy.
 */

import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import type { FastifyInstance } from "fastify";
import { buildApp } from "../src/app";

const BOUNDARY = "----abode-test-boundary";
const MULTIPART_BODY = [
  `--${BOUNDARY}`,
  'Content-Disposition: form-data; name="dry_run"',
  "",
  "true",
  `--${BOUNDARY}`,
  'Content-Disposition: form-data; name="file"; filename="listings.csv"',
  "Content-Type: text/csv",
  "",
  "Address,Price",
  "1 Test Road,200000",
  `--${BOUNDARY}--`,
  "",
].join("\r\n");

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("listing upload routes", () => {
  let app: FastifyInstance;
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeAll(async () => {
    app = await buildApp();
    await app.ready();
  });

  afterAll(async () => {
    await app.close();
  });

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("forwards multipart uploads with agent credentials", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ dry_run: true, received: 1, valid: 1, imported: 0 }),
    );

    const response = await app.inject({
      method: "POST",
      url: "/api/listings/import",
      headers: {
        "content-type": `multipart/form-data; boundary=${BOUNDARY}`,
        "x-api-key": "agent-key",
        "x-agent-id": "acme",
      },
      payload: MULTIPART_BODY,
    });

    expect(response.statusCode).toBe(200);
    expect(response.json().valid).toBe(1);

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(new URL(url).pathname).toBe("/listings/import");
    const headers = init.headers as Record<string, string>;
    expect(headers["x-api-key"]).toBe("agent-key");
    expect(headers["x-agent-id"]).toBe("acme");
    expect(headers["Content-Type"]).toContain("multipart/form-data");
  });

  it("rejects non-multipart uploads", async () => {
    const response = await app.inject({
      method: "POST",
      url: "/api/listings/import",
      payload: { file: "nope" },
    });

    expect(response.statusCode).toBe(415);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("forwards a single listing to the canonical endpoint", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ imported: 1 }));

    const response = await app.inject({
      method: "POST",
      url: "/api/listings",
      payload: { address: "1 Test Road", price: 200000 },
    });

    expect(response.statusCode).toBe(200);
    const [url] = fetchMock.mock.calls[0] as [string];
    expect(new URL(url).pathname).toBe("/listings/");
  });

  it("forwards pasted text", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ valid: 1 }));

    const response = await app.inject({
      method: "POST",
      url: "/api/listings/import/text",
      payload: { text: "3 bed semi in Sandbach, CW11 1JD, £300,000" },
    });

    expect(response.statusCode).toBe(200);
    const [url] = fetchMock.mock.calls[0] as [string];
    expect(new URL(url).pathname).toBe("/listings/import/text");
  });

  it("relays the template as a binary download", async () => {
    fetchMock.mockResolvedValue(
      new Response(Buffer.from("Address,Town\n1 A,B\n"), {
        status: 200,
        headers: {
          "content-type": "text/csv; charset=utf-8",
          "content-disposition": 'attachment; filename="template.csv"',
        },
      }),
    );

    const response = await app.inject({
      method: "GET",
      url: "/api/listings/import/template?format=csv",
    });

    expect(response.statusCode).toBe(200);
    expect(response.headers["content-type"]).toContain("text/csv");
    expect(response.headers["content-disposition"]).toContain("template.csv");
    expect(response.body).toContain("Address,Town");
  });

  it("passes list pagination through", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ total: 0, listings: [] }));

    const response = await app.inject({
      method: "GET",
      url: "/api/listings?limit=10&offset=20&agent_id=acme",
    });

    expect(response.statusCode).toBe(200);
    const [url] = fetchMock.mock.calls[0] as [string];
    const parsed = new URL(url);
    expect(parsed.pathname).toBe("/listings/");
    expect(parsed.searchParams.get("limit")).toBe("10");
    expect(parsed.searchParams.get("offset")).toBe("20");
    expect(parsed.searchParams.get("agent_id")).toBe("acme");
  });

  it("validates the template format", async () => {
    const response = await app.inject({
      method: "GET",
      url: "/api/listings/import/template?format=pdf",
    });
    expect(response.statusCode).toBe(400);
  });

  it("forwards a photo batch to the listing", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ added: 1, total: 1, photos: [] }));

    const photoBody = [
      `--${BOUNDARY}`,
      'Content-Disposition: form-data; name="files"; filename="photo.jpg"',
      "Content-Type: image/jpeg",
      "",
      "binary-image-bytes",
      `--${BOUNDARY}--`,
      "",
    ].join("\r\n");

    const response = await app.inject({
      method: "POST",
      url: "/api/listings/42/photos",
      headers: {
        "content-type": `multipart/form-data; boundary=${BOUNDARY}`,
        "x-agent-id": "acme",
        "x-api-key": "agent-key",
      },
      payload: photoBody,
    });

    expect(response.statusCode).toBe(200);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(new URL(url).pathname).toBe("/listings/42/photos");
    const headers = init.headers as Record<string, string>;
    expect(headers["x-agent-id"]).toBe("acme");
    expect(headers["x-api-key"]).toBe("agent-key");
  });

  it("forwards photo deletion and cover changes", async () => {
    fetchMock.mockImplementation(async () => jsonResponse({ photos: [] }));

    const photoId = "0123456789abcdef";
    const deletion = await app.inject({
      method: "DELETE",
      url: `/api/listings/42/photos/${photoId}`,
      headers: { "x-agent-id": "acme" },
    });
    expect(deletion.statusCode).toBe(200);
    expect(new URL(fetchMock.mock.calls[0][0] as string).pathname).toBe(
      `/listings/42/photos/${photoId}`,
    );

    const cover = await app.inject({
      method: "POST",
      url: `/api/listings/42/photos/${photoId}/cover`,
      headers: { "x-agent-id": "acme" },
    });
    expect(cover.statusCode).toBe(200);
    expect(new URL(fetchMock.mock.calls[1][0] as string).pathname).toBe(
      `/listings/42/photos/${photoId}/cover`,
    );
  });

  it("rejects a malformed photo id", async () => {
    const response = await app.inject({
      method: "DELETE",
      url: "/api/listings/42/photos/not-a-hash",
    });
    expect(response.statusCode).toBe(400);
  });

  it("proxies media with cache headers intact", async () => {
    fetchMock.mockResolvedValue(
      new Response(Buffer.from("webp-bytes"), {
        status: 200,
        headers: {
          "content-type": "image/webp",
          "cache-control": "public, max-age=31536000, immutable",
        },
      }),
    );

    const response = await app.inject({
      method: "GET",
      url: "/api/media/listings/42/0123456789abcdef-display.webp",
    });

    expect(response.statusCode).toBe(200);
    expect(response.headers["content-type"]).toBe("image/webp");
    expect(response.headers["cache-control"]).toContain("immutable");
    expect(new URL(fetchMock.mock.calls[0][0] as string).pathname).toBe(
      "/media/listings/42/0123456789abcdef-display.webp",
    );
  });
});
