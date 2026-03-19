"use client";

import { useEffect, useRef } from "react";
import { computeRms, rmsToDb } from "@/lib/audio-utils";

interface AudioVisualizerProps {
  analyserNode: AnalyserNode | null;
}

const FFT_SIZE = 2048;
const BUFFER_LENGTH = 512;

export function AudioVisualizer({ analyserNode }: AudioVisualizerProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animationRef = useRef<number | undefined>(undefined);

  useEffect(() => {
    if (!analyserNode || !canvasRef.current) return;

    const canvas = canvasRef.current;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const analyser = analyserNode;
    const dataArray = new Uint8Array(BUFFER_LENGTH);
    const timeData = new Float32Array(analyser.fftSize || FFT_SIZE);

    const draw = () => {
      animationRef.current = requestAnimationFrame(draw);

      analyser.getByteTimeDomainData(dataArray);
      analyser.getFloatTimeDomainData(timeData);

      const rms = computeRms(timeData);
      const db = rmsToDb(rms);

      const w = canvas.width;
      const h = canvas.height;

      ctx.fillStyle = "rgb(17, 24, 39)";
      ctx.fillRect(0, 0, w, h);

      ctx.lineWidth = 1;
      ctx.strokeStyle = "rgb(74, 222, 128)";
      ctx.beginPath();

      const sliceWidth = w / BUFFER_LENGTH;
      let x = 0;

      for (let i = 0; i < BUFFER_LENGTH; i++) {
        const v = dataArray[i] / 128;
        const y = (v * h) / 2 + h / 2;

        if (i === 0) {
          ctx.moveTo(x, y);
        } else {
          ctx.lineTo(x, y);
        }
        x += sliceWidth;
      }

      ctx.lineTo(w, h / 2);
      ctx.stroke();

      const dbNorm = Math.max(-60, Math.min(0, db));
      const barHeight = ((dbNorm + 60) / 60) * (h * 0.8);

      ctx.fillStyle =
        dbNorm > -12
          ? "rgb(239, 68, 68)"
          : dbNorm > -24
            ? "rgb(234, 179, 8)"
            : "rgb(74, 222, 128)";
      ctx.fillRect(w - 12, h - barHeight, 8, barHeight);
    };

    draw();

    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
    };
  }, [analyserNode]);

  return (
    <div className="rounded-xl border border-[#d2d2d7] bg-white p-2">
      <canvas
        ref={canvasRef}
        width={300}
        height={80}
        className="block w-full rounded-lg"
      />
    </div>
  );
}
