"use client";

/**
 * Agent listings — uploaded inventory plus a photo manager per listing.
 */

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ApiError, mediaUrl } from "../../../lib/api";
import { effectivePrice, formatPrice, formatStatus } from "../../../lib/format";
import {
  deleteListingPhoto,
  listListings,
  setListingCover,
  uploadListingPhotos,
  type ListingPage,
} from "../../../lib/listings-api";
import type { Photo, Property } from "../../../lib/types";

export default function AgentListingsPage() {
  const [apiKey, setApiKey] = useState("");
  const [agentId, setAgentId] = useState("");
  const [page, setPage] = useState<ListingPage | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<number | null>(null);

  const fetchListings = useCallback(async (key: string, agent: string) => {
    setLoading(true);
    setError(null);
    try {
      setPage(
        await listListings({
          apiKey: key || undefined,
          agentId: agent || undefined,
          limit: 100,
        }),
      );
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load listings");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const key = sessionStorage.getItem("abode.apiKey") ?? "";
    const agent = sessionStorage.getItem("abode.agentId") ?? "";
    setApiKey(key);
    setAgentId(agent);
    void fetchListings(key, agent);
  }, [fetchListings]);

  const updatePhotos = (listingId: number, photos: Photo[]) => {
    setPage((current) =>
      current
        ? {
            ...current,
            listings: current.listings.map((listing) =>
              listing.id === listingId ? { ...listing, photos } : listing,
            ),
          }
        : current,
    );
  };

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <header className="space-y-2">
        <h1 className="text-2xl font-bold">My listings</h1>
        <p className="text-gray-600">
          Everything you have imported, with photos. Listings without a photo show
          your latest upload here first.
        </p>
        <Link href="/agent/import" className="text-sm text-blue-600 hover:underline">
          Import more listings →
        </Link>
      </header>

      <section className="bg-white border rounded-xl p-4 space-y-3">
        <div className="grid sm:grid-cols-2 gap-3">
          <label className="text-sm">
            <span className="block text-gray-600 mb-1">API key</span>
            <input
              type="password"
              value={apiKey}
              onChange={(event) => {
                setApiKey(event.target.value);
                if (event.target.value) sessionStorage.setItem("abode.apiKey", event.target.value);
                else sessionStorage.removeItem("abode.apiKey");
              }}
              className="w-full border rounded-lg px-3 py-2"
              autoComplete="off"
            />
          </label>
          <label className="text-sm">
            <span className="block text-gray-600 mb-1">Agent / branch id</span>
            <input
              type="text"
              value={agentId}
              onChange={(event) => {
                setAgentId(event.target.value);
                if (event.target.value) sessionStorage.setItem("abode.agentId", event.target.value);
                else sessionStorage.removeItem("abode.agentId");
              }}
              className="w-full border rounded-lg px-3 py-2"
            />
          </label>
        </div>
        <button
          type="button"
          onClick={() => void fetchListings(apiKey, agentId)}
          disabled={loading}
          className="px-4 py-2 bg-gray-900 text-white rounded-lg text-sm hover:bg-gray-800 disabled:opacity-50"
        >
          {loading ? "Loading…" : "Refresh"}
        </button>
      </section>

      {error && (
        <div role="alert" className="p-4 bg-red-50 border border-red-200 rounded-lg text-red-800">
          {error}
        </div>
      )}

      {page && (
        <section className="bg-white border rounded-xl overflow-hidden">
          <div className="px-4 py-3 border-b text-sm text-gray-600">
            {page.total} {page.total === 1 ? "listing" : "listings"}
          </div>

          {page.listings.length === 0 ? (
            <div className="p-8 text-center text-gray-500">
              Nothing here yet.{" "}
              <Link href="/agent/import" className="text-blue-600 underline">
                Import listings
              </Link>
              .
            </div>
          ) : (
            <ul className="divide-y">
              {page.listings.map((listing) => (
                <li key={listing.id}>
                  <div className="flex items-center gap-3 p-3">
                    <ListingThumb listing={listing} />
                    <div className="min-w-0 flex-1">
                      <p className="font-medium truncate">{listing.address_line1}</p>
                      <p className="text-xs text-gray-500">
                        {[listing.town, listing.postcode].filter(Boolean).join(", ") ||
                          "No location"}{" "}
                        · {(listing.photos ?? []).length} photo
                        {(listing.photos ?? []).length === 1 ? "" : "s"}
                      </p>
                    </div>
                    <div className="text-right">
                      <p className="font-semibold text-green-700">
                        {formatPrice(effectivePrice(listing))}
                      </p>
                      <p className="text-xs text-gray-500 capitalize">
                        {formatStatus(listing.listing_status ?? "sold")}
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() =>
                        setExpanded((current) => (current === listing.id ? null : listing.id))
                      }
                      className="px-3 py-1.5 text-sm border rounded-lg hover:border-gray-400"
                      aria-expanded={expanded === listing.id}
                    >
                      {expanded === listing.id ? "Close" : "Photos"}
                    </button>
                  </div>

                  {expanded === listing.id && (
                    <PhotoManager
                      listing={listing}
                      apiKey={apiKey}
                      agentId={agentId}
                      onPhotos={(photos) => updatePhotos(listing.id, photos)}
                    />
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </div>
  );
}

function ListingThumb({ listing }: { listing: Property }) {
  const cover = listing.photos?.find((photo) => photo.is_cover) ?? listing.photos?.[0];
  const url = cover ? mediaUrl(cover.thumb_url) : null;

  return (
    <div className="w-16 h-12 rounded overflow-hidden bg-gray-100 shrink-0 flex items-center justify-center">
      {url ? (
        <img src={url} alt="" className="w-full h-full object-cover" loading="lazy" />
      ) : (
        <span className="text-gray-400 text-lg" aria-hidden>
          🏠
        </span>
      )}
    </div>
  );
}

interface PhotoManagerProps {
  listing: Property;
  apiKey: string;
  agentId: string;
  onPhotos: (photos: Photo[]) => void;
}

function PhotoManager({ listing, apiKey, agentId, onPhotos }: PhotoManagerProps) {
  const [files, setFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const photos = listing.photos ?? [];

  const credentials = { apiKey: apiKey || undefined, agentId: agentId || undefined };

  const upload = async () => {
    if (files.length === 0) return;
    setBusy(true);
    setError(null);
    try {
      const result = await uploadListingPhotos(listing.id, files, {
        ...credentials,
        cover: photos.length === 0,
      });
      onPhotos(result.photos);
      setFiles([]);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  };

  const remove = async (photoId: string) => {
    if (!window.confirm("Remove this photo?")) return;
    setBusy(true);
    setError(null);
    try {
      const result = await deleteListingPhoto(listing.id, photoId, credentials);
      onPhotos(result.photos);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not remove photo");
    } finally {
      setBusy(false);
    }
  };

  const makeCover = async (photoId: string) => {
    setBusy(true);
    setError(null);
    try {
      const result = await setListingCover(listing.id, photoId, credentials);
      onPhotos(result.photos);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not set cover");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="bg-gray-50 border-t p-4 space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center gap-3">
        <label className="text-sm">
          <span className="sr-only">Choose photos</span>
          <input
            type="file"
            accept="image/jpeg,image/png,image/webp,image/heic,image/heif,.heic,.heif"
            multiple
            onChange={(event) => setFiles(Array.from(event.target.files ?? []))}
            className="block text-sm"
          />
        </label>
        <button
          type="button"
          onClick={() => void upload()}
          disabled={busy || files.length === 0}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700 disabled:opacity-50"
        >
          {busy ? "Working…" : `Upload${files.length ? ` (${files.length})` : ""}`}
        </button>
        <span className="text-xs text-gray-500">
          JPEG/PNG/WebP · max 10 per upload · 12 MB each · EXIF/GPS removed
        </span>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      {photos.length === 0 ? (
        <p className="text-sm text-gray-500">No photos yet.</p>
      ) : (
        <ul className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {photos.map((photo) => {
            const thumb = mediaUrl(photo.thumb_url);
            return (
              <li key={photo.id} className="bg-white border rounded-lg overflow-hidden">
                <div className="relative h-28 bg-gray-100">
                  {thumb && (
                    <img
                      src={thumb}
                      alt=""
                      className="w-full h-full object-cover"
                      loading="lazy"
                    />
                  )}
                  {photo.is_cover && (
                    <span className="absolute top-1 left-1 px-1.5 py-0.5 bg-blue-600 text-white text-[10px] rounded">
                      Cover
                    </span>
                  )}
                </div>
                <div className="p-2 flex flex-col gap-1 text-xs">
                  <button
                    type="button"
                    onClick={() => void makeCover(photo.id)}
                    disabled={busy || photo.is_cover}
                    className="text-blue-600 hover:underline disabled:text-gray-400 disabled:no-underline text-left"
                  >
                    Make cover
                  </button>
                  <button
                    type="button"
                    onClick={() => void remove(photo.id)}
                    disabled={busy}
                    className="text-red-600 hover:underline disabled:text-gray-400 text-left"
                  >
                    Remove
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
