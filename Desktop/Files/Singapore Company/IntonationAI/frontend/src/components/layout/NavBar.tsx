"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/useAuth";

const NAV_LINKS = [
  { href: "/", label: "Home" },
  { href: "/pricing", label: "Pricing" },
  { href: "/dashboard", label: "Dashboard" },
  { href: "/coach/vocal", label: "Vocal Coach" },
  { href: "/coach/piano", label: "Piano Coach" },
  { href: "/coach/guitar", label: "Guitar Coach" },
  { href: "/warmup", label: "Warm Up" },
  { href: "/settings", label: "Settings" },
];

export function NavBar() {
  const router = useRouter();
  const { user, loading, signOut } = useAuth();
  const [drawerOpen, setDrawerOpen] = useState(false);

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

  const handleSignOut = async () => {
    setDrawerOpen(false);
    await signOut();
    router.push("/");
  };

  return (
    <>
      <nav className="fixed left-0 right-0 top-0 z-50 flex h-14 items-center border-b border-[#d2d2d7] bg-[#fbfbfd]/95 backdrop-blur px-4">
        <Link
          href="/"
          className="shrink-0 text-lg font-semibold text-[#1d1d1f]"
          onClick={() => setDrawerOpen(false)}
        >
          IntonationAI
        </Link>

        <div className="hidden flex-1 items-center justify-center gap-6 md:flex">
          {NAV_LINKS.map(({ href, label }) => (
            <Link
              key={href}
              href={href}
              className="text-sm text-[#6e6e73] transition hover:text-[#1d1d1f]"
            >
              {label}
            </Link>
          ))}
        </div>

        <div className="flex shrink-0 items-center gap-2">
          <button
            type="button"
            onClick={() => setDrawerOpen(true)}
            className="flex min-h-[44px] min-w-[44px] items-center justify-center rounded-xl text-[#1d1d1f] hover:bg-[#f5f5f7] md:hidden"
            aria-label="Open menu"
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
          {loading ? (
            <span className="text-sm text-[#6e6e73]">…</span>
          ) : user ? (
            <div className="hidden items-center gap-3 md:flex">
              <span className="max-w-[120px] truncate text-sm text-[#6e6e73]">
                {user.displayName || user.email}
              </span>
              <button
                type="button"
                onClick={handleSignOut}
                className="rounded-xl border border-[#d2d2d7] px-3 py-1.5 text-sm text-[#1d1d1f] transition hover:bg-[#f5f5f7]"
              >
                Sign Out
              </button>
            </div>
          ) : (
            <Link
              href="/login"
              className="rounded-full bg-[#0071e3] px-4 py-2 text-sm text-white transition hover:bg-[#0077ed]"
            >
              Sign In
            </Link>
          )}
        </div>
      </nav>

      {drawerOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/30 md:hidden"
          onClick={() => setDrawerOpen(false)}
          aria-hidden="true"
        />
      )}
      <div
        className={`fixed right-0 top-0 z-40 h-full w-[280px] max-w-[85vw] bg-[#fbfbfd] shadow-xl transition-transform duration-200 md:hidden ${
          drawerOpen ? "translate-x-0" : "translate-x-full"
        }`}
      >
        <div className="flex h-14 items-center justify-between border-b border-[#d2d2d7] px-4">
          <span className="font-semibold text-[#1d1d1f]">Menu</span>
          <button
            type="button"
            onClick={() => setDrawerOpen(false)}
            className="flex min-h-[44px] min-w-[44px] items-center justify-center rounded-xl text-[#6e6e73] hover:bg-[#f5f5f7]"
            aria-label="Close menu"
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
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
        <div className="flex flex-col gap-1 p-4">
          {NAV_LINKS.map(({ href, label }) => (
            <Link
              key={href}
              href={href}
              onClick={() => setDrawerOpen(false)}
              className="rounded-xl px-4 py-3 text-[#1d1d1f] hover:bg-[#f5f5f7]"
            >
              {label}
            </Link>
          ))}
          {user ? (
            <div className="mt-4 border-t border-[#d2d2d7] pt-4">
              <p className="mb-2 truncate px-4 text-sm text-[#6e6e73]">
                {user.displayName || user.email}
              </p>
              <button
                type="button"
                onClick={handleSignOut}
                className="w-full rounded-xl px-4 py-3 text-left text-[#1d1d1f] hover:bg-[#f5f5f7]"
              >
                Sign Out
              </button>
            </div>
          ) : (
            <Link
              href="/login"
              onClick={() => setDrawerOpen(false)}
              className="mt-4 block rounded-xl bg-[#0071e3] px-4 py-3 text-center font-medium text-white"
            >
              Sign In
            </Link>
          )}
        </div>
      </div>
    </>
  );
}
