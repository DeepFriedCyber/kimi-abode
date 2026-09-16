/**
 * AskLocation — POI intelligence panel for property detail pages.
 * Queries nearby amenities (schools, transport, shops) with proximity scoring.
 */

"use client";

import { useState, useEffect } from "react";

interface AskLocationProps {
  propertyId: number | string;
}

interface PoiResult {
  name: string;
  category: string;
  distance_m: number;
  walk_time_min: number;
  decay_score: number;
}

export default function AskLocation({ propertyId }: AskLocationProps) {
  const [loading, setLoading] = useState(false);
  const [nearby, setNearby] = useState<PoiResult[]>([]);
  const [scores, setScores] = useState<Record<string, number>>({});

  // Mock data for development (replace with real API call when POI data is available)
  useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://localhost:3001";
        const res = await fetch(`${apiBase}/api/ask/poi`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ lat: 53.1, lon: -2.4, n: 8 }),
        });

        if (res.ok) {
          const data = await res.json();
          setNearby(data.nearby || []);
          setScores(data.category_scores || {});
        } else {
          // Fall back to mock data for demo
          loadMockData();
        }
      } catch {
        loadMockData();
      } finally {
        setLoading(false);
      }
    }

    function loadMockData() {
      setNearby([
        { name: "Sandbach Primary School", category: "school", distance_m: 320, walk_time_min: 4, decay_score: 0.75 },
        { name: "Tesco Express", category: "supermarket", distance_m: 450, walk_time_min: 6, decay_score: 0.65 },
        { name: "Sandbach Railway Station", category: "station", distance_m: 680, walk_time_min: 9, decay_score: 0.45 },
        { name: "The Crown Pub", category: "pub", distance_m: 200, walk_time_min: 3, decay_score: 0.85 },
      ]);
      setScores({ school: 75, supermarket: 65, station: 45, pub: 85 });
    }

    load();
  }, [propertyId]);

  const categoryIcons: Record<string, string> = {
    school: "🎓",
    supermarket: "🛒",
    station: "🚂",
    pub: "🍺",
    restaurant: "🍽️",
    hospital: "🏥",
  };

  return (
    <div className="bg-white rounded-xl border p-4 mt-6">
      <h3 className="font-semibold mb-3 flex items-center gap-2">
        <span>📍</span> Nearby Amenities
      </h3>

      {loading ? (
        <p className="text-sm text-gray-400 animate-pulse">Loading...</p>
      ) : (
        <>
          {/* Category scores bar */}
          <div className="flex gap-2 mb-4 flex-wrap">
            {Object.entries(scores).map(([cat, score]) => (
              <span key={cat} className="text-xs bg-gray-100 px-2 py-1 rounded-full capitalize">
                {categoryIcons[cat] || "📍"} {score.toFixed(0)} pts
              </span>
            ))}
          </div>

          {/* List */}
          <div className="space-y-2">
            {nearby.map((poi, i) => (
              <div key={i} className="flex items-center justify-between py-1.5 text-sm border-b border-gray-100 last:border-0">
                <span className="flex items-center gap-2">
                  <span>{categoryIcons[poi.category] || "📍"}</span>
                  <span className="text-gray-900">{poi.name}</span>
                </span>
                <span className="text-gray-500 text-xs">
                  {poi.distance_m > 1000
                    ? `${(poi.distance_m / 1000).toFixed(1)} km · {poi.walk_time_min}m walk`
                    : `${poi.distance_m}m · ${poi.walk_time_min}m walk`}
                </span>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
