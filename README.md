# Audio2Text - 음성 전사 및 텍스트 정제 도구

음성 파일을 텍스트로 변환하고 AI API (Claude, Gemini 또는 DeepSeek)를 사용하여 깔끔하게 정제하는 도구입니다.

## Setup
- Ensure Python 3.9+ is installed.
- Install FFmpeg (needed to read m4a/mp3/etc). On macOS: `brew install ffmpeg`; on Ubuntu: `sudo apt-get install ffmpeg`.

## Create a virtualenv
```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
```

## Install dependencies
CPU only:
```bash
pip install -r requirements.txt
```

NVIDIA GPU (CUDA 12.1 wheels):
```bash
pip install torch --extra-index-url https://download.pytorch.org/whl/cu121
pip install -r requirements.txt
```

> **Note:** `openai-whisper`, `anthropic`, `torch` 등 주요 패키지는 `requirements.txt`에 포함되어 있습니다.
> Apple Silicon (MPS) 가속도 자동으로 감지됩니다.

## AI API 환경 설정

텍스트 정제 기능을 사용하려면 AI API 키가 필요합니다. Claude (권장), Gemini 또는 DeepSeek을 선택할 수 있습니다.

### 1. `.env` 파일 생성

```bash
cp .env.example .env
```

### 2. API 키 설정

#### Claude/Anthropic 사용 (권장)

`.env` 파일에 Anthropic API 키를 입력하세요:

```bash
AI_PROVIDER=claude
ANTHROPIC_API_KEY=your_actual_api_key_here
CLAUDE_MODEL=claude-sonnet-4-5-20250929
```

