import { useState, useEffect } from "react";
import type { JobStatus } from "../api/client";

interface Props {
  filename: string;
  status: JobStatus | null;
  isUploading: boolean;
  displayProgress: number;
  processingStartedAt: number | null;
}

interface StepInfo {
  label: string;
  key: string;
  hint: string | null;
}

const STEPS: StepInfo[] = [
  { label: "업로드", key: "uploaded", hint: null },
  { label: "음성 인식 (Gemini)", key: "transcribing", hint: "보통 1~3분 소요" },
  { label: "회의록 생성 (Claude)", key: "generating_minutes", hint: "보통 1~2분 소요" },
  { label: "완료", key: "completed", hint: null },
];

function getStepIndex(step: string): number {
  if (step === "uploaded") return 0;
  if (step === "transcribing" || step === "transcribed") return 1;
  if (step === "generating_minutes") return 2;
  if (step === "completed") return 3;
  return -1;
}

function formatElapsed(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export function ProgressTracker({
  filename,
  status,
  isUploading,
  displayProgress,
  processingStartedAt,
}: Props) {
  const currentStep = status ? getStepIndex(status.step) : isUploading ? 0 : -1;
  const progress = Math.round(Math.max(displayProgress, isUploading ? 1 : 0));
  const isActive = isUploading || (currentStep >= 0 && currentStep < 3);

  // Elapsed time counter
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    if (!processingStartedAt) {
      setElapsed(0);
      return;
    }

    setElapsed(Math.floor((Date.now() - processingStartedAt) / 1000));
    const timer = setInterval(() => {
      setElapsed(Math.floor((Date.now() - processingStartedAt) / 1000));
    }, 1000);

    return () => clearInterval(timer);
  }, [processingStartedAt]);

  return (
    <div className="space-y-6">
      {/* Filename */}
      <div className="flex items-center gap-2 text-gray-600">
        <span>&#127925;</span>
        <span className="font-medium">{filename}</span>
      </div>

      {/* Progress bar with percentage */}
      <div>
        <div className="flex items-center gap-3">
          <div className="flex-1 bg-gray-200 rounded-full h-3 overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-200 ease-out ${
                isActive ? "progress-bar-active" : "bg-blue-600"
              }`}
              style={{ width: `${Math.max(progress, 3)}%` }}
            />
          </div>
          <span className="text-sm font-medium text-gray-500 w-10 text-right tabular-nums">
            {progress}%
          </span>
        </div>

        {/* Elapsed time */}
        {processingStartedAt && currentStep < 3 && (
          <p className="text-xs text-gray-400 mt-1.5 tabular-nums">
            경과 시간: {formatElapsed(elapsed)}
          </p>
        )}
      </div>

      {/* Steps */}
      <div className="space-y-3">
        {STEPS.map((step, i) => {
          const isDone = currentStep > i;
          const isStepActive = currentStep === i;

          return (
            <div key={step.key} className="flex items-start gap-3">
              {/* Icon with pulse ring */}
              <div className="relative flex-shrink-0 mt-0.5">
                {isStepActive && (
                  <div className="absolute inset-0 w-6 h-6 rounded-full bg-blue-400 animate-pulse-ring" />
                )}
                <div
                  className={`relative w-6 h-6 rounded-full flex items-center justify-center text-xs font-medium ${
                    isDone
                      ? "bg-green-500 text-white"
                      : isStepActive
                        ? "bg-blue-500 text-white"
                        : "bg-gray-200 text-gray-400"
                  }`}
                >
                  {isDone ? (
                    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                    </svg>
                  ) : isStepActive ? (
                    <svg className="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                    </svg>
                  ) : (
                    i + 1
                  )}
                </div>
              </div>

              {/* Label + status message + hint */}
              <div className="min-w-0">
                <span
                  className={`text-sm ${
                    isDone
                      ? "text-green-600"
                      : isStepActive
                        ? "text-blue-600 font-medium"
                        : "text-gray-400"
                  }`}
                >
                  {step.label}
                  {isStepActive && status?.message ? ` — ${status.message}` : ""}
                </span>
                {isStepActive && step.hint && (
                  <p className="text-xs text-gray-400 mt-0.5">{step.hint}</p>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
