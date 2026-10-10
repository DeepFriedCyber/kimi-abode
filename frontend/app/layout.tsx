/**
 * Root layout — provides global styling and structure for all pages.
 */

import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Abode AI — UK Property Search",
  description: "UK property search with natural language queries and semantic matching.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="antialiased bg-gray-50 text-gray-900">
        <div className="min-h-screen flex flex-col">
          {/* Header */}
          <header className="bg-white border-b px-6 py-4 flex items-center justify-between sticky top-0 z-10">
            <a href="/" className="text-xl font-bold text-blue-600">🏠 Abode AI</a>
            <nav className="flex gap-4 text-sm">
              <a href="/" className="hover:text-blue-600">Search</a>
              <a href="/about" className="hover:text-blue-600">About</a>
            </nav>
          </header>

          {/* Main Content */}
          <main className="flex-grow max-w-7xl mx-auto px-4 py-8">{children}</main>

          {/* Footer */}
          <footer className="border-t bg-white mt-auto py-6 text-center text-sm text-gray-500">
            © 2025 Abode AI — UK Property Search Platform
          </footer>
        </div>
      </body>
    </html>
  );
}