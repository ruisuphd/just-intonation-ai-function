"use client";

import { useState, type MouseEvent } from "react";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { planBadgeLabel } from "@/lib/billing";
import { signOut } from "@/lib/firebase";
import NotificationPanel from "@/components/notification-panel";
import type { BillingSummary } from "@/types";

const SECTIONS = [
  { id: "overview", label: "Overview" },
  { id: "content", label: "Content" },
  { id: "newsletter", label: "Newsletter" },
  { id: "calendar", label: "Calendar" },
  { id: "analytics", label: "Analytics" },
  { id: "intelligence", label: "Intelligence" },
  { id: "leads", label: "Leads" },
  { id: "outreach", label: "Outreach" },
];

interface NavProps {
  companyName?: string;
  activeSection?: string;
  billing?: BillingSummary | null;
  onSectionSelect?: (sectionId: string) => void;
}

export default function Nav({
  companyName,
  activeSection,
  billing,
  onSectionSelect,
}: NavProps) {
  const { user } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);
  const initials = (user?.displayName || user?.email || "U")
    .split(/[\s@]/)
    .map((w) => w[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();

  function handleSectionClick(event: MouseEvent<HTMLButtonElement>, sectionId: string) {
    event.preventDefault();
    onSectionSelect?.(sectionId);
    window.history.replaceState(null, "", `#${sectionId}`);
    document.getElementById(sectionId)?.scrollIntoView({
      behavior: "smooth",
      block: "start",
    });
  }

  return (
    <header className="sticky top-0 z-50 border-b border-apple-border bg-apple-card/80 backdrop-blur-xl">
      <div className="mx-auto flex min-h-14 max-w-5xl items-center justify-between gap-3 px-4 py-3 sm:h-12 sm:py-0">
        <div className="flex min-w-0 items-center gap-2">
          <Link
            href="/dashboard"
            className="max-w-[11rem] truncate text-[15px] font-semibold tracking-tight sm:max-w-none"
          >
            {companyName || "IntoMarketing"}
          </Link>
          {billing && (
            <span className="hidden rounded-full bg-apple-bg px-2 py-0.5 text-[11px] font-medium text-apple-secondary sm:inline-flex">
              {planBadgeLabel(billing)}
            </span>
          )}
        </div>

        <div className="flex shrink-0 items-center gap-2">
          <NotificationPanel
            onNavigate={(sectionId) => {
              onSectionSelect?.(sectionId);
              document.getElementById(sectionId)?.scrollIntoView({ behavior: "smooth", block: "start" });
            }}
          />
          <Link
            href="/settings"
            className="rounded-full p-2 text-apple-secondary hover:bg-apple-bg"
            aria-label="Settings"
          >
            <svg className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.325.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 011.37.49l1.296 2.247a1.125 1.125 0 01-.26 1.431l-1.003.827c-.293.241-.438.613-.43.992a7.723 7.723 0 010 .255c-.008.378.137.75.43.991l1.004.827c.424.35.534.955.26 1.43l-1.298 2.247a1.125 1.125 0 01-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.47 6.47 0 01-.22.128c-.331.183-.581.495-.644.869l-.213 1.281c-.09.543-.56.94-1.11.94h-2.594c-.55 0-1.019-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 01-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 01-1.369-.49l-1.297-2.247a1.125 1.125 0 01.26-1.431l1.004-.827c.292-.24.437-.613.43-.991a6.932 6.932 0 010-.255c.007-.38-.138-.751-.43-.992l-1.004-.827a1.125 1.125 0 01-.26-1.43l1.297-2.247a1.125 1.125 0 011.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.086.22-.128.332-.183.582-.495.644-.869l.214-1.28z" />
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
          </Link>

          <div className="relative">
            <button
              onClick={() => setMenuOpen(!menuOpen)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  setMenuOpen((v) => !v);
                }
                if (e.key === "Escape") setMenuOpen(false);
              }}
              className="flex h-8 w-8 items-center justify-center rounded-full bg-apple-text text-xs font-bold text-white"
              aria-label="User menu"
              aria-expanded={menuOpen}
              aria-haspopup="true"
            >
              {initials}
            </button>
            {menuOpen && (
              <>
                <div className="fixed inset-0" onClick={() => setMenuOpen(false)} aria-hidden="true" />
                <div
                  className="absolute right-0 mt-2 w-48 rounded-apple-sm border border-apple-border bg-apple-card p-1 shadow-apple-lg"
                  role="dialog"
                  aria-modal="true"
                  aria-label="User menu options"
                  onKeyDown={(e) => {
                    if (e.key === "Escape") setMenuOpen(false);
                  }}
                >
                  <Link
                    href="/settings?tab=account"
                    onClick={() => setMenuOpen(false)}
                    className="block rounded-md px-3 py-2 text-left text-sm text-apple-text hover:bg-apple-bg"
                  >
                    Account settings
                  </Link>
                  <Link
                    href="/billing"
                    onClick={() => setMenuOpen(false)}
                    className="block rounded-md px-3 py-2 text-left text-sm text-apple-text hover:bg-apple-bg"
                  >
                    Billing
                  </Link>
                  <Link
                    href="/changelog"
                    onClick={() => setMenuOpen(false)}
                    className="block rounded-md px-3 py-2 text-left text-sm text-apple-text hover:bg-apple-bg"
                  >
                    What&apos;s New
                  </Link>
                  <Link
                    href="/help"
                    onClick={() => setMenuOpen(false)}
                    className="block rounded-md px-3 py-2 text-left text-sm text-apple-text hover:bg-apple-bg"
                  >
                    Help / Docs
                  </Link>
                  <button
                    onClick={() => { signOut(); setMenuOpen(false); }}
                    className="w-full rounded-md px-3 py-2 text-left text-sm text-apple-text hover:bg-apple-bg"
                  >
                    Sign out
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Section tabs */}
      <div className="mx-auto max-w-5xl overflow-x-auto px-4 [scrollbar-width:none] [-ms-overflow-style:none] [&::-webkit-scrollbar]:hidden">
        <div className="flex min-w-max gap-1 pb-3 sm:min-w-0 sm:pb-2">
          {SECTIONS.map((s) => (
            <button
              key={s.id}
              type="button"
              onClick={(event) => handleSectionClick(event, s.id)}
              aria-current={activeSection === s.id ? "page" : undefined}
              className={`whitespace-nowrap rounded-full px-3.5 py-1.5 text-[13px] font-medium transition-colors ${
                activeSection === s.id
                  ? "bg-apple-text text-white"
                  : "text-apple-secondary hover:bg-apple-bg"
              }`}
            >
              {s.label}
            </button>
          ))}
        </div>
      </div>
    </header>
  );
}
