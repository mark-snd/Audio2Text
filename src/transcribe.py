#!/usr/bin/env python3
"""
Audio Transcription Tool with Whisper + Claude Refinement

DESCRIPTION:
    Transcribes audio files using OpenAI's Whisper model with optional
    Claude API refinement for professional transcript output.

FEATURES:
    • Local Whisper transcription (no API key needed for basic use)
    • Optional Claude refinement with timestamps and term correction
    • Automatic GPU/CPU detection (CUDA, Apple Silicon MPS, CPU)
    • Supports all audio formats (m4a, mp3, wav, etc.)
    • Korean language optimized

REQUIREMENTS:
    pip install openai-whisper torch anthropic python-dotenv

SETUP (for Claude refinement):
    1. Create a .env file in the same directory
    2. Add: ANTHROPIC_API_KEY=your-api-key-here
    3. Get API key from: https://console.anthropic.com/

USAGE:

    # Basic transcription (no refinement, no API key needed)
    python transcribe.py -f meeting.m4a

    # With Claude refinement (adds timestamps, fixes terms, removes noise)
    python transcribe.py -f meeting.m4a --refine

    # Different Whisper models
    python transcribe.py -f audio.m4a -m tiny       # Fastest
    python transcribe.py -f audio.m4a -m small      # Balanced
    python transcribe.py -f audio.m4a -m medium     # Better quality
    python transcribe.py -f audio.m4a -m large-v3   # Best quality (default)

    # Custom output file
    python transcribe.py -f audio.m4a -o result.txt --refine

    # Custom refinement prompt
    python transcribe.py -f audio.m4a --refine --prompt "Summarize key points"

    # Show all options
    python transcribe.py --help

OUTPUT:
    Without --refine:
        transcript.txt               (Whisper raw output)

    With --refine:
        transcript_original.txt      (Whisper raw output)
        transcript.txt               (Claude refined with timestamps)

REFINEMENT FEATURES:
    • Adds timestamps: [00m15s], [01m30s], etc.
    • Fixes phonetic terms: "서브인 AI" → "Sovereign AI"
    • Removes noise: audience reactions, break conversations, applause
    • Cleans repeated phrases/hallucinations
    • Improves readability with proper sentence breaks

EXAMPLES:

    # Quick draft transcript (fast, no refinement)
    python transcribe.py -f meeting.m4a -m tiny

    # Production quality (accurate + refined)
    python transcribe.py -f conference.m4a -m large-v3 --refine

    # Best quality for important recordings
    python transcribe.py -f interview.m4a -m large-v3 --refine -o interview.txt

WHISPER MODEL COMPARISON:
    Model       Speed       Accuracy    Size      Best For
    ─────────────────────────────────────────────────────────
    tiny        Fastest     ⭐⭐        39MB      Quick tests
    base        Fast        ⭐⭐⭐      74MB      Drafts
    small       Medium      ⭐⭐⭐⭐    244MB     General use
    medium      Slow        ⭐⭐⭐⭐⭐  769MB     Important meetings
    large-v3    Slowest     ⭐⭐⭐⭐⭐⭐ 1550MB    Best quality (default) ⚡
    large       Same        ⭐⭐⭐⭐⭐⭐ 1550MB    Alias for large-v3

AUTHOR: Audio2Text Project
LICENSE: MIT
"""

import whisper
import os
import torch
import argparse
import ssl
import urllib.request
from pathlib import Path
from textwrap import dedent

# Fix SSL certificate verification issues (for corporate proxies/firewalls)
try:
    _create_unverified_https_context = ssl._create_unverified_context
except AttributeError:
    pass
