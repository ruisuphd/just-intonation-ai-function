"use client";

import type { ReactNode } from "react";

interface NoticeProps {
  children: ReactNode;
  tone?: "neutral" | "success" | "warning" | "danger";
}

const TONE_STYLES = {
  neutral: "border-apple-border bg-apple-card text-apple-text",
  success: "border-green-200 bg-green-50 text-green-800",
  warning: "border-amber-200 bg-amber-50 text-amber-900",
  danger: "border-red-200 bg-red-50 text-red-700",
};

export default function Notice({
  children,
  tone = "neutral",
}: NoticeProps) {
  return (
    <div className={`rounded-apple border px-4 py-3 text-sm shadow-apple ${TONE_STYLES[tone]}`}>
      {children}
    </div>
  );
}
