"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import Notice from "@/components/ui/notice";
import { ApiError, apiFetch } from "@/lib/api";
import { hasTierAccess } from "@/lib/billing";
import { PLATFORM_BY_ID } from "@/lib/platforms";
import type { BillingSummary, DashboardBootstrapResponse, PlatformId } from "@/types";

interface OverviewSectionProps {
  billing: BillingSummary | null;
  platforms: PlatformId[];
  onboardingCompleted?: boolean;
  companyName?: string;
  /** From GET /api/dashboard/bootstrap — avoids duplicate usage/pipeline/oauth fetches on first paint */
  overviewPrefetch?: Pick<
    DashboardBootstrapResponse,
    "usage" | "pipeline_status" | "oauth_status"
  >;
}

interface UsageSummary {
  tier?: string;
  usage?: Record<
    string,
    { used?: number; limit?: number; percentage?: number }
  >;
}

export default function OverviewSection({
  billing,
  platforms,
  onboardingCompleted = true,
  companyName,
  overviewPrefetch,
}: OverviewSectionProps) {
  const [drafts, setDrafts] = useState(0);
  const [intel, setIntel] = useState(0);
  const [leads, setLeads] = useState<number | null>(null);
  const [starterLocked, setStarterLocked] = useState(false);
  const [leadsLocked, setLeadsLocked] = useState(false);
  const [metricsError, setMetricsError] = useState("");
  const [usage, setUsage] = useState<UsageSummary | null>(null);
  const [oauthStatus, setOauthStatus] = useState<{ linkedin: boolean; x_twitter: boolean } | null>(null);
  const [checklistDismissed, setChecklistDismissed] = useState(false);
  const [pipelineStatus, setPipelineStatus] = useState<{
    last_run: {
      completed_at?: string;
      status?: string;
      drafts_generated?: number;
      signals_found?: number;
      leads_qualified?: number;
      skip_reason?: string;
    } | null;
    next_run?: string;
    next_run_local?: string;
    next_run_at?: string;
    has_run_before?: boolean;
  } | null>(null);
  const [pipelineTriggering, setPipelineTriggering] = useState(false);
  const [pipelineTriggerMessage, setPipelineTriggerMessage] = useState("");
  const [pipelineTriggerError, setPipelineTriggerError] = useState("");
  const consumedPrefetch = useRef(false);

  useEffect(() => {
    if (typeof localStorage !== "undefined") {
      setChecklistDismissed(localStorage.getItem("intomarketing_checklist_dismissed") === "true");
    }
  }, []);

  useEffect(() => {
    if (!billing) return;

    let cancelled = false;

    const canUseStarter = hasTierAccess(billing, "starter");
    const canUsePro = hasTierAccess(billing, "pro");

    setStarterLocked(!canUseStarter);
    setLeadsLocked(!canUsePro);
    setMetricsError("");

    async function loadDraftCount() {
      try {
        const data = await apiFetch<{ count: number }>("/api/drafts/count?status=draft");
        if (!cancelled) {
          setDrafts(data.count ?? 0);
        }
      } catch {
        if (!cancelled) {
          setDrafts(0);
          setMetricsError("Some overview metrics could not be loaded.");
        }
      }
    }

    async function loadIntelCount() {
      try {
        const data = await apiFetch<{ items?: unknown[] }>("/api/intelligence?limit=5");
        if (!cancelled) {
          setIntel(data.items?.length || 0);
        }
      } catch {
        if (!cancelled) {
          setIntel(0);
          setMetricsError("Some overview metrics could not be loaded.");
        }
      }
    }

    async function loadLeadCount() {
      try {
        const data = await apiFetch<{ leads?: unknown[] }>("/api/leads?limit=1");
        if (!cancelled) {
          setLeads(data.leads?.length || 0);
        }
      } catch {
        if (!cancelled) {
          setLeads(0);
          setMetricsError("Some overview metrics could not be loaded.");
        }
      }
    }

    if (!canUseStarter) {
      setDrafts(0);
      setIntel(0);
    } else {
      void loadDraftCount();
      void loadIntelCount();
    }

    if (!canUsePro) {
      setLeads(0);
    } else {
      void loadLeadCount();
    }

    const usePrefetch =
      overviewPrefetch && !consumedPrefetch.current;
    if (usePrefetch) {
      consumedPrefetch.current = true;
      setUsage(overviewPrefetch.usage as UsageSummary);
      setPipelineStatus(overviewPrefetch.pipeline_status);
      setOauthStatus({
        linkedin: overviewPrefetch.oauth_status.linkedin,
        x_twitter: overviewPrefetch.oauth_status.x_twitter,
      });
    } else {
      apiFetch<UsageSummary>("/api/usage").then((u) => {
        if (!cancelled) setUsage(u);
      }).catch(() => {
        if (!cancelled) setUsage(null);
      });

      apiFetch<{
        last_run: { completed_at?: string; status?: string; drafts_generated?: number; signals_found?: number; leads_qualified?: number } | null;
        next_run?: string;
        next_run_local?: string;
        next_run_at?: string;
        has_run_before?: boolean;
      }>("/api/pipeline/status").then((s) => {
        if (!cancelled) setPipelineStatus(s);
      }).catch(() => {
        if (!cancelled) setPipelineStatus(null);
      });

      apiFetch<{ linkedin: boolean; x_twitter: boolean }>("/api/oauth/status").then((o) => {
        if (!cancelled) setOauthStatus(o);
      }).catch(() => {
        if (!cancelled) setOauthStatus(null);
      });
    }

    const handleDraftsChanged = () => {
      if (canUseStarter) {
        void loadDraftCount();
      }
    };

    window.addEventListener("drafts:changed", handleDraftsChanged);

    return () => {
      cancelled = true;
      window.removeEventListener("drafts:changed", handleDraftsChanged);
    };
  }, [billing, overviewPrefetch]);

  const cards = [
    {
      label: "Content drafts",
      value: starterLocked ? null : drafts,
      sub: starterLocked ? "Starter plan and above" : "ready to review",
    },
    {
      label: "Market signals",
      value: starterLocked ? null : intel,
      sub: starterLocked ? "Starter plan and above" : "items today",
    },
    {
      label: "Warm leads",
      value: leadsLocked ? null : leads,
      sub: leadsLocked ? "Pro plan only" : "detected",
    },
  ];

  return (
    <div>
      <h2 className="mb-4 text-xl font-semibold">Overview</h2>
      <div className="grid gap-4 sm:grid-cols-3">
        {cards.map((c) => (
          <div key={c.label} className="rounded-apple bg-apple-card p-5 shadow-apple">
            <p className="text-sm text-apple-secondary">{c.label}</p>
            <p className="mt-1 text-3xl font-semibold">
              {c.value === null ? "\u2014" : c.value ?? "\u2026"}
            </p>
            <p className="mt-1 text-sm text-apple-secondary">{c.sub}</p>
          </div>
        ))}
      </div>

      {billing &&
        hasTierAccess(billing, "starter") &&
        !checklistDismissed &&
        (!(companyName?.trim() && oauthStatus && (oauthStatus.linkedin || oauthStatus.x_twitter) && drafts > 0) || !onboardingCompleted) && (
        <div className="mt-4 rounded-apple bg-apple-card p-5 shadow-apple">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="text-sm font-semibold">Getting started</h3>
            {(companyName?.trim() && oauthStatus && (oauthStatus.linkedin || oauthStatus.x_twitter) && drafts > 0) && (
              <button
                type="button"
                onClick={() => {
                  localStorage.setItem("intomarketing_checklist_dismissed", "true");
                  setChecklistDismissed(true);
                }}
                className="text-xs text-apple-secondary hover:text-apple-text"
              >
                Dismiss
              </button>
            )}
          </div>
          <ul className="space-y-2">
            <li className="flex items-center gap-2 text-sm">
              <span className={companyName?.trim() ? "text-green-500" : "text-apple-secondary"}>
                {companyName?.trim() ? "✓" : "○"}
              </span>
              <span className={companyName?.trim() ? "text-apple-secondary" : "text-apple-text"}>
                Complete company profile
              </span>
              {!companyName?.trim() && (
                <Link href="/settings?tab=company" className="text-xs text-apple-blue hover:underline">
                  Set up
                </Link>
              )}
            </li>
            <li className="flex items-center gap-2 text-sm">
              <span className={oauthStatus && (oauthStatus.linkedin || oauthStatus.x_twitter) ? "text-green-500" : "text-apple-secondary"}>
                {oauthStatus && (oauthStatus.linkedin || oauthStatus.x_twitter) ? "✓" : "○"}
              </span>
              <span className={oauthStatus && (oauthStatus.linkedin || oauthStatus.x_twitter) ? "text-apple-secondary" : "text-apple-text"}>
                Connect a platform
              </span>
              {oauthStatus && !oauthStatus.linkedin && !oauthStatus.x_twitter && (
                <Link href="/settings?tab=platforms" className="text-xs text-apple-blue hover:underline">
                  Connect
                </Link>
              )}
            </li>
            <li className="flex items-center gap-2 text-sm">
              <span className={drafts > 0 ? "text-green-500" : "text-apple-secondary"}>
                {drafts > 0 ? "✓" : "○"}
              </span>
              <span className={drafts > 0 ? "text-apple-secondary" : "text-apple-text"}>
                First draft ready
              </span>
              {drafts === 0 && (pipelineStatus?.next_run_local ?? pipelineStatus?.next_run) && (
                <span className="text-xs text-apple-secondary">{pipelineStatus.next_run_local ?? pipelineStatus.next_run}</span>
              )}
            </li>
          </ul>
        </div>
      )}

      {metricsError && (
        <div className="mt-4">
          <Notice tone="warning">{metricsError}</Notice>
        </div>
      )}

      {billing && pipelineStatus && hasTierAccess(billing, "starter") && (
        <div className="mt-4 rounded-apple bg-apple-card p-5 shadow-apple">
          <h3 className="mb-3 text-sm font-semibold">Pipeline status</h3>
          {pipelineStatus.last_run ? (
            <div className="space-y-2 text-sm">
              <p className="text-apple-secondary">
                Last run:{" "}
                {pipelineStatus.last_run.completed_at
                  ? new Date(pipelineStatus.last_run.completed_at).toLocaleString(undefined, {
                      dateStyle: "medium",
                      timeStyle: "short",
                    })
                  : "—"}
              </p>
              <p className="text-apple-secondary">
                {pipelineStatus.last_run.drafts_generated ?? 0} drafts ·{" "}
                {pipelineStatus.last_run.signals_found ?? 0} signals ·{" "}
                {pipelineStatus.last_run.leads_qualified ?? 0} leads
              </p>
              {pipelineStatus.last_run.status === "skipped" &&
              pipelineStatus.last_run.skip_reason ? (
                <p className="text-xs text-apple-secondary">
                  Skipped: {pipelineStatus.last_run.skip_reason.replace(/_/g, " ")}
                </p>
              ) : null}
            </div>
          ) : (
            <p className="text-sm text-apple-secondary">
              No runs yet. {(pipelineStatus.next_run_local ?? pipelineStatus.next_run) ? `Next run: ${pipelineStatus.next_run_local ?? pipelineStatus.next_run}` : "Your first pipeline will run at your configured notification time."}
            </p>
          )}
          <p className="mt-2 text-xs text-apple-secondary">
            {pipelineStatus.next_run_local ?? pipelineStatus.next_run ?? "Calculating next run…"}
          </p>
          {(!pipelineStatus.last_run || (pipelineStatus.last_run.completed_at && (Date.now() - new Date(pipelineStatus.last_run.completed_at).getTime()) > 12 * 60 * 60 * 1000)) && (
            <button
              type="button"
              onClick={async () => {
                setPipelineTriggering(true);
                setPipelineTriggerMessage("");
                setPipelineTriggerError("");
                try {
                  const res = await apiFetch<{
                    ok?: boolean;
                    accepted?: boolean;
                    message?: string;
                  }>("/api/pipeline/trigger", { method: "POST" });
                  setPipelineTriggerMessage(
                    res.message ?? "Pipeline started. Status updates in a few seconds.",
                  );
                  window.dispatchEvent(new Event("drafts:changed"));
                  setTimeout(() => {
                    apiFetch<typeof pipelineStatus>("/api/pipeline/status").then(setPipelineStatus).catch(() => {});
                  }, 3000);
                } catch (e) {
                  const msg =
                    e instanceof ApiError
                      ? e.message
                      : e instanceof Error
                        ? e.message
                        : "Could not start the pipeline.";
                  setPipelineTriggerError(msg);
                } finally {
                  setPipelineTriggering(false);
                }
              }}
              disabled={pipelineTriggering}
              className="mt-3 rounded-apple-sm bg-apple-blue px-4 py-2 text-sm font-medium text-white hover:bg-apple-blue-hover disabled:opacity-50"
            >
              {pipelineTriggering ? "Running…" : "Run now"}
            </button>
          )}
          {pipelineTriggerMessage ? (
            <p className="mt-2 text-xs text-apple-secondary">{pipelineTriggerMessage}</p>
          ) : null}
          {pipelineTriggerError ? (
            <p className="mt-2 text-xs text-red-600 dark:text-red-400">{pipelineTriggerError}</p>
          ) : null}
        </div>
      )}

      {billing && usage?.usage && hasTierAccess(billing, "starter") && (
        <div className="mt-4 rounded-apple bg-apple-card p-5 shadow-apple">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="text-sm font-semibold">Today&apos;s usage</h3>
            <Link
              href="/billing"
              className="text-xs text-apple-blue hover:underline"
            >
              View details
            </Link>
          </div>
          <div className="space-y-3">
            {Object.entries(usage.usage || {})
              .filter(([, data]) => data && typeof data.limit === "number" && data.limit > 0 && typeof (data as { used?: number }).used === "number")
              .map(([action, data]) => {
              const used = (data?.used ?? 0) as number;
              const limit = (data?.limit ?? 0) as number;
              const pct = limit > 0 ? Math.min((used / limit) * 100, 100) : 0;
              const label = (usage as { labels?: Record<string, string> }).labels?.[action]
                ?? action.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
              return (
                <div key={action} className="flex items-center gap-3">
                  <span className="w-40 truncate text-xs text-apple-secondary">{label}</span>
                  <div className="flex-1 h-2 rounded-full bg-apple-bg overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all ${
                        pct >= 100 ? "bg-red-500" : pct >= 80 ? "bg-amber-400" : "bg-apple-blue"
                      }`}
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                  <span className="text-xs text-apple-secondary w-14 text-right">
                    {used}/{limit}
                  </span>
                </div>
              );
            })}
          </div>
          {Object.values(usage.usage || {}).some(
            (d) => typeof d?.percentage === "number" && d.percentage >= 80
          ) && (
            <p className="mt-2 text-xs text-amber-600">
              Near your daily limit.{" "}
              <Link href="/billing" className="underline">
                Upgrade to Pro
              </Link>{" "}
              for higher quotas.
            </p>
          )}
        </div>
      )}

      {billing && hasTierAccess(billing, "starter") && (
        <div className="mt-4 rounded-apple bg-apple-card p-5 shadow-apple">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-sm font-medium">Enabled channels</p>
              <p className="text-sm text-apple-secondary">
                IntoMarketing generates channel-specific variants for every saved draft pack.
              </p>
            </div>
            <p className="text-sm font-medium text-apple-secondary">
              {platforms.length} platform{platforms.length === 1 ? "" : "s"}
            </p>
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            {platforms.map((platform) => (
              <span
                key={platform}
                className="rounded-full bg-apple-bg px-3 py-1 text-xs font-medium text-apple-secondary"
              >
                {PLATFORM_BY_ID[platform].label}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
