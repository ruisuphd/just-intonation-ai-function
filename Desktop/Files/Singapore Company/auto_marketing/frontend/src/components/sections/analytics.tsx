"use client";

import { useEffect, useMemo, useState } from "react";

import LockedState from "@/components/ui/locked-state";
import Notice from "@/components/ui/notice";
import { apiFetch } from "@/lib/api";
import { hasTierAccess } from "@/lib/billing";
import type { AnalyticsResponse, BillingSummary } from "@/types";

interface AnalyticsSectionProps {
  billing: BillingSummary;
  platforms?: string[];
}

export default function AnalyticsSection({ billing, platforms }: AnalyticsSectionProps) {
  const [data, setData] = useState<AnalyticsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!billing || !hasTierAccess(billing, "starter")) {
      setData(null);
      setLoading(false);
      setError("");
      return;
    }

    let cancelled = false;

    async function loadAnalytics() {
      setLoading(true);
      setError("");
      try {
        const response = await apiFetch<AnalyticsResponse>("/api/analytics?days=14");
        if (!cancelled) {
          setData(response);
        }
      } catch (err: any) {
        if (!cancelled) {
          setError(err?.message || "Unable to load analytics.");
          setData(null);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void loadAnalytics();
    return () => {
      cancelled = true;
    };
  }, [billing]);

  const chartMax = useMemo(() => {
    const values = (data?.series || []).map((point) => point.impressions);
    return values.length ? Math.max(...values, 1) : 1;
  }, [data]);

  function formatCompact(value: number) {
    return new Intl.NumberFormat("en", {
      notation: "compact",
      maximumFractionDigits: value >= 1000 ? 1 : 0,
    }).format(value);
  }

  function formatPercent(value: number) {
    return `${(value * 100).toFixed(1)}%`;
  }

  function handleExport() {
    if (!data) return;
    const rows = [
      ["Date", "Impressions", "Engagements", "Average Open Rate"],
      ...data.series.map((point) => [
        point.date,
        String(point.impressions),
        String(point.engagements),
        formatPercent(point.avg_open_rate),
      ]),
    ];
    const csv = rows
      .map((row) => row.map((cell) => `"${cell.replace(/"/g, '""')}"`).join(","))
      .join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "analytics-export.csv";
    anchor.click();
    URL.revokeObjectURL(url);
  }

  return (
    <section className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold">Analytics</h2>
          <p className="text-sm text-apple-secondary">
            Performance metrics when live provider data is available; otherwise values may be sample or partial.
          </p>
        </div>
        <button
          type="button"
          className="inline-flex items-center justify-center rounded-apple bg-apple-card px-4 py-2 text-sm font-medium text-apple-text shadow-apple border border-apple-border hover:bg-apple-bg transition-colors"
          onClick={handleExport}
          disabled={!data || data.series.length === 0}
        >
          Export to CSV
        </button>
      </div>

      {!hasTierAccess(billing, "starter") ? (
        <LockedState
          description="Performance analytics are available on the Starter and Pro plans."
          ctaLabel="Unlock Starter"
        />
      ) : error ? (
        <div className="rounded-apple border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 shadow-apple">
          {error}
        </div>
      ) : loading ? (
        <p className="py-8 text-center text-sm text-apple-secondary">Loading analytics…</p>
      ) : (
        <>
          {!data?.live_metrics_available && (
            <Notice tone="warning">
              Live engagement from connected platforms is not fully wired yet. Charts may use placeholder or historical
              snapshots until OAuth and analytics sync are complete for your accounts.
            </Notice>
          )}

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div className="rounded-apple bg-apple-card p-5 shadow-apple border border-apple-border">
              <p className="text-sm font-medium text-apple-secondary">Total Impressions</p>
              <p className="mt-2 text-3xl font-semibold tracking-tight">
                {formatCompact(data?.summary.total_impressions || 0)}
              </p>
              <p className="mt-1 text-sm text-apple-secondary">
                Across {data?.summary.published_posts || 0} published posts
              </p>
            </div>

            <div className="rounded-apple bg-apple-card p-5 shadow-apple border border-apple-border">
              <p className="text-sm font-medium text-apple-secondary">Average Open Rate</p>
              <p className="mt-2 text-3xl font-semibold tracking-tight">
                {formatPercent(data?.summary.avg_open_rate || 0)}
              </p>
              <p className="mt-1 text-sm text-apple-secondary">
                Based on {data?.summary.outreach_sent || 0} outreach records
              </p>
            </div>

            <div className="rounded-apple bg-apple-card p-5 shadow-apple border border-apple-border">
              <p className="text-sm font-medium text-apple-secondary">Qualified Leads</p>
              <p className="mt-2 text-3xl font-semibold tracking-tight">
                {formatCompact(data?.summary.qualified_leads || 0)}
              </p>
              <p className="mt-1 text-sm text-apple-secondary">
                {data?.summary.reply_received || 0} advanced beyond outreach
              </p>
            </div>
          </div>

          <div className="rounded-apple bg-apple-card p-6 shadow-apple border border-apple-border">
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
              <div>
                <h3 className="text-base font-semibold">Engagement Over Time</h3>
                <p className="text-sm text-apple-secondary">
                  Last {data?.series.length || 0} analytics snapshots across {platforms?.length || 0} connected platforms.
                </p>
              </div>
              <div className="flex flex-wrap gap-2 text-xs text-apple-secondary">
                <span className="rounded-full bg-apple-bg px-3 py-1">
                  Signals: {data?.summary.signals_detected || 0}
                </span>
                <span className="rounded-full bg-apple-bg px-3 py-1">
                  Outreach sent: {data?.summary.outreach_sent || 0}
                </span>
              </div>
            </div>

            {data && data.series.length > 0 ? (
              <>
                <div className="flex h-64 items-end justify-between gap-2 rounded-apple-sm border border-apple-border/50 bg-apple-bg p-4">
                  {data.series.map((point) => (
                    <div key={point.date} className="flex h-full w-full flex-col justify-end gap-2">
                      <div className="text-center text-[11px] text-apple-secondary">
                        {formatPercent(point.avg_open_rate)}
                      </div>
                      <div
                        className="w-full rounded-t-sm bg-apple-blue/80 transition-colors hover:bg-apple-blue"
                        style={{
                          height: `${Math.max((point.impressions / chartMax) * 100, 8)}%`,
                        }}
                        title={`${point.label}: ${point.impressions} impressions`}
                      />
                    </div>
                  ))}
                </div>
                <div className="mt-2 flex flex-wrap justify-between gap-2 px-1 text-center text-xs text-apple-secondary">
                  {data.series.map((point) => (
                    <span key={point.date}>{point.label}</span>
                  ))}
                </div>
              </>
            ) : (
              <div className="rounded-apple-sm border border-dashed border-apple-border bg-apple-bg px-4 py-10 text-center text-sm text-apple-secondary">
                Analytics snapshots will appear here once scheduled content has been published.
              </div>
            )}
          </div>
        </>
      )}
    </section>
  );
}
