/**
 * Agent listing import API — uploads, paste, templates and listing queries.
 */

import { API_BASE, request } from "./api";
import type { Photo, Property } from "./types";
export interface ImportIssue {
  row: number;
  message: string;
  field?: string;
}

export interface ImportReport {
  dry_run: boolean;
  format: string;
  encoding?: string | null;
  delimiter?: string | null;
  received: number;
  valid: number;
  invalid: number;
  duplicates: number;
  imported: number;
  geocoded: number;
  columns: Record<string, string>;
  confidence: Record<string, number>;
  unmapped_columns: string[];
  errors: ImportIssue[];
  warnings: ImportIssue[];
  preview: Property[];
  imported_ids?: number[];
  agent_id?: string;
  filename?: string;
}

export interface ImportOptions {
  dryRun: boolean;
  mapping?: Record<string, string>;
  source?: string;
  apiKey?: string;
  agentId?: string;
}

function agentHeaders(apiKey?: string, agentId?: string): Record<string, string> {
  const headers: Record<string, string> = {};
  if (apiKey) headers["x-api-key"] = apiKey;
  if (agentId) headers["x-agent-id"] = agentId;
  return headers;
}

/** Upload a listing file. `dryRun` previews without writing anything. */
export async function importListingsFile(
  file: File,
  options: ImportOptions,
): Promise<ImportReport> {
  const form = new FormData();
  form.append("file", file);
  form.append("dry_run", String(options.dryRun));
  if (options.mapping) form.append("mapping", JSON.stringify(options.mapping));
  if (options.source) form.append("source", options.source);

  return request<ImportReport>(
    "/api/listings/import",
    {
      method: "POST",
      body: form,
      headers: agentHeaders(options.apiKey, options.agentId),
    },
    60_000,
  );
}

/** Import a pasted email/description as a draft listing. */
export async function importListingText(
  text: string,
  options: ImportOptions,
): Promise<ImportReport> {
  return request<ImportReport>(
    "/api/listings/import/text",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...agentHeaders(options.apiKey, options.agentId),
      },
      body: JSON.stringify({ text, dry_run: options.dryRun }),
    },
    60_000,
  );
}

export interface ImportColumnCatalogue {
  canonical: string[];
  synonyms: Record<string, string[]>;
  required: string[];
  formats: string[];
}

export async function getImportColumns(): Promise<ImportColumnCatalogue> {
  return request<ImportColumnCatalogue>("/api/listings/import/columns");
}

export function importTemplateUrl(format: "csv" | "xlsx" = "csv"): string {
  return `${API_BASE}/api/listings/import/template?format=${format}`;
}

export interface ListingPage {
  total: number;
  limit: number;
  offset: number;
  listings: Property[];
}

export async function listListings(
  options: { limit?: number; offset?: number; agentId?: string; apiKey?: string } = {},
): Promise<ListingPage> {
  const params = new URLSearchParams({
    limit: String(options.limit ?? 50),
    offset: String(options.offset ?? 0),
  });
  if (options.agentId) params.set("agent_id", options.agentId);

  return request<ListingPage>(`/api/listings?${params.toString()}`, {
    headers: agentHeaders(options.apiKey, options.agentId),
  });
}

// ---- photos ----------------------------------------------------------------

export interface PhotoBatch {
  added: number;
  total: number;
  photos: Photo[];
}

/** Upload up to 10 photos in one request. Duplicates are ignored. */
export async function uploadListingPhotos(
  listingId: number,
  files: File[],
  options: { cover?: boolean; apiKey?: string; agentId?: string } = {},
): Promise<PhotoBatch> {
  const form = new FormData();
  for (const file of files) form.append("files", file);
  form.append("cover", String(Boolean(options.cover)));

  return request<PhotoBatch>(
    `/api/listings/${listingId}/photos`,
    {
      method: "POST",
      body: form,
      headers: agentHeaders(options.apiKey, options.agentId),
    },
    120_000,
  );
}

export async function deleteListingPhoto(
  listingId: number,
  photoId: string,
  options: { apiKey?: string; agentId?: string } = {},
): Promise<PhotoBatch> {
  return request<PhotoBatch>(`/api/listings/${listingId}/photos/${photoId}`, {
    method: "DELETE",
    headers: agentHeaders(options.apiKey, options.agentId),
  });
}

export async function setListingCover(
  listingId: number,
  photoId: string,
  options: { apiKey?: string; agentId?: string } = {},
): Promise<{ photos: Photo[] }> {
  return request<{ photos: Photo[] }>(
    `/api/listings/${listingId}/photos/${photoId}/cover`,
    {
      method: "POST",
      headers: agentHeaders(options.apiKey, options.agentId),
    },
  );
}