else:
    ssl._create_default_https_context = _create_unverified_https_context

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Default transcription refinement prompt
TRANSCRIPTION_PROMPT = """Generate a clean transcript of the speech following these rules:

1. TIMESTAMPS: Add timestamps [XXmXXs] at the start of each sentence or phrase.

2. CONSOLIDATE TERMS: Convert phonetic Korean-English terms to proper English:
   - 서브인 AI → Sovereign AI
   - 릴라이어빌리티 → Reliability
   - 컨트롤러빌리티 → Controllability
   - 리스폰서블 AI → Responsible AI
   - 어카운터빌리티 → Accountability
   - 트랜스페런시 → Transparency
   - 프레임워크 → Framework
   - (Apply similar logic to other phonetic English terms in Korean)

3. PROPER NAMES: Use the exact official spelling for these company names:
   - SNDWorks
   - YES24
   - 동아출판
   - GripLaps

4. REMOVE the following unrelated content:
   - Break-time conversations (discussions about food, restaurants, logistics)
   - Moderator transitions and introductions for next speakers
   - Audience reactions, applause markers like [박수] or [applause]
   - Repeated phrases/hallucinations (same phrase repeated many times)
   - Informal chatter before/after the main presentation

5. KEEP only the speaker's actual presentation content.

6. OUTPUT LANGUAGE: Keep the transcript in the same language as the input. Do NOT translate to English.

Output a clean, readable transcript with timestamps."""


def refine_with_claude(text, custom_prompt=None, model=None, max_tokens=8000):
    """
    Refine transcription using Claude API.

    Args:
        text: The transcription text to refine
        custom_prompt: Optional custom prompt (defaults to TRANSCRIPTION_PROMPT)
        model: Claude model to use (defaults to CLAUDE_MODEL env var or claude-sonnet-4-5)
        max_tokens: Maximum tokens in response

    Returns:
        Refined text or None on failure
    """
    # Get model from environment if not specified
    if model is None:
        model = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-5")
    try:
        import anthropic
    except ImportError:
        print("\n" + "!"*70)
        print("오류: anthropic 라이브러리가 설치되지 않았습니다.")
        print("!"*70)
        print("다음 명령어로 설치하세요: pip install anthropic\n")
        return None

    # Get API key
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("\n" + "!"*70)
        print("오류: ANTHROPIC_API_KEY 환경 변수가 설정되지 않았습니다.")
        print("!"*70)
        print("\n.env 파일에 설정하거나:")
        print("  export ANTHROPIC_API_KEY='your-key'\n")
        return None

    # Use custom prompt or default
    prompt = custom_prompt or TRANSCRIPTION_PROMPT

    try:
        client = anthropic.Anthropic(api_key=api_key)
        print(f"\nClaude로 정제 중 ({model})...")

        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=0.3,
            system=prompt,
            messages=[
                {"role": "user", "content": text}
            ]
        )

        if response.content and len(response.content) > 0:
            refined_text = response.content[0].text
            print(f"✓ Claude 정제 완료 (입력: {len(text):,}자 → 출력: {len(refined_text):,}자)")
            return refined_text
        else:
            print("\n" + "!"*70)
            print("오류: Claude API가 빈 응답을 반환했습니다.")
            print("!"*70)
            print("가능한 원인:")
            print("  - API 요청이 너무 큼 (텍스트 길이 확인)")
            print("  - API 제한 초과 (요금제 확인)")
            print("  - 일시적 API 문제\n")
            return None

    except anthropic.APIError as e:
        print("\n" + "!"*70)
        print(f"Claude API 오류: {type(e).__name__}")
        print("!"*70)
        print(f"상세 메시지: {e}")
        if "authentication" in str(e).lower() or "api key" in str(e).lower():
            print("\n가능한 원인: API 키가 유효하지 않습니다.")
            print("  1. https://console.anthropic.com/ 에서 새 키를 발급받으세요")
            print("  2. .env 파일의 ANTHROPIC_API_KEY를 확인하세요\n")
        elif "rate_limit" in str(e).lower():
            print("\n가능한 원인: API 요청 한도를 초과했습니다.")
            print("  - 잠시 후 다시 시도하세요\n")
        return None
    except Exception as e:
        print("\n" + "!"*70)
        print(f"예상치 못한 오류: {type(e).__name__}")
        print("!"*70)
        print(f"상세 메시지: {e}")
        print("\n가능한 원인:")
        print("  - 네트워크 연결 문제")
        print("  - 방화벽 또는 프록시 설정")
        print("  - API 서버 일시적 문제\n")
        return None


