import Link from "next/link";

export default function NotFound() {
  return (
    <div className="max-w-lg mx-auto text-center py-16 space-y-4">
      <h1 className="text-2xl font-bold text-gray-900">Page not found</h1>
      <p className="text-gray-600">
        The page you were looking for does not exist.
      </p>
      <Link href="/" className="text-blue-600 hover:underline">
        Back to search
      </Link>
    </div>
  );
}
