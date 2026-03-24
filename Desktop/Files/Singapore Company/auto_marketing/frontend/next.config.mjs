import { spawnSync } from "node:child_process";
import withSerwistInit from "@serwist/next";
import { withSentryConfig } from "@sentry/nextjs";

const isProduction = process.env.NODE_ENV === "production";

if (isProduction && !process.env.NEXT_PUBLIC_API_URL?.trim()) {
  throw new Error(
    "NEXT_PUBLIC_API_URL is required for production builds (see .env.example).",
  );
}

if (isProduction && !process.env.NEXT_PUBLIC_SITE_URL?.trim()) {
  throw new Error(
    "NEXT_PUBLIC_SITE_URL is required for production builds (see .env.example).",
  );
}

function pwaRevision() {
  const out = spawnSync("git", ["rev-parse", "HEAD"], {
    encoding: "utf-8",
    maxBuffer: 64 * 1024,
  });
  const hash = out.stdout?.trim();
  if (hash) return hash;
  return (
    process.env.VERCEL_GIT_COMMIT_SHA ||
    process.env.CF_PAGES_COMMIT_SHA ||
    "development"
  );
}

const withSerwist = withSerwistInit({
  swSrc: "src/app/sw.ts",
  swDest: "public/sw.js",
  disable: !isProduction,
  additionalPrecacheEntries: [{ url: "/~offline", revision: pwaRevision() }],
});

const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  {
    key: "Referrer-Policy",
    value: "strict-origin-when-cross-origin",
  },
  {
    key: "Permissions-Policy",
    value: "camera=(), microphone=(), geolocation=(), payment=()",
  },
];

if (isProduction) {
  securityHeaders.push({
    key: "Strict-Transport-Security",
    value: "max-age=63072000; includeSubDomains; preload",
  });
}

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  async headers() {
    return [
      {
        source: "/:path*",
        headers: securityHeaders,
      },
    ];
  },
};

export default withSentryConfig(withSerwist(nextConfig), {
  silent: true,
  disableLogger: true,
});
