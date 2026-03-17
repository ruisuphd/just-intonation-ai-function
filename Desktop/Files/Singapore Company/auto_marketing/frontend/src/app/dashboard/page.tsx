"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { apiFetch } from "@/lib/api";
import { normalizePlatforms } from "@/lib/platforms";
import ChatWidget from "@/components/chat-widget";
import ErrorBoundary from "@/components/error-boundary";
import Nav from "@/components/nav";
import OverviewSection from "@/components/sections/overview";
import ContentDraftsSection from "@/components/sections/content-drafts";
import NewsletterSection from "@/components/sections/newsletter";
import CalendarSection from "@/components/sections/calendar";
import AnalyticsSection from "@/components/sections/analytics";
import IntelligenceSection from "@/components/sections/intelligence";
import LeadsSection from "@/components/sections/leads";
import OutreachSection from "@/components/sections/outreach";
import Notice from "@/components/ui/notice";
import { formatStarterAccessDate } from "@/lib/billing";
import type { BillingSummary, TenantProfile } from "@/types";

const SECTION_IDS = [
  "overview",
  "content",
  "newsletter",
  "calendar",
  "analytics",
  "intelligence",
  "leads",
  "outreach",
] as const;

export default function DashboardPage() {
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();
  const [companyName, setCompanyName] = useState("");
  const [settings, setSettings] = useState<Partial<TenantProfile> | null>(null);
  const [activeSection, setActiveSection] = useState("overview");
  const [billing, setBilling] = useState<BillingSummary | null>(null);
  const [dataLoading, setDataLoading] = useState(true);
  const [pageError, setPageError] = useState("");
  const [dismissedVerification, setDismissedVerification] = useState(false);

  useEffect(() => {
    if (!authLoading && !user) router.replace("/");
  }, [user, authLoading, router]);

  const loadDashboard = useCallback(async () => {
    if (!user) return;
    setDataLoading(true);
    setPageError("");
    try {
      const [settingsData, billingState] = await Promise.all([
        apiFetch<Partial<TenantProfile>>("/api/settings"),
        apiFetch<BillingSummary>("/billing/subscription"),
      ]);

      // Redirect to onboarding if not completed
      if (!settingsData.onboarding_completed) {
        router.replace("/onboarding");
        return;
      }

      setSettings(settingsData);
      setCompanyName(settingsData.company_name || "");
      setBilling(billingState);
    } catch (err: any) {
      setPageError(err.message || "Unable to load your workspace.");
    } finally {
      setDataLoading(false);
    }
  }, [user]);

  useEffect(() => {
    if (!authLoading && user) {
      loadDashboard();
    }
  }, [authLoading, user, loadDashboard]);

  useEffect(() => {
    if (!billing || pageError) return;

    const updateActiveSection = () => {
      const offset = 132;
      let currentSection: (typeof SECTION_IDS)[number] = SECTION_IDS[0];

      for (const sectionId of SECTION_IDS) {
        const element = document.getElementById(sectionId);
        if (!element) continue;
        if (element.getBoundingClientRect().top - offset <= 0) {
          currentSection = sectionId;
        } else {
          break;
        }
      }

      setActiveSection((prev) => (prev === currentSection ? prev : currentSection));
    };

    const rafId = window.requestAnimationFrame(updateActiveSection);
    window.addEventListener("scroll", updateActiveSection, { passive: true });
    window.addEventListener("resize", updateActiveSection);
    window.addEventListener("hashchange", updateActiveSection);

    return () => {
      window.cancelAnimationFrame(rafId);
      window.removeEventListener("scroll", updateActiveSection);
      window.removeEventListener("resize", updateActiveSection);
      window.removeEventListener("hashchange", updateActiveSection);
    };
  }, [billing, pageError]);

  const platformsEnabled = normalizePlatforms(settings?.platforms_enabled);

  if (authLoading || dataLoading || !user) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-apple-bg">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-apple-text border-t-transparent" />
      </div>
    );
  }

  const now = new Date();
  const today = now.toLocaleDateString("en-GB", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  });
  const hour = now.getHours();
  const greeting =
    hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";

  return (
    <div className="min-h-screen bg-apple-bg">
      <Nav
        companyName={companyName}
        activeSection={activeSection}
        billing={billing}
        onSectionSelect={setActiveSection}
      />

      {user && !user.emailVerified && user.providerData?.[0]?.providerId === "password" && !dismissedVerification && (
        <div className="mx-4 mt-3 flex items-center justify-between rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          <span>
            Please verify your email address. Check your inbox or{" "}
            <button
              className="underline font-medium hover:text-amber-900"
              onClick={async () => {
                try {
                  const { verifyEmail } = await import("@/lib/firebase");
                  await verifyEmail();
                } catch {}
              }}
            >
              resend verification email
            </button>.
          </span>
          <button
            className="ml-4 text-amber-500 hover:text-amber-700"
            onClick={() => setDismissedVerification(true)}
          >
            ✕
          </button>
        </div>
      )}

      <main className="mx-auto max-w-5xl space-y-10 px-4 py-8">
        <section id="overview" className="space-y-8 scroll-mt-28">
          <div>
            <h1 className="text-2xl font-semibold">{greeting}</h1>
            <p className="text-sm text-apple-secondary">
              Here&apos;s your marketing brief for {today}.
            </p>
          </div>

          {pageError && <Notice tone="danger">{pageError}</Notice>}

          {!pageError && billing?.is_internal && (
            <Notice tone="success">
              Internal test access is enabled for this account. Billing controls stay hidden.
            </Notice>
          )}

          {!pageError && billing?.access_source === "starter_access" && (
            <Notice>
              Starter access is active until {formatStarterAccessDate(billing) || "your trial ends"}.
            </Notice>
          )}

          {!pageError && billing?.subscription_status === "past_due" && (
            <Notice tone="warning">
              Your paid subscription has a billing issue. Update it in{" "}
              <Link href="/settings?tab=billing" className="font-medium text-apple-blue">
                Settings
              </Link>
              .
            </Notice>
          )}

          {!pageError && billing?.effective_tier === "free" && !billing.is_internal && (
            <Notice tone="warning">
              You&apos;re on the Free plan. Upgrade in{" "}
              <Link href="/settings?tab=billing" className="font-medium text-apple-blue">
                Settings
              </Link>{" "}
              to unlock content generation and automation.
            </Notice>
          )}

          {billing && !pageError && (
            <OverviewSection billing={billing} platforms={platformsEnabled} />
          )}
        </section>

        {billing && !pageError && (
          <>
            <ErrorBoundary>
              <ContentDraftsSection billing={billing} platforms={platformsEnabled} />
            </ErrorBoundary>
            <ErrorBoundary>
              <NewsletterSection billing={billing} />
            </ErrorBoundary>
            <ErrorBoundary>
              <CalendarSection billing={billing} platforms={platformsEnabled} />
            </ErrorBoundary>
            <ErrorBoundary>
              <AnalyticsSection billing={billing} platforms={platformsEnabled} />
            </ErrorBoundary>
            <ErrorBoundary>
              <IntelligenceSection billing={billing} />
            </ErrorBoundary>
            <ErrorBoundary>
              <LeadsSection billing={billing} />
            </ErrorBoundary>
            <ErrorBoundary>
              <OutreachSection billing={billing} />
            </ErrorBoundary>
          </>
        )}
      </main>
      <ChatWidget />
    </div>
  );
}
