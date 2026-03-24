"use client";

import { useState, useEffect, useCallback, useRef } from "react";

interface TimerProps {
  durationSec?: number;
  onComplete?: () => void;
  autoStart?: boolean;
  onTick?: (seconds: number, running: boolean) => void;
}

function pad(n: number): string {
  return n.toString().padStart(2, "0");
}

export function Timer({
  durationSec,
  onComplete,
  autoStart = false,
  onTick,
}: TimerProps) {
  const isCountdown = typeof durationSec === "number" && durationSec > 0;
  const initial = isCountdown ? durationSec : 0;

  const [seconds, setSeconds] = useState(initial);
  const [running, setRunning] = useState(autoStart);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const onCompleteRef = useRef(onComplete);
  const firedCompleteRef = useRef(false);

  useEffect(() => {
    onCompleteRef.current = onComplete;
  }, [onComplete]);

  const tick = useCallback(() => {
    setSeconds((prev) => {
      if (isCountdown) {
        if (prev <= 1) {
          setRunning(false);
          return 0;
        }
        return prev - 1;
      }
      return prev + 1;
    });
  }, [isCountdown]);

  useEffect(() => {
    if (running) {
      intervalRef.current = setInterval(tick, 1000);
    }
    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [running, tick]);

  useEffect(() => {
    if (
      isCountdown &&
      seconds === 0 &&
      !running &&
      !firedCompleteRef.current
    ) {
      firedCompleteRef.current = true;
      onCompleteRef.current?.();
    }
    if (isCountdown && seconds > 0) {
      firedCompleteRef.current = false;
    }
  }, [isCountdown, seconds, running]);

  useEffect(() => {
    onTick?.(seconds, running);
  }, [seconds, running, onTick]);

  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  const display = `${pad(mins)}:${pad(secs)}`;

  const handleStart = () => setRunning(true);
  const handlePause = () => setRunning(false);
  const handleReset = () => {
    setRunning(false);
    firedCompleteRef.current = false;
    setSeconds(initial);
  };

  return (
    <div className="flex flex-col items-center gap-4">
      <div
        className={`
          font-mono text-5xl tabular-nums text-[#1d1d1f]
          ${running ? "motion-safe:animate-pulse" : ""}
        `}
        role="timer"
        aria-live="polite"
      >
        {display}
      </div>
      <div className="flex gap-2">
        {!running ? (
          <button
            type="button"
            onClick={handleStart}
            className="rounded-xl bg-[#0071e3] px-4 py-2 text-sm font-medium text-white hover:bg-[#0077ed]"
          >
            Start
          </button>
        ) : (
          <button
            type="button"
            onClick={handlePause}
            className="rounded-xl bg-[#6e6e73] px-4 py-2 text-sm font-medium text-white hover:bg-[#5e5e63]"
          >
            Pause
          </button>
        )}
        <button
          type="button"
          onClick={handleReset}
          className="rounded-xl border border-[#d2d2d7] px-4 py-2 text-sm font-medium text-[#1d1d1f] hover:bg-[#f5f5f7]"
        >
          Reset
        </button>
      </div>
    </div>
  );
}
