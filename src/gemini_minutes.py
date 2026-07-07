#!/usr/bin/env python3
"""
End-to-end audio → transcription → meeting minutes using Gemini.

Pipeline:
1. Transcribe audio using Gemini (via trans_gemini)
2. Generate meeting minutes from transcript using Gemini

Usage:
    python gemini_minutes.py audio/meeting.ogg
    python gemini_minutes.py audio/meeting.ogg -m event-meta.json
    python gemini_minutes.py audio/meeting.ogg -o my_minutes.md
    python gemini_minutes.py --from-transcript output/meeting_transcript.json
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from google import genai
from google.genai import types

from trans_gemini import (
    audio_to_text,
    get_client,
    get_output_dir,
    is_supported_audio,
    load_event_meta,
    load_presentation_context,
    save_transcript,
    json_to_txt,
)

load_dotenv()

GEMINI_MODEL = os.getenv("GEMINI_MINUTES_MODEL", "gemini-2.5-flash")
MAX_OUTPUT_TOKENS = 65536

MINUTES_PROMPT = """당신은 회의록 작성 전문가입니다. 주어진 회의 녹취록을 바탕으로 한국어 회의록을 작성하세요.

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
   - YES24 (예스24)
   - 동아출판
   - GripLabs
   - DCinside (회의에서 'DC'로 약칭하기도 함)
10. 다음 고유명사를 정확히 표기:
    - Kimi (기미X, 키미X)
    - Deepseek (딥시크X)
    - AX (NX는 오타)
    - Sarak (사라X, 사랑X)
11. 메타 정보에 speaker_mapping이 있으면, 녹취록의 화자 ID(S0, S1 등)를 해당 이름으로 치환하여 작성"""


LECTURE_PROMPT = """당신은 강의 내용을 정리하는 전문가입니다. 주어진 강의 녹취록을 바탕으로 한국어 강의록(강의 노트)을 작성하세요.

다음 형식을 따르세요:

# 강의록

## 강의 개요
- 일시:
- 강사: (녹취록에서 파악 가능한 경우)
- 주제:
- 한 줄 요약: (강의 전체를 한 문장으로)

## 핵심 주제
(강의를 논리적 흐름에 따라 주제별로 정리)

### 1. [소주제 제목]
- 강사가 전달한 핵심 내용
- 사용한 예시·비유·사례 (강의의 핵심이므로 반드시 포함)
- 강조하거나 반복한 포인트

### 2. [소주제 제목]
...

## 주요 개념·용어
- **용어**: 강의에서 설명한 정의/맥락

## 강사의 핵심 주장과 인사이트
- (강사가 강조한 관점, 결론, 통찰)

## 인상적인 예시·사례
- (기억할 만한 비유, 데이터, 스토리)

## Q&A (있는 경우)
- **질문**: ...
- **답변**: ...

## 핵심 정리 (Takeaways)
- (강의에서 꼭 기억해야 할 3~5가지)

작성 규칙:
1. 강의 내용을 충실하게 정리하되, 단순 받아쓰기가 아니라 논리적 흐름으로 재구성
2. 강사가 든 예시·비유·사례는 강의의 핵심이므로 절대 생략하지 말 것
3. 구어체를 문어체로 변환하되, 강사의 강조점과 뉘앙스는 유지
4. 숫자, 날짜, 통계, 고유명사는 반드시 정확히 포함
5. 녹취록에 '[질문]', '[강사]' 표시가 있으면 Q&A 섹션으로 정리
6. 반드시 한국어로 작성
7. 다음 고유명사를 정확히 표기:
   - Magnificent Seven (빅테크 7개사 별칭, '위대한 일곱'X)
   - Kimi (기미X, 키미X)
   - Deepseek (딥시크X)
   - AX (NX는 오타)
8. 의미가 불분명한 받아쓰기 오류는 문맥상 가장 그럴듯하게 보정하되, 추측이 과한 경우 원문을 유지"""


def generate_minutes_gemini(
    transcript_text: str,
    event_meta: Optional[dict] = None,
    mode: str = "meeting",
) -> str:
    """Generate meeting minutes from transcript text using Gemini.

    Args:
        transcript_text: Plain text transcript
        event_meta: Optional event metadata for additional context

    Returns:
        Meeting minutes as markdown string
    """
    client = get_client()

    system_prompt = LECTURE_PROMPT if mode == "lecture" else MINUTES_PROMPT

    user_content = transcript_text

    if event_meta:
        meta_json = json.dumps(event_meta, ensure_ascii=False, indent=2)
        user_content = f"""회의 메타 정보:
{meta_json}