def transcribe_audio(file_path, model_size="turbo", output_file="transcript.txt", refine=False, custom_prompt=None):
    """
    Transcribe an audio file using Whisper.

    Args:
        file_path: Path to the audio file (m4a, mp3, wav, etc.)
        model_size: Whisper model size (tiny, base, small, medium, large-v3, turbo)
        output_file: Path to save the transcription
        refine: Whether to refine with Claude API
        custom_prompt: Optional custom prompt for Claude refinement

    Returns:
        Transcribed text or None on failure
    """

    # Check if file exists
    if not os.path.exists(file_path):
        print(f"오류: '{file_path}' 파일을 찾을 수 없습니다.")
        return None

    # Validate API key early if refinement is requested
    if refine:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            print("\n" + "!"*70)
            print("경고: --refine 플래그가 설정되었지만 ANTHROPIC_API_KEY가 없습니다.")
            print("!"*70)
            print("\n정제 없이 기본 전사만 진행됩니다.")
            print("\nClaude 정제를 사용하려면:")
            print("  1. .env 파일을 만들고 다음을 추가하세요:")
            print("     ANTHROPIC_API_KEY=your-api-key-here")
            print("  2. 또는 환경 변수를 설정하세요:")
            print("     export ANTHROPIC_API_KEY='your-key'")
            print("  3. API 키는 https://console.anthropic.com/ 에서 받으세요\n")
            refine = False  # Disable refinement to avoid confusion

    # Select device (GPU if available, otherwise CPU)
    if torch.cuda.is_available():
        device = "cuda"
        print("Using NVIDIA GPU (CUDA)")
    elif torch.backends.mps.is_available():
        device = "mps"
        print("Using Apple Silicon GPU (MPS)")
    else:
        device = "cpu"
        print("Using CPU")

    # Load Whisper model
    print(f"\nLoading Whisper '{model_size}' model...")
    try:
        model = whisper.load_model(model_size, device=device)
    except Exception as e:
        print(f"모델 로드 실패: {e}")
        return None

    # Transcribe audio
    print(f"Transcribing '{file_path}'...")
    print("(This may take a few minutes depending on file length and model size)\n")

    try:
        # Use fp16 only on CUDA for best performance and stability
        result = model.transcribe(
            file_path,
            language="ko",  # Korean language
            fp16=(device == "cuda")
        )

        transcribed_text = result["text"]

        # Save original transcription
        if refine:
            original_output = output_file.replace(".txt", "_original.txt") if output_file.endswith(".txt") else f"{output_file}_original"
            with open(original_output, "w", encoding="utf-8") as f:
                f.write(transcribed_text)
            original_size = os.path.getsize(original_output)
            print(f"✓ Original saved to '{original_output}' ({original_size:,} bytes)")

        # Refine with Claude if requested
        final_text = transcribed_text
        refinement_successful = False

        if refine:
            refined = refine_with_claude(transcribed_text, custom_prompt=custom_prompt)
            if refined:
                # Verify that refinement actually changed the text
                if refined.strip() != transcribed_text.strip():
                    final_text = refined
                    refinement_successful = True

                    # Show refinement statistics
                    orig_len = len(transcribed_text)
                    refined_len = len(refined)
                    change_pct = ((refined_len - orig_len) / orig_len * 100) if orig_len > 0 else 0
                    print(f"📊 정제 통계:")
                    print(f"   원본 길이: {orig_len:,}자")
                    print(f"   정제 후: {refined_len:,}자")
                    print(f"   변화: {change_pct:+.1f}%\n")
                else:
                    print("\n" + "!"*70)
                    print("경고: 정제된 텍스트가 원본과 동일합니다.")
                    print("!"*70)
                    print("가능한 원인:")
                    print("  - Claude가 변경할 내용을 찾지 못함")
                    print("  - 프롬프트가 텍스트와 맞지 않음")
                    print("  - 원본 품질이 이미 높음\n")
                    print("원본 텍스트를 그대로 사용합니다.\n")
            else:
                print("\n" + "!"*70)
                print("정제 실패: 원본 전사 내용을 사용합니다.")
                print("!"*70)
                print("두 파일 모두 동일한 내용(원본)을 포함하게 됩니다.\n")

        # Save final output
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(final_text)

        file_size = os.path.getsize(output_file)

        # Clear status message based on what actually happened
        if refine and refinement_successful:
            status_msg = "✓ 정제된 최종 전사"
        elif refine and not refinement_successful:
            status_msg = "⚠ 원본 전사 (정제 실패)"
        else:
            status_msg = "✓ 최종 전사"

        print(f"{status_msg}가 '{output_file}'에 저장되었습니다 ({file_size:,} bytes)")

        return final_text

    except Exception as e:
        print(f"전사 중 오류 발생: {e}")
        return None


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Transcribe audio files using Whisper with optional Claude refinement",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic transcription only
  %(prog)s -f meeting.m4a

  # With Claude refinement (adds timestamps, removes noise, fixes terms)
  %(prog)s -f meeting.m4a --refine

  # Custom model and output
  %(prog)s -f audio.mp3 -m large-v3 -o output.txt --refine

  # Custom refinement prompt
  %(prog)s -f interview.wav --refine --prompt "Summarize the key points"

  # End-to-end: audio → transcription → refinement → meeting minutes
  %(prog)s -f meeting.m4a --minutes

