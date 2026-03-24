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
  if (billing.effective_tier === "pro") return "Pro";
  return "Starter";
}

/** Display string for Pro list price from /billing/subscription Stripe snapshot. */
export function formatProListPrice(billing: BillingSummary | null | undefined): string {
  if (!billing) return "$29/mo";
  const amt = billing.pro_unit_amount;
  const cur = billing.pro_currency;
  const interval = billing.pro_interval;
  if (amt != null && cur) {
    try {
      const formatted = new Intl.NumberFormat(undefined, {
        style: "currency",
        currency: cur.toUpperCase(),
      }).format(amt / 100);
      if (interval === "year") return `${formatted}/yr`;
      return `${formatted}/mo`;
    } catch {
      /* fall through */
    }
  }
  return "$29/mo";
}
