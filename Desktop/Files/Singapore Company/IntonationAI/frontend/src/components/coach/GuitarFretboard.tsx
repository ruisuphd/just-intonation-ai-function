"use client";

interface GuitarFretboardProps {
  detectedChord: string | null;
  chordConfidence?: number;
  mutedStrings?: number[];
}

// finger positions use 1-indexed strings: 1=high-E, 2=B, 3=G, 4=D, 5=A, 6=low-E
const CHORD_SHAPES: Record<string, { string: number; fret: number }[]> = {
  // Open chords
  Am:  [{ string: 2, fret: 2 }, { string: 3, fret: 2 }, { string: 4, fret: 1 }],
  A:   [{ string: 2, fret: 2 }, { string: 3, fret: 2 }, { string: 4, fret: 2 }],
  A7:  [{ string: 2, fret: 2 }, { string: 4, fret: 2 }],
  Amaj7:[{ string: 2, fret: 2 }, { string: 3, fret: 1 }, { string: 4, fret: 2 }],
  Am7: [{ string: 2, fret: 2 }, { string: 3, fret: 0 }, { string: 4, fret: 1 }],
  Em:  [{ string: 3, fret: 2 }, { string: 4, fret: 2 }],
  E:   [{ string: 3, fret: 1 }, { string: 4, fret: 2 }, { string: 5, fret: 2 }],
  E7:  [{ string: 3, fret: 1 }, { string: 5, fret: 2 }],
  Em7: [{ string: 3, fret: 2 }, { string: 4, fret: 2 }],
  G:   [{ string: 1, fret: 3 }, { string: 2, fret: 3 }, { string: 5, fret: 2 }, { string: 6, fret: 3 }],
  Gmaj7:[{ string: 1, fret: 2 }, { string: 2, fret: 3 }, { string: 5, fret: 2 }, { string: 6, fret: 3 }],
  C:   [{ string: 2, fret: 1 }, { string: 4, fret: 2 }, { string: 5, fret: 3 }],
  Cmaj7:[{ string: 2, fret: 1 }, { string: 3, fret: 0 }, { string: 4, fret: 2 }, { string: 5, fret: 3 }],
  C7:  [{ string: 2, fret: 1 }, { string: 3, fret: 3 }, { string: 4, fret: 2 }, { string: 5, fret: 3 }],
  D:   [{ string: 1, fret: 2 }, { string: 2, fret: 3 }, { string: 3, fret: 2 }],
  Dm:  [{ string: 1, fret: 1 }, { string: 2, fret: 3 }, { string: 3, fret: 2 }],
  D7:  [{ string: 1, fret: 2 }, { string: 2, fret: 1 }, { string: 3, fret: 2 }],
  Dmaj7:[{ string: 1, fret: 2 }, { string: 2, fret: 2 }, { string: 3, fret: 2 }],
  Dm7: [{ string: 1, fret: 1 }, { string: 2, fret: 1 }, { string: 3, fret: 2 }],
  // Barre chords (2nd position)
  Bm:  [{ string: 1, fret: 2 }, { string: 2, fret: 3 }, { string: 3, fret: 4 }, { string: 4, fret: 4 }, { string: 5, fret: 2 }, { string: 6, fret: 2 }],
  B7:  [{ string: 1, fret: 2 }, { string: 2, fret: 0 }, { string: 3, fret: 2 }, { string: 4, fret: 1 }, { string: 5, fret: 2 }],
  F:   [{ string: 1, fret: 1 }, { string: 2, fret: 1 }, { string: 3, fret: 2 }, { string: 4, fret: 3 }, { string: 5, fret: 3 }, { string: 6, fret: 1 }],
  Fm:  [{ string: 1, fret: 1 }, { string: 2, fret: 1 }, { string: 3, fret: 1 }, { string: 4, fret: 3 }, { string: 5, fret: 3 }, { string: 6, fret: 1 }],
  // Sharps / flats (barre shapes)
  "F#": [{ string: 1, fret: 2 }, { string: 2, fret: 2 }, { string: 3, fret: 3 }, { string: 4, fret: 4 }, { string: 5, fret: 4 }, { string: 6, fret: 2 }],
  "F#m":[{ string: 1, fret: 2 }, { string: 2, fret: 2 }, { string: 3, fret: 2 }, { string: 4, fret: 4 }, { string: 5, fret: 4 }, { string: 6, fret: 2 }],
  Bb:  [{ string: 1, fret: 1 }, { string: 2, fret: 3 }, { string: 3, fret: 3 }, { string: 4, fret: 3 }, { string: 5, fret: 1 }, { string: 6, fret: 1 }],
  Bbm: [{ string: 1, fret: 1 }, { string: 2, fret: 2 }, { string: 3, fret: 3 }, { string: 4, fret: 3 }, { string: 5, fret: 1 }, { string: 6, fret: 1 }],
  // Power chords / other common
  "D#": [{ string: 1, fret: 3 }, { string: 2, fret: 4 }, { string: 3, fret: 3 }],
  "A#": [{ string: 2, fret: 3 }, { string: 3, fret: 3 }, { string: 4, fret: 3 }],
  "G#": [{ string: 1, fret: 4 }, { string: 2, fret: 4 }, { string: 3, fret: 5 }, { string: 4, fret: 6 }, { string: 5, fret: 6 }, { string: 6, fret: 4 }],
};

