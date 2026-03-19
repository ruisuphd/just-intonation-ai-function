"use client";

import { useState } from "react";
import Link from "next/link";
import { useAuth } from "@/hooks/useAuth";
import { api } from "@/lib/api";

const FREE_FEATURES = [
  "3 vocal coach sessions per week",
  "3 basic warm-up exercises",
  "Text-only coaching feedback",
  "Vocal coach access",
];

const ESSENTIAL_FEATURES = [
  "Unlimited vocal, piano & guitar sessions",
  "Full warm-up library",
  "Audio analysis in every response",
  "RAG-enhanced pedagogy (all 3 instruments)",
  "AI dynamic exercises",
  "Progress analytics",
];

const PRO_FEATURES = [
  ...ESSENTIAL_FEATURES,
  "Lyria backing tracks for practice",
  "Session history export",
];

export default function PricingPage() {
  const { user } = useAuth();
  const [loading, setLoading] = useState<string | null>(null);

  const handleUpgrade = async (
    plan: "essential" | "pro",
    interval: "monthly" | "yearly"
  ) => {
    if (!user) {
      window.location.href = "/login?redirect=/pricing";
      return;
    }
    setLoading(`${plan}-${interval}`);
    try {
      const { url } = await api.createCheckoutSession({
        plan,
        interval,
      });
      if (url) window.location.href = url;
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(null);
    }
  };

  return (
    <div className="min-h-screen bg-[#fbfbfd]">
      <section className="mx-auto max-w-4xl px-6 py-20 text-center">
        <h1 className="text-4xl font-bold tracking-tight text-[#1d1d1f] sm:text-5xl">
          Simple pricing
        </h1>
        <p className="mt-6 text-lg text-[#6e6e73]">
          Start free. Upgrade for full multi-instrument coaching.
        </p>
      </section>

      <section className="mx-auto flex max-w-5xl flex-col items-stretch gap-8 px-6 pb-24 md:flex-row md:items-stretch md:justify-center">
        <div className="w-full max-w-sm rounded-2xl border border-[#d2d2d7] bg-white p-8">
          <h2 className="text-xl font-semibold text-[#1d1d1f]">Free</h2>
          <p className="mt-2 text-3xl font-bold text-[#1d1d1f]">$0</p>
          <p className="mt-1 text-sm text-[#6e6e73]">Forever</p>
          <ul className="mt-6 space-y-3">
            {FREE_FEATURES.map((f) => (
              <li key={f} className="flex items-start gap-2 text-[#1d1d1f]">
                <span className="text-[#34c759]">✓</span>
                {f}
              </li>
            ))}
          </ul>
          <Link
            href="/login"
            className="mt-8 block w-full rounded-xl border border-[#d2d2d7] py-3.5 text-center font-medium text-[#1d1d1f] transition hover:bg-[#f5f5f7]"
          >
            Get Started
          </Link>
        </div>

        <div className="relative w-full max-w-sm rounded-2xl border-2 border-[#0071e3] bg-white p-8 shadow-lg">
          <div className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-[#0071e3] px-3 py-1 text-xs font-medium text-white">
            Most popular
          </div>
          <h2 className="text-xl font-semibold text-[#1d1d1f]">Essential</h2>
          <p className="mt-2 text-3xl font-bold text-[#1d1d1f]">$19</p>
          <p className="mt-1 text-sm text-[#6e6e73]">per month</p>
          <ul className="mt-6 space-y-3">
            {ESSENTIAL_FEATURES.map((f) => (
              <li key={f} className="flex items-start gap-2 text-[#1d1d1f]">
                <span className="text-[#34c759]">✓</span>
                {f}
              </li>
            ))}
          </ul>
          <button
            onClick={() => handleUpgrade("essential", "monthly")}
            disabled={!!loading}
            className="mt-8 w-full rounded-xl bg-[#0071e3] py-3.5 font-medium text-white transition hover:bg-[#0077ed] disabled:opacity-50"
          >
            {loading === "essential-monthly" ? "Redirecting…" : "Upgrade to Essential"}
          </button>
          <p className="mt-3 text-center text-xs text-[#6e6e73]">
            or $168/year (save 26%)
          </p>
          <button
            onClick={() => handleUpgrade("essential", "yearly")}
            disabled={!!loading}
            className="mt-2 w-full rounded-xl border border-[#0071e3] py-2 font-medium text-[#0071e3] transition hover:bg-[#0071e3]/5 disabled:opacity-50"
          >
            {loading === "essential-yearly" ? "Redirecting…" : "Annual plan"}
          </button>
        </div>

        <div className="w-full max-w-sm rounded-2xl border border-[#d2d2d7] bg-white p-8">
          <h2 className="text-xl font-semibold text-[#1d1d1f]">Pro</h2>
          <p className="mt-2 text-3xl font-bold text-[#1d1d1f]">$29</p>
          <p className="mt-1 text-sm text-[#6e6e73]">per month</p>
          <ul className="mt-6 space-y-3">
            {PRO_FEATURES.map((f) => (
              <li key={f} className="flex items-start gap-2 text-[#1d1d1f]">
                <span className="text-[#34c759]">✓</span>
                {f}
              </li>
            ))}
          </ul>
          <button
            onClick={() => handleUpgrade("pro", "monthly")}
            disabled={!!loading}
            className="mt-8 w-full rounded-xl bg-[#1d1d1f] py-3.5 font-medium text-white transition hover:bg-[#333] disabled:opacity-50"
          >
            {loading === "pro-monthly" ? "Redirecting…" : "Upgrade to Pro"}
          </button>
          <p className="mt-3 text-center text-xs text-[#6e6e73]">
            or $228/year (save 34%)
          </p>
          <button
            onClick={() => handleUpgrade("pro", "yearly")}
            disabled={!!loading}
            className="mt-2 w-full rounded-xl border border-[#d2d2d7] py-2 font-medium text-[#1d1d1f] transition hover:bg-[#f5f5f7] disabled:opacity-50"
          >
            {loading === "pro-yearly" ? "Redirecting…" : "Annual plan"}
          </button>
        </div>
      </section>
    </div>
  );
}
