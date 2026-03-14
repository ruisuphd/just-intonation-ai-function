"use client";

import { useCallback, useEffect, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { apiFetch } from "@/lib/api";
import LockedState from "@/components/ui/locked-state";
import { hasTierAccess } from "@/lib/billing";
import type { BillingSummary } from "@/types";

interface NewsletterItem {
  id: string;
  subject?: string;
  preview_text?: string;
  html_body?: string;
  plain_body?: string;
  week_start?: string;
  intel_count?: number;
  status?: string;
  created_at?: string;
}

interface NewsletterSectionProps {
  billing: BillingSummary | null;
}

export default function NewsletterSection({ billing }: NewsletterSectionProps) {
  const [newsletters, setNewsletters] = useState<NewsletterItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [generating, setGenerating] = useState(false);
  const [previewItem, setPreviewItem] = useState<NewsletterItem | null>(null);
  const [scheduleItem, setScheduleItem] = useState<NewsletterItem | null>(null);
  const [scheduleDate, setScheduleDate] = useState("");
  const [scheduleTime, setScheduleTime] = useState("09:00");
  const [scheduling, setScheduling] = useState(false);
  const [success, setSuccess] = useState("");

  const fetchNewsletters = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await apiFetch<{ newsletters?: NewsletterItem[] }>("/api/newsletters");
      setNewsletters(data.newsletters || []);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (billing && hasTierAccess(billing, "pro")) {
      fetchNewsletters();
      return;
    }
    setNewsletters([]);
    setLoading(false);
  }, [billing, fetchNewsletters]);

  useEffect(() => {
    const handler = () => void fetchNewsletters();
    window.addEventListener("newsletters:changed", handler);
    return () => window.removeEventListener("newsletters:changed", handler);
  }, [fetchNewsletters]);

  async function handleGenerate() {
    setGenerating(true);
    setError("");
    setSuccess("");
    try {
      const res = await apiFetch<{ status?: string; reason?: string }>(
        "/api/newsletters/generate",
        { method: "POST" }
      );
      if (res?.status === "skipped" && res.reason) {
        setError(res.reason);
      } else {
        await fetchNewsletters();
        window.dispatchEvent(new Event("newsletters:changed"));
      }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setGenerating(false);
    }
  }

  async function handleSchedule() {
    if (!scheduleItem?.id || !scheduleDate || !scheduleTime) return;
    const scheduledAt = `${scheduleDate}T${scheduleTime}:00Z`;
    if (new Date(scheduledAt) <= new Date()) {
      setError("Scheduled date must be in the future.");
      return;
    }
    setScheduling(true);
    setError("");
    setSuccess("");
    try {
      await apiFetch("/api/newsletters/schedule", {
        method: "POST",
        body: JSON.stringify({
          newsletter_id: scheduleItem.id,
          scheduled_at: scheduledAt,
          platform: "ghost",
        }),
      });
      setScheduleItem(null);
      setScheduleDate("");
      setScheduleTime("09:00");
      setSuccess("Newsletter scheduled successfully.");
      await fetchNewsletters();
      window.dispatchEvent(new Event("newsletters:changed"));
    } catch (e: any) {
      setError(e.message);
    } finally {
      setScheduling(false);
    }
  }

  const draftItems = newsletters.filter(
    (n) => n.status === "draft" || !n.status || n.status === "scheduled"
  );

  return (
    <section id="newsletter" className="scroll-mt-28">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold">Email Newsletter</h2>
          <p className="text-sm text-apple-secondary">
            Weekly digest from your top intelligence. Generate, preview, and schedule to Ghost.
          </p>
        </div>
        {billing && hasTierAccess(billing, "pro") && (
          <button
            onClick={handleGenerate}
            disabled={generating}
            className="rounded-apple-sm bg-apple-blue px-4 py-2 text-sm font-medium text-white hover:bg-apple-blue-hover disabled:opacity-50"
          >
            {generating ? "Generating..." : "Generate newsletter"}
          </button>
        )}
      </div>

      {billing && !hasTierAccess(billing, "pro") ? (
        <LockedState
          description="Email newsletter is available on the Pro plan."
          ctaLabel="Upgrade to Pro"
        />
      ) : (
        <>
          {success && <p className="mb-3 text-sm text-green-600">{success}</p>}
          {error && <p className="mb-3 text-sm text-red-500">{error}</p>}

          {loading ? (
            <p className="py-8 text-center text-sm text-apple-secondary">Loading...</p>
          ) : draftItems.length === 0 ? (
            <div className="rounded-apple bg-apple-card px-5 py-8 text-center shadow-apple">
              <p className="text-sm font-medium">No newsletters yet</p>
              <p className="mt-1 text-sm text-apple-secondary">
                Click &quot;Generate newsletter&quot; to create a weekly digest from your
                intelligence.
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              {draftItems.map((item) => (
                <div
                  key={item.id}
                  className="rounded-apple bg-apple-card p-5 shadow-apple"
                >
                  <p className="mb-1 text-sm font-semibold">{item.subject || "Untitled"}</p>
                  {item.preview_text && (
                    <p className="mb-2 line-clamp-2 text-sm text-apple-secondary">
                      {item.preview_text}
                    </p>
                  )}
                  <div className="flex flex-wrap items-center gap-3 text-xs text-apple-secondary">
                    {item.week_start && <span>Week of {item.week_start}</span>}
                    {item.intel_count != null && (
                      <span>{item.intel_count} intel items</span>
                    )}
                    {item.status && (
                      <span className="rounded bg-apple-bg px-1.5 py-0.5">{item.status}</span>
                    )}
                  </div>
                  <div className="mt-3 flex gap-2">
                    <button
                      onClick={() => setPreviewItem(item)}
                      className="rounded-apple-sm border border-apple-border px-4 py-1.5 text-xs font-medium text-apple-text hover:bg-apple-bg"
                    >
                      Preview
                    </button>
                    {(item.status === "draft" || !item.status) && (
                      <button
                        onClick={() => {
                          setScheduleItem(item);
                          const d = new Date();
                          d.setDate(d.getDate() + 1);
                          setScheduleDate(d.toISOString().split("T")[0]);
                        }}
                        className="rounded-apple-sm bg-apple-blue px-4 py-1.5 text-xs font-medium text-white hover:bg-apple-blue-hover"
                      >
                        Schedule
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}

      <Dialog.Root
        open={!!previewItem}
        onOpenChange={(o) => !o && setPreviewItem(null)}
      >
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-40 bg-black/50" />
          <Dialog.Content className="fixed left-1/2 top-1/2 z-50 max-h-[85vh] w-full max-w-2xl -translate-x-1/2 -translate-y-1/2 overflow-auto rounded-apple bg-white p-6 shadow-apple">
            {previewItem && (
              <>
                <Dialog.Title className="mb-4 text-lg font-semibold">
                  {previewItem.subject || "Preview"}
                </Dialog.Title>
                {previewItem.preview_text && (
                  <p className="mb-4 text-sm text-apple-secondary">{previewItem.preview_text}</p>
                )}
                {previewItem.html_body ? (
                  <div
                    className="prose prose-sm mb-4 max-w-none rounded-apple-sm border border-apple-border bg-apple-bg p-4"
                    dangerouslySetInnerHTML={{ __html: previewItem.html_body }}
                  />
                ) : previewItem.plain_body ? (
                  <pre className="mb-4 max-h-96 overflow-auto whitespace-pre-wrap rounded-apple-sm border border-apple-border bg-apple-bg p-4 text-sm">
                    {previewItem.plain_body}
                  </pre>
                ) : (
                  <p className="mb-4 text-sm text-apple-secondary">No content body available.</p>
                )}
                <button
                  type="button"
                  onClick={() => setPreviewItem(null)}
                  className="rounded-apple-sm border border-apple-border px-4 py-2 text-sm font-medium text-apple-text hover:bg-apple-bg"
                >
                  Close
                </button>
              </>
            )}
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>

      <Dialog.Root
        open={!!scheduleItem}
        onOpenChange={(o) => {
          if (!o) {
            setScheduleItem(null);
            setError("");
          }
        }}
      >
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-40 bg-black/50" />
          <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-full max-w-sm -translate-x-1/2 -translate-y-1/2 rounded-apple bg-white p-6 shadow-apple">
            {scheduleItem && (
              <>
                <Dialog.Title className="mb-4 text-lg font-semibold">
                  Schedule newsletter
                </Dialog.Title>
                <div className="space-y-4">
                  <div>
                    <label className="mb-1 block text-sm font-medium text-apple-text">
                      Date
                    </label>
                    <input
                      type="date"
                      value={scheduleDate}
                      onChange={(e) => setScheduleDate(e.target.value)}
                      className="w-full rounded-apple-sm border border-apple-border px-3 py-2 text-sm"
                    />
                  </div>
                  <div>
                    <label className="mb-1 block text-sm font-medium text-apple-text">
                      Time (UTC)
                    </label>
                    <input
                      type="time"
                      value={scheduleTime}
                      onChange={(e) => setScheduleTime(e.target.value)}
                      className="w-full rounded-apple-sm border border-apple-border px-3 py-2 text-sm"
                    />
                  </div>
                </div>
                <div className="mt-6 flex justify-end gap-2">
                  <button
                    type="button"
                    onClick={() => setScheduleItem(null)}
                    className="rounded-apple-sm border border-apple-border px-4 py-2 text-sm font-medium text-apple-text hover:bg-apple-bg"
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    onClick={handleSchedule}
                    disabled={scheduling || !scheduleDate || !scheduleTime}
                    className="rounded-apple-sm bg-apple-blue px-4 py-2 text-sm font-medium text-white hover:bg-apple-blue-hover disabled:opacity-50"
                  >
                    {scheduling ? "Scheduling..." : "Schedule"}
                  </button>
                </div>
              </>
            )}
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </section>
  );
}
