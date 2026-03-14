"use client";

import type { BillingSummary, SubscriptionTier } from "@/types";

const TIER_ORDER: Record<SubscriptionTier, number> = {
  free: 0,
  starter: 1,
  growth: 1,
  pro: 2,
};

export function hasTierAccess(
  billing: BillingSummary | null | undefined,
  requiredTier: SubscriptionTier,
): boolean {
  if (!billing) return false;
  return TIER_ORDER[billing.effective_tier] >= TIER_ORDER[requiredTier];
}

export function formatStarterAccessDate(
  billing: BillingSummary | null | undefined,
): string | null {
  if (!billing?.starter_access_expires_at) return null;
  const value = new Date(billing.starter_access_expires_at);
  if (Number.isNaN(value.getTime())) return null;
  return value.toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

export function planBadgeLabel(
  billing: BillingSummary | null | undefined,
): string {
  if (!billing) return "Loading";
  if (billing.is_internal) return "Internal";
  if (billing.access_source === "starter_access") return "Starter trial";
  if (billing.has_paid_subscription) {
    return billing.subscription_tier[0].toUpperCase() + billing.subscription_tier.slice(1);
  }
  return billing.effective_tier[0].toUpperCase() + billing.effective_tier.slice(1);
}
