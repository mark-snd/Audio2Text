#!/usr/bin/env python3
"""
End-to-end audio → transcription (Gemini) → meeting minutes (Claude).

Pipeline:
1. Transcribe audio using Gemini (via trans_gemini)
2. Generate meeting minutes from transcript using Claude Sonnet

Usage:
    python gemini_claude_minutes.py audio/meeting.ogg
    python gemini_claude_minutes.py audio/meeting.ogg -m event-meta.json
    python gemini_claude_minutes.py audio/meeting.ogg -o my_minutes.md
    python gemini_claude_minutes.py --from-transcript output/meeting_transcript.json
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from trans_gemini import (
    audio_to_text,
    get_output_dir,
    is_supported_audio,
    load_event_meta,
    load_presentation_context,
    save_transcript,
    json_to_txt,
)

load_dotenv()

CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")

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
   - YES24
   - 동아출판
   - GripLaps"""


def generate_minutes_claude(
    transcript_text: str,
    event_meta: Optional[dict] = None,
    model: Optional[str] = None,
    max_tokens: int = 8192,
) -> str:
    """Generate meeting minutes from transcript text using Claude.

    Args:
        transcript_text: Plain text transcript
        event_meta: Optional event metadata for additional context
        model: Claude model to use (default: from CLAUDE_MODEL env var)
        max_tokens: Maximum output tokens

    Returns:
        Meeting minutes as markdown string
    """
    import anthropic

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY not set in .env")
        sys.exit(1)

    if model is None:
        model = CLAUDE_MODEL

    user_content = transcript_text

    if event_meta:
        meta_json = json.dumps(event_meta, ensure_ascii=False, indent=2)
        user_content = f"""회의 메타 정보:
{meta_json}

---
녹취록:
{transcript_text}"""

    print(f"회의록 생성 중 ({model})...")

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=0.3,
        system=MINUTES_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )

    if not response.content:
        raise RuntimeError("Claude returned empty response")

    minutes = response.content[0].text
    print(f"회의록 생성 완료 (입력: {len(transcript_text):,}자 → 출력: {len(minutes):,}자)")
    return minutes


def segments_to_text(segments: list[dict]) -> str:
    """Convert transcript segments to plain text."""
    return "\n\n".join(
        seg["text"].strip() for seg in segments if seg.get("text", "").strip()
    )


def main():
    parser = argparse.ArgumentParser(
        description="Audio → Transcription (Gemini) → Meeting Minutes (Claude)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python gemini_claude_minutes.py audio/meeting.ogg
  python gemini_claude_minutes.py audio/meeting.ogg -m event-meta.json
  python gemini_claude_minutes.py audio/meeting.ogg -o custom_minutes.md
  python gemini_claude_minutes.py --from-transcript output/meeting_transcript.json
        """,
    )

    parser.add_argument("audio_path", nargs="?", help="Path to audio file")
    parser.add_argument(
        "--from-transcript",
        help="Skip transcription; use existing transcript JSON file",
    )
    parser.add_argument(
        "-m", "--meta",
        help="Path to event-meta.json (only loaded when specified)",
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
        "--model",
        help=f"Claude model for minutes generation (default: {CLAUDE_MODEL})",
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

        presentation_context = None
        if args.presentation:
            presentation_context = load_presentation_context(args.presentation)
            if presentation_context:
                print(f"Loaded presentation context: {args.presentation}")

        print(f"\n=== Step 1: Transcription (Gemini) ===")
        print(f"Audio: {audio_path.name}")
        t0 = time.time()

        segments = audio_to_text(
            str(audio_path), event_meta, presentation_context, output_dir=output_dir
        )

        transcript_json_path = output_dir / f"{stem}_transcript.json"
        save_transcript(segments, str(transcript_json_path))
        print(f"Transcript saved: {transcript_json_path} ({len(segments)} segments, {time.time() - t0:.1f}s)")

        txt_path = json_to_txt(str(transcript_json_path))
        print(f"Text saved: {txt_path}")

    else:
        parser.print_help()
        sys.exit(1)

    # Step 2: Generate meeting minutes with Claude
    print(f"\n=== Step 2: Meeting Minutes (Claude) ===")
    transcript_text = segments_to_text(segments)

    if not transcript_text.strip():
        print("Error: Transcript is empty, cannot generate minutes.")
        sys.exit(1)

    t0 = time.time()
    minutes = generate_minutes_claude(transcript_text, event_meta, model=args.model)
    print(f"Generation time: {time.time() - t0:.1f}s")

    # Save minutes
    if args.output:
        output_filename = args.output
    else:
        output_filename = f"{stem}_minutes_claude.md"

    minutes_path = output_dir / output_filename
    with open(minutes_path, "w", encoding="utf-8") as f:
        f.write(minutes)

    print(f"\n=== Done ===")
    print(f"Meeting minutes: {minutes_path}")


if __name__ == "__main__":
    main()
