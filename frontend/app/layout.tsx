/**
 * Root layout — header, main content and footer.
 */

import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Abode AI — UK Property Search",
  description:
    "Natural-language property search with area intelligence for the UK market.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="antialiased bg-gray-50 text-gray-900">
        <div className="min-h-screen flex flex-col">
          <header className="bg-white border-b px-6 py-4 flex items-center justify-between sticky top-0 z-10">
            <Link href="/" className="text-xl font-bold text-blue-600">
              🏠 Abode AI
            </Link>
            <nav className="flex gap-4 text-sm">
              <Link href="/" className="hover:text-blue-600">
                Search
              </Link>
              <Link href="/search" className="hover:text-blue-600">
                Advanced
              </Link>
              <Link href="/agent/import" className="hover:text-blue-600">
                Agent import
              </Link>
              <Link href="/agent/listings" className="hover:text-blue-600">
                My listings
              </Link>
            </nav>
          </header>

          <main className="flex-grow max-w-7xl w-full mx-auto px-4 py-8">
            {children}
          </main>

          <footer className="border-t bg-white mt-auto py-6 text-center text-sm text-gray-500">
            © {new Date().getFullYear()} Abode AI — UK property intelligence
          </footer>
        </div>
      </body>
    </html>
  );
}