const STRING_LABELS = ["E", "A", "D", "G", "B", "E"];
const FRETS = 8;

export function GuitarFretboard({
  detectedChord,
  chordConfidence = 0,
  mutedStrings = [],
}: GuitarFretboardProps) {
  const w = 200;
  const h = 140;
  const stringSpacing = (w - 40) / 5;
  const fretSpacing = (h - 30) / FRETS;

  const fingers = detectedChord ? (CHORD_SHAPES[detectedChord] ?? []) : [];
  const hasShape = detectedChord ? detectedChord in CHORD_SHAPES : false;

  return (
    <div className="flex flex-col gap-2 rounded-xl border border-[#d2d2d7] bg-white p-4">
      {detectedChord && (
        <div className="flex items-center justify-between text-sm font-medium text-[#1d1d1f]">
          <span>{detectedChord}</span>
          <span className="text-xs text-[#6e6e73]">
            {Math.round(chordConfidence * 100)}%
          </span>
        </div>
      )}
      <svg viewBox={`0 0 ${w} ${h}`} className="w-full max-w-[200px]">
        {Array.from({ length: 6 }, (_, i) => (
          <line
            key={i}
            x1={30 + i * stringSpacing}
            y1={10}
            x2={30 + i * stringSpacing}
            y2={h - 20}
            stroke="#6b7280"
            strokeWidth={i === 0 ? 2 : 1}
          />
        ))}
        {Array.from({ length: FRETS + 1 }, (_, i) => (
          <line
            key={i}
            x1={30}
            y1={10 + i * fretSpacing}
            x2={w - 10}
            y2={10 + i * fretSpacing}
            stroke="#6b7280"
            strokeWidth={1}
          />
        ))}
        {fingers.map((f, i) => (
          <circle
            key={i}
            cx={30 + (f.string - 1) * stringSpacing}
            cy={10 + (f.fret + 0.5) * fretSpacing}
            r={6}
            fill="#0071e3"
            stroke="#fff"
            strokeWidth={1}
          />
        ))}
        {mutedStrings.map((s) => (
          <text
            key={s}
            x={30 + s * stringSpacing}
            y={18}
            textAnchor="middle"
            fill="#ef4444"
            fontSize={12}
            fontWeight="bold"
          >
            ×
          </text>
        ))}
      </svg>
      <div className="flex gap-1 text-[10px] text-[#6e6e73]">
        {STRING_LABELS.map((l, i) => (
          <span key={i} className="flex-1 text-center">
            {l}
          </span>
        ))}
      </div>
      {detectedChord && !hasShape && (
        <p className="text-center text-xs text-[#6e6e73]">
          Shape diagram coming soon for {detectedChord}
        </p>
      )}
    </div>
  );
}
