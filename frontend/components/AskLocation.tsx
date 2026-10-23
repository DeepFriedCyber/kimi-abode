/**
 * AskLocation — nearby amenities for a property.
 */

"use client";

import { useEffect, useState } from "react";
import { getNearbyPois } from "../lib/api";
import { formatDistance } from "../lib/format";
import type { PoiResult } from "../lib/types";

interface AskLocationProps {
  lat: number;
  lon: number;
}

const CATEGORY_ICONS: Record<string, string> = {
  school: "🎓",
  supermarket: "🛒",
  convenience: "🏪",
  station: "🚂",
  pub: "🍺",
  restaurant: "🍽️",
  cafe: "☕",
  fitness: "🏋️",
  pharmacy: "💊",
  doctors: "🩺",
  dentist: "🦷",
  hospital: "🏥",
  park: "🌳",
  playground: "🛝",
  nursery: "🧸",
  bar: "🍸",
};

export default function AskLocation({ lat, lon }: AskLocationProps) {
  const [loading, setLoading] = useState(true);
  const [nearby, setNearby] = useState<PoiResult[]>([]);
  const [scores, setScores] = useState<Record<string, number>>({});
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) {
      setError("Coordinates are unavailable for this property");
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);

    getNearbyPois(lat, lon, undefined, 8)
      .then((data) => {
        if (cancelled) return;
        setNearby(data.nearby ?? []);
        setScores(data.category_scores ?? {});
      })
      .catch(() => {
        if (!cancelled) setError("Unable to load nearby amenities");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [lat, lon]);

  return (
    <section className="bg-white rounded-xl border p-4">
      <h2 className="font-semibold mb-3 flex items-center gap-2">
        <span aria-hidden>📍</span> Nearby amenities
      </h2>

      {loading ? (
        <p className="text-sm text-gray-400 animate-pulse">Loading…</p>
      ) : error ? (
        <p className="text-sm text-gray-500">{error}</p>
      ) : nearby.length === 0 ? (
        <p className="text-sm text-gray-500">No amenity data available for this area.</p>
      ) : (
        <>
          {Object.keys(scores).length > 0 && (
            <div className="flex gap-2 mb-4 flex-wrap">
              {Object.entries(scores).map(([category, score]) => (
                <span
                  key={category}
                  className="text-xs bg-gray-100 px-2 py-1 rounded-full capitalize"
                >
                  {CATEGORY_ICONS[category] ?? "📍"} {score.toFixed(0)} pts
                </span>
              ))}
            </div>
          )}

          <ul className="space-y-2">
            {nearby.map((poi) => (
              <li
                key={`${poi.category}-${poi.name}-${poi.distance_m}`}
                className="flex items-center justify-between py-1.5 text-sm border-b border-gray-100 last:border-0"
              >
                <span className="flex items-center gap-2">
                  <span aria-hidden>{CATEGORY_ICONS[poi.category] ?? "📍"}</span>
                  <span className="text-gray-900">{poi.name}</span>
                </span>
                <span className="text-gray-500 text-xs">
                  {formatDistance(poi.distance_m)}
                  {" · "}
                  {poi.walk_time_min} min walk
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
