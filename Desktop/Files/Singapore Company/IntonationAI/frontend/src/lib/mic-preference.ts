const KEY = "intonationai_mic_device_id";

export function getStoredMicId(): string | null {
  if (typeof window === "undefined") return null;
  try {
    const v = localStorage.getItem(KEY);
    return v && v.length > 0 ? v : null;
  } catch {
    return null;
  }
}

export function setStoredMicId(deviceId: string): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(KEY, deviceId);
  } catch {
    /* ignore */
  }
}
