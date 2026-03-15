export function Skeleton({ className = "" }: { className?: string }) {
  return (
    <div
      className={`animate-pulse rounded bg-gray-200 ${className}`}
      aria-hidden="true"
    />
  );
}

export function SkeletonCard({ lines = 3 }: { lines?: number }) {
  return (
    <div className="rounded-apple bg-apple-card p-5 shadow-apple space-y-3">
      <Skeleton className="h-5 w-2/5" />
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton key={i} className={`h-4 ${i === lines - 1 ? "w-3/5" : "w-full"}`} />
      ))}
    </div>
  );
}

export function SkeletonText({ lines = 2 }: { lines?: number }) {
  return (
    <div className="space-y-2">
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton key={i} className={`h-4 ${i === lines - 1 ? "w-4/5" : "w-full"}`} />
      ))}
    </div>
  );
}
