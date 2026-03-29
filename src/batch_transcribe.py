#!/usr/bin/env python3
"""
Batch Audio Transcription Tool - Process Multiple Audio Files

DESCRIPTION:
    Transcribes all audio files in a folder using Whisper + Claude refinement.
    Automatically processes all supported audio formats in the specified directory.

FEATURES:
    • Batch processing of multiple audio files
    • Supports all audio formats (m4a, mp3, wav, flac, etc.)
    • Automatic output file naming based on input filename
    • Resume capability - skips already processed files
    • Progress tracking with detailed logs
    • Uses existing transcribe.py for core functionality

REQUIREMENTS:
    pip install openai-whisper torch anthropic python-dotenv

SETUP:
    1. Create a .env file with your API key (for refinement)
    2. Add: ANTHROPIC_API_KEY=your-api-key-here

USAGE:
    # Basic - transcribe all audio files in folder
    python batch_transcribe.py -d "/Users/marksnd/Documents/AI Conference Audio"

    # With Claude refinement
    python batch_transcribe.py -d "/path/to/folder" --refine

    # Specify Whisper model
    python batch_transcribe.py -d "/path/to/folder" -m large-v3 --refine

    # Skip already processed files
    python batch_transcribe.py -d "/path/to/folder" --refine --skip-existing

    # Custom output directory
    python batch_transcribe.py -d "/path/to/folder" -o "/path/to/output" --refine

OUTPUT:
    For each audio file (e.g., meeting.m4a):
    - Without --refine:
        meeting_transcript.txt

    - With --refine:
        meeting_transcript_original.txt  (Whisper raw output)
        meeting_transcript.txt           (Claude refined)

EXAMPLES:
    # Quick batch transcription (fast, no refinement)
    python batch_transcribe.py -d "./audio" -m small

    # Production quality batch processing
    python batch_transcribe.py -d "./conference" -m large-v3 --refine --skip-existing

    # Process specific folder with custom output
    python batch_transcribe.py -d "/Volumes/USB/recordings" -o "./transcripts" --refine

AUTHOR: Audio2Text Project
LICENSE: MIT
"""

import os
import argparse
from pathlib import Path
from datetime import datetime
import sys

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import transcribe function from existing transcribe.py
try:
    from transcribe import transcribe_audio
except ImportError as e:
    print(f"Error: transcribe.py not found in the same directory: {e}")
    print("Make sure transcribe.py exists and is in the same folder as this script.")
    sys.exit(1)

# Supported audio file extensions
AUDIO_EXTENSIONS = {'.m4a', '.mp3', '.wav', '.flac', '.aac', '.ogg', '.wma', '.opus'}


def get_audio_files(directory):
    """
    Get all audio files from the specified directory.

    Args:
        directory: Path to the directory containing audio files

    Returns:
        List of Path objects for audio files
    """
    dir_path = Path(directory)

    if not dir_path.exists():
        print(f"Error: Directory not found: {directory}")
        return []

    if not dir_path.is_dir():
        print(f"Error: Not a directory: {directory}")
        return []

    audio_files = []
    for file_path in dir_path.iterdir():
        if file_path.is_file() and file_path.suffix.lower() in AUDIO_EXTENSIONS:
            audio_files.append(file_path)

    # Sort by name for consistent processing order
    audio_files.sort()
    return audio_files


def get_output_path(audio_file, output_dir=None, suffix="_transcript.txt"):
    """
    Generate output file path for transcript.

    Args:
        audio_file: Path to the audio file
        output_dir: Optional custom output directory (defaults to same as audio file)
        suffix: Suffix to add to filename

    Returns:
        Path object for output file
    """
    audio_path = Path(audio_file)

    # Determine output directory
    if output_dir:
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
    else:
        out_dir = audio_path.parent

    # Generate output filename
    output_name = audio_path.stem + suffix
    return out_dir / output_name


def should_skip_file(audio_file, output_dir, skip_existing):
    """
    Check if file should be skipped based on existing output.

    Args:
        audio_file: Path to the audio file
        output_dir: Output directory
        skip_existing: Whether to skip if output exists

    Returns:
        True if should skip, False otherwise
    """
    if not skip_existing:
        return False

    output_path = get_output_path(audio_file, output_dir)
    return output_path.exists()


