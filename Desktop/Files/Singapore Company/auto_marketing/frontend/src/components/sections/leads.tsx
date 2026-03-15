"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import LockedState from "@/components/ui/locked-state";
import { hasTierAccess } from "@/lib/billing";
import type { BillingSummary, QualifiedLead } from "@/types";

interface LeadsSectionProps {
  billing: BillingSummary | null;
}

const COLUMNS = [
  { id: "new", label: "Qualified" },
  { id: "contacted", label: "Outreach Sent" },
  { id: "meeting_booked", label: "Meeting Booked" },
  { id: "negotiation", label: "Negotiation" },
  { id: "closed_won", label: "Won" },
  { id: "closed_lost", label: "Lost" },
];

const PAGE_SIZE = 20;

export default function LeadsSection({ billing }: LeadsSectionProps) {
  const [leads, setLeads] = useState<QualifiedLead[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState("");
  const [enrichingId, setEnrichingId] = useState<string | null>(null);

  useEffect(() => {
    if (!billing || !hasTierAccess(billing, "pro")) {
      setLeads([]);
      setNextCursor(null);
      setError("");
      setLoading(false);
      return;
    }

    apiFetch<{ leads?: QualifiedLead[]; next_cursor?: string }>(`/api/leads?limit=${PAGE_SIZE}`)
      .then((d) => {
        setLeads(d.leads || []);
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
      const d = await apiFetch<{ leads?: QualifiedLead[]; next_cursor?: string }>(
        `/api/leads?limit=${PAGE_SIZE}&cursor=${encodeURIComponent(nextCursor)}`
      );
      setLeads((prev) => [...prev, ...(d.leads || [])]);
      setNextCursor(d.next_cursor || null);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoadingMore(false);
    }
  }

  function fitColor(fit: string) {
    if (fit === "high") return "bg-green-100 text-green-700";
    if (fit === "medium") return "bg-yellow-100 text-yellow-700";
    return "bg-neutral-100 text-neutral-500";
  }

  const handleDragStart = (e: React.DragEvent, leadId: string) => {
    e.dataTransfer.setData("leadId", leadId);
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
  };

  const handleDrop = async (e: React.DragEvent, newStatus: string) => {
    e.preventDefault();
    const leadId = e.dataTransfer.getData("leadId");
    if (!leadId) return;
    setError("");
    const previousLeads = leads;
    setLeads((prev) => prev.map((lead) => (lead.id === leadId ? { ...lead, status: newStatus } : lead)));

    try {
      await apiFetch(`/api/leads/${leadId}`, {
        method: "PATCH",
        body: JSON.stringify({ status: newStatus }),
      });
    } catch (err: any) {
      setLeads(previousLeads);
      setError(err?.message || "Unable to update lead status.");
    }
  };

  async function handleSendOutreach(lead: QualifiedLead) {
    const targetEmail = lead.contact_email || "contact@example.com";
    const subject = encodeURIComponent(
      lead.draft_subject || `Outreach to ${lead.company_name || "your company"}`,
    );
    const body = encodeURIComponent(
      lead.draft_content || lead.suggested_outreach_angle || "Hi there,",
    );
    const mailtoLink = `mailto:${targetEmail}?subject=${subject}&body=${body}`;

    if (lead.id && lead.status === "new") {
      try {
        const timestamp = new Date().toISOString();
        await apiFetch(`/api/leads/${lead.id}`, {
          method: "PATCH",
          body: JSON.stringify({ status: "contacted", last_contacted_at: timestamp }),
        });
        setLeads((prev) =>
          prev.map((item) =>
            item.id === lead.id
              ? { ...item, status: "contacted", last_contacted_at: timestamp }
              : item,
          ),
        );
      } catch (err: any) {
        setError(err?.message || "Lead status could not be updated before opening outreach.");
      }
    }

    window.location.href = mailtoLink;
  }

  async function handleEnrich(lead: QualifiedLead) {
    if (!lead.id || !lead.contact_linkedin_url) return;
    setEnrichingId(lead.id);
    setError("");
    try {
      const updated = await apiFetch<QualifiedLead>(`/api/leads/${lead.id}/enrich`, { method: "POST" });
      setLeads((prev) =>
        prev.map((l) => (l.id === lead.id ? { ...l, ...updated } : l)),
      );
    } catch (err: any) {
      setError(err?.message || "Enrichment failed.");
    } finally {
      setEnrichingId(null);
    }
  }

  return (
    <section id="leads" className="scroll-mt-28">
      <h2 className="mb-4 text-xl font-semibold">Lead Pipeline</h2>

      {billing && !hasTierAccess(billing, "pro") ? (
        <LockedState
          description="Lead detection is available on the Pro plan."
          ctaLabel="Upgrade to Pro"
        />
      ) : loading ? (
        <p className="py-8 text-center text-sm text-apple-secondary">Loading&hellip;</p>
      ) : (
        <div className="space-y-3">
          {error && <p className="text-sm text-red-500">{error}</p>}
          <div className="flex gap-4 overflow-x-auto pb-4">
            {COLUMNS.map((col) => {
              const columnLeads = leads.filter((l) => (l.status || "new") === col.id);
              return (
                <div
                  key={col.id}
                  className="flex h-full min-h-[400px] w-80 shrink-0 flex-col rounded-xl bg-apple-bg p-3"
                  onDragOver={handleDragOver}
                  onDrop={(e) => handleDrop(e, col.id)}
                >
                  <div className="mb-3 flex items-center justify-between px-1">
                    <h3 className="text-sm font-semibold text-apple-secondary">{col.label}</h3>
                    <span className="rounded-full bg-apple-border/50 px-2 py-0.5 text-xs font-medium text-apple-secondary">
                      {columnLeads.length}
                    </span>
                  </div>
                  <div className="flex flex-col gap-3">
                    {columnLeads.map((lead, i) => {
                      return (
                        <div
                          key={lead.id || i}
                          draggable
                          onDragStart={(e) => handleDragStart(e, lead.id)}
                          className="cursor-grab rounded-apple bg-apple-card p-4 shadow-sm transition-shadow hover:shadow-apple active:cursor-grabbing"
                        >
                          <div className="flex items-start justify-between">
                            <div>
                              <h4 className="text-[15px] font-semibold">{lead.company_name || "Unknown"}</h4>
                              {(lead.draft_subject || lead.suggested_outreach_angle) && (
                                <p className="mt-1 line-clamp-2 text-xs text-apple-secondary">
                                  {lead.draft_subject || lead.suggested_outreach_angle}
                                </p>
                              )}
                            </div>
                            <span
                              className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${fitColor(
                                lead.icp_fit || "low"
                              )}`}
                            >
                              {lead.icp_fit || "low"} fit
                            </span>
                          </div>
                          <div className="mt-4 flex flex-wrap items-center gap-2">
                            <p className="text-xs text-apple-secondary">
                              Score: {Math.round((lead.icp_fit_score || 0) * 100)}%
                            </p>
                            {lead.contact_linkedin_url && lead.enrichment_status !== "completed" && (
                              <button
                                type="button"
                                className="rounded-full border border-apple-border bg-apple-card px-3 py-1.5 text-xs font-medium text-apple-text transition-colors hover:bg-apple-bg disabled:opacity-50"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  void handleEnrich(lead);
                                }}
                                disabled={enrichingId === lead.id}
                              >
                                {enrichingId === lead.id ? "Enriching…" : "Enrich"}
                              </button>
                            )}
                            <button
                              type="button"
                              className="rounded-full bg-apple-blue px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-apple-blue-hover"
                              onClick={(e) => {
                                e.stopPropagation();
                                void handleSendOutreach(lead);
                              }}
                            >
                              Send Outreach
                            </button>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
          {nextCursor && (
            <div className="mt-4 text-center">
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
