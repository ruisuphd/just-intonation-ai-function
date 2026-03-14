"use client";

import { useEffect, useState } from "react";
import Notice from "@/components/ui/notice";
import { apiFetch } from "@/lib/api";
import { hasTierAccess } from "@/lib/billing";
import { PLATFORM_BY_ID } from "@/lib/platforms";
import type { BillingSummary, PlatformId } from "@/types";

interface OverviewSectionProps {
  billing: BillingSummary | null;
  platforms: PlatformId[];
}

export default function OverviewSection({ billing, platforms }: OverviewSectionProps) {
  const [drafts, setDrafts] = useState(0);
  const [intel, setIntel] = useState(0);
  const [leads, setLeads] = useState<number | null>(null);
  const [starterLocked, setStarterLocked] = useState(false);
  const [leadsLocked, setLeadsLocked] = useState(false);
  const [metricsError, setMetricsError] = useState("");

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
        const data = await apiFetch<{ drafts?: unknown[] }>("/api/drafts?status=draft");
        if (!cancelled) {
          setDrafts(data.drafts?.length || 0);
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
  }, [billing]);

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

      {metricsError && (
        <div className="mt-4">
          <Notice tone="warning">{metricsError}</Notice>
        </div>
      )}

      {billing && hasTierAccess(billing, "starter") && (
        <div className="mt-4 rounded-apple bg-apple-card p-5 shadow-apple">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-sm font-medium">Enabled channels</p>
              <p className="text-sm text-apple-secondary">
                AutoMark generates channel-specific variants for every saved draft pack.
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
