"use client";

interface ProgressRingProps {
  value: number;
  size?: number;
  label?: string;
}

function ringColor(value: number): string {
  if (value < 40) return "#ef4444";
  if (value < 70) return "#eab308";
  return "#22c55e";
}

export function ProgressRing({
  value,
  size = 120,
  label,
}: ProgressRingProps) {
  const clamped = Math.max(0, Math.min(100, value));
  const strokeWidth = Math.max(4, size * 0.08);
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const dashOffset = circumference * (1 - clamped / 100);
  const color = ringColor(clamped);

  return (
    <div className="relative inline-flex flex-col items-center">
      <svg
        width={size}
        height={size}
        className="-rotate-90"
        aria-hidden
      >
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="currentColor"
          strokeWidth={strokeWidth}
          className="text-[#1d1d1f]"
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={dashOffset}
          className="transition-all duration-500 ease-out"
        />
      </svg>
      <div
        className="absolute inset-0 flex flex-col items-center justify-center"
        aria-live="polite"
      >
        <span className="text-2xl font-semibold tabular-nums text-white">
          {Math.round(clamped)}%
        </span>
        {label && (
          <span className="mt-1 text-sm text-[#6e6e73]">{label}</span>
        )}
      </div>
    </div>
  );
}
