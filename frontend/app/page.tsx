"use client";

/**
 * Home page — natural-language search with inline results.
 */

import Link from "next/link";
import { useState } from "react";
import PropertyCard from "../components/PropertyCard";
import { ApiError, searchProperties } from "../lib/api";
import type { SearchResult } from "../lib/types";

const EXAMPLE_QUERIES = [
  "3 bed detached in Sandbach under £350k",
  "semi-detached with a garden",
  "2 bed flat under £150k",
  "bungalow in Crewe",
  "4 bed family home near a school",
];

export default function Home() {
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<SearchResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const runSearch = async (searchQuery: string) => {
    const trimmed = searchQuery.trim();
    if (!trimmed) return;

    setLoading(true);
    setError(null);

    try {
      setResult(await searchProperties(trimmed));
    } catch (err) {
      setResult(null);
      setError(
        err instanceof ApiError
          ? err.message
          : "Search failed. Is the API running on port 3001?",
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-10">
      <section className="text-center space-y-4">
        <h1 className="text-4xl font-bold text-gray-900">
          Find a home by describing it
        </h1>
        <p className="text-lg text-gray-600 max-w-2xl mx-auto">
          Search sold prices and property characteristics in plain English — then
          dig into the area around each result.
        </p>
      </section>

      <form
        onSubmit={(event) => {
          event.preventDefault();
          void runSearch(query);
        }}
        className="max-w-3xl mx-auto"
      >
        <div className="bg-white rounded-xl shadow-lg p-6 border border-gray-200">
          <label htmlFor="query" className="sr-only">
            Search query
          </label>
          <input
            id="query"
            type="text"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="e.g. 3 bed semi in Sandbach under £250k"
            maxLength={500}
            className="w-full px-4 py-3 text-lg border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:outline-none"
            disabled={loading}
          />
          <button
            type="submit"
            disabled={loading || !query.trim()}
            className="mt-4 w-full sm:w-auto px-6 py-3 bg-blue-600 text-white font-semibold rounded-lg hover:bg-blue-700 disabled:opacity-50"
          >
            {loading ? "Searching…" : "Search properties"}
          </button>
        </div>

        {error && (
          <div
            role="alert"
            className="mt-4 p-4 bg-red-50 border border-red-200 rounded-lg text-red-800"
          >
            {error}
          </div>
        )}
      </form>

      {!result && !loading && (
        <section className="max-w-3xl mx-auto">
          <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3 text-center">
            Try one of these
          </h2>
          <div className="flex flex-wrap gap-2 justify-center">
            {EXAMPLE_QUERIES.map((example) => (
              <button
                key={example}
                type="button"
                onClick={() => {
                  setQuery(example);
                  void runSearch(example);
                }}
                className="px-3 py-1.5 bg-indigo-50 text-indigo-700 rounded-full text-sm hover:bg-indigo-100"
              >
                {example}
              </button>
            ))}
          </div>
        </section>
      )}

      {result && (
        <section className="space-y-4">
          <div className="flex flex-wrap items-center gap-3">
            <h2 className="text-xl font-semibold text-gray-900">
              {result.total_matches} {result.total_matches === 1 ? "result" : "results"}
            </h2>
            <span className="px-2 py-1 bg-green-100 text-green-800 rounded-full text-xs font-medium">
              {result.tier_used}
            </span>
            {result.message && (
              <span className="text-sm text-gray-500">{result.message}</span>
            )}
          </div>

          {result.properties.length === 0 ? (
            <div className="text-center py-12 text-gray-500 bg-white rounded-xl border">
              No matches. Try removing a filter or describing a wider area.
            </div>
          ) : (
            <div className="property-grid">
              {result.properties.map((property) => (
                <PropertyCard key={property.id} property={property} />
              ))}
            </div>
          )}

          <div className="text-center pt-2">
            <Link
              href={`/search?q=${encodeURIComponent(query)}`}
              className="text-sm text-blue-600 hover:underline"
            >
              Open in advanced search →
            </Link>
          </div>
        </section>
      )}
    </div>
  );
}
