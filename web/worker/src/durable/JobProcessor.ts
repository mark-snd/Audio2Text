/**
 * Durable Object that orchestrates the transcription → minutes pipeline.
 *
 * Uses alarms for reliable long-running execution:
 * 1. fetch() stores job params and schedules an immediate alarm
 * 2. alarm() runs the actual pipeline (Gemini transcription → Gemini minutes)
 *
 * This decouples the pipeline from the calling Worker's lifecycle,
 * preventing timeouts from killing the processing.
 */
import type { Env, JobStatus, EventMeta } from "../types";
import { transcribeAudio } from "../services/gemini";
import { generateMinutesGemini } from "../services/gemini-minutes";

interface JobParams {
  jobId: string;
  filename: string;
  eventMeta?: EventMeta;
}

export class JobProcessor implements DurableObject {
  private state: DurableObjectState;
  private env: Env;

  constructor(state: DurableObjectState, env: Env) {
    this.state = state;
    this.env = env;
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === "/process" && request.method === "POST") {
      const body = (await request.json()) as JobParams;

      // Store job params in DO storage and schedule immediate alarm
      await this.state.storage.put("jobParams", body);
      await this.state.storage.setAlarm(Date.now() + 1);

      return new Response(
        JSON.stringify({ jobId: body.jobId, status: "started" }),
        { headers: { "Content-Type": "application/json" } }
      );
    }

    return new Response("Not found", { status: 404 });
  }

  /**
   * Alarm handler — runs the pipeline independently of any fetch context.
   * This has its own execution lifetime (up to 15 min wall clock).
   */
  async alarm(): Promise<void> {
    const params = await this.state.storage.get<JobParams>("jobParams");
    if (!params) return;

    await this.runPipeline(params.jobId, params.filename, params.eventMeta);

    // Clean up stored params
    await this.state.storage.delete("jobParams");
  }

  private async updateStatus(
    jobId: string,
    step: JobStatus["step"],
    progress: number,
    message: string,
    error?: string
  ): Promise<void> {
    const existing = await this.env.JOB_STATUS.get(jobId);
    const current: JobStatus = existing
      ? JSON.parse(existing)
      : {
          jobId,
          filename: "",
          step: "uploaded",
          progress: 0,
          message: "",
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString(),
        };

    const updated: JobStatus = {
      ...current,
      step,
      progress,
      message,
      updatedAt: new Date().toISOString(),
      ...(error ? { error } : {}),
    };

    await this.env.JOB_STATUS.put(jobId, JSON.stringify(updated), {
      expirationTtl: 86400,
    });
  }

  private async runPipeline(
    jobId: string,
    filename: string,
    eventMeta?: EventMeta
  ): Promise<void> {
    try {
      // Step 1: Fetch audio from R2
      await this.updateStatus(jobId, "transcribing", 10, "오디오 파일 로딩 중...");

      const audioObject = await this.env.BUCKET.get(`audio/${jobId}/${filename}`);
      if (!audioObject) {
        throw new Error("Audio file not found in R2");
      }
      const audioData = await audioObject.arrayBuffer();

      // Step 2: Transcribe with Gemini
      await this.updateStatus(jobId, "transcribing", 20, "음성 인식 중 (Gemini)...");

      const segments = await transcribeAudio(
        audioData,
        filename,
        this.env.GEMINI_API_KEY,
        this.env.GEMINI_MODEL,
        eventMeta
      );

      if (segments.length === 0) {
        throw new Error(
          "Gemini transcription returned no segments — audio may contain no speech"
        );
      }

      // Save transcript to R2
      await this.updateStatus(jobId, "transcribed", 50, "전사 완료, 결과 저장 중...");

      await this.env.BUCKET.put(
        `results/${jobId}/transcript.json`,
        JSON.stringify(segments, null, 2),
        { httpMetadata: { contentType: "application/json" } }
      );

      // Step 3: Generate minutes with Gemini
      await this.updateStatus(jobId, "generating_minutes", 60, "회의록 생성 중 (Gemini)...");

      const minutes = await generateMinutesGemini(
        segments,
        this.env.GEMINI_API_KEY,
        this.env.GEMINI_MODEL,
        eventMeta
      );

      // Save minutes to R2
      await this.env.BUCKET.put(`results/${jobId}/minutes.md`, minutes, {
        httpMetadata: { contentType: "text/markdown; charset=utf-8" },
      });

      // Done
      await this.updateStatus(jobId, "completed", 100, "완료!");
    } catch (err) {
      const errorMessage =
        err instanceof Error ? err.message : "Unknown error occurred";
      await this.updateStatus(jobId, "error", 0, "오류 발생", errorMessage);
    }
  }
}
