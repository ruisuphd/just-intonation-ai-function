"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import LockedState from "@/components/ui/locked-state";
import Notice from "@/components/ui/notice";
import { hasTierAccess } from "@/lib/billing";
import { PLATFORM_BY_ID, normalizePlatforms } from "@/lib/platforms";
import type { BillingSummary, DraftContent, PlatformId } from "@/types";

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

const PLATFORM_COLORS: Record<string, string> = {
  linkedin: "bg-blue-100 text-blue-700",
  x_twitter: "bg-neutral-200 text-neutral-700",
  instagram: "bg-pink-100 text-pink-700",
  google_business_profile: "bg-green-100 text-green-700",
  tiktok: "bg-violet-100 text-violet-700",
  xiaohongshu: "bg-rose-100 text-rose-700",
  newsletter: "bg-amber-100 text-amber-700",
};

function getWeekDates(): string[] {
  const now = new Date();
  const monday = new Date(now);
  monday.setDate(now.getDate() - ((now.getDay() + 6) % 7));
  return Array.from({ length: 7 }, (_, i) => {
    const d = new Date(monday);
    d.setDate(monday.getDate() + i);
    return d.toISOString().split("T")[0];
  });
}

interface CalendarSectionProps {
  billing: BillingSummary | null;
  platforms: PlatformId[];
}

interface NewsletterEvent {
  id: string;
  type: string;
  subject?: string;
}

