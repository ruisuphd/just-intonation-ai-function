"use client";

interface PitchMeterProps {
  pitch: { frequency: number; note: string; cents: number; clarity: number } | null;
  compact?: boolean;
}

export function PitchMeter({ pitch, compact = false }: PitchMeterProps) {
  if (!pitch) {
    return (
      <div
        className={`flex items-center justify-center rounded-xl border border-[#d2d2d7] bg-white text-[#6e6e73] ${
          compact ? "flex-row gap-2 px-4 py-3" : "flex-col p-8"
        }`}
      >
        <span className={compact ? "text-lg font-medium" : "text-2xl font-medium"}>
          —
        </span>
        <span className={compact ? "text-sm" : "mt-1 text-sm"}>
          No pitch detected
        </span>
      </div>
    );
  }

  const centsNorm = Math.max(-50, Math.min(50, pitch.cents));
  const barPosition = ((centsNorm + 50) / 100) * 100;
  const absCents = Math.abs(pitch.cents);
  const pitchLabel =
    pitch.cents > 15 ? "Sharp" : pitch.cents < -15 ? "Flat" : "On pitch";
  const pitchLabelColor =
    pitch.cents > 15
      ? "text-red-500"
      : pitch.cents < -15
        ? "text-red-500"
        : "text-emerald-500";
  const barColor =
    absCents <= 10
      ? "bg-emerald-500"
      : absCents <= 25
        ? "bg-amber-500"
        : "bg-red-500";

  if (compact) {
    return (
      <div className="flex items-center gap-3 rounded-xl border border-[#d2d2d7] bg-white px-4 py-3">
        <span className="text-xl font-semibold text-[#1d1d1f]">{pitch.note}</span>
        <div className="min-w-0 flex-1">
          <div className="relative h-2 w-full overflow-hidden rounded-full bg-[#f5f5f7]">
            <div
              className={`absolute top-0 h-full w-1 rounded-full transition-all duration-75 ${barColor}`}
              style={{ left: `calc(${barPosition}% - 2px)` }}
            />
          </div>
        </div>
        <span className={`text-xs font-medium ${pitchLabelColor}`}>
          {pitchLabel}
        </span>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center gap-4 rounded-xl border border-[#d2d2d7] bg-white p-6">
      <span className="text-4xl font-semibold tracking-tight text-[#1d1d1f]">
        {pitch.note}
      </span>
      <span className={`text-sm font-medium ${pitchLabelColor}`}>{pitchLabel}</span>
      <span className="text-sm text-[#6e6e73]">{pitch.frequency.toFixed(1)} Hz</span>

      <div className="w-full max-w-xs">
        <div className="relative h-3 w-full overflow-hidden rounded-full bg-[#f5f5f7]">
          <div
            className={`absolute top-0 h-full rounded-full transition-all duration-75 ${barColor}`}
            style={{
              width: "6px",
              left: `calc(${barPosition}% - 3px)`,
            }}
          />
        </div>
        <div className="mt-1 flex justify-between text-xs text-[#6e6e73]">
          <span>-50¢</span>
          <span>0¢</span>
          <span>+50¢</span>
        </div>
      </div>

      <div className="flex items-center gap-2">
        <span className="text-xs text-[#6e6e73]">Clarity</span>
        <div className="h-2 w-24 overflow-hidden rounded-full bg-[#f5f5f7]">
          <div
            className="h-full bg-[#0071e3] transition-all duration-100"
            style={{ width: `${Math.min(100, pitch.clarity * 100)}%` }}
          />
        </div>
        <span className="text-xs text-[#6e6e73]">
          {Math.round(pitch.clarity * 100)}%
        </span>
      </div>
    </div>
  );
}