def format_duration(seconds):
    """Format duration in seconds to readable string."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)

    if hours > 0:
        return f"{hours}h {minutes}m {secs}s"
    elif minutes > 0:
        return f"{minutes}m {secs}s"
    else:
        return f"{secs}s"


def batch_transcribe(
    directory,
    output_dir=None,
    model_size="small",
    refine=False,
    skip_existing=False,
    custom_prompt=None
):
    """
    Batch transcribe all audio files in a directory.

    Args:
        directory: Directory containing audio files
        output_dir: Optional custom output directory
        model_size: Whisper model size
        refine: Whether to refine with Claude
        skip_existing: Skip files with existing transcripts
        custom_prompt: Optional custom prompt for refinement

    Returns:
        Dictionary with processing statistics
    """
    # Get all audio files
    audio_files = get_audio_files(directory)

    if not audio_files:
        print(f"\nNo audio files found in: {directory}")
        print(f"Supported formats: {', '.join(sorted(AUDIO_EXTENSIONS))}")
        return {
            'total': 0,
            'processed': 0,
            'skipped': 0,
            'failed': 0
        }

    print(f"\n{'='*70}")
    print(f"BATCH TRANSCRIPTION")
    print(f"{'='*70}")
    print(f"Directory: {directory}")
    print(f"Found {len(audio_files)} audio file(s)")
    print(f"Model: {model_size}")
    print(f"Refinement: {'Enabled' if refine else 'Disabled'}")
    print(f"Skip existing: {'Yes' if skip_existing else 'No'}")
    if output_dir:
        print(f"Output directory: {output_dir}")
    print(f"{'='*70}\n")

    # Process each file
    stats = {
        'total': len(audio_files),
        'processed': 0,
        'skipped': 0,
        'failed': 0
    }

    start_time = datetime.now()

    for idx, audio_file in enumerate(audio_files, 1):
        print(f"\n{'─'*70}")
        print(f"[{idx}/{len(audio_files)}] Processing: {audio_file.name}")
        print(f"{'─'*70}")

        # Check if should skip
        if should_skip_file(audio_file, output_dir, skip_existing):
            print(f"⊘ Skipping (output already exists)")
            stats['skipped'] += 1
            continue

        # Generate output path
        output_path = get_output_path(audio_file, output_dir)

        # Process file
        file_start_time = datetime.now()

        try:
            result = transcribe_audio(
                file_path=str(audio_file),
                model_size=model_size,
                output_file=str(output_path),
                refine=refine,
                custom_prompt=custom_prompt
            )

            if result:
                file_duration = (datetime.now() - file_start_time).total_seconds()
                print(f"\n✓ Completed in {format_duration(file_duration)}")
                stats['processed'] += 1
            else:
                print(f"\n✗ Failed to process file")
                stats['failed'] += 1

        except KeyboardInterrupt:
            print(f"\n\n⚠ Interrupted by user")
            print(f"Progress saved: {stats['processed']} files processed")
            raise
        except Exception as e:
            print(f"\n✗ Error processing file: {e}")
            stats['failed'] += 1

    # Print summary
    total_duration = (datetime.now() - start_time).total_seconds()

    print(f"\n{'='*70}")
    print(f"BATCH PROCESSING COMPLETE")
    print(f"{'='*70}")
    print(f"Total files: {stats['total']}")
    print(f"✓ Successfully processed: {stats['processed']}")
    if stats['skipped'] > 0:
        print(f"⊘ Skipped (already exists): {stats['skipped']}")
    if stats['failed'] > 0:
        print(f"✗ Failed: {stats['failed']}")
    print(f"Total time: {format_duration(total_duration)}")
    print(f"{'='*70}\n")

    return stats


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Batch transcribe all audio files in a folder using Whisper + Claude",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic batch transcription
  %(prog)s -d "/Users/marksnd/Documents/AI Conference Audio"

  # With Claude refinement (recommended)
  %(prog)s -d "/path/to/folder" --refine

  # High quality with refinement
  %(prog)s -d "/path/to/folder" -m large-v3 --refine --skip-existing

  # Custom output directory
  %(prog)s -d "/path/to/audio" -o "/path/to/transcripts" --refine

Supported audio formats:
  .m4a, .mp3, .wav, .flac, .aac, .ogg, .wma, .opus

Output files:
  For input "meeting.m4a":
  - meeting_transcript.txt              (final output)
  - meeting_transcript_original.txt     (original Whisper output, if --refine used)
        """
    )

    parser.add_argument(
        "-d",
        "--directory",
        required=True,
        help="Directory containing audio files to transcribe"
    )

    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="Output directory for transcripts (defaults to same as input directory)"
    )

    parser.add_argument(
        "-m",
        "--model",
        default="small",
        choices=["tiny", "base", "small", "medium", "large-v1", "large-v2", "large-v3", "large"],
        help="Whisper model size (default: %(default)s)"
    )

    parser.add_argument(
        "--refine",
        action="store_true",
        help="Refine transcriptions with Claude API (requires ANTHROPIC_API_KEY)"
    )

    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip files that already have transcripts"
    )

    parser.add_argument(
        "--prompt",
        default=None,
        help="Custom refinement prompt (overrides default)"
    )

    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_args()

    try:
        stats = batch_transcribe(
            directory=args.directory,
            output_dir=args.output,
            model_size=args.model,
            refine=args.refine,
            skip_existing=args.skip_existing,
            custom_prompt=args.prompt
        )

        # Exit with error code if any files failed
        if stats['failed'] > 0:
            sys.exit(1)

    except KeyboardInterrupt:
        print("\n\nBatch processing interrupted by user.")
        sys.exit(130)  # Standard exit code for Ctrl+C
    except Exception as e:
        print(f"\n\nFatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
