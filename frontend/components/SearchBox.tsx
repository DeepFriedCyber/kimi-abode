/**
 * SearchBox — the main search input component.
 * Supports natural-language queries with a submit button and placeholder.
 */

"use client";

import { useState, FormEvent } from "react";

interface SearchBoxProps {
  onSubmit: (query: string) => void;
  placeholder?: string;
}

export default function SearchBox({ onSubmit, placeholder = "3 bed semi-detached in Sandbach under £250k" }: SearchBoxProps) {
  const [value, setValue] = useState("");

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (value.trim()) {
      onSubmit(value.trim());
    }
  };

  return (
    <form onSubmit={handleSubmit} className="flex gap-3">
      <input
        type="text"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder={placeholder}
        className="flex-1 px-5 py-3.5 text-lg border border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
      />
      <button
        type="submit"
        className="px-8 py-3.5 bg-blue-600 text-white font-semibold rounded-xl hover:bg-blue-700 transition-colors shadow-sm"
      >
        Search
      </button>
    </form>
  );
}
