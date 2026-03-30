import { useState, useEffect, useRef, useCallback } from "react";
import {
  uploadAudio,
  startProcessing,
  getStatus,
  getResult,
  type JobStatus,
  type JobResult,
  type EventMeta,
} from "../api/client";

export type AppState = "idle" | "uploading" | "processing" | "completed" | "error";

// Soft ceilings: progress creeps toward these values but never overshoots
function getSoftCeiling(serverProgress: number): number {
  if (serverProgress >= 100) return 100;
  if (serverProgress >= 60) return 92;
  if (serverProgress >= 50) return 58;
  if (serverProgress >= 20) return 45;
  if (serverProgress >= 10) return 18;
  return 5;
}

export function useJob() {
  const [appState, setAppState] = useState<AppState>("idle");
  const [jobId, setJobId] = useState<string | null>(null);
  const [filename, setFilename] = useState<string>("");
  const [status, setStatus] = useState<JobStatus | null>(null);
  const [result, setResult] = useState<JobResult | null>(null);
  const [error, setError] = useState<string>("");
  const [displayProgress, setDisplayProgress] = useState(0);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const interpRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const serverProgressRef = useRef(0);
  const processingStartedAt = useRef<number | null>(null);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const stopInterpolation = useCallback(() => {
    if (interpRef.current) {
      clearInterval(interpRef.current);
      interpRef.current = null;
    }
  }, []);

  // Progress interpolation — smooth easing between server updates
  useEffect(() => {
    if (appState !== "processing") {
      stopInterpolation();
      return;
    }

    interpRef.current = setInterval(() => {
      setDisplayProgress((prev) => {
        const ceiling = getSoftCeiling(serverProgressRef.current);
        if (prev >= ceiling) return prev;
        // Ease-out: fast at first, slows near ceiling
        const next = prev + (ceiling - prev) * 0.08;
        return Math.min(next, ceiling);
      });
    }, 200);

    return stopInterpolation;
  }, [appState, stopInterpolation]);

  // Poll for status updates
  useEffect(() => {
    if (!jobId || appState !== "processing") return;

    const poll = async () => {
      try {
        const s = await getStatus(jobId);
        setStatus(s);
        serverProgressRef.current = s.progress;

        // Jump displayProgress to at least the server value
        setDisplayProgress((prev) => Math.max(prev, s.progress));

        if (s.step === "completed") {
          stopPolling();
          stopInterpolation();
          setDisplayProgress(100);
          const r = await getResult(jobId);
          setResult(r);
          setAppState("completed");
        } else if (s.step === "error") {
          stopPolling();
          stopInterpolation();
          setError(s.error || "Unknown error");
          setAppState("error");
        }
      } catch {
        // Network error - keep polling
      }
    };

    poll(); // immediate first poll
    pollRef.current = setInterval(poll, 2000);

    return stopPolling;
  }, [jobId, appState, stopPolling, stopInterpolation]);

  const submit = async (file: File, eventMeta?: EventMeta) => {
    try {
      setError("");
      setResult(null);
      setFilename(file.name);
      setDisplayProgress(0);
      serverProgressRef.current = 0;

      // Upload — track real upload progress (maps to 0-8% of overall)
      setAppState("uploading");
      processingStartedAt.current = Date.now();
      const { jobId: id } = await uploadAudio(file, (uploadPercent) => {
        setDisplayProgress(Math.round(uploadPercent * 0.08));
      });
      setJobId(id);

      // Start processing
      setAppState("processing");
      await startProcessing(id, eventMeta);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
      setAppState("error");
    }
  };

  const reset = () => {
    stopPolling();
    stopInterpolation();
    setAppState("idle");
    setJobId(null);
    setFilename("");
    setStatus(null);
    setResult(null);
    setError("");
    setDisplayProgress(0);
    serverProgressRef.current = 0;
    processingStartedAt.current = null;
  };

  return {
    appState, jobId, filename, status, result, error, submit, reset,
    displayProgress, processingStartedAt: processingStartedAt.current,
  };
}
