"use client";

import { useRef, useState, useCallback } from "react";
import { SAMPLE_RATE, FFT_SIZE } from "@/lib/constants";

const RECORDER_CHUNK_MS = 250;

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
      const source = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = FFT_SIZE;
      source.connect(analyser);

      chunksRef.current = [];
      const recorder = new MediaRecorder(stream, {
        mimeType: MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
          ? "audio/webm;codecs=opus"
          : "audio/webm",
        audioBitsPerSecond: 128000,
      });
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      recorder.start(RECORDER_CHUNK_MS);

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
    ctxRef.current?.close();
    streamRef.current = null;
    ctxRef.current = null;
    sourceRef.current = null;
    setState({ isCapturing: false, analyserNode: null, error: null });
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
    return new Blob(toKeep, { type: chunks[0]?.type ?? "audio/webm" });
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
