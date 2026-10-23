/**
 * SearchBox — natural-language search input.
 */

"use client";

import { useEffect, useState, type FormEvent } from "react";

interface SearchBoxProps {
  onSubmit: (query: string) => void;
  initialValue?: string;
  placeholder?: string;
}

export default function SearchBox({
  onSubmit,
  initialValue = "",
  placeholder = "3 bed semi-detached in Sandbach under £250k",
}: SearchBoxProps) {
  const [value, setValue] = useState(initialValue);

  // Keep the input in sync when the URL changes (e.g. back button).
  useEffect(() => {
    setValue(initialValue);
  }, [initialValue]);

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmed = value.trim();
    if (trimmed) onSubmit(trimmed);
  };

  return (
    <form onSubmit={handleSubmit} className="flex flex-col sm:flex-row gap-3">
      <label htmlFor="search-input" className="sr-only">
        Search properties
      </label>
      <input
        id="search-input"
        type="text"
        value={value}
        onChange={(event) => setValue(event.target.value)}
        placeholder={placeholder}
        maxLength={500}
        className="flex-1 px-5 py-3.5 text-lg border border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
      />
      <button
        type="submit"
        disabled={!value.trim()}
        className="px-8 py-3.5 bg-blue-600 text-white font-semibold rounded-xl hover:bg-blue-700 transition-colors shadow-sm disabled:opacity-50"
      >
        Search
      </button>
    </form>
  );
}
