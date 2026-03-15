"use client";

import * as Sentry from "@sentry/nextjs";
import { useEffect } from "react";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    Sentry.captureException(error);
  }, [error]);

  return (
    <html lang="en">
      <body className="font-sans">
        <div className="flex min-h-screen items-center justify-center">
          <div className="text-center">
            <h2 className="text-lg font-semibold text-red-800">
              Something went wrong
            </h2>
            <p className="mt-2 text-sm text-red-600">
              {error.message || "An unexpected error occurred."}
            </p>
            <button
              onClick={reset}
              className="mt-4 rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700"
            >
              Try again
            </button>
          </div>
        </div>
      </body>
    </html>
  );
}