---
녹취록:
{transcript_text}"""

    doc_label = "강의록" if mode == "lecture" else "회의록"
    print(f"{doc_label} 생성 중 ({GEMINI_MODEL})...")

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=[{"text": user_content}],
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            max_output_tokens=MAX_OUTPUT_TOKENS,
            temperature=0.3,
        ),
    )

    if response.text is None:
        finish_reason = None
        if response.candidates:
            finish_reason = response.candidates[0].finish_reason
        raise RuntimeError(
            f"Gemini returned empty response (finish_reason={finish_reason})"
        )

    print(f"{doc_label} 생성 완료 (입력: {len(transcript_text):,}자 → 출력: {len(response.text):,}자)")
    return response.text


def segments_to_text(segments: list[dict]) -> str:
    """Convert transcript segments to plain text."""
    return "\n\n".join(
        seg["text"].strip() for seg in segments if seg.get("text", "").strip()
    )


def main():
    parser = argparse.ArgumentParser(
        description="Audio → Transcription → Meeting Minutes (Gemini)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python gemini_minutes.py audio/meeting.ogg
  python gemini_minutes.py audio/meeting.ogg -m event-meta.json
  python gemini_minutes.py audio/meeting.ogg -o custom_minutes.md
  python gemini_minutes.py --from-transcript output/meeting_transcript.json
        """,
    )

    parser.add_argument(
        "audio_path", nargs="?", help="Path to audio file"
    )
    parser.add_argument(
        "--from-transcript",
        help="Skip transcription; use existing transcript JSON file",
    )
    parser.add_argument(
        "-m", "--meta",
        default=None,
        help="Path to event-meta.json (default: None)",
    )
    parser.add_argument(
        "-p", "--presentation",
        help="Path to presentation text file for transcription context",
    )
    parser.add_argument(
        "-o", "--output",
        help="Output filename for meeting minutes (default: {stem}_minutes.md)",
    )
    parser.add_argument(
        "--mode",
        choices=["meeting", "lecture"],
        default="meeting",
        help="Document style: 'meeting' produces meeting minutes (default); "
             "'lecture' produces lecture notes and keeps the full talk verbatim",
    )

    args = parser.parse_args()
    output_dir = get_output_dir()

    # Load event metadata
    event_meta = None
    if args.meta:
        event_meta = load_event_meta(args.meta)
        if event_meta:
            print(f"Loaded event context: {args.meta}")

    # Step 1: Get transcript segments
    if args.from_transcript:
        # Use existing transcript
        transcript_path = Path(args.from_transcript)
        if not transcript_path.exists():
            print(f"Error: Transcript not found: {args.from_transcript}")
            sys.exit(1)

        with open(transcript_path, "r", encoding="utf-8") as f:
            segments = json.load(f)

        stem = transcript_path.stem.replace("_transcript", "")
        print(f"Loaded transcript: {transcript_path} ({len(segments)} segments)")

    elif args.audio_path:
        audio_path = Path(args.audio_path)
        if not audio_path.exists():
            print(f"Error: Audio file not found: {args.audio_path}")
            sys.exit(1)

        if not is_supported_audio(audio_path):
            print(f"Error: Unsupported audio format: {audio_path.suffix}")
            sys.exit(1)

        stem = audio_path.stem

        # Load presentation context if provided
        presentation_context = None
        if args.presentation:
            presentation_context = load_presentation_context(args.presentation)
            if presentation_context:
                print(f"Loaded presentation context: {args.presentation}")

        # Transcribe
        print(f"\n=== Step 1: Transcription ===")
        print(f"Audio: {audio_path.name}")
        t0 = time.time()

        segments = audio_to_text(
            str(audio_path), event_meta, presentation_context, output_dir=output_dir, mode=args.mode
        )

        # Save transcript JSON and TXT
        transcript_json_path = output_dir / f"{stem}_transcript.json"
        save_transcript(segments, str(transcript_json_path))
        print(f"Transcript saved: {transcript_json_path} ({len(segments)} segments, {time.time() - t0:.1f}s)")

        txt_path = json_to_txt(str(transcript_json_path))
        print(f"Text saved: {txt_path}")

    else:
        parser.print_help()
        sys.exit(1)

    # Step 2: Generate meeting minutes
    print(f"\n=== Step 2: {'Lecture Notes' if args.mode == 'lecture' else 'Meeting Minutes'} ===")
    transcript_text = segments_to_text(segments)

    if not transcript_text.strip():
        print("Error: Transcript is empty, cannot generate minutes.")
        sys.exit(1)

    t0 = time.time()
    minutes = generate_minutes_gemini(transcript_text, event_meta, mode=args.mode)
    print(f"Generation time: {time.time() - t0:.1f}s")

    # Save minutes
    if args.output:
        output_filename = args.output
    elif args.mode == "lecture":
        output_filename = f"{stem}_lecture_notes.md"
    else:
        output_filename = f"{stem}_minutes_gemini.md"

    minutes_path = output_dir / output_filename
    with open(minutes_path, "w", encoding="utf-8") as f:
        f.write(minutes)

    print(f"\n=== Done ===")
    print(f"Meeting minutes: {minutes_path}")


if __name__ == "__main__":
    main()