- API 키는 [Anthropic Console](https://console.anthropic.com/)에서 발급받을 수 있습니다.
- Claude는 한국어 처리와 음성 전사 정제에 탁월한 성능을 보입니다.

#### Gemini 사용

`.env` 파일에 Gemini API 키를 입력하세요:

```bash
GEMINI_API_KEY=your_actual_api_key_here
```

- API 키는 [Google AI Studio](https://aistudio.google.com/)에서 발급받을 수 있습니다.
- Gemini는 음성 파일을 직접 처리하여 타임스탬프가 포함된 고품질 전사를 제공합니다.

#### DeepSeek 사용

`.env` 파일에 DeepSeek API 키를 입력하세요:

```bash
AI_PROVIDER=deepseek
DEEPSEEK_API_KEY=your_actual_api_key_here
```

- API 키는 [DeepSeek Platform](https://platform.deepseek.com/)에서 발급받을 수 있습니다.

#### 공통 런타임 파라미터

모든 AI 프로바이더에 적용되는 파라미터:

```bash
AI_TEMPERATURE=0.3      # 샘플링 온도 (0.0-1.0)
AI_MAX_TOKENS=8192      # 최대 응답 토큰 수
AI_TIMEOUT=120           # 요청 타임아웃 (초)
AI_MAX_RETRIES=3         # 최대 재시도 횟수
```

## Run

### 방법 1: 단일 파일 전사 및 정제 (transcribe.py)

가장 간단하고 권장되는 방법입니다:

```bash
# 기본 전사만 (Whisper만 사용, API 키 불필요)
python transcribe.py -f meeting.m4a

# Claude 정제 포함 (권장 - 타임스탬프 추가, 용어 정리, 노이즈 제거)
python transcribe.py -f meeting.m4a --refine

# 고품질 모델 + 정제
python transcribe.py -f conference.m4a -m large-v3 --refine

# 커스텀 출력 파일
python transcribe.py -f audio.m4a -o result.txt --refine

# 오디오 → 전사 → 정제 → 회의록 한 번에 생성
python transcribe.py -f meeting.m4a --minutes

# 회의록 출력 파일명 지정
python transcribe.py -f meeting.m4a --minutes -mo 회의록.md
```

**출력 파일:**
- `--refine` 없이: `transcript.txt` (Whisper 원본만)
- `--refine` 사용시:
  - `transcript_original.txt` - Whisper 원본
  - `transcript.txt` - Claude 정제 후
- `--minutes` 사용시 (위 파일 + 추가):
  - `meeting_minutes.md` - 한국어 회의록

### 방법 2: 회의록만 생성 (meeting_minutes.py)

이미 전사된 텍스트 파일에서 회의록만 생성:

```bash
# 전사 파일에서 회의록 생성
python meeting_minutes.py -f transcript.txt

# 출력 파일 지정
python meeting_minutes.py -f transcript.txt -o 회의록.md
```

**출력 파일:** `meeting_minutes.md` (한국어 마크다운 회의록)

회의록에는 다음 항목이 포함됩니다:
- 회의 개요 (일시, 참석자, 주제)
- 주요 논의 사항 (안건별 정리)
- 결정 사항
- Action Items (후속 조치)
- 기타 참고사항

### 방법 3: 배치 처리 (batch_transcribe.py)

폴더 내 모든 오디오 파일을 자동으로 처리:

```bash
# 기본 배치 전사
python batch_transcribe.py -d "/path/to/audio/folder"

# Claude 정제 포함 배치 처리
python batch_transcribe.py -d "/path/to/audio/folder" --refine

# 이미 처리된 파일 건너뛰기
python batch_transcribe.py -d "/path/to/audio/folder" --refine --skip-existing
```

**출력 파일:**
- `--refine` 없이: `meeting_transcript.txt` (Whisper 원본만)
- `--refine` 사용시:
  - `meeting_transcript_original.txt` - Whisper 원본
  - `meeting_transcript.txt` - Claude 정제 후

### 방법 4: 기존 텍스트 정제만 (refine_text_claude.py)

이미 전사된 텍스트 파일을 Claude로 정제:

```bash
# Claude로 텍스트 정제
python refine_text_claude.py -i result.txt -o result_refined.txt

# 상세 로그
python refine_text_claude.py -i result.txt -v
```

#### 텍스트 정제 옵션

| 옵션 | 설명 | 기본값 |
|------|------|--------|
| `-i, --input` | 입력 파일 경로 | result.txt |
| `-o, --output` | 출력 파일 경로 | result_refined.txt |
| `--model` | Claude 모델 이름 | .env의 CLAUDE_MODEL |
| `--temperature` | 샘플링 온도 (0.0-1.0) | 0.3 |
| `--max-tokens` | 최대 응답 토큰 수 | 8192 |
| `--max-retries` | 최대 재시도 횟수 | 3 |
| `--prompt` | 커스텀 시스템 프롬프트 | - |
| `--backup` | 기존 출력 파일 백업 | - |
| `-v, --verbose` | 상세 로그 출력 | - |

### 방법 5: Gemini API 전사 (trans_gemini.py)

Google Gemini API를 사용한 고품질 음성 전사:

```bash
# 기본 전사
python trans_gemini.py audio.mp3

# 커스텀 출력 경로
python trans_gemini.py audio.mp3 -o transcript.json

# 컨텍스트 메타데이터 활용 (정확도 향상)
python trans_gemini.py audio.mp3 -m event-meta.json

# 프레젠테이션 텍스트로 용어 정확도 향상
python trans_gemini.py audio.mp3 -p slides.txt

# WAV를 MP3로 변환
python trans_gemini.py --convert audio.wav -o output/
python trans_gemini.py --convert wav_folder/ -o mp3_output/

# JSON 전사본을 텍스트로 변환 (벡터 임베딩용)
python trans_gemini.py --to-txt transcript.json
```

**Gemini API 설정:**

`.env` 파일에 Gemini API 키 추가:
```bash
GEMINI_API_KEY=your_gemini_api_key_here
```

**출력 형식 (JSON):**
```json
[
    {"start_time": 0.0, "end_time": 5.2, "text": "첫 번째 문장"},
    {"start_time": 5.2, "end_time": 10.5, "text": "두 번째 문장"}
]
```

**지원 오디오 포맷:** WAV, MP3, AIFF, AAC, OGG, FLAC, M4A

| 옵션 | 설명 |
|------|------|
| `audio_path` | 오디오 파일 경로 |
| `-o, --output` | 출력 경로 (파일 또는 디렉터리) |
| `-m, --meta` | 이벤트 메타데이터 JSON (컨텍스트용) |
| `-p, --presentation` | 프레젠테이션 텍스트 파일 (용어 정확도 향상) |
| `--to-txt` | JSON 전사본을 텍스트로 변환 |
| `--convert` | WAV 파일을 MP3로 변환 |

**특징:**
- Gemini 2.5 Flash 모델 사용 (최대 65,536 토큰 출력)
- 원본 언어 유지 (한국어 그대로 전사)
- 휴식 시간 대화, 박수 등 불필요한 내용 자동 필터링
- Rate limiting 자동 재시도 (지수 백오프)
- 디버깅용 원본 응답 저장 (`_raw_response.txt`)

## 파일 구조

```
Audio2Text/
├── transcribe.py          # 단일 파일 전사 (Whisper + Claude 정제 + 회의록)
├── meeting_minutes.py     # 회의록 생성 (전사 파일 → 한국어 회의록)
├── batch_transcribe.py    # 배치 전사 스크립트
├── trans_gemini.py        # Gemini API 전사 스크립트
├── refine_text_claude.py  # Claude 텍스트 정제 (독립 실행)
├── config.py              # DeepSeek 설정 관리
├── trans_org.py           # 이전 버전 전사 스크립트 (레거시)
├── trans_gemini_old.py    # 이전 버전 Gemini 스크립트 (레거시)
├── .env.example           # 환경 변수 예제
├── .env                   # 환경 변수 (생성 필요)
├── .gitignore             # Git 제외 파일 목록
├── requirements.txt       # Python 패키지 목록
├── PLAN.md                # 향후 웹 서비스 확장 계획
├── audio/                 # 오디오 샘플 파일
├── test/                  # 테스트 오디오 및 결과 샘플
└── README.md              # 이 파일
```

---

## 성능 비교: Whisper + Claude vs Gemini

한국어 회의 오디오(OGG, 약 17분)를 사용한 실제 테스트 결과입니다.

### 처리 시간

| 방식 | 소요 시간 |
|------|----------|
| Whisper (small) + Claude | ~2분 |
| Gemini 2.5 Flash | ~63초 |

### 출력 형식

| 방식 | 형식 | 세그먼트 수 |
|------|------|------------|
| Whisper + Claude | 정제된 텍스트 + 타임스탬프 `[00m15s]` | 27개 (정제됨) |
| Gemini | JSON 배열 + 정밀 타임스탬프 (초 단위) | 90개 (상세) |

### 전사 품질

#### Whisper 원본 문제점
- 오타 발생: "맵낙상" → "맥락상", "동아추리판" → "동아출판"
- Hallucination: 오디오 끝부분에 무의미한 외국어 텍스트 생성
- 반복 구간 과다 전사: "네, 네, 네" 등

#### Claude 정제 후 개선점
- 오타 자동 교정
- 기술 용어 정리: RAG, STT, avatar, B2B 등
- 불필요한 내용 제거 (박수, 잡담 등)
- 문장 구조 정리로 가독성 향상

#### Gemini 특징
- 정밀한 타임스탬프 (5.923초 ~ 8.163초 형태)
- 대화 흐름을 상세히 캡처
- 일부 고유명사 오류 (예: "공화출판" ← 실제는 "동아출판")

### 용도별 추천

| 용도 | 추천 방식 | 이유 |
|------|----------|------|
| 회의록/발표 정리 | Whisper + Claude | 가독성 높은 정제된 텍스트 |
| 자막 제작/동기화 | Gemini | 정밀한 타임스탬프 |
| 빠른 초안 작성 | Gemini | 단일 API 호출로 빠름 |
| 고품질 문서화 | Whisper + Claude | 전문 용어 정리, 노이즈 제거 |

---

## 문제 해결

### "ANTHROPIC_API_KEY is not set"
→ `.env` 파일에 `ANTHROPIC_API_KEY`가 올바르게 설정되어 있는지 확인하세요.
→ API 키는 [Anthropic Console](https://console.anthropic.com/)에서 발급받을 수 있습니다.

### "GEMINI_API_KEY is not set"
→ `.env` 파일에 `GEMINI_API_KEY`가 올바르게 설정되어 있는지 확인하세요.

### "파일 인코딩 오류"
→ 입력 파일이 UTF-8 인코딩으로 저장되어 있는지 확인하세요.

### FFmpeg 관련 오류
→ FFmpeg가 설치되어 있는지 확인하세요: `ffmpeg -version`
→ macOS: `brew install ffmpeg` / Ubuntu: `sudo apt-get install ffmpeg`

### Whisper 모델 다운로드 실패
→ 인터넷 연결을 확인하세요. Whisper 모델은 첫 실행 시 자동으로 다운로드됩니다.
→ 사용 가능한 모델: tiny, base, small (기본), medium, large-v3, turbo
