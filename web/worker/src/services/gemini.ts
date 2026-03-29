/**
 * Gemini transcription service - ported from trans_gemini.py
 */
import type { TranscriptSegment, EventMeta } from "../types";

const MAX_OUTPUT_TOKENS = 65536;

const MIME_TYPE_MAP: Record<string, string> = {
  ".wav": "audio/wav",
  ".mp3": "audio/mp3",
  ".aiff": "audio/aiff",
  ".aac": "audio/aac",
  ".ogg": "audio/ogg",
  ".flac": "audio/flac",
  ".m4a": "audio/mp4",
};

export function getMimeType(filename: string): string {
  const ext = "." + filename.split(".").pop()?.toLowerCase();
  return MIME_TYPE_MAP[ext] || "application/octet-stream";
}

export function isSupportedAudio(filename: string): boolean {
  const ext = "." + filename.split(".").pop()?.toLowerCase();
  return ext in MIME_TYPE_MAP;
}

function buildTranscriptionPrompt(eventMeta?: EventMeta): string {
  const basePrompt = `Transcribe this audio and output ONLY a valid JSON array.

Output format - a JSON array of segments with timestamps:
[
    {"start_time": 0.0, "end_time": 5.2, "text": "First sentence here"},
    {"start_time": 5.2, "end_time": 10.5, "text": "Second sentence here"}
]

Rules:
1. COMPLETE TRANSCRIPTION: Transcribe the ENTIRE audio from start to finish. Do not truncate or summarize.

2. TIMESTAMPS: Use seconds as float values (e.g., 65.5 for 1 minute 5.5 seconds).

3. LANGUAGE: Transcribe in Korean if the speaker is speaking Korean. Preserve the original language.

4. CONSOLIDATE TERMS: Convert phonetic Korean-English terms to proper English:
   - Convert phonetic readings to proper English terms where appropriate

5. REMOVE the following unrelated content:
   - Break-time conversations (discussions about food, restaurants, logistics)
   - Moderator transitions and introductions for next speakers
   - Audience reactions, applause
   - Repeated phrases/hallucinations (same phrase repeated many times)
   - Informal chatter before/after the main presentation

6. OUTPUT: Return ONLY the JSON array, no markdown code blocks, no explanations.`;

  if (eventMeta) {
    const metaJson = JSON.stringify(eventMeta, null, 2);
    return `Event context (use this for accurate transcription of names, terms, and topics):
${metaJson}

${basePrompt}`;
  }

  return basePrompt;
}

/**
 * Parse timestamp that may be in various formats from Gemini.
 * Ported from trans_gemini.py parse_timestamp()
 */
function parseTimestamp(
  value: number | string,
  prevTimestamp?: number
): number {
  if (typeof value === "number") return value;

  const str = String(value).trim();

  if (str.includes(":")) {
    const parts = str.split(":");
    try {
      if (parts.length === 3) {
        // T:S:mmm format
        const tens = parseInt(parts[0]);
        const secDigit = parseInt(parts[1]);
        const millisStr = parts[2];
        const millis = millisStr.includes(".")
          ? parseFloat(millisStr)
          : parseFloat(millisStr) / 1000;
        return tens * 600 + secDigit + millis;
      } else if (parts.length === 2) {
        const first = parseInt(parts[0]);
        const second = parseFloat(parts[1]);
        const mmSs = first * 60 + second;
        const tSs = first * 600 + second;

        if (first > 5) return mmSs;
        if (second >= 60) return tSs;

        if (prevTimestamp !== undefined) {
          const mmValid = mmSs >= prevTimestamp;
          const tValid = tSs >= prevTimestamp;
          if (tValid && !mmValid) return tSs;
          if (mmValid && !tValid) return mmSs;
          if (tValid && mmValid && prevTimestamp > 500) return tSs;
        }
        return mmSs;
      }
    } catch {
      // fall through
    }
  }

  const parsed = parseFloat(str);
  return isNaN(parsed) ? 0 : parsed;
}

/**
 * Parse JSON transcript from Gemini response.
 * Ported from trans_gemini.py parse_transcript_json()
 */
