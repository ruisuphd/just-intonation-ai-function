"use client";

import { useState, useEffect, useRef } from "react";
import { PitchDetector } from "pitchy";
import { frequencyToNote } from "@/lib/audio-utils";
import { PITCH_MIN_HZ, PITCH_MAX_HZ } from "@/lib/constants";
import type { PitchData } from "@/types";

export function usePitchDetection(analyserNode: AnalyserNode | null) {
  const [pitch, setPitch] = useState<PitchData | null>(null);
  const rafRef = useRef<number>(0);

  useEffect(() => {
    if (!analyserNode) return;
    const node: AnalyserNode = analyserNode;

    let cancelled = false;
    const detector = PitchDetector.forFloat32Array(node.fftSize);
    const buf = new Float32Array(node.fftSize);

    function tick() {
      if (cancelled) return;
      node.getFloatTimeDomainData(buf);
      const [freq, clarity] = detector.findPitch(buf, node.context.sampleRate);

      if (clarity > 0.9 && freq >= PITCH_MIN_HZ && freq <= PITCH_MAX_HZ) {
        const { name, cents } = frequencyToNote(freq);
        setPitch({ frequency: freq, note: name, cents, clarity });
      } else {
        setPitch(null);
      }

      rafRef.current = requestAnimationFrame(tick);
    }

    rafRef.current = requestAnimationFrame(tick);
    return () => {
      cancelled = true;
      cancelAnimationFrame(rafRef.current);
    };
  }, [analyserNode]);

  return analyserNode ? pitch : null;
}
