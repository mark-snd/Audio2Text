#!/usr/bin/env python3
"""
Meeting Minutes Generator

DESCRIPTION:
    Reads a transcript file and generates meeting minutes in Korean
    using the Claude API.

USAGE:
    python meeting_minutes.py -f transcript.txt
    python meeting_minutes.py -f transcript.txt -o minutes.txt
"""

import argparse
import os
import sys

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

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


def generate_minutes(text, model=None, max_tokens=8000):
    """Generate meeting minutes from transcript text using Claude API."""
    try:
        import anthropic
    except ImportError:
        print("오류: anthropic 라이브러리가 설치되지 않았습니다.")
        print("설치: pip install anthropic")
        return None

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("오류: ANTHROPIC_API_KEY 환경 변수가 설정되지 않았습니다.")
        print(".env 파일에 ANTHROPIC_API_KEY=your-key 를 추가하세요.")
        return None

    if model is None:
        model = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-5")

    try:
        client = anthropic.Anthropic(api_key=api_key)
        print(f"회의록 생성 중 ({model})...")

        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=0.3,
            system=MINUTES_PROMPT,
            messages=[
                {"role": "user", "content": text}
            ]
        )

        if response.content and len(response.content) > 0:
            minutes = response.content[0].text
            print(f"회의록 생성 완료 (입력: {len(text):,}자 → 출력: {len(minutes):,}자)")
            return minutes
        else:
            print("오류: Claude API가 빈 응답을 반환했습니다.")
            return None

    except Exception as e:
        print(f"오류: {type(e).__name__}: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description="회의 녹취록에서 회의록 생성")
    parser.add_argument("-f", "--file", required=True, help="녹취록 파일 경로")
    parser.add_argument("-o", "--output", default="meeting_minutes.md", help="출력 파일명 (기본: meeting_minutes.md, output/ 폴더에 저장)")
    parser.add_argument("-m", "--model", default=None, help="Claude 모델 (기본: claude-sonnet-4-5)")
    args = parser.parse_args()

    if not os.path.exists(args.file):
        print(f"오류: 파일을 찾을 수 없습니다: {args.file}")
        sys.exit(1)

    with open(args.file, "r", encoding="utf-8") as f:
        text = f.read()

    if not text.strip():
        print("오류: 파일이 비어 있습니다.")
        sys.exit(1)

    print(f"입력 파일: {args.file} ({len(text):,}자)")

    minutes = generate_minutes(text, model=args.model)
    if minutes:
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        output_dir = os.path.join(project_root, "output")
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, args.output)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(minutes)
        print(f"회의록 저장: {output_path}")
    else:
        print("회의록 생성에 실패했습니다.")
        sys.exit(1)


if __name__ == "__main__":
    main()
