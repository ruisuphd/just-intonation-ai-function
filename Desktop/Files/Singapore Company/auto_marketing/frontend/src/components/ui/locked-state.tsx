"use client";

import Link from "next/link";

interface LockedStateProps {
  description: string;
  ctaLabel: string;
  href?: string;
}

export default function LockedState({
  description,
  ctaLabel,
  href = "/billing",
}: LockedStateProps) {
  return (
    <div className="rounded-apple bg-apple-card p-8 text-center shadow-apple">
      <p className="text-sm text-apple-secondary">{description}</p>
      <Link
        href={href}
        className="mt-3 inline-block rounded-apple-sm bg-apple-blue px-5 py-2 text-sm font-medium text-white hover:bg-apple-blue-hover"
      >
        {ctaLabel}
      </Link>
    </div>
  );
}
