/**
 * Shared upstream helpers for proxying to the Python AI service.
 *
 * Failures are a discriminated union rather than a thrown Response, because a
 * Response also has a numeric `status` (a previous type guard confused them).
 */

import type { FastifyReply, FastifyRequest } from "fastify";
import { config } from "../config";

export type FailureReason = "timeout" | "unavailable" | "bad_response" | "not_ready";

export interface UpstreamFailure {
  reason: FailureReason;
}

export type UpstreamResult =
  | { ok: true; response: Response }
  | { ok: false; failure: UpstreamFailure };

const FAILURE_MESSAGES: Record<FailureReason, string> = {
  timeout: "The AI service timed out. Please try again.",
  unavailable: "The AI service is currently unavailable.",
  bad_response: "The AI service returned an invalid response.",
  not_ready: "The property service is not configured yet.",
};

export function fail(reply: FastifyReply, request: FastifyRequest, failure: UpstreamFailure) {
  const statusCode =
    failure.reason === "timeout" ? 504 : failure.reason === "not_ready" ? 503 : 502;
  return reply.code(statusCode).send({
    error: FAILURE_MESSAGES[failure.reason],
    correlation_id: request.id,
  });
}

export async function callUpstream(
  request: FastifyRequest,
  url: string,
  init: RequestInit = {},
  timeoutMs: number = config.upstreamTimeoutMs,
): Promise<UpstreamResult> {
  try {
    const response = await fetch(url, {
      ...init,
      signal: AbortSignal.timeout(timeoutMs),
      headers: { Accept: "application/json", ...(init.headers ?? {}) },
    });
    return { ok: true, response };
  } catch (error) {
    const name = error instanceof Error ? error.name : "";
    if (name === "TimeoutError" || name === "AbortError") {
      request.log.warn({ url }, "AI service request timed out");
      return { ok: false, failure: { reason: "timeout" } };
    }
    request.log.warn({ err: error, url }, "AI service request failed");
    return { ok: false, failure: { reason: "unavailable" } };
  }
}

export async function readJson(response: Response): Promise<unknown | null> {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

/** Forward a JSON request and relay the payload, or a normalised failure. */
export async function forwardJson(
  request: FastifyRequest,
  reply: FastifyReply,
  url: string,
  init: RequestInit = {},
  timeoutMs?: number,
) {
  const result = await callUpstream(request, url, init, timeoutMs);
  if (!result.ok) return fail(reply, request, result.failure);

  const { response } = result;
  const data = await readJson(response);

  if (!response.ok || data === null) {
    request.log.warn(
      { status: response.status, url },
      "AI service returned an error or invalid JSON",
    );
    return fail(reply, request, {
      reason:
        response.status === 503
          ? "not_ready"
          : response.ok
            ? "bad_response"
            : "unavailable",
    });
  }

  return reply.send(data);
}

/** Relay a binary response (e.g. an XLSX template) without parsing it. */
export async function forwardBinary(
  request: FastifyRequest,
  reply: FastifyReply,
  url: string,
  init: RequestInit = {},
) {
  const result = await callUpstream(request, url, init);
  if (!result.ok) return fail(reply, request, result.failure);

  const { response } = result;
  if (!response.ok) {
    return fail(reply, request, { reason: response.status === 503 ? "not_ready" : "unavailable" });
  }

  const buffer = Buffer.from(await response.arrayBuffer());
  const contentType = response.headers.get("content-type");
  const disposition = response.headers.get("content-disposition");
  if (contentType) reply.header("content-type", contentType);
  if (disposition) reply.header("content-disposition", disposition);
  const cacheControl = response.headers.get("cache-control");
  const etag = response.headers.get("etag");
  if (cacheControl) reply.header("cache-control", cacheControl);
  if (etag) reply.header("etag", etag);
  return reply.send(buffer);
}
