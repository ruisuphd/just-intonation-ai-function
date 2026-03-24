"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { apiFetch, ApiError } from "@/lib/api";
import { normalizePlatforms } from "@/lib/platforms";
import ChatWidget from "@/components/chat-widget";
import CommandPalette from "@/components/command-palette";
import ErrorBoundary from "@/components/error-boundary";
import LazySection from "@/components/lazy-section";
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
import type { BillingSummary, DashboardBootstrapResponse, TenantProfile } from "@/types";

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

function DashboardMainSkeleton() {
  return (
    <main className="mx-auto max-w-5xl space-y-10 px-4 py-8">
      <section className="space-y-8 scroll-mt-28">
        <div className="space-y-2">
          <div className="h-8 w-48 animate-pulse rounded bg-apple-border" />
          <div className="h-4 w-72 animate-pulse rounded bg-apple-border" />
        </div>
        <div className="animate-pulse space-y-4 rounded-apple border border-apple-border bg-apple-card/50 p-6">
          <div className="h-5 w-36 rounded bg-apple-border" />
          <div className="h-24 rounded-lg bg-apple-bg" />
        </div>
      </section>
      <div className="h-64 animate-pulse rounded-apple border border-apple-border bg-apple-card/40" />
      <div className="h-48 animate-pulse rounded-apple border border-apple-border bg-apple-card/40" />
    </main>
  );
}

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
  const [overviewPrefetch, setOverviewPrefetch] = useState<
    Pick<DashboardBootstrapResponse, "usage" | "pipeline_status" | "oauth_status"> | null
  >(null);

  useEffect(() => {
    if (!authLoading && !user) router.replace("/login");
  }, [user, authLoading, router]);

  const loadDashboard = useCallback(async () => {
    if (!user) return;
    setDataLoading(true);
    setPageError("");
    try {
      const boot = await apiFetch<DashboardBootstrapResponse>("/api/dashboard/bootstrap");
      const settingsData = boot.settings as Partial<TenantProfile>;
      const billingState = boot.billing;

      if (!settingsData.onboarding_completed) {
        router.replace("/onboarding");
        return;
      }

      const legalCurrent = settingsData.legal_docs_current_version;
      const legalAccepted = settingsData.legal_terms_version;
      if (legalCurrent && legalAccepted !== legalCurrent) {
        router.replace(`/legal/accept?redirect=${encodeURIComponent("/dashboard")}`);
        return;
      }

      setSettings(settingsData);
      setCompanyName(settingsData.company_name || "");
      setBilling(billingState);
      setOverviewPrefetch({
        usage: boot.usage,
        pipeline_status: boot.pipeline_status,
        oauth_status: boot.oauth_status,
      });
    } catch (err: unknown) {
      setOverviewPrefetch(null);
      let message = "Unable to load your workspace.";
      if (err instanceof ApiError) {
        message = err.message;
        if (process.env.NODE_ENV === "development" && err.traceId) {
          message = `${message} (trace: ${err.traceId}${err.code ? `, ${err.code}` : ""})`;
        }
      } else if (err instanceof Error) {
        message = err.message;
      }
      setPageError(message);
    } finally {
      setDataLoading(false);
    }
  }, [router, user]);

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

  if (authLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-apple-bg">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-apple-text border-t-transparent" />
      </div>
    );
  }

  if (!user) {
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

  if (dataLoading) {
    return (
      <div className="min-h-screen bg-apple-bg">
        <Nav
          companyName={companyName}
          activeSection={activeSection}
          billing={null}
          onSectionSelect={setActiveSection}
        />
        <DashboardMainSkeleton />
        <ChatWidget />
      </div>
    );
  }

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

      <CommandPalette enabled={!pageError && !!billing} />
      <main className="mx-auto max-w-5xl space-y-10 px-4 py-8">
        <section id="overview" className="space-y-8 scroll-mt-28">
          <div>
            <h1 className="text-2xl font-semibold">{greeting}</h1>
            <p className="text-sm text-apple-secondary">
              Here&apos;s your marketing brief for {today}.
            </p>
          </div>

          {pageError && <Notice tone="danger">{pageError}</Notice>}

          {!pageError && billing?.subscription_status === "past_due" && (
            <Notice tone="warning">
              Your paid subscription has a billing issue. Update it in{" "}
              <Link href="/billing" className="font-medium text-apple-blue">
                Settings
              </Link>
              .
            </Notice>
          )}

          {billing && !pageError && (
            <OverviewSection
              billing={billing}
              platforms={platformsEnabled}
              onboardingCompleted={settings?.onboarding_completed}
              companyName={settings?.company_name}
              overviewPrefetch={overviewPrefetch ?? undefined}
            />
          )}
        </section>

        {billing && !pageError && (
          <>
            <ErrorBoundary>
              <LazySection anchorId="content" minHeight="380px">
                <ContentDraftsSection billing={billing} platforms={platformsEnabled} />
              </LazySection>
            </ErrorBoundary>
            <ErrorBoundary>
              <LazySection anchorId="newsletter" minHeight="320px">
                <NewsletterSection billing={billing} />
              </LazySection>
            </ErrorBoundary>
            <ErrorBoundary>
              <LazySection anchorId="calendar" minHeight="360px">
                <CalendarSection billing={billing} platforms={platformsEnabled} />
              </LazySection>
            </ErrorBoundary>
            <ErrorBoundary>
              <LazySection anchorId="analytics" minHeight="300px">
                <AnalyticsSection billing={billing} platforms={platformsEnabled} />
              </LazySection>
            </ErrorBoundary>
            <ErrorBoundary>
              <LazySection anchorId="intelligence" minHeight="320px">
                <IntelligenceSection billing={billing} />
              </LazySection>
            </ErrorBoundary>
            <ErrorBoundary>
              <LazySection anchorId="leads" minHeight="360px">
                <LeadsSection billing={billing} />
              </LazySection>
            </ErrorBoundary>
            <ErrorBoundary>
              <LazySection anchorId="outreach" minHeight="240px">
                <OutreachSection billing={billing} />
              </LazySection>
            </ErrorBoundary>
          </>
        )}
      </main>
      <ChatWidget />
    </div>
  );
}
