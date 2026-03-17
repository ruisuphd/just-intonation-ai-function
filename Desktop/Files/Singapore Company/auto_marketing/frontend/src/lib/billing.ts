"use client";

import type { BillingSummary } from "@/types";

const TIER_ORDER: Record<string, number> = {
  starter: 0,
  pro: 1,
};

export function hasTierAccess(
  billing: BillingSummary | null | undefined,
  requiredTier: string,
): boolean {
  if (!billing) return false;
  const current = TIER_ORDER[billing.effective_tier] ?? 0;
  const required = TIER_ORDER[requiredTier] ?? 0;
  return current >= required;
}

export function planBadgeLabel(
  billing: BillingSummary | null | undefined,
): string {
  if (!billing) return "Starter";
  if (billing.is_internal) return "Internal";
  if (billing.effective_tier === "pro") return "Pro";
  return "Starter";
}
