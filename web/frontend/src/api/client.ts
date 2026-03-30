const API_BASE = import.meta.env.DEV
  ? "/api"
  : "https://minutes-worker.sndworks.workers.dev/api";

// Passcode stored in sessionStorage
const PASSCODE_KEY = "app_passcode";

export function getPasscode(): string | null {
  return sessionStorage.getItem(PASSCODE_KEY);
}

export function setPasscode(code: string): void {
  sessionStorage.setItem(PASSCODE_KEY, code);
}

export function clearPasscode(): void {
  sessionStorage.removeItem(PASSCODE_KEY);
}

function authHeaders(extra?: Record<string, string>): Record<string, string> {
  const passcode = getPasscode();
  return {
    ...(passcode ? { "X-Passcode": passcode } : {}),
    ...extra,
  };
}

export async function verifyPasscode(passcode: string): Promise<boolean> {
  const res = await fetch(`${API_BASE}/verify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ passcode }),
  });
  if (!res.ok) return false;
  const data = (await res.json()) as { ok: boolean };
  return data.ok;
}

export async function uploadAudio(
  file: File,
  onProgress?: (percent: number) => void
): Promise<{ jobId: string; filename: string; size: number }> {
  const formData = new FormData();
  formData.append("file", file);

  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE}/upload`);

    // Set auth header
    const passcode = getPasscode();
    if (passcode) xhr.setRequestHeader("X-Passcode", passcode);

    // Track upload progress
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) {
        onProgress(Math.round((e.loaded / e.total) * 100));
      }
    };

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(JSON.parse(xhr.responseText));
      } else {
        try {
          const err = JSON.parse(xhr.responseText);
          reject(new Error(err.error || "Upload failed"));
        } catch {
          reject(new Error("Upload failed"));
        }
      }
    };

    xhr.onerror = () => reject(new Error("Upload failed"));
    xhr.send(formData);
  });
}

export interface EventMeta {
  event_name?: string;
  date?: string;
  speakers?: Array<{ name: string; role: string }>;
  terminology?: string[];
}

export async function startProcessing(
  jobId: string,
  eventMeta?: EventMeta,
): Promise<void> {
  const res = await fetch(`${API_BASE}/process/${jobId}`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ eventMeta }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: "Failed to start" }));
    throw new Error((err as { error: string }).error);
  }
}

export interface JobStatus {
  jobId: string;
  filename: string;
  step: string;
  progress: number;
  message: string;
  error?: string;
}

export async function getStatus(jobId: string): Promise<JobStatus> {
  const res = await fetch(`${API_BASE}/status/${jobId}`, {
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error("Failed to get status");
  return res.json();
}

export interface TranscriptSegment {
  start_time: number;
  end_time: number;
  text: string;
}

export interface JobResult {
  jobId: string;
  transcript: TranscriptSegment[];
  minutes: string;
}

export async function getResult(jobId: string): Promise<JobResult> {
  const res = await fetch(`${API_BASE}/result/${jobId}`, {
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error("Failed to get result");
  return res.json();
}

export async function downloadFile(jobId: string): Promise<Blob> {
  const res = await fetch(`${API_BASE}/download/${jobId}`, {
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error("Failed to download");
  return res.blob();
}
