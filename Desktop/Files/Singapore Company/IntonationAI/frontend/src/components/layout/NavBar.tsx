"use client";

import { useState, useEffect, useRef, type HTMLAttributes } from "react";
import { useTranslations } from "next-intl";
import { Link, useRouter } from "@/i18n/navigation";
import { useAuth } from "@/hooks/useAuth";

const DESKTOP_HREFS = [
  "/",
  "/pricing",
  "/dashboard",
  "/coach",
  "/songs",
  "/warmup",
  "/settings",
] as const;

export function NavBar() {
  const t = useTranslations("nav");
  const tc = useTranslations("common");
  const router = useRouter();
  const { user, loading, signOut } = useAuth();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const menuOpenBtnRef = useRef<HTMLButtonElement>(null);
  const drawerPanelRef = useRef<HTMLDivElement>(null);

  const desktopLinks = [
    { href: DESKTOP_HREFS[0], labelKey: "home" as const },
    { href: DESKTOP_HREFS[1], labelKey: "pricing" as const },
    { href: DESKTOP_HREFS[2], labelKey: "progress" as const },
    { href: DESKTOP_HREFS[3], labelKey: "coach" as const },
    { href: DESKTOP_HREFS[4], labelKey: "songs" as const },
    { href: DESKTOP_HREFS[5], labelKey: "warmUp" as const },
    { href: DESKTOP_HREFS[6], labelKey: "settings" as const },
  ];

  useEffect(() => {
    if (drawerOpen) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => {
      document.body.style.overflow = "";
    };
  }, [drawerOpen]);

  useEffect(() => {
    if (!drawerOpen) return;
    const panel = drawerPanelRef.current;
    if (!panel) return;
    const focusables = panel.querySelectorAll<HTMLElement>(
      'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])'
    );
    const first = focusables[0];
    const last = focusables[focusables.length - 1];
    first?.focus();
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        setDrawerOpen(false);
        menuOpenBtnRef.current?.focus();
        return;
      }
      if (e.key !== "Tab" || !focusables.length) return;
      if (e.shiftKey) {
        if (document.activeElement === first) {
          e.preventDefault();
          last?.focus();
        }
      } else if (document.activeElement === last) {
        e.preventDefault();
        first?.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [drawerOpen]);

  const handleSignOut = async () => {
    setDrawerOpen(false);
    await signOut();
    router.push("/");
  };

  return (
    <>
      <nav className="fixed left-0 right-0 top-0 z-50 hidden h-14 items-center px-6 shadow-[0_2px_8px_rgba(0,0,0,0.04)] backdrop-blur md:flex bg-[#fbfbfd]/95">
        <Link
          href="/"
          className="shrink-0 text-lg font-semibold tracking-tight text-[#1d1d1f]"
          onClick={() => setDrawerOpen(false)}
        >
          IntonationAI
        </Link>

        <div className="flex flex-1 items-center justify-center gap-8">
          {desktopLinks.map(({ href, labelKey }) => (
            <Link
              key={href}
              href={href}
              className="text-sm font-medium text-[#6e6e73] transition hover:text-[#1d1d1f]"
            >
              {t(labelKey)}
            </Link>
          ))}
        </div>

        <div className="flex shrink-0 items-center gap-3">
          {loading ? (
            <span className="text-sm text-[#6e6e73]">…</span>
          ) : user ? (
            <>
              <span className="max-w-[140px] truncate text-sm text-[#6e6e73]">
                {user.displayName || user.email}
              </span>
              <button
                type="button"
                onClick={handleSignOut}
                className="rounded-full border border-[#d2d2d7] px-4 py-2 text-sm text-[#1d1d1f] transition active:scale-[0.97] hover:bg-[#f5f5f7]"
              >
                {tc("signOut")}
              </button>
            </>
          ) : (
            <Link
              href="/login"
              className="rounded-full bg-[#0071e3] px-4 py-2 text-sm font-medium text-white transition active:scale-[0.97] hover:bg-[#0077ed]"
            >
              {tc("signIn")}
            </Link>
          )}
        </div>
      </nav>

      <nav className="fixed left-0 right-0 top-0 z-50 flex h-14 items-center justify-between px-4 shadow-[0_2px_8px_rgba(0,0,0,0.04)] backdrop-blur md:hidden bg-[#fbfbfd]/95">
        <Link href="/" className="text-lg font-semibold text-[#1d1d1f]">
          IntonationAI
        </Link>
        <button
          ref={menuOpenBtnRef}
          type="button"
          onClick={() => setDrawerOpen(true)}
          className="flex min-h-[44px] min-w-[44px] items-center justify-center rounded-xl text-[#1d1d1f]"
          aria-label={tc("openMenu")}
        >
          <svg
            width="24"
            height="24"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <line x1="3" y1="6" x2="21" y2="6" />
            <line x1="3" y1="12" x2="21" y2="12" />
            <line x1="3" y1="18" x2="21" y2="18" />
          </svg>
        </button>
      </nav>

      {drawerOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/30 md:hidden"
          onClick={() => setDrawerOpen(false)}
          aria-hidden="true"
        />
      )}
      <div
        ref={drawerPanelRef}
        className={`fixed right-0 top-0 z-40 h-full w-[280px] max-w-[85vw] bg-[#fbfbfd] shadow-xl transition-transform duration-200 md:hidden ${
          drawerOpen ? "translate-x-0" : "translate-x-full pointer-events-none"
        }`}
        aria-hidden={!drawerOpen}
        {...({ inert: !drawerOpen ? true : undefined } as HTMLAttributes<HTMLDivElement>)}
        {...(drawerOpen
          ? ({
              role: "dialog",
              "aria-modal": true,
              "aria-label": tc("menu"),
            } as const)
          : {})}
      >
        <div className="flex h-14 items-center justify-between border-b border-[#e8e8ed] px-4">
          <span className="font-semibold text-[#1d1d1f]">{tc("menu")}</span>
          <button
            type="button"
            onClick={() => setDrawerOpen(false)}
            className="flex min-h-[44px] min-w-[44px] items-center justify-center rounded-xl text-[#6e6e73]"
            aria-label={tc("closeMenu")}
          >
            <svg
              width="24"
              height="24"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
        <div className="flex flex-col gap-1 p-4">
          {desktopLinks.map(({ href, labelKey }) => (
            <Link
              key={href}
              href={href}
              onClick={() => setDrawerOpen(false)}
              className="rounded-xl px-4 py-3 text-[#1d1d1f] hover:bg-[#f5f5f7]"
            >
              {t(labelKey)}
            </Link>
          ))}
          <div className="mt-4 border-t border-[#e8e8ed] pt-4">
            <p className="mb-2 px-4 text-xs font-medium uppercase tracking-wide text-[#6e6e73]">
              {tc("legal")}
            </p>
            <Link
              href="/legal/terms"
              onClick={() => setDrawerOpen(false)}
              className="block rounded-xl px-4 py-3 text-[#1d1d1f] hover:bg-[#f5f5f7]"
            >
              {tc("termsOfService")}
            </Link>
            <Link
              href="/legal/privacy"
              onClick={() => setDrawerOpen(false)}
              className="block rounded-xl px-4 py-3 text-[#1d1d1f] hover:bg-[#f5f5f7]"
            >
              {tc("privacyPolicy")}
            </Link>
          </div>
          {user ? (
            <div className="mt-4 border-t border-[#e8e8ed] pt-4">
              <p className="mb-2 truncate px-4 text-sm text-[#6e6e73]">
                {user.displayName || user.email}
              </p>
              <button
                type="button"
                onClick={handleSignOut}
                className="w-full rounded-xl px-4 py-3 text-left text-[#1d1d1f] hover:bg-[#f5f5f7]"
              >
                {tc("signOut")}
              </button>
            </div>
          ) : (
            <Link
              href="/login"
              onClick={() => setDrawerOpen(false)}
              className="mt-4 block rounded-full bg-[#0071e3] px-4 py-3 text-center font-medium text-white"
            >
              {tc("signIn")}
            </Link>
          )}
        </div>
      </div>
    </>
  );
}
