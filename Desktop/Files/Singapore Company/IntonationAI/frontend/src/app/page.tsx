"use client";

import { useEffect } from "react";
import { defaultLocale } from "@/i18n/routing";

export default function RootIndexRedirect() {
  useEffect(() => {
    const path = window.location.pathname;
    if (path === "/" || path === "") {
      window.location.replace(`/${defaultLocale}/`);
    }
  }, []);
  return (
    <p className="flex min-h-screen items-center justify-center bg-background p-6 text-muted">
      Redirecting…
    </p>
  );
}
