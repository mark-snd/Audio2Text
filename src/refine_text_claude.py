"""
Refine transcript text using Claude API (Anthropic).

This script provides better Korean language understanding and
audio transcription error correction compared to other models.
"""

import argparse
import logging
import os
import sys
from pathlib import Path
from textwrap import dedent
from typing import Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# File size limit: 10MB
MAX_FILE_SIZE_MB = 10
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

# Default transcription refinement prompt
TRANSCRIPTION_PROMPT = """다음 규칙에 따라 음성 전사 내용을 깔끔하게 정제하여 한국어로 출력하세요:

1. 타임스탬프: 각 문장이나 구문의 시작 부분에 타임스탬프 [XXmXXs]를 추가합니다.

2. 용어 통합: 한국어로 음차된 영어 전문용어는 적절한 영어 표기로 변환합니다:
   - 서브인 AI → Sovereign AI
   - 릴라이어빌리티 → Reliability
   - 컨트롤러빌리티 → Controllability
   - 리스폰서블 AI → Responsible AI
   - 어카운터빌리티 → Accountability
   - 트랜스페런시 → Transparency
   - 프레임워크 → Framework
   - (기타 한국어로 음차된 영어 전문용어도 동일한 논리를 적용)

3. 다음 내용은 제거합니다:
   - 쉬는 시간 대화 (음식, 식당, 일정 등에 관한 이야기)
   - 사회자의 전환 멘트 및 다음 발표자 소개
   - 청중 반응, [박수] 또는 [applause] 같은 표시
   - 반복되는 구문/환각 현상 (같은 구문이 여러 번 반복되는 경우)
   - 발표 전후의 비공식적인 잡담

4. 발표자의 실제 발표 내용만 유지합니다.

**반드시 한국어로 깔끔하고 읽기 쉬운 전사본을 타임스탬프와 함께 출력하세요.**"""


def load_env_config():
    """Load configuration from .env file."""
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        with open(env_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    os.environ[key] = value


def refine_with_claude(
    text: str,
    api_key: str,
    model: str = "claude-sonnet-4-5",
    temperature: float = 0.3,
    max_tokens: int = 8192,
    max_retries: int = 3,
    custom_prompt: Optional[str] = None
) -> Optional[str]:
    """
    Refine text using Claude API.

    Args:
        text: The text to refine.
        api_key: Anthropic API key.
        model: Claude model name.
        temperature: Sampling temperature (0.0 to 1.0).
        max_tokens: Maximum tokens in response.
        max_retries: Maximum number of retry attempts.
        custom_prompt: Optional custom system prompt (uses TRANSCRIPTION_PROMPT if None).

    Returns:
        Refined text or None on failure.
    """
    try:
        import anthropic
    except ImportError:
        logger.error("anthropic 라이브러리를 가져올 수 없습니다.")
        logger.error("'pip install anthropic' 명령으로 설치하세요.")
        return None

    # Use custom prompt or default TRANSCRIPTION_PROMPT
    system_prompt = custom_prompt or TRANSCRIPTION_PROMPT

    client = anthropic.Anthropic(api_key=api_key)

    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"Claude API 호출 중... (시도 {attempt}/{max_retries})")

            message = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": text}
                ]
            )

            if not message.content:
                logger.error("API 응답에 content가 없습니다.")
                continue

            # Extract text from response
            refined_text = message.content[0].text

            if not refined_text:
                logger.error("API 응답의 텍스트가 비어 있습니다.")
                continue

            logger.info("Claude 처리 완료")
            return refined_text

        except anthropic.APIError as exc:
            logger.error(f"Claude API 오류 (시도 {attempt}/{max_retries}): {exc}")
            if attempt == max_retries:
                return None
        except Exception as exc:
            logger.error(f"Claude 호출 실패 (시도 {attempt}/{max_retries}): {exc}")
            if attempt == max_retries:
                return None

    return None


