/**
 * AskLocation — POI intelligence panel for property detail pages.
 * Queries nearby amenities (schools, transport, shops) with proximity scoring.
 */

"use client";

import { useState, useEffect } from "react";
import { getNearbyPois } from "../lib/api";
import type { PoiResult } from "../lib/types";

interface AskLocationProps {
  propertyId?: string | number;
  lat: number;
  lon: number;
}

export default function AskLocation({ propertyId, lat, lon }: AskLocationProps) {
  const [loading, setLoading] = useState(false);
  const [nearby, setNearby] = useState<PoiResult[]>([]);
  const [scores, setScores] = useState<Record<string, number>>({});
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      if (lat == null || lon == null) {
        if (!cancelled) setError("Property coordinates not available");
        if (!cancelled) setLoading(false);
        return;
      }

      setLoading(true);
      setError(null);
      try {
        const data = await getNearbyPois(lat, lon, undefined, 8);
        if (cancelled) return;
        setNearby(data.nearby || []);
        setScores(data.category_scores || {});
      } catch (err) {
        if (!cancelled) {
          setError("Unable to load nearby amenities. Please try again later.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();

    return () => {
      cancelled = true;
    };
  }, [lat, lon, propertyId]);

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
      ) : error ? (
        <p className="text-sm text-red-500">{error}</p>
      ) : nearby.length === 0 ? (
        <p className="text-sm text-gray-500">No nearby amenities found.</p>
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
                    ? `${(poi.distance_m / 1000).toFixed(1)} km · ${poi.walk_time_min}m walk`
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
