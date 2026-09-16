/**
 * Search page — dedicated results view with URL-based query parameters.
 */

"use client";

import { useSearchParams, useRouter } from "next/navigation";
import { Suspense, useEffect, useRef, useState, useCallback } from "react";
import SearchBox from "../../components/SearchBox";
import FilterChips from "../../components/FilterChips";
import ResultsList from "../../components/ResultsList";
import type { Property } from "../../lib/types";

export default function SearchPage() {
  return (
    <Suspense fallback={<div className="text-center py-8"><p>Loading search results...</p></div>}>
      <SearchPageContent />
    </Suspense>
  );
}

function SearchPageContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const [results, setResults] = useState<Property[]>([]);
  const [loading, setLoading] = useState(false);
  const [filters, setFilters] = useState({
    minBeds: undefined as number | undefined,
    maxPrice: undefined as number | undefined,
    propertyType: "" as string,
  });

  // Initialize from URL query param
  const initialQuery = searchParams.get("q") || "";
  const abortControllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (!initialQuery) return;
    performSearch(initialQuery);
  }, [initialQuery]);

  const performSearch = useCallback(async (query: string) => {
    // Cancel any in-flight request
    abortControllerRef.current?.abort();
    abortControllerRef.current = new AbortController();

    setLoading(true);
    try {
      const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://localhost:3001";
      const res = await fetch(`${apiBase}/api/search?q=${encodeURIComponent(query)}`, {
        signal: abortControllerRef.current.signal,
      });
      if (res.ok) {
        const data = await res.json();
        setResults((data.properties ?? []) as Property[]);
      }
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        console.error("Search failed:", err);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Property Search</h1>

      <SearchBox onSubmit={(q) => router.push(`/search?q=${encodeURIComponent(q)}`)} />

      {initialQuery && (
        <FilterChips filters={{...filters}} onChange={(f) => setFilters({...filters, ...f})} />
      )}

      {loading && (
        <div className="text-center py-8">
          <p className="animate-pulse text-gray-500">Searching...</p>
        </div>
      )}

      {!loading && results.length > 0 && (
        <>
          <p className="text-sm text-gray-600">{results.length} properties found</p>
          <ResultsList properties={results} />
        </>
      )}

      {!loading && initialQuery && results.length === 0 && (
        <div className="text-center py-12 text-gray-400">
          <p>No matches. Try adjusting your filters.</p>
        </div>
      )}
    </div>
  );
}