def main():
    """Main entry point."""
    # Load environment configuration
    load_env_config()

    # Get configuration from environment
    api_key = os.getenv("ANTHROPIC_API_KEY")
    model = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-5")
    temperature = float(os.getenv("AI_TEMPERATURE", "0.3"))
    max_tokens = int(os.getenv("AI_MAX_TOKENS", "8192"))
    max_retries = int(os.getenv("AI_MAX_RETRIES", "3"))

    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Refine transcript text using Claude API.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=dedent(
            """
            Examples:
              %(prog)s -i result.txt -o result_refined.txt
              %(prog)s -i transcript.txt --temperature 0.5 -v

            Environment Variables (.env file):
              ANTHROPIC_API_KEY: Your Anthropic API key (required)
              CLAUDE_MODEL: Model name (default: claude-3-5-sonnet-20241022)
              AI_TEMPERATURE: Sampling temperature (default: 0.3)
              AI_MAX_TOKENS: Maximum tokens (default: 8192)
              AI_MAX_RETRIES: Max retry attempts (default: 3)
            """
        )
    )
    parser.add_argument(
        "-i", "--input",
        default="result.txt",
        help="Input transcript file (default: %(default)s)"
    )
    parser.add_argument(
        "-o", "--output",
        default="result_refined_claude.txt",
        help="Output file (default: %(default)s)"
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="Claude API key (overrides .env)"
    )
    parser.add_argument(
        "--model",
        default=None,
        help=f"Claude model name (default: {model})"
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=None,
        help=f"Sampling temperature (default: {temperature})"
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=None,
        help=f"Maximum tokens (default: {max_tokens})"
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=None,
        help=f"Max retry attempts (default: {max_retries})"
    )
    parser.add_argument(
        "--prompt",
        default=None,
        help="Custom system prompt (overrides default TRANSCRIPTION_PROMPT)"
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        help="Create backup of output file if it exists"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )

    args = parser.parse_args()

    # Set logging level
    if args.verbose:
        logger.setLevel(logging.DEBUG)
        logger.debug("Verbose logging enabled")

    # Override config with command line arguments
    api_key = args.api_key or api_key
    model = args.model or model
    temperature = args.temperature if args.temperature is not None else temperature
    max_tokens = args.max_tokens if args.max_tokens is not None else max_tokens
    max_retries = args.max_retries if args.max_retries is not None else max_retries

    # Validate API key
    if not api_key:
        logger.error("ANTHROPIC_API_KEY가 설정되지 않았습니다.")
        logger.error(".env 파일에 API 키를 설정하거나 --api-key 옵션을 사용하세요.")
        sys.exit(1)

    # Validate input file
    input_path = Path(args.input)
    if not input_path.exists():
        logger.error(f"입력 파일을 찾을 수 없습니다: {input_path}")
        sys.exit(1)

    if not input_path.is_file():
        logger.error(f"입력 경로가 파일이 아닙니다: {input_path}")
        sys.exit(1)

    # Check file size
    file_size = input_path.stat().st_size
    if file_size > MAX_FILE_SIZE_BYTES:
        logger.error(
            f"파일 크기가 너무 큽니다: {file_size / 1024 / 1024:.2f}MB "
            f"(최대: {MAX_FILE_SIZE_MB}MB)"
        )
        sys.exit(1)

    # Read input file
    try:
        text = input_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        logger.error(f"파일 인코딩 오류: {exc}")
        logger.error("UTF-8 인코딩으로 저장된 파일인지 확인하세요.")
        sys.exit(1)
    except Exception as exc:
        logger.error(f"파일 읽기 실패: {exc}")
        sys.exit(1)

    if not text.strip():
        logger.error(f"입력 파일이 비어 있습니다: {input_path}")
        sys.exit(1)

    logger.info(f"입력 파일: {input_path} ({file_size:,} bytes)")

    # Backup existing output file if requested
    output_path = Path(args.output)
    if args.backup and output_path.exists():
        backup_path = output_path.with_suffix(output_path.suffix + ".bak")
        try:
            output_path.rename(backup_path)
            logger.info(f"기존 파일을 백업했습니다: {backup_path}")
        except Exception as exc:
            logger.warning(f"백업 생성 실패: {exc}")

    # Refine text
    logger.info("Claude로 텍스트 정제 중...")
    logger.info(f"설정 - Model: {model}, Temperature: {temperature}, Max Tokens: {max_tokens}")
    if args.prompt:
        logger.info("커스텀 프롬프트 사용")

    refined = refine_with_claude(
        text,
        api_key=api_key,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        max_retries=max_retries,
        custom_prompt=args.prompt
    )

    if not refined:
        logger.error("텍스트 정제에 실패했습니다.")
        sys.exit(1)

    if not refined.strip():
        logger.error("정제된 텍스트가 비어 있습니다.")
        sys.exit(1)

    # Save output
    try:
        output_path.write_text(refined, encoding="utf-8")
        output_size = output_path.stat().st_size
        logger.info(f"완료: '{args.output}' 파일에 저장했습니다. ({output_size:,} bytes)")
    except Exception as exc:
        logger.error(f"파일 쓰기 실패: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
