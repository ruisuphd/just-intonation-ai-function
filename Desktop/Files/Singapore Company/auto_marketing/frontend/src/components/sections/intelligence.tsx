"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import LockedState from "@/components/ui/locked-state";
import { hasTierAccess } from "@/lib/billing";
import type { BillingSummary } from "@/types";

interface IntelligenceSectionProps {
  billing: BillingSummary | null;
}

const PAGE_SIZE = 20;

export default function IntelligenceSection({ billing }: IntelligenceSectionProps) {
  const [items, setItems] = useState<any[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!billing || !hasTierAccess(billing, "starter")) {
      setItems([]);
      setNextCursor(null);
      setError("");
      setLoading(false);
      return;
    }

    apiFetch<{ items?: any[]; next_cursor?: string }>(`/api/intelligence?limit=${PAGE_SIZE}`)
      .then((d) => {
        setItems(d.items || []);
        setNextCursor(d.next_cursor || null);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [billing]);

  async function loadMore() {
    if (!nextCursor || loadingMore) return;
    setLoadingMore(true);
    setError("");
    try {
      const d = await apiFetch<{ items?: any[]; next_cursor?: string }>(
        `/api/intelligence?limit=${PAGE_SIZE}&cursor=${encodeURIComponent(nextCursor)}`
      );
      setItems((prev) => [...prev, ...(d.items || [])]);
      setNextCursor(d.next_cursor || null);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoadingMore(false);
    }
  }

  function relevanceColor(score: number) {
    if (score >= 0.7) return "bg-green-100 text-green-700";
    if (score >= 0.4) return "bg-yellow-100 text-yellow-700";
    return "bg-neutral-100 text-neutral-500";
  }

  return (
    <section id="intelligence" className="scroll-mt-28">
      <h2 className="mb-1 text-xl font-semibold">Market Intelligence</h2>
      <p className="mb-4 text-sm text-apple-secondary">AI-curated industry digest.</p>

      {billing && !hasTierAccess(billing, "starter") ? (
        <LockedState
          description="Market intelligence is available on the Starter and Pro plans."
          ctaLabel="Unlock Starter"
        />
      ) : loading ? (
        <p className="py-8 text-center text-sm text-apple-secondary">Loading&hellip;</p>
      ) : error ? (
        <p className="mb-3 text-sm text-red-500">{error}</p>
      ) : items.length === 0 ? (
        <p className="py-8 text-center text-sm text-apple-secondary">
          No intelligence items yet. Check back after the next pipeline run.
        </p>
      ) : (
        <div className="space-y-3">
          {items.map((item, i) => (
            <article key={item.id || i} className="rounded-apple bg-apple-card p-5 shadow-apple">
              <div className="mb-2 flex items-start justify-between gap-3">
                <h3 className="text-[15px] font-semibold leading-snug">{item.title}</h3>
                <span className={`flex-shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${relevanceColor(item.relevance_score || 0)}`}>
                  {Math.round((item.relevance_score || 0) * 100)}%
                </span>
              </div>
              <p className="mb-2 text-xs text-apple-secondary">
                {item.source_name} &middot; {item.batch_date}
              </p>
              <p className="text-sm leading-relaxed text-apple-text">{item.summary}</p>
              {item.suggested_angle && (
                <p className="mt-2 text-xs text-apple-secondary">
                  <span className="font-medium">Angle:</span> {item.suggested_angle}
                </p>
              )}
              {item.tags?.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1">
                  {item.tags.map((tag: string, j: number) => (
                    <span key={`tag-${j}`} className="rounded bg-apple-bg px-1.5 py-0.5 text-xs text-apple-secondary">
                      {tag}
                    </span>
                  ))}
                </div>
              )}
            </article>
          ))}
          {nextCursor && (
            <div className="text-center">
              <button
                type="button"
                onClick={loadMore}
                disabled={loadingMore}
                className="rounded-apple-sm border border-apple-border px-4 py-2 text-sm font-medium text-apple-text hover:bg-apple-bg disabled:opacity-50"
              >
                {loadingMore ? "Loading..." : "Load more"}
              </button>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
