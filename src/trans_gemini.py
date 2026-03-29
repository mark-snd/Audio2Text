#!/usr/bin/env python3
"""
Audio to Text transcription using Gemini API.

Converts audio files to timestamped transcription JSON format:
[
    {"start_time": float, "end_time": float, "text": str},
    ...
]

Receives event-meta.json for context to improve transcription accuracy.
"""

import argparse
import json
import mimetypes
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from google import genai
from google.genai import types

# Load environment variables
load_dotenv()

# Constants
GEMINI_MODEL = "gemini-2.5-pro"
MAX_OUTPUT_TOKENS = 65536  # Maximum for Gemini 2.5 Flash

# MIME type mapping for Gemini-compatible audio formats
# Reference: https://ai.google.dev/gemini-api/docs/audio
MIME_TYPE_MAP = {
    ".wav": "audio/wav",
    ".mp3": "audio/mp3",
    ".aiff": "audio/aiff",
    ".aac": "audio/aac",
    ".ogg": "audio/ogg",
    ".flac": "audio/flac",
    ".m4a": "audio/mp4",
}

SUPPORTED_EXTENSIONS = set(MIME_TYPE_MAP.keys())
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"


@dataclass
class TranscriptSegment:
    """A single segment of transcription with timestamps."""
    start_time: float
    end_time: float
    text: str


class TranscriptionError(Exception):
    """Raised when transcription fails."""
    pass


def convert_to_mp3(
    input_path: Path,
    output_path: Path,
    bitrate: str = "128k"
) -> Path:
    """Convert audio file to MP3 format using ffmpeg.

    Args:
        input_path: Path to input audio file
        output_path: Path for output MP3 file
        bitrate: MP3 bitrate (default: 128k)

    Returns:
        Path to the converted MP3 file
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    result = subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(input_path),
            "-vn",  # No video
            "-acodec", "libmp3lame",
            "-b:a", bitrate,
            str(output_path)
        ],
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        raise TranscriptionError(f"ffmpeg conversion failed: {result.stderr}")

    return output_path


def convert_wav_to_mp3(input_dir: Path, output_dir: Path) -> list[Path]:
    """Convert all WAV files in a directory to MP3.

    Args:
        input_dir: Directory containing WAV files
        output_dir: Directory for output MP3 files

    Returns:
        List of paths to converted MP3 files
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    converted = []

    wav_files = list(input_dir.glob("*.WAV")) + list(input_dir.glob("*.wav"))

    for wav_path in wav_files:
        mp3_path = output_dir / f"{wav_path.stem}.mp3"
        print(f"Converting: {wav_path.name} -> {mp3_path.name}")
        convert_to_mp3(wav_path, mp3_path)
        converted.append(mp3_path)
        print(f"  Done: {mp3_path} ({mp3_path.stat().st_size / 1024 / 1024:.1f} MB)")

    return converted


def get_api_key() -> str:
    """Get Gemini API key from environment."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError(
            "GEMINI_API_KEY environment variable not set. "
            "Add it to .env file or set as environment variable."
        )
    return api_key


# Singleton client instance
_client: Optional[genai.Client] = None


def get_client() -> genai.Client:
    """Get or create Gemini client singleton."""
    global _client
    if _client is None:
        _client = genai.Client(api_key=get_api_key())
    return _client


def get_mime_type(file_path: Path) -> str:
    """Get the MIME type for a file.

    Args:
        file_path: Path to the file

    Returns:
        MIME type string
    """
    ext = file_path.suffix.lower()
    if ext in MIME_TYPE_MAP:
        return MIME_TYPE_MAP[ext]

    # Fallback to mimetypes library
    mime_type, _ = mimetypes.guess_type(str(file_path))
    if mime_type:
        return mime_type

    # Default to octet-stream if unknown
    return "application/octet-stream"


def is_supported_audio(file_path: Path) -> bool:
    """Check if file is a supported audio format.

    Args:
        file_path: Path to the file

    Returns:
        True if file extension is supported
    """
    return file_path.suffix.lower() in SUPPORTED_EXTENSIONS


def get_output_dir(custom_dir: Optional[Path] = None) -> Path:
    """Resolve and create the output directory, defaulting to ./audio."""
    if custom_dir:
        custom_dir = Path(custom_dir)
        output_dir = custom_dir if custom_dir.is_absolute() else DEFAULT_OUTPUT_DIR / custom_dir
    else:
        output_dir = DEFAULT_OUTPUT_DIR

    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def build_transcription_prompt(
    event_meta: Optional[dict] = None,
    presentation_context: Optional[str] = None
) -> str:
    """Build the transcription prompt with optional event and presentation context.

    Args:
        event_meta: Optional event metadata dict for context
        presentation_context: Optional presentation text for terminology and structure context

    Returns:
        The transcription prompt string
    """
    base_prompt = """Transcribe this audio and output ONLY a valid JSON array.

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