export default function CalendarSection({ billing, platforms }: CalendarSectionProps) {
  const [drafts, setDrafts] = useState<DraftContent[]>([]);
  const [newslettersByDate, setNewslettersByDate] = useState<Record<string, NewsletterEvent[]>>({});
  const [error, setError] = useState("");
  const weekDates = getWeekDates();

  useEffect(() => {
    let cancelled = false;

    if (!billing || !hasTierAccess(billing, "starter")) {
      setDrafts([]);
      setNewslettersByDate({});
      setError("");
      return;
    }

    async function loadEvents() {
      try {
        const data = await apiFetch<{
          drafts?: DraftContent[];
          newsletters_by_date?: Record<string, NewsletterEvent[]>;
        }>("/api/calendar/events");
        if (!cancelled) {
          setDrafts(data.drafts || []);
          setNewslettersByDate(data.newsletters_by_date || {});
          setError("");
        }
      } catch (e: any) {
        if (!cancelled) {
          setError(e.message);
        }
      }
    }

    const handleChange = () => void loadEvents();
    void loadEvents();
    window.addEventListener("drafts:changed", handleChange);
    window.addEventListener("newsletters:changed", handleChange);

    return () => {
      cancelled = true;
      window.removeEventListener("drafts:changed", handleChange);
      window.removeEventListener("newsletters:changed", handleChange);
    };
  }, [billing]);

  const enabledPlatforms = new Set(platforms);
  const byDate: Record<string, (DraftContent | NewsletterEvent)[]> = {};
  for (const d of drafts) {
    const date = d.batch_date || "";
    if (!byDate[date]) byDate[date] = [];
    byDate[date].push(d);
  }
  for (const [date, items] of Object.entries(newslettersByDate)) {
    if (!byDate[date]) byDate[date] = [];
    byDate[date].push(...items);
  }

  const [draggedDraft, setDraggedDraft] = useState<DraftContent | null>(null);

  async function handleDrop(date: string) {
    if (!draggedDraft || !draggedDraft.id) return;
    if (draggedDraft.batch_date === date) {
      setDraggedDraft(null);
      return;
    }
    try {
      await apiFetch(`/api/drafts/${draggedDraft.id}/status`, {
        method: "PATCH",
        body: JSON.stringify({ batch_date: date }),
      });
      setDrafts((prev) =>
        prev.map((d) => (d.id === draggedDraft.id ? { ...d, batch_date: date } : d)),
      );
      window.dispatchEvent(new Event("drafts:changed"));
    } catch (e: any) {
      setError(e.message);
    } finally {
      setDraggedDraft(null);
    }
  }

  function getPlatformsForDraft(draft: DraftContent): PlatformId[] {
    const rawPlatforms =
      draft.platforms_generated && draft.platforms_generated.length > 0
        ? draft.platforms_generated
        : draft.platform
          ? [draft.platform]
          : [];
    if (rawPlatforms.length === 0) return [];
    return normalizePlatforms(rawPlatforms).filter((platform) => enabledPlatforms.has(platform));
  }

  return (
    <section>
      <h2 className="mb-4 text-xl font-semibold">Content Calendar</h2>

      {billing && !hasTierAccess(billing, "starter") ? (
        <LockedState
          description="The content calendar is available on the Starter and Pro plans."
          ctaLabel="Unlock Starter"
        />
      ) : (
        <>
          <div className="mb-4">
            <Notice tone="neutral">
              The calendar plans when drafts and newsletters run. Direct auto-post to every network is still in rollout;
              you can copy drafts out or use connected accounts where OAuth is enabled.
            </Notice>
          </div>
          {error && <p className="mb-3 text-sm text-red-500">{error}</p>}

          {drafts.length === 0 ? (
            <div className="rounded-apple bg-apple-card px-5 py-8 text-center shadow-apple">
              <p className="text-sm font-medium">No scheduled content yet</p>
              <p className="mt-1 text-sm text-apple-secondary">
                Generate your first post pack and it will appear here across your enabled channels.
              </p>
            </div>
          ) : (
            <>
              <div className="hidden sm:grid sm:grid-cols-7 sm:gap-2">
                {DAYS.map((day, i) => {
                  const dateStr = weekDates[i];
                  const suggestedTime = ["09:00 AM", "12:30 PM", "05:15 PM", "08:00 AM", "01:00 PM", "06:45 PM", "10:00 AM"][i % 7];

                  return (
                    <div key={day}>
                      <p className="mb-2 text-center text-xs font-medium text-apple-secondary">{day}</p>
                      <div
                        className="min-h-[120px] rounded-apple bg-apple-card p-2 shadow-apple transition-colors hover:bg-apple-border/10"
                        onDragOver={(e) => e.preventDefault()}
                        onDrop={() => handleDrop(dateStr)}
                      >
                        <div className="mb-2 flex items-center justify-between">
                          <p className="text-xs font-medium text-apple-secondary">{dateStr?.slice(5)}</p>
                          <span className="text-[10px] text-apple-blue" title="AI Suggested Time">✨ {suggestedTime}</span>
                        </div>
                        <div className="space-y-1">
                          {(byDate[dateStr] || []).map((item, j) =>
                            "platforms_generated" in item ? (
                              getPlatformsForDraft(item as DraftContent).map((platform) => (
                                <div
                                  key={`${item.id}-${platform}-${j}`}
                                  draggable
                                  onDragStart={() => setDraggedDraft(item as DraftContent)}
                                  className={`cursor-grab active:cursor-grabbing block truncate rounded px-1.5 py-1 text-xs shadow-sm ${PLATFORM_COLORS[platform] || "bg-neutral-100 text-neutral-600"}`}
                                >
                                  {PLATFORM_BY_ID[platform].shortLabel}
                                </div>
                              ))
                            ) : (
                              <div
                                key={`${item.id}-${j}`}
                                className={`block truncate rounded px-1.5 py-1 text-xs shadow-sm ${PLATFORM_COLORS.newsletter}`}
                              >
                                Newsletter
                              </div>
                            ),
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>

              <div className="space-y-2 sm:hidden">
                {DAYS.map((day, i) => {
                  const items = byDate[weekDates[i]] || [];
                  return (
                    <div key={day} className="flex items-start gap-3 rounded-apple bg-apple-card p-3 shadow-apple">
                      <div className="w-10 text-center">
                        <p className="text-xs font-medium text-apple-secondary">{day}</p>
                        <p className="text-lg font-semibold">{weekDates[i]?.slice(8)}</p>
                      </div>
                      <div className="flex flex-1 flex-wrap gap-1">
                        {items.length === 0 ? (
                          <span className="text-xs text-apple-secondary">&mdash;</span>
                        ) : (
                          items.flatMap((item, j) =>
                            "platforms_generated" in item
                              ? getPlatformsForDraft(item as DraftContent).map((platform) => (
                                  <span
                                    key={`${item.id}-${platform}-${j}`}
                                    className={`rounded px-1.5 py-0.5 text-xs ${PLATFORM_COLORS[platform] || "bg-neutral-100 text-neutral-600"}`}
                                  >
                                    {PLATFORM_BY_ID[platform].shortLabel}
                                  </span>
                                ))
                              : [
                                  <span
                                    key={`${item.id}-${j}`}
                                    className="rounded px-1.5 py-0.5 text-xs bg-amber-100 text-amber-700"
                                  >
                                    Newsletter
                                  </span>,
                                ],
                          )
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </>
          )}
        </>
      )}
    </section>
  );
}
