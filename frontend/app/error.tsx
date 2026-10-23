"use client";

/**
 * Route-level error boundary. Replaces the unused withErrorBoundary HOC.
 */

import { useEffect } from "react";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("[AppError]", error);
  }, [error]);

  return (
    <div className="max-w-lg mx-auto text-center py-16 space-y-4">
      <h1 className="text-2xl font-bold text-gray-900">Something went wrong</h1>
      <p className="text-gray-600">
        The page could not be loaded. This is usually temporary.
      </p>
      {error.digest && (
        <p className="text-xs text-gray-400">Reference: {error.digest}</p>
      )}
      <button
        onClick={reset}
        className="px-5 py-2.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
      >
        Try again
      </button>
    </div>
  );
}