function parseTranscriptJson(responseText: string): TranscriptSegment[] {
  let text = responseText.trim();

  // Remove markdown code blocks
  if (text.startsWith("```")) {
    const firstNewline = text.indexOf("\n");
    if (firstNewline !== -1) text = text.slice(firstNewline + 1);
    if (text.endsWith("```")) text = text.slice(0, -3);
    text = text.trim();
  }
  text = text.replace(/^```json\s*/, "").replace(/\s*```$/, "");

  try {
    const segments = JSON.parse(text);
    if (!Array.isArray(segments)) {
      throw new Error(`Expected JSON array, got ${typeof segments}`);
    }

    const validated: TranscriptSegment[] = [];
    let prevEndTime: number | undefined;

    for (const seg of segments) {
      if (typeof seg !== "object" || seg === null) continue;

      const startRaw = seg.start_time ?? seg.start ?? 0;
      const endRaw = seg.end_time ?? seg.end ?? 0;
      const textContent = seg.text || seg.content || "";

      if (textContent) {
        const startTime = parseTimestamp(startRaw, prevEndTime);
        const endTime = parseTimestamp(endRaw, startTime);
        validated.push({
          start_time: startTime,
          end_time: endTime,
          text: String(textContent).trim(),
        });
        prevEndTime = endTime;
      }
    }
    return validated;
  } catch (e) {
    // Try to salvage truncated JSON
    const pattern =
      /\{\s*"start_time"\s*:\s*[\d.:]+\s*(?:,\s*"end_time"\s*:\s*[\d.:]+\s*)?,\s*"text"\s*:\s*"(?:[^"\\]|\\.)*"\s*\}/g;
    const matches = text.match(pattern);

    if (matches && matches.length > 0) {
      const salvaged: TranscriptSegment[] = [];
      let prevEnd: number | undefined;

      for (const match of matches) {
        try {
          // Fix colon-format timestamps for JSON parsing
          const fixed = match.replace(
            /"(start_time|end_time)"\s*:\s*([\d]+:[\d.:]+)/g,
            '"$1": "$2"'
          );
          const seg = JSON.parse(fixed);
          if (seg.text) {
            const startTime = parseTimestamp(seg.start_time ?? 0, prevEnd);
            const endTime = parseTimestamp(seg.end_time ?? 0, startTime);
            salvaged.push({
              start_time: startTime,
              end_time: endTime,
              text: String(seg.text).trim(),
            });
            prevEnd = endTime;
          }
        } catch {
          continue;
        }
      }

      if (salvaged.length > 0) return salvaged;
    }

    throw new Error(`Failed to parse transcript JSON: ${e}`);
  }
}

/**
 * Transcribe audio using Gemini API.
 *
 * Uses the Gemini File API to upload audio, then generates transcription.
 */
/**
 * Convert ArrayBuffer to base64 string.
 */
function arrayBufferToBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (let i = 0; i < bytes.byteLength; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}

// 20MB threshold: inline base64 for smaller files, File API for larger
const INLINE_MAX_BYTES = 20 * 1024 * 1024;

