/**
 * Search page — dedicated results view with URL-driven filters.
 *
 * The URL is the source of truth so results are shareable and the back button
 * behaves as expected.
 */

"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import SearchBox from "../../components/SearchBox";
import FilterChips from "../../components/FilterChips";
import ResultsList from "../../components/ResultsList";
import { ApiError, searchProperties } from "../../lib/api";
import type { Property } from "../../lib/types";

export default function SearchPage() {
  return (
    <Suspense
      fallback={
        <div className="text-center py-8">
          <p className="animate-pulse text-gray-500">Loading search…</p>
        </div>
      }
    >
      <SearchPageContent />
    </Suspense>
  );
}

interface Filters {
  minBeds?: number;
  maxPrice?: number;
  propertyType: string;
}

function parseNumber(value: string | null): number | undefined {
  if (!value) return undefined;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : undefined;
}

function SearchPageContent() {
  const searchParams = useSearchParams();
  const router = useRouter();

  const query = searchParams.get("q") ?? "";
  const minBeds = parseNumber(searchParams.get("min_beds"));
  const maxPrice = parseNumber(searchParams.get("max_price"));
  const propertyType = searchParams.get("type") ?? "";

  const [results, setResults] = useState<Property[]>([]);
  const [total, setTotal] = useState(0);
  const [tier, setTier] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!query) {
      setResults([]);
      setTotal(0);
      setError(null);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);

    searchProperties(query, {
      minBeds,
      maxPrice,
      propertyType: propertyType || undefined,
      limit: 50,
    })
      .then((data) => {
        if (cancelled) return;
        setResults(data.properties ?? []);
        setTotal(data.total_matches ?? data.properties?.length ?? 0);
        setTier(data.tier_used ?? "");
      })
      .catch((err) => {
        if (cancelled) return;
        setResults([]);
        setTotal(0);
        setError(
          err instanceof ApiError
            ? err.message
            : "Search failed. Please try again.",
        );
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [query, minBeds, maxPrice, propertyType]);

  const updateFilters = (next: Filters) => {
    const params = new URLSearchParams(searchParams.toString());

    if (next.minBeds === undefined) params.delete("min_beds");
    else params.set("min_beds", String(next.minBeds));

    if (next.maxPrice === undefined) params.delete("max_price");
    else params.set("max_price", String(next.maxPrice));

    if (!next.propertyType) params.delete("type");
    else params.set("type", next.propertyType);

    router.replace(`/search?${params.toString()}`);
  };

  const filters: Filters = { minBeds, maxPrice, propertyType };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Property search</h1>

      <SearchBox
        initialValue={query}
        onSubmit={(value) => {
          const params = new URLSearchParams(searchParams.toString());
          params.set("q", value);
          router.push(`/search?${params.toString()}`);
        }}
      />

      <FilterChips filters={filters} onChange={updateFilters} />

      {error && (
        <div
          role="alert"
          className="p-4 bg-red-50 border border-red-200 rounded-lg text-red-800"
        >
          {error}
        </div>
      )}

      {loading && (
        <p className="text-center py-8 animate-pulse text-gray-500">Searching…</p>
      )}

      {!loading && !error && query && (
        <>
          <div className="flex items-center gap-3">
            <p className="text-sm text-gray-600">
              {total} {total === 1 ? "property" : "properties"} found
            </p>
            {tier && (
              <span className="px-2 py-0.5 bg-green-100 text-green-800 rounded-full text-xs">
                {tier}
              </span>
            )}
          </div>

          {results.length > 0 ? (
            <ResultsList properties={results} />
          ) : (
            <div className="text-center py-12 text-gray-400">
              <p>No matches. Try removing a filter or broadening the area.</p>
            </div>
          )}
        </>
      )}

      {!query && (
        <p className="text-center py-12 text-gray-500">
          Enter a query above, or try “3 bed detached in Sandbach”.
        </p>
      )}
    </div>
  );
}
