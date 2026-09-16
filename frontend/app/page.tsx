"use client";

import { useState } from "react";
import SearchBox from "../components/SearchBox";
import FilterChips from "../components/FilterChips";
import ResultsList from "../components/ResultsList";
import type { Property } from "../lib/types";

export default function Home() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Property[]>([]);
  const [loading, setLoading] = useState(false);
  const [filters, setFilters] = useState({
    minBeds: undefined as number | undefined,
    maxPrice: undefined as number | undefined,
    propertyType: "" as string,
  });

  const handleSearch = async (searchQuery: string) => {
    setLoading(true);
    setQuery(searchQuery);
    try {
      const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://localhost:3001";
      const res = await fetch(`${apiBase}/api/parse`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: searchQuery }),
      });

      if (res.ok) {
        // Parse was successful — now do a real search
        const searchRes = await fetch(
          `${apiBase}/api/search?q=${encodeURIComponent(searchQuery)}`
        );
        if (searchRes.ok) {
          const data = await searchRes.json();
          setResults((data.properties ?? []) as Property[]);
        } else {
          setResults([]);
        }
      }
    } catch (err) {
      console.error("Search failed:", err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-8">
      {/* Hero / Search */}
      <section className="text-center py-12 px-4 bg-gradient-to-b from-blue-50 to-transparent rounded-2xl">
        <h1 className="text-4xl font-bold mb-3">Find your next home in the UK</h1>
        <p className="text-gray-600 mb-8 max-w-xl mx-auto">
          Describe what you&apos;re looking for in plain English. Our AI understands property types, locations, prices, and more.
        </p>
        <div className="max-w-2xl mx-auto">
          <SearchBox onSubmit={handleSearch} />
        </div>
      </section>

      {/* Filters */}
      {query && (
        <section className="flex justify-center">
          <FilterChips
            filters={{...filters}}
            onChange={(f) => setFilters({...filters, ...f})}
          />
        </section>
      )}

      {/* Results */}
      {loading && (
        <div className="text-center py-8 text-gray-500">
          <p className="animate-pulse">Searching properties...</p>
        </div>
      )}

      {!loading && results.length > 0 && (
        <section>
          <h2 className="text-xl font-semibold mb-4">
            {results.length} property{results.length !== 1 ? "s" : ""} found
          </h2>
          <ResultsList properties={results} />
        </section>
      )}

      {!loading && query && results.length === 0 && (
        <div className="text-center py-12 text-gray-500">
          <p>No properties found matching your criteria.</p>
          <p className="text-sm mt-2">Try a different location or adjust your filters.</p>
        </div>
      )}

      {/* Landing state */}
      {!query && (
        <section className="grid grid-cols-1 md:grid-cols-3 gap-6 py-8 max-w-4xl mx-auto">
          <FeatureCard
            icon="🔍"
            title="Semantic Search"
            desc="Describe what you want in plain English. We understand property types, locations, and budgets."
          />
          <FeatureCard
            icon="💬"
            title="AI Chat Assistant"
            desc="Ask about stamp duty, mortgages, local amenities, and more — powered by AI with 70% API cost savings."
          />
          <FeatureCard
            icon="📍"
            title="Local Intelligence"
            desc="See nearby schools, transport, shops, and parks scored by proximity to each property."
          />
        </section>
      )}
    </div>
  );
}

function FeatureCard({ icon, title, desc }: { icon: string; title: string; desc: string }) {
  return (
    <div className="bg-white rounded-xl p-6 shadow-sm border">
      <div className="text-3xl mb-3">{icon}</div>
      <h3 className="font-semibold mb-1">{title}</h3>
      <p className="text-sm text-gray-600">{desc}</p>
    </div>
  );
}
