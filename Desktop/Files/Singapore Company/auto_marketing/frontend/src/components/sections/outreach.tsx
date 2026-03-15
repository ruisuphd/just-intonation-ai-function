"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import LockedState from "@/components/ui/locked-state";
import { hasTierAccess } from "@/lib/billing";
import type { BillingSummary } from "@/types";

interface OutreachSectionProps {
  billing: BillingSummary | null;
}

export default function OutreachSection({ billing }: OutreachSectionProps) {
  const [drafts, setDrafts] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!billing || !hasTierAccess(billing, "pro")) {
      setDrafts([]);
      setError("");
      setLoading(false);
      return;
    }

    apiFetch("/api/outreach")
      .then((d) => setDrafts(d.drafts || []))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [billing]);

  return (
    <section id="outreach" className="scroll-mt-28">
      <h2 className="mb-4 text-xl font-semibold">Outreach</h2>

      {billing && !hasTierAccess(billing, "pro") ? (
        <LockedState
          description="Outreach drafts are available on the Pro plan."
          ctaLabel="Upgrade to Pro"
        />
      ) : error ? (
        <p className="py-4 text-sm text-red-500">{error}</p>
      ) : loading ? (
        <p className="py-8 text-center text-sm text-apple-secondary">Loading&hellip;</p>
      ) : drafts.length === 0 ? (
        <p className="py-8 text-center text-sm text-apple-secondary">No outreach drafts yet.</p>
      ) : (
        <div className="space-y-3">
          {drafts.map((draft, i) => (
            <div key={draft.id || i} className="rounded-apple bg-apple-card p-5 shadow-apple">
              <div className="flex items-center justify-between">
                <h3 className="text-[15px] font-semibold">{draft.company_name || "Draft"}</h3>
                <span className="rounded-full bg-apple-bg px-2 py-0.5 text-xs text-apple-secondary capitalize">
                  {draft.draft_type?.replace("_", " ") || "outreach"}
                </span>
              </div>
              {draft.content?.subject && (
                <p className="mt-2 text-sm text-apple-text">{draft.content.subject}</p>
              )}
              {draft.content?.message && (
                <p className="mt-2 text-sm text-apple-text line-clamp-3">{draft.content.message}</p>
              )}
              <p className="mt-2 text-xs text-apple-secondary capitalize">{draft.status?.replace(/_/g, " ")}</p>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
