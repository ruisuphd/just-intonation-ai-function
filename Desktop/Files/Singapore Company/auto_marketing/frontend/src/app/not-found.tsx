import Link from "next/link";

export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-apple-bg px-4 text-center">
      <div className="max-w-md">
        <p className="text-6xl font-bold text-apple-blue">404</p>
        <h1 className="mt-4 text-2xl font-semibold text-apple-text">Page not found</h1>
        <p className="mt-2 text-sm text-apple-secondary">
          The page you&apos;re looking for doesn&apos;t exist or has been moved.
        </p>
        <Link
          href="/dashboard"
          className="mt-6 inline-block rounded-apple-sm bg-apple-blue px-6 py-2.5 text-sm font-medium text-white hover:bg-apple-blue-hover"
        >
          Back to Dashboard
        </Link>
      </div>
    </div>
  );
}
