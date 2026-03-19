const MIC_STORAGE_KEY = "intonation_mic_device_id";

export function getStoredMicId(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(MIC_STORAGE_KEY);
}

export function setStoredMicId(deviceId: string | null): void {
  if (typeof window === "undefined") return;
  if (deviceId) {
    localStorage.setItem(MIC_STORAGE_KEY, deviceId);
  } else {
    localStorage.removeItem(MIC_STORAGE_KEY);
  }
}
