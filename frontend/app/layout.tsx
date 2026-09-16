import type { Metadata } from "next";
import "./globals.css";
import ChatPanel from "../components/ChatPanel";

export const metadata: Metadata = {
  title: "Abode AI — UK Property Search",
  description: "AI-powered property search for the UK market. Natural language queries, semantic matching, and local intelligence.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-gray-50 text-gray-900">
        <header className="bg-white border-b px-6 py-4 flex items-center justify-between sticky top-0 z-10">
          <a href="/" className="text-xl font-bold text-blue-600">
            🏠 Abode AI
          </a>
          <nav className="flex gap-4 text-sm">
            <a href="/" className="hover:text-blue-600">Search</a>
            <a href="/about" className="hover:text-blue-600">About</a>
          </nav>
        </header>
        <main className="max-w-7xl mx-auto px-4 py-8">
          {children}
        </main>
        <footer className="border-t bg-white mt-auto py-6 text-center text-sm text-gray-500">
          © 2025 Abode AI — UK Property Search Platform
        </footer>
        <ChatPanel />
      </body>
    </html>
  );
}
