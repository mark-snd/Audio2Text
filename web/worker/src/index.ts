/**
 * Cloudflare Worker - Minutes Generation API
 *
 * Routes:
 *   POST /api/upload          - Upload audio file to R2
 *   POST /api/process/:jobId  - Start transcription + minutes pipeline
 *   GET  /api/status/:jobId   - Poll job progress
 *   GET  /api/result/:jobId   - Get transcript + minutes
 *   GET  /api/download/:jobId - Download minutes as .md file
 */
import { Hono } from "hono";
import { cors } from "hono/cors";
import type { Env, JobStatus, ProcessRequest, UploadResponse } from "./types";
import { isSupportedAudio } from "./services/gemini";

// Re-export Durable Object
export { JobProcessor } from "./durable/JobProcessor";

const app = new Hono<{ Bindings: Env }>();

// CORS for frontend
app.use(
  "/api/*",
  cors({
    origin: [
      "http://localhost:5173",
      "http://localhost:4173",
      "https://minutes-app.pages.dev",
    ],
    allowMethods: ["GET", "POST", "OPTIONS"],
    allowHeaders: ["Content-Type", "X-Passcode"],
  })
);

// Health check (no auth required)
app.get("/api/health", (c) => c.json({ status: "ok" }));

// Passcode verification endpoint (no auth middleware)
app.post("/api/verify", async (c) => {
  const { passcode } = await c.req.json<{ passcode: string }>();
  if (passcode === c.env.APP_PASSCODE) {
    return c.json({ ok: true });
  }
  return c.json({ ok: false, error: "Invalid passcode" }, 401);
});

// Auth middleware — all routes below require passcode
app.use("/api/*", async (c, next) => {
  // Skip for health and verify endpoints (already handled above)
  const path = new URL(c.req.url).pathname;
  if (path === "/api/health" || path === "/api/verify") {
    return next();
  }

  const passcode =
    c.req.header("X-Passcode") ||
    new URL(c.req.url).searchParams.get("passcode");
  if (!passcode || passcode !== c.env.APP_PASSCODE) {
    return c.json({ error: "Unauthorized" }, 401);
  }
  return next();
});

// Upload audio file
app.post("/api/upload", async (c) => {
  const maxSize =
    parseInt(c.env.MAX_UPLOAD_SIZE_MB || "100") * 1024 * 1024;

  const formData = await c.req.formData();
  const file = formData.get("file") as File | null;

  if (!file) {
    return c.json({ error: "No file provided" }, 400);
  }

  if (!isSupportedAudio(file.name)) {
    return c.json(
      {
        error: `Unsupported format. Supported: wav, mp3, aiff, aac, ogg, flac, m4a`,
      },
      400
    );
  }

  if (file.size > maxSize) {
    return c.json(
      { error: `File too large. Max: ${c.env.MAX_UPLOAD_SIZE_MB}MB` },
      400
    );
  }

  // Generate job ID
  const jobId = crypto.randomUUID();

  // Store in R2
  const arrayBuffer = await file.arrayBuffer();
  await c.env.BUCKET.put(`audio/${jobId}/${file.name}`, arrayBuffer, {
    httpMetadata: { contentType: file.type || "audio/mpeg" },
    customMetadata: { originalName: file.name },
  });

  // Initialize job status in KV
  const status: JobStatus = {
    jobId,
    filename: file.name,
    step: "uploaded",
    progress: 0,
    message: "업로드 완료",
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  };

  await c.env.JOB_STATUS.put(jobId, JSON.stringify(status), {
    expirationTtl: 86400,
  });

  const response: UploadResponse = {
    jobId,
    filename: file.name,
    size: file.size,
  };

  return c.json(response, 201);
});

// Start processing pipeline
app.post("/api/process/:jobId", async (c) => {
  const jobId = c.req.param("jobId");

  // Check job exists
  const statusRaw = await c.env.JOB_STATUS.get(jobId);
  if (!statusRaw) {
    return c.json({ error: "Job not found" }, 404);
  }

  const status: JobStatus = JSON.parse(statusRaw);

  if (status.step !== "uploaded" && status.step !== "error") {
    return c.json({ error: "Job already processing or completed" }, 409);
  }

  // Parse optional event metadata
  let body: ProcessRequest = {};
  try {
    body = await c.req.json<ProcessRequest>();
  } catch {
    // No body is fine
  }

  // Get Durable Object and start processing
  // Place DO in Western North America to avoid Gemini API geo-restrictions
  const doId = c.env.JOB_PROCESSOR.idFromName(jobId);
  const doStub = c.env.JOB_PROCESSOR.get(doId, { locationHint: "wnam" });

  const doRequest = new Request("https://do/process", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      jobId,
      filename: status.filename,
      eventMeta: body.eventMeta,
      minutesEngine: body.minutesEngine,
    }),
  });

  // DO stores params and sets an alarm, then responds immediately.
  // The alarm runs the pipeline independently.
  await doStub.fetch(doRequest);

  return c.json({ jobId, status: "processing" });
});

// Poll job status
app.get("/api/status/:jobId", async (c) => {
  const jobId = c.req.param("jobId");
  const statusRaw = await c.env.JOB_STATUS.get(jobId);

  if (!statusRaw) {
    return c.json({ error: "Job not found" }, 404);
  }

  return c.json(JSON.parse(statusRaw));
});

// Get results
app.get("/api/result/:jobId", async (c) => {
  const jobId = c.req.param("jobId");

  // Check job is completed
  const statusRaw = await c.env.JOB_STATUS.get(jobId);
  if (!statusRaw) {
    return c.json({ error: "Job not found" }, 404);
  }

  const status: JobStatus = JSON.parse(statusRaw);
  if (status.step !== "completed") {
    return c.json({ error: "Job not completed yet", step: status.step }, 400);
  }

  // Fetch results from R2
  const [transcriptObj, minutesObj] = await Promise.all([
    c.env.BUCKET.get(`results/${jobId}/transcript.json`),
    c.env.BUCKET.get(`results/${jobId}/minutes.md`),
  ]);

  const transcript = transcriptObj
    ? JSON.parse(await transcriptObj.text())
    : [];
  const minutes = minutesObj ? await minutesObj.text() : "";

  return c.json({ jobId, transcript, minutes });
});

// Download minutes as file
app.get("/api/download/:jobId", async (c) => {
  const jobId = c.req.param("jobId");

  // Try to fetch the file from R2 directly (strongly consistent)
  // instead of gating on KV status which has eventual consistency
  const minutesObj = await c.env.BUCKET.get(`results/${jobId}/minutes.md`);
  if (!minutesObj) {
    // Check KV to give a more specific error message
    const statusRaw = await c.env.JOB_STATUS.get(jobId);
    if (!statusRaw) {
      return c.json({ error: "Job not found" }, 404);
    }
    const status: JobStatus = JSON.parse(statusRaw);
    if (status.step === "error") {
      return c.json({ error: status.error || "Job failed" }, 400);
    }
    return c.json({ error: "Job not completed yet" }, 400);
  }

  // Get filename from KV for the download name, with fallback
  let downloadName = "minutes.md";
  const statusRaw = await c.env.JOB_STATUS.get(jobId);
  if (statusRaw) {
    const status: JobStatus = JSON.parse(statusRaw);
    const stem = status.filename.replace(/\.[^.]+$/, "");
    downloadName = `${stem}_minutes.md`;
  }

  return new Response(minutesObj.body, {
    headers: {
      "Content-Type": "text/markdown; charset=utf-8",
      "Content-Disposition": `attachment; filename="${downloadName}"`,
    },
  });
});

export default app;
