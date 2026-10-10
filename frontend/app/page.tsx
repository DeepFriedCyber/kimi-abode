"use client";

import { useState } from "react";

interface Property {
  id: number;
  address_line1: string;
  town: string;
  postcode: string;
  property_type: string;
  num_beds: number;
  price_paid: number;
  date_sold?: string;
}

interface SearchResult {
  properties: Property[];
  tier_used: string;
  total_matches: number;
  message: string;
}

export default function Home() {
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<SearchResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleSearch = async (searchQuery: string) => {
    if (!searchQuery.trim()) return;
    
    setLoading(true);
    setError(null);
    
    try {
      const response = await fetch("http://localhost:3001/api/search");
      
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      
      const data: SearchResult = await response.json();
      setResult(data);
    } catch (err: any) {
      setError(err.message || "Search failed");
    } finally {
      setLoading(false);
    }
  };

  const exampleQueries = [
    { text: "detached house", type: "button" as const },
    { text: "terraced property", type: "button" as const },
    { text: "flat apartment", type: "button" as const },
    { text: "3 bed under 300k", type: "button" as const },
    { text: "bungalow", type: "button" as const },
    { text: "detached 4 bed", type: "button" as const },
    { text: "semi detached 2 bed", type: "button" as const },
  ];

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-white to-indigo-50">
      {/* Header */}
      <header className="bg-white border-b shadow-sm sticky top-0 z-10">
        <div className="max-w-4xl mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="text-2xl">🏠</span>
            <h1 className="text-xl font-bold text-gray-900">Abode AI — Property Search Demo</h1>
          </div>
        </div>
      </header>

      {/* Hero */}
      <main className="max-w-4xl mx-auto px-4 py-12">
        <div className="text-center mb-12">
          <h2 className="text-4xl font-bold text-gray-900 mb-3">
            Search Sandbach Properties with Natural Language
          </h2>
          <p className="text-lg text-gray-600 max-w-2xl mx-auto">
            Try searching for properties like "detached house", "3 bed properties under £300k", or "flat in Sandbach"
          </p>
        </div>

        {/* Search Form */}
        <form onSubmit={(e) => { e.preventDefault(); handleSearch(query); }} className="mb-8">
          <div className="bg-white rounded-xl shadow-lg p-6 border border-gray-200">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="What are you looking for? (e.g., detached house 4 bed)"
              className="w-full px-4 py-3 text-lg border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
              disabled={loading}
            />
            <button
              type="submit"
              disabled={loading || !query.trim()}
              className="mt-4 px-6 py-3 bg-gradient-to-r from-blue-600 to-indigo-600 text-white font-semibold rounded-lg hover:from-blue-700 hover:to-indigo-700 disabled:opacity-50"
            >
              {loading ? "Searching..." : "Search Properties"}
            </button>
          </div>

          {/* Error */}
          {error && (
            <div className="mt-4 p-4 bg-red-50 border border-red-200 rounded-lg text-red-800">
              ⚠️ {error}
            </div>
          )}
        </form>

        {/* Results */}
        {result && (
          <div className="space-y-6 animate-fade-in">
            {/* Summary Card */}
            <div className="bg-white rounded-xl shadow-lg border border-gray-200 p-6">
              <h3 className="text-xl font-semibold text-gray-900 mb-2">Search Results</h3>
              <p className="text-gray-600">{result.message}</p>
              <div className="mt-4 flex gap-2">
                <span className="px-3 py-1 bg-blue-100 text-blue-800 rounded-full text-sm font-medium">
                  {result.total_matches} matches found
                </span>
                <span className="px-3 py-1 bg-green-100 text-green-800 rounded-full text-sm font-medium">
                  Using {result.tier_used} search
                </span>
              </div>
            </div>

            {/* Properties Grid */}
            <div className="grid md:grid-cols-2 gap-4">
              {result.properties.slice(0, 12).map((p) => (
                <div key={p.id} className="bg-white rounded-lg shadow-md border border-gray-200 p-5">
                  <h4 className="text-base font-semibold text-gray-900">{p.address_line1}</h4>
                  <p className="text-sm text-gray-600">{p.town}, {p.postcode}</p>
                  <div className="flex items-center justify-between mt-3 pt-3 border-t">
                    <span className="font-medium text-lg text-gray-900">£{p.price_paid.toLocaleString()}</span>
                    <span className="px-2 py-1 bg-gray-100 rounded text-xs capitalize">
                      {p.property_type.replace(/_/g, " ")}
                    </span>
                  </div>
                  {p.num_beds > 0 && (
                    <span className="text-sm text-gray-500 mt-2 block">{p.num_beds} bed{p.num_beds !== 1 ? "s" : ""}</span>
                  )}
                </div>
              ))}
            </div>

            {result.properties.length > 12 && (
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 text-center">
                <p className="text-blue-900 font-medium">
                  Showing first 12 of {result.properties.length} properties
                </p>
              </div>
            )}

            {/* Example queries */}
            <div className="bg-white rounded-xl shadow border p-6 mt-8">
              <h4 className="font-semibold text-gray-900 mb-3">Try these searches:</h4>
              <div className="flex flex-wrap gap-2">
                {exampleQueries.map((ex, idx) => (
                  <button
                    key={idx}
                    onClick={() => handleSearch(ex.text)}
                    className="px-3 py-1 bg-indigo-50 text-indigo-700 rounded-full text-sm hover:bg-indigo-100"
                  >
                    {ex.text}
                  </button>
                ))}
              </div>
            </div>
          </div) }

        {!result && !loading && (
          <div className="bg-white rounded-xl shadow-lg border border-gray-200 p-8 text-center">
            <p className="text-gray-500 mb-6">Enter a search query to find properties</p>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 max-w-2xl mx-auto">
              {[
                { icon: "🏡", text: "Detached Houses" },
                { icon: "🏘️", text: "Terraced Properties" },
                { icon: "🏢", text: "Flats & Apartments" },
              ].map((cat) => (
                <button
                  key={cat.text}
                  onClick={() => handleSearch(cat.text)}
                  className="p-4 bg-gradient-to-br from-gray-50 to-gray-100 rounded-lg hover:from-blue-50 hover:to-indigo-50 border transition-all text-left"
                >
                  <span className="text-2xl mb-2 block">{cat.icon}</span>
                  <span className="font-medium text-gray-700">{cat.text}</span>
                </button>
              ))}
            </div>
          </div) }

      </main>

      {/* Footer */}
      <footer className="bg-white border-t mt-12">
        <div className="max-w-4xl mx-auto px-4 py-6 text-center text-sm text-gray-600">
          <p>Built with ⚛️ Next.js and Fastify API</p>
          <p className="mt-1">Powered by real Sandbach property data (500 listings)</p>
        </div>
      </footer>

      <style jsx global>{`
        @keyframes fade-in { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
        .animate-fade-in { animation: fade-in 0.3s ease-out; }
      `}</style>
    </div>
  );
}