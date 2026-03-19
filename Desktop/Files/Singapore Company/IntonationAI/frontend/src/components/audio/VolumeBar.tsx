"use client";

interface VolumeBarProps {
  db: number;
}

export function VolumeBar({ db }: VolumeBarProps) {
  const clamped = Math.max(-60, Math.min(0, db));
  const percent = ((clamped + 60) / 60) * 100;
  const color =
    clamped > -12
      ? "bg-red-500"
      : clamped > -24
        ? "bg-amber-500"
        : "bg-emerald-500";

  return (
    <div className="flex items-center gap-3">
      <div className="relative h-24 w-6 overflow-hidden rounded-lg bg-gray-800">
        <div
          className={`absolute bottom-0 left-0 w-full ${color} transition-all duration-150`}
          style={{ height: `${percent}%` }}
        />
      </div>
      <span className="min-w-[3rem] text-sm tabular-nums text-gray-400">
        {db > -60 ? db.toFixed(0) : "−∞"} dB
      </span>
    </div>
  );
}