Available Whisper models (from fastest to most accurate):
  tiny      - Fastest, lowest accuracy
  base      - Fast, basic accuracy
  small     - Good balance
  medium    - Better accuracy, slower
  large-v3  - Best accuracy, slowest
  turbo     - Fast and accurate (recommended!)

Refinement:
  When --refine is used, the script will:
  1. Save original transcription to *_original.txt
  2. Refine with Claude API (adds timestamps, fixes phonetic terms, removes noise)
  3. Save refined version to the output file
        """
    )

    parser.add_argument(
        "-f",
        "--file",
        required=True,
        help="Path to the audio file (m4a, mp3, wav, etc.)"
    )

    parser.add_argument(
        "-m",
        "--model",
        default="small",
        choices=["tiny", "base", "small", "medium", "large-v1", "large-v2", "large-v3", "large"],
        help="Whisper model size (default: %(default)s)"
    )

    parser.add_argument(
        "-o",
        "--output",
        default="transcript.txt",
        help="Output file path (default: %(default)s)"
    )

    parser.add_argument(
        "--refine",
        action="store_true",
        help="Refine transcription with Claude API (requires ANTHROPIC_API_KEY)"
    )

    parser.add_argument(
        "--prompt",
        default=None,
        help="Custom refinement prompt (overrides default)"
    )

    parser.add_argument(
        "--minutes",
        action="store_true",
        help="Generate meeting minutes from the transcript (implies --refine)"
    )

    parser.add_argument(
        "-mo", "--minutes-output",
        default="meeting_minutes.md",
        help="Output file for meeting minutes (default: %(default)s)"
    )

    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_args()

    # Resolve output paths relative to project output/ directory
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    output_dir = os.path.join(project_root, "output")
    os.makedirs(output_dir, exist_ok=True)

    # If output paths are just filenames (no directory), place them in output/
    if os.path.dirname(args.output) == "":
        args.output = os.path.join(output_dir, args.output)
    if os.path.dirname(args.minutes_output) == "":
        args.minutes_output = os.path.join(output_dir, args.minutes_output)

    # --minutes implies --refine
    if args.minutes:
        args.refine = True

    result = transcribe_audio(
        file_path=args.file,
        model_size=args.model,
        output_file=args.output,
        refine=args.refine,
        custom_prompt=args.prompt
    )

    if result:
        if args.refine:
            print("\n✓ Transcription and refinement completed successfully!")
        else:
            print("\n✓ Transcription completed successfully!")
    else:
        print("\n✗ Transcription failed.")
        exit(1)

    # Generate meeting minutes if requested
    if args.minutes and result:
        print("\n" + "="*60)
        print("회의록 생성")
        print("="*60)
        from meeting_minutes import generate_minutes
        minutes = generate_minutes(result)
        if minutes:
            with open(args.minutes_output, "w", encoding="utf-8") as f:
                f.write(minutes)
            print(f"✓ 회의록 저장: {args.minutes_output}")
        else:
            print("✗ 회의록 생성에 실패했습니다.")
            exit(1)


if __name__ == "__main__":
    main()
