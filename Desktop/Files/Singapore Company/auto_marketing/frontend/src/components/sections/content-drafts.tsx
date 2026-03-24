"use client";

import { useCallback, useEffect, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { apiFetch } from "@/lib/api";
import LockedState from "@/components/ui/locked-state";
import Notice from "@/components/ui/notice";
import CopyButton from "@/components/ui/copy-button";
import { useToast } from "@/components/ui/toast";
import { hasTierAccess } from "@/lib/billing";
import {
  ALL_PLATFORMS,
  PLATFORM_BY_ID,
  getDraftText,
  normalizePlatforms,
} from "@/lib/platforms";
import type { BillingSummary, DraftContent, PlatformId } from "@/types";

interface ContentDraftsSectionProps {
  billing: BillingSummary | null;
  platforms: PlatformId[];
}

interface EditDraftFormProps {
  draft: DraftContent;
  enabledPlatforms: PlatformId[];
  onSave: (data: {
    headline: string;
    content_by_platform: Record<string, string>;
    hashtags: string[];
    why_it_matters: string;
  }) => void;
  onCancel: () => void;
  onDirtyChange?: (dirty: boolean) => void;
}

function EditDraftForm({ draft, enabledPlatforms, onSave, onCancel, onDirtyChange }: EditDraftFormProps) {
  const [headline, setHeadline] = useState(draft.headline || "");
  const [contentByPlatform, setContentByPlatform] = useState<Record<string, string>>(() => {
    const init: Record<string, string> = {};
    for (const p of enabledPlatforms) {
      init[p] = getDraftText(draft, p);
    }
    return init;
  });
  const [hashtags, setHashtags] = useState(draft.hashtags?.join(" ") || "");
  const [whyItMatters, setWhyItMatters] = useState(draft.why_it_matters || "");

  const initialSnapshot = JSON.stringify({
    headline: draft.headline || "",
    ...Object.fromEntries(enabledPlatforms.map((p) => [p, getDraftText(draft, p)])),
    hashtags: draft.hashtags?.join(" ") || "",
    why_it_matters: draft.why_it_matters || "",
  });
  const currentSnapshot = JSON.stringify({
    headline,
    ...contentByPlatform,
    hashtags,
    why_it_matters: whyItMatters,
  });
  const isDirty = initialSnapshot !== currentSnapshot;

  useEffect(() => {
    onDirtyChange?.(isDirty);
  }, [isDirty, onDirtyChange]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const cp: Record<string, string> = {};
    for (const p of enabledPlatforms) {
      const v = contentByPlatform[p]?.trim();
      if (v) cp[p] = v;
    }
    onDirtyChange?.(false);
    onSave({
      headline: headline.trim(),
      content_by_platform: cp,
      hashtags: hashtags.trim() ? hashtags.trim().split(/\s+/).filter(Boolean) : [],
      why_it_matters: whyItMatters.trim(),
    });
  };

  return (
    <form onSubmit={handleSubmit}>
      <Dialog.Title className="mb-4 text-lg font-semibold">Edit draft</Dialog.Title>
      <div className="space-y-4">
        <div>
          <label className="mb-1 block text-sm font-medium text-apple-text">Headline</label>
          <input
            type="text"
            value={headline}
            onChange={(e) => setHeadline(e.target.value)}
            className="w-full rounded-apple-sm border border-apple-border px-3 py-2 text-sm"
          />
        </div>
        {enabledPlatforms.map((platformId) => (
          <div key={platformId}>
            <label className="mb-1 block text-sm font-medium text-apple-text">
              {PLATFORM_BY_ID[platformId]?.label ?? platformId}
            </label>
            <textarea
              value={contentByPlatform[platformId] ?? ""}
              onChange={(e) =>
                setContentByPlatform((prev) => ({ ...prev, [platformId]: e.target.value }))
              }
              rows={3}
              className="w-full rounded-apple-sm border border-apple-border px-3 py-2 text-sm"
            />
          </div>
        ))}
        <div>
          <label className="mb-1 block text-sm font-medium text-apple-text">Hashtags</label>
          <input
            type="text"
            value={hashtags}
            onChange={(e) => setHashtags(e.target.value)}
            placeholder="#tag1 #tag2"
            className="w-full rounded-apple-sm border border-apple-border px-3 py-2 text-sm"
          />
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium text-apple-text">
            Why it matters
          </label>
          <textarea
            value={whyItMatters}
            onChange={(e) => setWhyItMatters(e.target.value)}
            rows={2}
            className="w-full rounded-apple-sm border border-apple-border px-3 py-2 text-sm"
          />
        </div>
      </div>
      <div className="mt-6 flex justify-end gap-2">
        <button
          type="button"
          onClick={onCancel}
          className="rounded-apple-sm border border-apple-border px-4 py-2 text-sm font-medium text-apple-text hover:bg-apple-bg"
        >
          Cancel
        </button>
        <button
          type="submit"
          className="rounded-apple-sm bg-apple-blue px-4 py-2 text-sm font-medium text-white hover:bg-apple-blue-hover"
        >
          Save
        </button>
      </div>
    </form>
  );
}

function sortDrafts(items: DraftContent[]): DraftContent[] {
  return [...items].sort((a, b) => {
    const aTime = new Date(a.created_at || a.updated_at || a.batch_date).getTime();
    const bTime = new Date(b.created_at || b.updated_at || b.batch_date).getTime();
    return bTime - aTime;
  });
}

export default function ContentDraftsSection({
  billing,
  platforms,
}: ContentDraftsSectionProps) {
  const enabledPlatforms = normalizePlatforms(platforms);
  const [drafts, setDrafts] = useState<DraftContent[]>([]);
  const [platform, setPlatform] = useState<PlatformId>(enabledPlatforms[0]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [generating, setGenerating] = useState(false);
  const [editingDraft, setEditingDraft] = useState<DraftContent | null>(null);
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);
  const [regeneratingId, setRegeneratingId] = useState<string | null>(null);
  const [votedThumbs, setVotedThumbs] = useState<Record<string, "up" | "down">>({});
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [editFormDirty, setEditFormDirty] = useState(false);
  const [discardConfirmOpen, setDiscardConfirmOpen] = useState(false);
  const [pendingDiscardAction, setPendingDiscardAction] = useState<(() => void) | null>(null);
  const { toast } = useToast();

  function requestDiscard(action: () => void) {
    setPendingDiscardAction(() => action);
    setDiscardConfirmOpen(true);
  }

  function confirmDiscard() {
    pendingDiscardAction?.();
    setPendingDiscardAction(null);
    setDiscardConfirmOpen(false);
    setEditFormDirty(false);
    setEditingDraft(null);
  }

  useEffect(() => {
    if (!enabledPlatforms.includes(platform)) {
      setPlatform(enabledPlatforms[0]);
    }
  }, [enabledPlatforms, platform]);

  const fetchDrafts = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await apiFetch<{ drafts?: DraftContent[]; next_cursor?: string }>(
        "/api/drafts?status=draft&limit=20"
      );
      const draftList = sortDrafts(data.drafts || []);
      setDrafts(draftList);
      setNextCursor(data.next_cursor || null);
      setVotedThumbs((prev) => {
        const next = { ...prev };
        for (const d of draftList) {
          if (d.id && d.feedback_thumbs) {
            next[d.id] = d.feedback_thumbs;
          }
        }
        return next;
      });
    } catch (e: any) {
      setError(e.message === "Failed to fetch" ? "Unable to reach the server. Please try refreshing the page." : e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  async function handleLoadMore() {
    if (!nextCursor || loadingMore) return;
    setLoadingMore(true);
    setError("");
    try {
      const data = await apiFetch<{ drafts?: DraftContent[]; next_cursor?: string }>(
        `/api/drafts?status=draft&limit=20&cursor=${encodeURIComponent(nextCursor)}`
      );
      setDrafts((prev) => sortDrafts([...prev, ...(data.drafts || [])]));
      setNextCursor(data.next_cursor || null);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoadingMore(false);
    }
  }

  useEffect(() => {
    if (billing && hasTierAccess(billing, "starter")) {
      fetchDrafts();
      return;
    }
    setDrafts([]);
    setLoading(false);
  }, [billing, fetchDrafts]);

  async function handleGenerate() {
    setGenerating(true);
    setError("");
    try {
      const result = await apiFetch<DraftContent>("/api/drafts/quick-generate", {
        method: "POST",
        body: JSON.stringify({ platform }),
      });
      setDrafts((prev) =>
        sortDrafts([result, ...prev.filter((draft) => draft.id !== result.id)]),
      );
      window.dispatchEvent(new Event("drafts:changed"));
    } catch (e: any) {
      setError(e.message);
    } finally {
      setGenerating(false);
    }
  }

  async function handleSchedule(draft: DraftContent) {
    if (!draft.id) return;
    setError("");
    try {
      await apiFetch(`/api/drafts/${draft.id}/status`, {
        method: "PATCH",
        body: JSON.stringify({
          status: "scheduled",
          batch_date: draft.batch_date,
        }),
      });
      setDrafts((prev) => prev.filter((d) => d.id !== draft.id));
      window.dispatchEvent(new Event("drafts:changed"));
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function handleDelete(draft: DraftContent) {
    if (!draft.id) return;
    if (deleteConfirmId !== draft.id) {
      setDeleteConfirmId(draft.id);
      return;
    }
    setError("");
    try {
      await apiFetch(`/api/drafts/${draft.id}`, { method: "DELETE" });
      setDrafts((prev) => prev.filter((d) => d.id !== draft.id));
      setDeleteConfirmId(null);
      window.dispatchEvent(new Event("drafts:changed"));
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function handleRegenerate(draft: DraftContent) {
    if (!draft.id) return;
    setRegeneratingId(draft.id);
    setError("");
    try {
      const result = await apiFetch<DraftContent>(`/api/drafts/${draft.id}/regenerate`, {
        method: "POST",
      });
      setDrafts((prev) =>
        sortDrafts(prev.map((d) => (d.id === draft.id ? result : d)))
      );
      window.dispatchEvent(new Event("drafts:changed"));
      toast("Draft regenerated", "success");
    } catch (e: any) {
      setError(e.message);
      toast("Couldn't regenerate — try again", "error");
    } finally {
      setRegeneratingId(null);
    }
  }

  async function handleFeedback(draft: DraftContent, thumbs: "up" | "down") {
    if (!draft.id || votedThumbs[draft.id]) return;
    try {
      await apiFetch(`/api/drafts/${draft.id}/feedback`, {
        method: "POST",
        body: JSON.stringify({ thumbs }),
      });
      setVotedThumbs((prev) => ({ ...prev, [draft.id!]: thumbs }));
      toast("Thanks for your feedback", "success");
    } catch {
      toast("Feedback could not be saved", "error");
    }
  }

  async function handleEditSave(formData: {
    headline: string;
    content_by_platform: Record<string, string>;
    hashtags: string[];
    why_it_matters: string;
  }) {
    if (!editingDraft?.id) return;
    setError("");
    try {
      const result = await apiFetch<{ draft: DraftContent }>(
        `/api/drafts/${editingDraft.id}`,
        {
          method: "PATCH",
          body: JSON.stringify({
            headline: formData.headline,
            content_by_platform: formData.content_by_platform,
            hashtags: formData.hashtags,
            why_it_matters: formData.why_it_matters,
          }),
        }
      );
      setDrafts((prev) =>
        sortDrafts(
          prev.map((d) => (d.id === editingDraft.id ? { ...d, ...result.draft } : d))
        )
      );
      setEditingDraft(null);
      window.dispatchEvent(new Event("drafts:changed"));
    } catch (e: any) {
      setError(e.message);
    }
  }

  const visibleDrafts = drafts.filter((draft) => {
    const rawPlatforms =
      draft.platforms_generated && draft.platforms_generated.length > 0
        ? draft.platforms_generated
        : draft.platform
          ? [draft.platform]
          : [];
    const draftPlatforms =
      rawPlatforms.length > 0 ? normalizePlatforms(rawPlatforms) : [];
    return draftPlatforms.includes(platform) && Boolean(getDraftText(draft, platform));
  });

  return (
    <section>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold">Content Drafts</h2>
          <p className="text-sm text-apple-secondary">
            Each pack includes channel-specific copy for your enabled platforms. Publishing may be manual or via
            integrations as we ship them.
          </p>
        </div>
        {billing && hasTierAccess(billing, "starter") && (
          <button
            onClick={handleGenerate}
            disabled={generating}
            className="rounded-apple-sm bg-apple-blue px-4 py-2 text-sm font-medium text-white hover:bg-apple-blue-hover disabled:opacity-50"
          >
            {generating ? "Generating..." : "Write a post"}
          </button>
        )}
      </div>

      {billing && !hasTierAccess(billing, "starter") && (
        <LockedState
          description="Content drafts are available on the Starter and Pro plans."
          ctaLabel="Unlock Starter"
        />
      )}

      {billing && !hasTierAccess(billing, "starter") ? null : (
        <>
          <div className="mb-4">
            <Notice tone="neutral">
              Drafts are production-ready text and assets. Auto-publish to all six channels is not guaranteed yet—copy
              to your tools or use linked accounts where available.
            </Notice>
          </div>
          <div className="mb-4 flex gap-1 overflow-x-auto rounded-apple-sm bg-apple-card p-1 shadow-apple [scrollbar-width:none] [-ms-overflow-style:none] [&::-webkit-scrollbar]:hidden">
            {ALL_PLATFORMS.filter((item) => enabledPlatforms.includes(item.id)).map((item) => (
              <button
                key={item.id}
                onClick={() => setPlatform(item.id)}
                className={`whitespace-nowrap rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                  platform === item.id
                    ? "bg-apple-text text-white"
                    : "text-apple-secondary hover:bg-apple-bg"
                }`}
              >
                {item.label}
              </button>
            ))}
          </div>

          {error && <p className="mb-3 text-sm text-red-500">{error}</p>}

          {loading ? (
            <p className="py-8 text-center text-sm text-apple-secondary">Loading...</p>
          ) : visibleDrafts.length === 0 ? (
            <div className="rounded-apple bg-apple-card px-5 py-8 text-center shadow-apple">
              <p className="text-sm font-medium">
                No {PLATFORM_BY_ID[platform].label} drafts yet
              </p>
              <p className="mt-1 text-sm text-apple-secondary">
                Click &quot;Write a post&quot; to generate a reusable draft pack for your enabled
                channels.
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              {visibleDrafts.map((draft, index) => {
                const text = getDraftText(draft, platform);
                return (
                  <div
                    key={draft.id || index}
                    className="rounded-apple bg-apple-card p-5 shadow-apple"
                  >
                    {draft.image_url && (
                      <div className="mb-3">
                        <img
                          src={draft.image_url}
                          alt=""
                          className="max-h-48 rounded-apple-sm object-cover"
                        />
                      </div>
                    )}
                    {draft.headline && (
                      <p className="mb-2 text-sm font-semibold">{draft.headline}</p>
                    )}
                    <div className="flex items-start justify-between gap-3">
                      <p className="whitespace-pre-wrap text-[15px] leading-relaxed text-apple-text flex-1">
                        {text}
                      </p>
                      <CopyButton text={text} label="post" className="flex-shrink-0 mt-0.5" />
                    </div>
                    <div className="mt-3 flex items-center gap-4 text-xs text-apple-secondary">
                      <span>{text.length} chars</span>
                      {draft.hashtags?.length > 0 && <span>{draft.hashtags.join(" ")}</span>}
                    </div>
                    {draft.why_it_matters && (
                      <p className="mt-3 text-sm text-apple-secondary">
                        {draft.why_it_matters}
                      </p>
                    )}
                    <div className="mt-3 flex flex-wrap items-center gap-2">
                      <button
                        onClick={() => handleSchedule(draft)}
                        className="rounded-apple-sm bg-apple-blue px-4 py-1.5 text-xs font-medium text-white hover:bg-apple-blue-hover"
                      >
                        Approve & Schedule
                      </button>
                      <button
                        onClick={() => setEditingDraft(draft)}
                        className="rounded-apple-sm border border-apple-border px-4 py-1.5 text-xs font-medium text-apple-text hover:bg-apple-bg"
                      >
                        Edit
                      </button>
                      <button
                        onClick={() => handleRegenerate(draft)}
                        disabled={regeneratingId === draft.id}
                        className="rounded-apple-sm border border-apple-border px-4 py-1.5 text-xs font-medium text-apple-text hover:bg-apple-bg disabled:opacity-50"
                      >
                        {regeneratingId === draft.id ? "Regenerating..." : "Regenerate"}
                      </button>
                      <span className="mx-1 text-apple-border">|</span>
                      <div className="flex gap-1">
                        <button
                          onClick={() => handleFeedback(draft, "up")}
                          disabled={!!votedThumbs[draft.id || ""]}
                          className={`rounded p-1 ${votedThumbs[draft.id || ""] ? "opacity-50 cursor-not-allowed" : "hover:bg-apple-bg"} ${(votedThumbs[draft.id || ""] || (draft as { feedback_thumbs?: string }).feedback_thumbs) === "up" ? "text-green-600 bg-green-50" : "text-apple-secondary hover:text-green-600"}`}
                          aria-label="Good"
                        >
                          &#x1F44D;
                        </button>
                        <button
                          onClick={() => handleFeedback(draft, "down")}
                          disabled={!!votedThumbs[draft.id || ""]}
                          className={`rounded p-1 ${votedThumbs[draft.id || ""] ? "opacity-50 cursor-not-allowed" : "hover:bg-apple-bg"} ${(votedThumbs[draft.id || ""] || (draft as { feedback_thumbs?: string }).feedback_thumbs) === "down" ? "text-red-500 bg-red-50" : "text-apple-secondary hover:text-red-500"}`}
                          aria-label="Poor"
                        >
                          &#x1F44E;
                        </button>
                      </div>
                      {deleteConfirmId === draft.id ? (
                        <>
                          <button
                            onClick={() => handleDelete(draft)}
                            className="rounded-apple-sm border border-red-500 px-4 py-1.5 text-xs font-medium text-red-500 hover:bg-red-50"
                          >
                            Confirm delete
                          </button>
                          <button
                            onClick={() => setDeleteConfirmId(null)}
                            className="rounded-apple-sm border border-apple-border px-4 py-1.5 text-xs font-medium text-apple-secondary hover:bg-apple-bg"
                          >
                            Cancel
                          </button>
                        </>
                      ) : (
                        <button
                          onClick={() => handleDelete(draft)}
                          className="rounded-apple-sm border border-apple-border px-4 py-1.5 text-xs font-medium text-apple-secondary hover:bg-apple-bg"
                        >
                          Delete
                        </button>
                      )}
                      <button
                        onClick={handleGenerate}
                        className="rounded-apple-sm border border-apple-border px-4 py-1.5 text-xs font-medium text-apple-text hover:bg-apple-bg"
                      >
                        Generate another
                      </button>
                    </div>
                  </div>
                );
              })}
              {nextCursor && (
                <button
                  onClick={handleLoadMore}
                  disabled={loadingMore}
                  className="mt-4 w-full rounded-apple-sm border border-apple-border py-2 text-sm font-medium text-apple-secondary hover:bg-apple-bg disabled:opacity-50"
                >
                  {loadingMore ? "Loading..." : "Load more drafts"}
                </button>
              )}
            </div>
          )}
        </>
      )}

      <Dialog.Root
        open={!!editingDraft}
        onOpenChange={(o) => {
          if (!o) {
            if (editFormDirty) {
              requestDiscard(() => {});
            } else {
              setEditingDraft(null);
            }
          }
        }}
      >
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-40 bg-black/50" />
          <Dialog.Content
            className="fixed left-1/2 top-1/2 z-50 w-full max-w-lg -translate-x-1/2 -translate-y-1/2 rounded-apple bg-white p-6 shadow-apple"
            onPointerDownOutside={(e) => {
              if (editFormDirty) {
                e.preventDefault();
                requestDiscard(() => {});
              }
            }}
            onEscapeKeyDown={(e) => {
              if (editFormDirty) {
                e.preventDefault();
                requestDiscard(() => {});
              }
            }}
          >
            {editingDraft && (
              <EditDraftForm
                draft={editingDraft}
                enabledPlatforms={enabledPlatforms}
                onSave={handleEditSave}
                onCancel={() => {
                  if (editFormDirty) {
                    requestDiscard(() => {});
                  } else {
                    setEditingDraft(null);
                  }
                }}
                onDirtyChange={setEditFormDirty}
              />
            )}
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>

      <Dialog.Root open={discardConfirmOpen} onOpenChange={setDiscardConfirmOpen}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-[70] bg-black/50" />
          <Dialog.Content className="fixed left-1/2 top-1/2 z-[71] w-full max-w-sm -translate-x-1/2 -translate-y-1/2 rounded-apple bg-white p-6 shadow-apple">
            <Dialog.Title className="text-lg font-semibold">Discard unsaved changes?</Dialog.Title>
            <p className="mt-2 text-sm text-apple-secondary">Your edits will not be saved.</p>
            <div className="mt-6 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => { setDiscardConfirmOpen(false); setPendingDiscardAction(null); }}
                className="rounded-apple-sm border border-apple-border px-4 py-2 text-sm font-medium text-apple-text hover:bg-apple-bg"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={confirmDiscard}
                className="rounded-apple-sm bg-red-500 px-4 py-2 text-sm font-medium text-white hover:bg-red-600"
              >
                Discard
              </button>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </section>
  );
}
