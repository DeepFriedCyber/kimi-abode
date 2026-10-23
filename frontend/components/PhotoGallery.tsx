/**
 * PhotoGallery — main image plus thumbnails for a property.
 */

"use client";

import { useEffect, useState } from "react";
import { mediaUrl } from "../lib/api";
import type { Photo } from "../lib/types";

interface PhotoGalleryProps {
  photos: Photo[];
  address: string;
}

function ordered(photos: Photo[]): Photo[] {
  return [...photos].sort((a, b) => {
    if (a.is_cover !== b.is_cover) return a.is_cover ? -1 : 1;
    return (a.position ?? 0) - (b.position ?? 0);
  });
}

export default function PhotoGallery({ photos, address }: PhotoGalleryProps) {
  const [active, setActive] = useState(0);
  const sorted = ordered(photos);

  useEffect(() => {
    setActive(0);
  }, [photos]);

  if (sorted.length === 0) {
    return (
      <div className="h-64 bg-gradient-to-br from-gray-100 to-gray-200 flex items-center justify-center">
        <span className="text-7xl opacity-40" aria-hidden>
          🏠
        </span>
      </div>
    );
  }

  const current = sorted[Math.min(active, sorted.length - 1)];
  const src = mediaUrl(current.url);

  return (
    <div>
      <div className="h-64 sm:h-80 bg-gray-100">
        {src && (
          // Plain img: media is served by the API, not the Next image optimiser.
          <img
            src={src}
            alt={`${address} — photo ${Math.min(active, sorted.length - 1) + 1} of ${sorted.length}`}
            className="w-full h-full object-cover"
            width={current.width}
            height={current.height}
          />
        )}
      </div>

      {sorted.length > 1 && (
        <div className="flex gap-2 overflow-x-auto p-2 bg-gray-50">
          {sorted.map((photo, index) => {
            const thumb = mediaUrl(photo.thumb_url);
            return (
              <button
                key={photo.id}
                type="button"
                onClick={() => setActive(index)}
                aria-label={`Show photo ${index + 1}`}
                aria-pressed={index === active}
                className={`shrink-0 rounded overflow-hidden border-2 ${
                  index === active ? "border-blue-600" : "border-transparent"
                }`}
              >
                {thumb && (
                  <img
                    src={thumb}
                    alt=""
                    width={96}
                    height={72}
                    className="w-24 h-[72px] object-cover"
                    loading="lazy"
                  />
                )}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
