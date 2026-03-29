/**
 * Gemini minutes generation service - alternative to Claude for cost savings.
 */
import type { TranscriptSegment, EventMeta } from "../types";
import { segmentsToText } from "./claude";

const MINUTES_PROMPT = `당신은 회의록 작성 전문가입니다. 주어진 회의 녹취록을 바탕으로 한국어 회의록을 작성하세요.

다음 형식을 따르세요:

# 회의록

## 회의 개요
- 일시:
- 참석자: (녹취록에서 파악 가능한 경우)
- 주제:

## 주요 논의 사항
(각 안건별로 정리)

### 안건 1: [제목]
- 배경 및 경과
- 논의 내용 (발언자별 주요 의견 포함)
- 논의 결과

### 안건 2: [제목]
...

## 결정 사항
- (합의된 내용, 확정된 방향 등)

## Action Items (후속 조치)
- [ ] 담당자: 할 일 내용

## 기타 참고사항
- (추가로 언급된 사항)

작성 규칙:
1. 녹취록의 내용을 빠짐없이 충실하게 정리 (과도한 축약 금지)
2. 각 안건별로 누가 어떤 발언을 했는지, 어떤 맥락에서 논의가 이루어졌는지 구체적으로 기술
3. 서로 다른 의견이 있었다면 각 의견과 그 근거를 모두 기록
4. 구어체를 문어체로 변환하되, 발언의 뉘앙스와 강조점은 유지
5. 완전히 동일한 반복만 제거하고, 비슷하지만 다른 맥락의 발언은 각각 기록
6. 결정 사항과 Action Item을 명확히 구분하고, 결정에 이르기까지의 논의 과정도 요약
7. 숫자, 날짜, 금액 등 구체적인 수치 정보는 반드시 포함
8. 반드시 한국어로 작성
9. 다음 회사명은 반드시 공식 명칭을 사용:
   - SNDWorks
   - YES24
   - 동아출판
   - GripLaps`;

/**
 * Generate meeting minutes from transcript using Gemini API.
 */
export async function generateMinutesGemini(
  segments: TranscriptSegment[],
  apiKey: string,
  model: string,
  eventMeta?: EventMeta
): Promise<string> {
  const transcriptText = segmentsToText(segments);

  if (!transcriptText.trim()) {
    throw new Error("Transcript is empty, cannot generate minutes");
  }

  let userContent = transcriptText;

  if (eventMeta) {
    const metaJson = JSON.stringify(eventMeta, null, 2);
    userContent = `회의 메타 정보:\n${metaJson}\n\n---\n녹취록:\n${transcriptText}`;
  }

  const generateUrl = `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${apiKey}`;

  const response = await fetch(generateUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      systemInstruction: { parts: [{ text: MINUTES_PROMPT }] },
      contents: [{ parts: [{ text: userContent }] }],
      generationConfig: {
        maxOutputTokens: 8192,
        temperature: 0.3,
      },
    }),
  });

  if (!response.ok) {
    const errText = await response.text();
    throw new Error(`Gemini API error: ${response.status} ${errText}`);
  }

  const result = (await response.json()) as {
    candidates?: Array<{
      content: { parts: Array<{ text?: string; thought?: boolean }> };
    }>;
  };

  const parts = result.candidates?.[0]?.content?.parts ?? [];
  const responsePart = parts.find((p) => !p.thought && p.text);
  const text = responsePart?.text;

  if (!text) {
    throw new Error("Gemini returned empty response");
  }

  return text;
}
