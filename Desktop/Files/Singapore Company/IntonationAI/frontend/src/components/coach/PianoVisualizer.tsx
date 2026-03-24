"use client";

interface PianoVisualizerProps {
  detectedNote: string | null;
  targetNote?: string | null;
  chord?: string | null;
  timingOffsetMs?: number;
  /** Pitch deviation in cents for the detected note — enables yellow "close" highlight */
  centsDev?: number;
}

const WHITE_KEYS = [
  "C3", "D3", "E3", "F3", "G3", "A3", "B3",
  "C4", "D4", "E4", "F4", "G4", "A4", "B4",
];

const BLACK_KEYS = [
  "C#3", "D#3", null, "F#3", "G#3", "A#3", null,
  "C#4", "D#4", null, "F#4", "G#4", "A#4", null,
];

function parseNote(n: string): { name: string; octave: number } | null {
  const m = n?.match(/^([A-G]#?)(\d+)$/);
  if (!m) return null;
  return { name: m[1], octave: parseInt(m[2], 10) };
}

function getKeyState(
  key: string,
  detectedNote: string | null,
  targetNote: string | null,
  centsDev: number
): "correct" | "wrong" | "close" | "idle" {
  if (!detectedNote && !targetNote) return "idle";
  const det = parseNote(detectedNote || "");
  const tgt = parseNote(targetNote || "");
  const keyParsed = parseNote(key);
  if (!keyParsed) return "idle";

  const isDetected = det && det.name === keyParsed.name && det.octave === keyParsed.octave;
  const isTarget = tgt && tgt.name === keyParsed.name && tgt.octave === keyParsed.octave;

  if (isDetected && isTarget) return "correct";
  if (isDetected && !isTarget) return "wrong";
  // "close": active pitch near target (requires a detected note, not silence at centsDev=0)
  if (
    detectedNote &&
    isTarget &&
    !isDetected &&
    Math.abs(centsDev) <= 50
  )
    return "close";
  return "idle";
}

export function PianoVisualizer({
  detectedNote,
  targetNote = null,
  chord = null,
  timingOffsetMs = 0,
  centsDev = 0,
}: PianoVisualizerProps) {
  const w = 280;
  const whiteW = w / 14;
  const blackW = whiteW * 0.6;
  const blackH = 60;
  const whiteH = 100;

  const getWhiteFill = (key: string) => {
    const s = getKeyState(key, detectedNote, targetNote, centsDev);
    if (s === "correct") return "#22c55e";
    if (s === "wrong") return "#ef4444";
    if (s === "close") return "#fbbf24"; // yellow — within ±50 cents
    return "#ffffff";
  };

  const getBlackFill = (key: string | null) => {
    if (!key) return "transparent";
    const s = getKeyState(key, detectedNote, targetNote, centsDev);
    if (s === "correct") return "#16a34a";
    if (s === "wrong") return "#dc2626";
    if (s === "close") return "#f59e0b"; // amber — within ±50 cents
    return "#1d1d1f";
  };

  return (
    <div className="flex flex-col gap-2 rounded-xl border border-[#d2d2d7] bg-white p-4">
      {chord && (
        <div className="text-center text-sm font-medium text-[#1d1d1f]">
          Chord: {chord}
        </div>
      )}
      <svg
        viewBox={`0 0 ${w} ${whiteH}`}
        className="w-full"
        style={{ maxWidth: w }}
        preserveAspectRatio="none"
        role="img"
        aria-label="Piano keyboard showing detected and target notes"
      >
        {WHITE_KEYS.map((key, i) => (
          <rect
            key={key}
            x={i * whiteW}
            y={0}
            width={whiteW - 1}
            height={whiteH}
            fill={getWhiteFill(key)}
            stroke="#d2d2d7"
            strokeWidth={1}
            rx={2}
          />
        ))}
        {BLACK_KEYS.map((key, i) => {
          if (!key) return null;
          const x = i * whiteW + whiteW - blackW / 2;
          return (
            <rect
              key={key}
              x={x}
              y={0}
              width={blackW}
              height={blackH}
              fill={getBlackFill(key)}
              stroke="#374151"
              strokeWidth={1}
              rx={2}
            />
          );
        })}
      </svg>
      {detectedNote && (
        <div className="text-center text-xs text-[#6e6e73]">
          {detectedNote}
          {Math.abs(timingOffsetMs) > 5 && (
            <span className="ml-2">
              {timingOffsetMs > 0 ? "+" : ""}
              {Math.round(timingOffsetMs)}ms
            </span>
          )}
        </div>
      )}
    </div>
  );
}
