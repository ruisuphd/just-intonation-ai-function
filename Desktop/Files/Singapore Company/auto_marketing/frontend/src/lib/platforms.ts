import type { DraftContent, PlatformId } from "@/types";

type PlatformDefinition = {
  id: PlatformId;
  label: string;
  shortLabel: string;
};

export const ALL_PLATFORMS: PlatformDefinition[] = [
  { id: "linkedin", label: "LinkedIn", shortLabel: "LinkedIn" },
  { id: "x_twitter", label: "X", shortLabel: "X" },
  { id: "instagram", label: "Instagram", shortLabel: "Instagram" },
  {
    id: "google_business_profile",
    label: "Google Business",
    shortLabel: "GBP",
  },
  { id: "tiktok", label: "TikTok", shortLabel: "TikTok" },
  { id: "xiaohongshu", label: "Xiaohongshu", shortLabel: "XHS" },
];

export const DEFAULT_ENABLED_PLATFORMS: PlatformId[] = [
  "linkedin",
  "x_twitter",
  "instagram",
  "google_business_profile",
];

export const PLATFORM_BY_ID: Record<PlatformId, PlatformDefinition> = ALL_PLATFORMS.reduce(
  (acc, platform) => {
    acc[platform.id] = platform;
    return acc;
  },
  {} as Record<PlatformId, PlatformDefinition>,
);

export function normalizePlatforms(platforms?: string[] | null): PlatformId[] {
  const seen = new Set<PlatformId>();
  const normalized: PlatformId[] = [];

  for (const raw of platforms || DEFAULT_ENABLED_PLATFORMS) {
    if (!raw || !(raw in PLATFORM_BY_ID)) continue;
    const platform = raw as PlatformId;
    if (seen.has(platform)) continue;
    seen.add(platform);
    normalized.push(platform);
  }

  return normalized.length > 0 ? normalized : [...DEFAULT_ENABLED_PLATFORMS];
}

export function getDraftText(draft: DraftContent, platform: PlatformId): string {
  const contentByPlatform = draft.content_by_platform?.[platform];
  if (contentByPlatform?.trim()) return contentByPlatform.trim();

  const fieldMap: Record<PlatformId, string | undefined> = {
    linkedin: draft.linkedin_post,
    x_twitter: draft.x_post,
    instagram: draft.instagram_caption,
    google_business_profile: draft.google_business_profile_post,
    tiktok: draft.tiktok_caption,
    xiaohongshu: draft.xiaohongshu_post,
  };
  const fieldText = fieldMap[platform];
  if (fieldText?.trim()) return fieldText.trim();

  if (draft.platform === platform && draft.text?.trim()) {
    return draft.text.trim();
  }
  return "";
}