export async function transcribeAudio(
  audioData: ArrayBuffer,
  filename: string,
  apiKey: string,
  model: string,
  eventMeta?: EventMeta
): Promise<TranscriptSegment[]> {
  const mimeType = getMimeType(filename);
  const prompt = buildTranscriptionPrompt(eventMeta);

  // Build the audio part — inline base64 for files under 20MB,
  // File API for larger files (avoids "location not supported" errors
  // from Cloudflare Worker edge locations)
  let audioPart: Record<string, unknown>;

  if (audioData.byteLength <= INLINE_MAX_BYTES) {
    const base64Data = arrayBufferToBase64(audioData);
    audioPart = {
      inline_data: { mime_type: mimeType, data: base64Data },
    };
  } else {
    // Fall back to File API for large files
    const { fileUri, fileName } = await uploadToGeminiFileApi(
      audioData,
      filename,
      mimeType,
      apiKey
    );
    audioPart = {
      file_data: { file_uri: fileUri, mime_type: mimeType },
    };
    // Clean up uploaded file after generation (best effort)
    setTimeout(() => {
      fetch(
        `https://generativelanguage.googleapis.com/v1beta/${fileName}?key=${apiKey}`,
        { method: "DELETE" }
      ).catch(() => {});
    }, 300000); // clean up after 5 min
  }

  // Generate transcription
  const generateUrl = `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${apiKey}`;

  const generateRes = await fetch(generateUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      contents: [
        {
          parts: [{ text: prompt }, audioPart],
        },
      ],
      generationConfig: {
        maxOutputTokens: MAX_OUTPUT_TOKENS,
        // Only enable thinking for models that require it (e.g. 2.5 Pro)
        ...(model.includes("2.5-pro") && {
          thinkingConfig: { thinkingBudget: 1024 },
        }),
      },
    }),
  });

  if (!generateRes.ok) {
    const errText = await generateRes.text();
    throw new Error(
      `Gemini generation failed: ${generateRes.status} ${errText}`
    );
  }

  const genResult = (await generateRes.json()) as {
    candidates?: Array<{
      content: { parts: Array<{ text?: string; thought?: boolean }> };
      finishReason?: string;
    }>;
  };

  // Gemini 2.5 Pro has thinking enabled by default.
  // The parts array may contain { thought: true, text: "..." } entries.
  // We need the non-thinking part that has the actual transcript.
  const parts = genResult.candidates?.[0]?.content?.parts ?? [];
  const responsePart = parts.find((p) => !p.thought && p.text);
  const responseText = responsePart?.text;
  if (!responseText) {
    const finishReason = genResult.candidates?.[0]?.finishReason;
    console.log(
      "Gemini parts:",
      JSON.stringify(
        parts.map((p) => ({ thought: p.thought, textLen: p.text?.length }))
      )
    );
    throw new Error(
      `Gemini returned empty response (finishReason=${finishReason})`
    );
  }

  return parseTranscriptJson(responseText);
}

/**
 * Upload file to Gemini File API (for files > 20MB).
 */
async function uploadToGeminiFileApi(
  audioData: ArrayBuffer,
  filename: string,
  mimeType: string,
  apiKey: string
): Promise<{ fileUri: string; fileName: string }> {
  const uploadUrl = `https://generativelanguage.googleapis.com/upload/v1beta/files?key=${apiKey}`;

  const startRes = await fetch(uploadUrl, {
    method: "POST",
    headers: {
      "X-Goog-Upload-Protocol": "resumable",
      "X-Goog-Upload-Command": "start",
      "X-Goog-Upload-Header-Content-Length": String(audioData.byteLength),
      "X-Goog-Upload-Header-Content-Type": mimeType,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ file: { display_name: filename } }),
  });

  if (!startRes.ok) {
    const errText = await startRes.text();
    throw new Error(
      `Gemini upload start failed: ${startRes.status} ${errText}`
    );
  }

  const uploadUri = startRes.headers.get("X-Goog-Upload-URL");
  if (!uploadUri) throw new Error("No upload URI returned from Gemini");

  const uploadRes = await fetch(uploadUri, {
    method: "POST",
    headers: {
      "X-Goog-Upload-Command": "upload, finalize",
      "X-Goog-Upload-Offset": "0",
      "Content-Type": mimeType,
    },
    body: audioData,
  });

  if (!uploadRes.ok) {
    const errText = await uploadRes.text();
    throw new Error(`Gemini upload failed: ${uploadRes.status} ${errText}`);
  }

  const result = (await uploadRes.json()) as {
    file: { uri: string; name: string; state: string };
  };

  let fileState = result.file.state;
  while (fileState === "PROCESSING") {
    await new Promise((r) => setTimeout(r, 2000));
    const checkRes = await fetch(
      `https://generativelanguage.googleapis.com/v1beta/${result.file.name}?key=${apiKey}`
    );
    const checkData = (await checkRes.json()) as { state: string };
    fileState = checkData.state;
  }

  if (fileState === "FAILED") {
    throw new Error("Gemini file processing failed");
  }

  return { fileUri: result.file.uri, fileName: result.file.name };
}