6. OUTPUT: Return ONLY the JSON array, no markdown code blocks, no explanations.
"""

    context_sections = []

    if event_meta:
        event_meta_json = json.dumps(event_meta, ensure_ascii=False, indent=2)
        context_sections.append(f"""Event context (use this for accurate transcription of names, terms, and topics):
{event_meta_json}""")

    if presentation_context:
        context_sections.append(f"""Presentation slides context (use this for accurate spelling of terms, proper nouns, and understanding the structure of the talk):
{presentation_context}""")

    if context_sections:
        context = "\n\n".join(context_sections)
        base_prompt = f"""{context}

{base_prompt}"""

    return base_prompt


def parse_timestamp(ts_value, prev_timestamp: float = None) -> float:
    """Parse timestamp value that may be in different formats.

    Handles various Gemini output formats:
    - Decimal seconds: 120.983
    - MM:SS.mmm format: 19:56.543 (19 min 56.543 sec)
    - T:SS:mmm format: 2:5:343 -> 2*600 + 5.343 = 1205.343s
      (Gemini uses T = tens of minutes, SS:mmm = seconds within 10-min block)
    - T:SS.mmm format: 2:10.133 -> 2*600 + 10.133 = 1210.133s

    Args:
        ts_value: Timestamp value (int, float, or string)
        prev_timestamp: Previous timestamp in seconds, used for context-aware parsing

    Returns:
        Timestamp in seconds as float
    """
    if isinstance(ts_value, (int, float)):
        return float(ts_value)

    ts_str = str(ts_value).strip()

    # Check if it contains colons (various time formats)
    if ':' in ts_str:
        # Split on colons, keeping dots intact for now
        colon_parts = ts_str.split(':')

        try:
            if len(colon_parts) == 3:
                # Format: T:S:mmm where T=tens of minutes, S=seconds digit, mmm=milliseconds
                # Example: 2:5:343 = 2*600 + 5 + 0.343 = 1205.343s
                # Example: 2:0:983 = 2*600 + 0 + 0.983 = 1200.983s
                tens_of_minutes = int(colon_parts[0])
                seconds_digit = int(colon_parts[1])
                millis_str = colon_parts[2]

                # Handle milliseconds
                if '.' in millis_str:
                    millis = float(millis_str)
                else:
                    millis = float(millis_str) / 1000

                # Total seconds = (tens_of_minutes * 600) + seconds_digit + milliseconds
                return tens_of_minutes * 600 + seconds_digit + millis

            elif len(colon_parts) == 2:
                first = int(colon_parts[0])
                second_str = colon_parts[1]

                # Second part may have decimal
                if '.' in second_str:
                    second = float(second_str)
                else:
                    second = float(second_str)

                # Calculate both possible interpretations
                mm_ss_result = first * 60 + second  # Standard MM:SS (minutes:seconds)
                t_ss_result = first * 600 + second  # T:SS (tens-of-minutes:seconds)

                # Decision logic:
                # 1. If first > 5, MUST be MM:SS (T:SS can only have T=0-5 for 0-50 min)
                # 2. If seconds >= 60, must be T:SS format (MM:SS can't have seconds >= 60)
                # 3. For T=0-5 with seconds<60, use context if available
                # 4. Default to MM:SS for ambiguous cases without context

                if first > 5:
                    # MUST be MM:SS - T:SS format only uses T=0-5
                    # e.g., 19:56.543 = 19 min 56.543 sec = 1196.543s
                    return mm_ss_result

                if second >= 60:
                    # Must be T:SS format - seconds >= 60 is invalid for MM:SS
                    return t_ss_result

                # For first=0-5 with second<60, both interpretations are possible
                # Use context to disambiguate
                if prev_timestamp is not None:
                    # Use context: timestamps should be monotonically increasing
                    mm_ss_valid = mm_ss_result >= prev_timestamp
                    t_ss_valid = t_ss_result >= prev_timestamp

                    if t_ss_valid and not mm_ss_valid:
                        # Only T:SS maintains monotonicity
                        return t_ss_result
                    elif mm_ss_valid and not t_ss_valid:
                        # Only MM:SS maintains monotonicity
                        return mm_ss_result
                    elif t_ss_valid and mm_ss_valid:
                        # Both valid - prefer T:SS if prev > 500s (we're in tens-of-min territory)
                        if prev_timestamp > 500:
                            return t_ss_result
                        return mm_ss_result

                # Default: standard MM:SS format
                return mm_ss_result

        except (ValueError, IndexError):
            pass

    # Try parsing as plain float
    try:
        return float(ts_str)
    except ValueError:
        return 0.0


def parse_transcript_json(response_text: str) -> list[dict]:
    """Parse the JSON transcript from Gemini response.

    Args:
        response_text: Raw response text from Gemini

    Returns:
        List of transcript segment dicts

    Raises:
        TranscriptionError: If parsing fails
    """
    # Clean up response - remove markdown code blocks if present
    text = response_text.strip()

    # Remove markdown code block markers
    if text.startswith("```"):
        # Find the end of the first line (language identifier)
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1:]
        # Remove trailing ```
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    # Also handle ```json specifically
    text = re.sub(r'^```json\s*', '', text)
    text = re.sub(r'\s*```$', '', text)

    try:
        segments = json.loads(text)

        if not isinstance(segments, list):
            raise TranscriptionError(f"Expected JSON array, got {type(segments)}")

        # Validate segment structure with context-aware timestamp parsing
        validated = []
        prev_end_time = None

        for i, seg in enumerate(segments):
            if not isinstance(seg, dict):
                continue

            # Allow flexible key names
            start = seg.get("start_time") if seg.get("start_time") is not None else seg.get("start", 0.0)
            end = seg.get("end_time") if seg.get("end_time") is not None else seg.get("end", 0.0)
            text_content = seg.get("text") or seg.get("content") or ""

            if text_content:  # Only include segments with text
                # Use previous end_time as context for parsing ambiguous timestamps
                start_time = parse_timestamp(start, prev_end_time)
                end_time = parse_timestamp(end, start_time)

                validated.append({
                    "start_time": start_time,
                    "end_time": end_time,
                    "text": str(text_content).strip()
                })
                prev_end_time = end_time

        return validated

    except json.JSONDecodeError as e:
        # Try to salvage truncated JSON by finding last complete segment
        print(f"  Warning: JSON parse error, attempting to salvage results...")

        # Find all complete JSON objects in the array
        salvaged = []
        prev_end_time = None

        # Match complete segment objects with flexible timestamp format
        # Timestamps can be: 120.983 (decimal seconds) or 2:0:983 or 2:0.983 (M:SS:mmm)
        # Supports segments with or without end_time
        ts_pattern = r'[\d.:]+'
        pattern = rf'\{{\s*"start_time"\s*:\s*{ts_pattern}\s*(?:,\s*"end_time"\s*:\s*{ts_pattern}\s*)?,\s*"text"\s*:\s*"(?:[^"\\]|\\.)*"\s*\}}'
        matches = re.findall(pattern, text, re.DOTALL)

        for match in matches:
            try:
                # Fix malformed timestamps before parsing
                # Convert timestamps like 2:0:983 to strings for JSON parsing
                fixed_match = re.sub(
                    r'"(start_time|end_time)"\s*:\s*([\d]+:[\d.:]+)',
                    r'"\1": "\2"',
                    match
                )
                seg = json.loads(fixed_match)
                if seg.get("text"):
                    # Use context-aware timestamp parsing
                    start_time = parse_timestamp(seg.get("start_time", 0), prev_end_time)
                    end_time = parse_timestamp(seg.get("end_time", 0), start_time)

                    salvaged.append({
                        "start_time": start_time,
                        "end_time": end_time,
                        "text": str(seg["text"]).strip()
                    })
                    prev_end_time = end_time
            except json.JSONDecodeError:
                continue

        if salvaged:
            print(f"  Salvaged {len(salvaged)} segments from response")
            return salvaged

        raise TranscriptionError(f"Failed to parse JSON response: {e}\nResponse: {text[:500]}")


def transcribe_file(
    file_path: Path,
    event_meta: Optional[dict] = None,
    presentation_context: Optional[str] = None,
    max_retries: int = 3,
    base_delay: float = 2.0,
    output_dir: Optional[Path] = None,
) -> list[dict]:
    """Transcribe an audio file using Gemini.

    Args:
        file_path: Path to the audio file
        event_meta: Optional event metadata for context
        presentation_context: Optional presentation text for terminology context
        max_retries: Maximum number of retry attempts for rate limiting
        base_delay: Base delay in seconds for exponential backoff
        output_dir: Directory to store raw responses (defaults to ./audio)

    Returns:
        List of transcript segment dicts

    Raises:
        TranscriptionError: If transcription fails after all retries
    """
    client = get_client()
    mime_type = get_mime_type(file_path)
    prompt = build_transcription_prompt(event_meta, presentation_context)

    for attempt in range(max_retries):
        try:
            # Upload file to Gemini with explicit mime type
            print(f"  Uploading {file_path.name}...")
            with open(file_path, "rb") as f:
                uploaded_file = client.files.upload(file=f, config={"mime_type": mime_type})

            # Wait for file to be processed
            print(f"  Processing...")
            while uploaded_file.state.name == "PROCESSING":
                time.sleep(1)
                uploaded_file = client.files.get(name=uploaded_file.name)

            if uploaded_file.state.name == "FAILED":
                raise TranscriptionError(
                    f"File upload failed: {uploaded_file.state.name}"
                )

            # Generate transcription
            print(f"  Transcribing...")
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=[
                    {"text": prompt},
                    {"file_data": {"file_uri": uploaded_file.uri}},
                ],
                config=types.GenerateContentConfig(
                    max_output_tokens=MAX_OUTPUT_TOKENS,
                ),
            )

            # Clean up uploaded file
            try:
                client.files.delete(name=uploaded_file.name)
            except Exception:
                pass  # Ignore cleanup errors

            # Check if the response has content
            if response.text is None:
                # Log finish reason for debugging
                finish_reason = None
                if response.candidates:
                    finish_reason = response.candidates[0].finish_reason
                raise TranscriptionError(
                    f"Gemini returned empty response (finish_reason={finish_reason}). "
                    "This may be due to safety filters or an unsupported audio format."
                )

            # Save raw response before parsing (in case of truncation)
            target_dir = get_output_dir(output_dir)
            raw_path = target_dir / f"{file_path.stem}_raw_response.txt"
            with open(raw_path, "w", encoding="utf-8") as f:
                f.write(response.text)
            print(f"  Raw response saved to: {raw_path}")

            # Parse and return the transcript
            return parse_transcript_json(response.text)

        except TranscriptionError:
            raise  # Don't retry parsing errors

        except Exception as e:
            error_str = str(e).lower()

            # Check for rate limiting
            if "rate" in error_str or "quota" in error_str or "429" in error_str:
                if attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)
                    print(f"  Rate limited, retrying in {delay:.1f}s...")
                    time.sleep(delay)
                    continue

            # For other errors, raise immediately
            raise TranscriptionError(f"Transcription failed: {e}")

    raise TranscriptionError("Max retries exceeded due to rate limiting")


def audio_to_text(
    audio_path: str,
    event_meta: Optional[dict] = None,
    presentation_context: Optional[str] = None,
    output_dir: Optional[Path] = None
) -> list[dict]:
    """Convert audio file to timestamped text segments.

    Args:
        audio_path: Path to the audio file
        event_meta: Optional event metadata dict for context
        presentation_context: Optional presentation text for terminology context
        output_dir: Directory to store raw responses (defaults to ./audio)

    Returns:
        List of transcript segment dicts:
        [{"start_time": float, "end_time": float, "text": str}, ...]
    """
    file_path = Path(audio_path)

    if not file_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    if not is_supported_audio(file_path):
        raise ValueError(
            f"Unsupported audio format: {file_path.suffix}\n"
            f"Supported formats: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )

    return transcribe_file(file_path, event_meta, presentation_context, output_dir=output_dir)


def save_transcript(segments: list[dict], output_path: str) -> None:
    """Save transcript segments to JSON file.

    Args:
        segments: List of transcript segment dicts
        output_path: Path to save the JSON file
    """
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(segments, f, ensure_ascii=False, indent=2)


def json_to_txt(json_path: str, txt_path: Optional[str] = None) -> str:
    """Convert transcript JSON to plain text optimized for vector embedding.

    Args:
        json_path: Path to the transcript JSON file
        txt_path: Output path for text file. Default: saves to ./audio/{json_name}.txt

    Returns:
        Path to the created text file
    """
    json_file = Path(json_path)
    if not json_file.exists():
        raise FileNotFoundError(f"JSON file not found: {json_path}")

    with open(json_file, "r", encoding="utf-8") as f:
        segments = json.load(f)

    # Extract text only - no timestamps (they add noise for embeddings)
    lines = [seg.get("text", "").strip() for seg in segments if seg.get("text", "").strip()]

    # Join with double newlines for clear segment boundaries
    text = "\n\n".join(lines)

    base_output_dir = get_output_dir()

    # Determine output path
    if txt_path:
        out_path = Path(txt_path)
        if not out_path.is_absolute():
            out_path = base_output_dir / out_path

        if out_path.suffix:
            out_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            out_path = get_output_dir(out_path) / json_file.with_suffix(".txt").name
    else:
        out_path = base_output_dir / json_file.with_suffix(".txt").name

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(text)

    return str(out_path)


def load_event_meta(meta_path: str) -> Optional[dict]:
    """Load event metadata from JSON file.

    Args:
        meta_path: Path to the event-meta.json file

    Returns:
        Event metadata dict, or None if file doesn't exist
    """
    path = Path(meta_path)
    if not path.exists():
        return None

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_presentation_context(presentation_path: str) -> Optional[str]:
    """Load presentation text from file.

    Args:
        presentation_path: Path to the presentation text file (from pptx2text)

    Returns:
        Presentation text content, or None if file doesn't exist
    """
    path = Path(presentation_path)
    if not path.exists():
        return None

    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def main():
    """CLI entry point for audio transcription."""
    parser = argparse.ArgumentParser(
        description="Transcribe audio files to timestamped JSON using Gemini API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python a2t.py audio.mp3
  python a2t.py audio.mp3 -o transcript.json
  python a2t.py audio.mp3 -m event-meta.json
  python a2t.py audio.mp3 -p slides.txt          # Use presentation text as context
  python a2t.py --to-txt transcript.json
  python a2t.py --to-txt transcript.json -o output.txt
  python a2t.py --convert 0-raw/audio/ -o 0.3-audio-converted/   # Convert WAV to MP3
        """,
    )

    parser.add_argument("audio_path", nargs="?", help="Path to audio file (or JSON file with --to-txt, or directory with --convert)")

    parser.add_argument(
        "-o", "--output",
        help="Output path (file or directory). Default: {audio_name}_transcript.json",
    )

    parser.add_argument(
        "-m", "--meta",
        default="2.1-meta-to-append-to-system-prompt/event-meta.json",
        help="Path to event-meta.json for context (default: 2.1-meta-to-append-to-system-prompt/event-meta.json)",
    )

    parser.add_argument(
        "-p", "--presentation",
        help="Path to presentation text file (from pptx2text) for terminology context",
    )

    parser.add_argument(
        "--to-txt",
        action="store_true",
        help="Convert transcript JSON to plain text file instead of transcribing",
    )

    parser.add_argument(
        "--convert",
        action="store_true",
        help="Convert WAV files to MP3 (input can be file or directory)",
    )

    args = parser.parse_args()
    default_output_dir = get_output_dir()

    # Handle WAV to MP3 conversion
    if args.convert:
        if not args.audio_path:
            print("Error: Please provide input path for --convert")
            sys.exit(1)
        input_path = Path(args.audio_path)
        output_dir = get_output_dir(Path(args.output)) if args.output else default_output_dir

        try:
            if input_path.is_dir():
                converted = convert_wav_to_mp3(input_path, output_dir)
                print(f"\nConverted {len(converted)} files to: {output_dir}")
            else:
                output_path = output_dir / f"{input_path.stem}.mp3"
                convert_to_mp3(input_path, output_path)
                print(f"Converted to: {output_path}")
        except Exception as e:
            print(f"Error: {e}")
            sys.exit(1)
        return

    # Handle JSON to TXT conversion
    if args.to_txt:
        if not args.audio_path:
            print("Error: Please provide JSON file path for --to-txt")
            sys.exit(1)
        try:
            txt_path = json_to_txt(args.audio_path, args.output)
            print(f"Converted to: {txt_path}")
        except Exception as e:
            print(f"Error: {e}")
            sys.exit(1)
        return

    if not args.audio_path:
        parser.print_help()
        sys.exit(1)

    # Validate input
    audio_path = Path(args.audio_path)
    if not audio_path.exists():
        print(f"Error: Audio file not found: {args.audio_path}")
        sys.exit(1)

    if not is_supported_audio(audio_path):
        print(f"Error: Unsupported audio format: {audio_path.suffix}")
        print(f"Supported formats: {', '.join(sorted(SUPPORTED_EXTENSIONS))}")
        sys.exit(1)

    # Determine output path
    if args.output:
        output_arg = Path(args.output)
        if output_arg.suffix:
            if output_arg.is_absolute():
                output_path = output_arg
                output_path.parent.mkdir(parents=True, exist_ok=True)
            else:
                output_path = default_output_dir / output_arg.name
        else:
            output_dir = get_output_dir(output_arg)
            output_path = output_dir / f"{audio_path.stem}_transcript.json"
    else:
        output_path = default_output_dir / f"{audio_path.stem}_transcript.json"

    # Load event metadata if available
    event_meta = None
    if args.meta:
        event_meta = load_event_meta(args.meta)
        if event_meta:
            print(f"Loaded event context from: {args.meta}")
        else:
            print(f"Note: Event metadata not found at {args.meta}, proceeding without context")

    # Load presentation context if provided
    presentation_context = None
    if args.presentation:
        presentation_context = load_presentation_context(args.presentation)
        if presentation_context:
            print(f"Loaded presentation context from: {args.presentation}")
        else:
            print(f"Note: Presentation file not found at {args.presentation}, proceeding without context")

    # Transcribe
    print(f"\nTranscribing: {audio_path.name}")
    start_time = time.time()

    try:
        segments = audio_to_text(str(audio_path), event_meta, presentation_context, output_dir=output_path.parent)
        duration = time.time() - start_time

        # Save output
        output_path.parent.mkdir(parents=True, exist_ok=True)
        save_transcript(segments, str(output_path))

        print(f"\nCompleted in {duration:.1f}s")
        print(f"Segments: {len(segments)}")
        print(f"Output: {output_path}")

        # Show preview
        if segments:
            print("\nPreview (first 3 segments):")
            for seg in segments[:3]:
                text_preview = seg["text"][:60] + "..." if len(seg["text"]) > 60 else seg["text"]
                print(f"  [{seg['start_time']:.1f}s - {seg['end_time']:.1f}s] {text_preview}")

    except KeyboardInterrupt:
        print("\n\nTranscription cancelled by user.")
        sys.exit(130)

    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
