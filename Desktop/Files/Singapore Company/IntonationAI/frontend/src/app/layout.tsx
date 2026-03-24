import type { ReactNode } from "react";

/** Root pass-through; `<html>` / `<body>` live in `[locale]/layout.tsx` for per-locale `lang`. */
export default function RootLayout({ children }: { children: ReactNode }) {
  return children;
}
