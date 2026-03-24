"use client";

import { useRef, useState, useCallback } from "react";
import { SAMPLE_RATE, FFT_SIZE } from "@/lib/constants";

const RECORDER_CHUNK_MS = 250;
const MAX_CHUNK_RETENTION_SEC = 60;
const MAX_CHUNKS = Math.ceil(
  (MAX_CHUNK_RETENTION_SEC * 1000) / RECORDER_CHUNK_MS
);

function pickRecorderMimeType(): string {
  const candidates = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/mp4",
    "audio/mp4;codecs=mp4a.40.2",
    "audio/aac",
  ];
  for (const t of candidates) {
    if (typeof MediaRecorder !== "undefined" && MediaRecorder.isTypeSupported(t)) {
      return t;
    }
  }
  return "";
}

export interface AudioCaptureState {
  isCapturing: boolean;
  analyserNode: AnalyserNode | null;
  error: string | null;
}

export interface AudioCaptureOptions {
  deviceId?: string;
}

export function useAudioCapture() {
  const [state, setState] = useState<AudioCaptureState>({
    isCapturing: false,
    analyserNode: null,
    error: null,
  });

  const ctxRef = useRef<AudioContext | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const recordedMimeRef = useRef<string>("audio/webm");

  const start = useCallback(async (options?: AudioCaptureOptions) => {
    try {
      const audioConstraints: MediaTrackConstraints = {
        sampleRate: SAMPLE_RATE,
        echoCancellation: true,
        noiseSuppression: true,
      };
      if (options?.deviceId) {
        audioConstraints.deviceId = { exact: options.deviceId };
      }
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: audioConstraints,
      });
      const ctx = new AudioContext({ sampleRate: SAMPLE_RATE });
      await ctx.resume();
      const source = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = FFT_SIZE;
      source.connect(analyser);

      const mimeType = pickRecorderMimeType();
      recordedMimeRef.current = mimeType || "audio/webm";
      const recorderOptions: MediaRecorderOptions = {
        audioBitsPerSecond: 128000,
      };
      if (mimeType) {
        recorderOptions.mimeType = mimeType;
      }
      const recorder = new MediaRecorder(stream, recorderOptions);

      chunksRef.current = [];
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) {
          chunksRef.current.push(e.data);
          if (chunksRef.current.length > MAX_CHUNKS) {
            chunksRef.current = chunksRef.current.slice(-MAX_CHUNKS);
          }
        }
      };
      recorder.start(RECORDER_CHUNK_MS);

      const audioTrack = stream.getAudioTracks()[0];
      if (audioTrack) {
        audioTrack.addEventListener(
          "ended",
          () => {
            setState({
              isCapturing: false,
              analyserNode: null,
              error:
                "Microphone disconnected. Reconnect your mic or pick another device.",
            });
            if (recorderRef.current?.state === "recording") {
              try {
                recorderRef.current.stop();
              } catch {
                /* ignore */
              }
            }
            recorderRef.current = null;
            streamRef.current?.getTracks().forEach((t) => t.stop());
            streamRef.current = null;
            sourceRef.current = null;
            const c = ctxRef.current;
            ctxRef.current = null;
            if (c) {
              requestAnimationFrame(() => {
                void c.close().catch(() => {});
              });
            }
          },
          { once: true }
        );
      }

      ctxRef.current = ctx;
      streamRef.current = stream;
      sourceRef.current = source;
      recorderRef.current = recorder;

      setState({ isCapturing: true, analyserNode: analyser, error: null });
    } catch (err) {
      setState({
        isCapturing: false,
        analyserNode: null,
        error: err instanceof Error ? err.message : "Microphone access denied",
      });
    }
  }, []);

  const stop = useCallback(() => {
    if (recorderRef.current?.state === "recording") recorderRef.current.stop();
    recorderRef.current = null;
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    sourceRef.current = null;
    const ctx = ctxRef.current;
    ctxRef.current = null;
    setState({ isCapturing: false, analyserNode: null, error: null });
    if (ctx) {
      requestAnimationFrame(() => {
        void ctx.close().catch(() => {});
      });
    }
  }, []);

  const getLastSeconds = useCallback((seconds: number): Blob | null => {
    const chunks = chunksRef.current;
    if (chunks.length === 0) return null;
    const chunksPerSecond = 1000 / RECORDER_CHUNK_MS;
    const targetChunks = Math.min(
      Math.ceil(seconds * chunksPerSecond),
      chunks.length
    );
    const toKeep = chunks.slice(-targetChunks);
    const blobType = chunks[0]?.type || recordedMimeRef.current;
    return new Blob(toKeep, { type: blobType });
  }, []);

  const getTimeDomainData = useCallback((): Float32Array | null => {
    if (!state.analyserNode) return null;
    const buf = new Float32Array(state.analyserNode.fftSize);
    state.analyserNode.getFloatTimeDomainData(buf);
    return buf;
  }, [state.analyserNode]);

  const getFrequencyData = useCallback((): Float32Array | null => {
    if (!state.analyserNode) return null;
    const buf = new Float32Array(state.analyserNode.frequencyBinCount);
    state.analyserNode.getFloatFrequencyData(buf);
    return buf;
  }, [state.analyserNode]);

  return {
    ...state,
    start,
    stop,
    getLastSeconds,
    getTimeDomainData,
    getFrequencyData,
  };
}
