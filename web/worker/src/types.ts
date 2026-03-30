// Cloudflare bindings
export interface Env {
  BUCKET: R2Bucket;
  JOB_STATUS: KVNamespace;
  JOB_PROCESSOR: DurableObjectNamespace;
  GEMINI_API_KEY: string;
  APP_PASSCODE: string;
  GEMINI_MODEL: string;
  MAX_UPLOAD_SIZE_MB: string;
}

// Job status tracking
export type JobStep =
  | "uploaded"
  | "transcribing"
  | "transcribed"
  | "generating_minutes"
  | "completed"
  | "error";

export interface JobStatus {
  jobId: string;
  filename: string;
  step: JobStep;
  progress: number; // 0-100
  message: string;
  createdAt: string;
  updatedAt: string;
  error?: string;
}

// Transcript segment (matches Python version)
export interface TranscriptSegment {
  start_time: number;
  end_time: number;
  text: string;
}

// Event metadata (matches event-meta.json format)
export interface EventMeta {
  event_name?: string;
  date?: string;
  speakers?: Array<{ name: string; role: string }>;
  terminology?: string[];
}

// API request/response types
export interface UploadResponse {
  jobId: string;
  filename: string;
  size: number;
}

export interface ProcessRequest {
  eventMeta?: EventMeta;
}

export interface StatusResponse extends JobStatus {}

export interface ResultResponse {
  jobId: string;
  transcript: TranscriptSegment[];
  minutes: string;
}
