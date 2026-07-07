# Audio-to-Text 2.0 아키텍처 리팩토링 계획

## 현재 문제 (Pain Points)

| 문제 | 현재 상태 |
|------|----------|
| **모델 하드코딩** | `gemini_minutes.py`는 Gemini만, `meeting_minutes.py`는 Claude만 사용 |
| **파일 중복** | 회의록 생성 로직이 4개 파일에 거의 동일하게 복사됨 |
| **프롬프트 중복** | MINUTES_PROMPT / LECTURE_PROMPT가 각 파일에 하드코딩되어 수정 시 일관성 깨짐 |
| **전사-분석 강결합** | `gemini_minutes.py`가 전사+분석을 한 번에 해서 중간 결과물을 재활용하기 어려움 |
| **보정 미통합** | MainVault 기반 오타 보정이 전혀 연결되어 있지 않음 |
| **옵시디언 미연동** | 회의록 작성 시 이전 회의 내용, 프로젝트 상태, 용어 정의를 볼트에서 참고하지 않음 |
| **설정 분산** | API 키/모델/URL이 `.env`, 코드, `config.py`에 흩어져 있음 |

## 목표 아키텍처

```
audio-to-text/
├── src/
│   ├── __init__.py
│   │
│   ├── adapters/              # 어댑터 패턴: 모델 바꿔 끼우기
│   │   ├── __init__.py
│   │   ├── base.py            # BaseAdapter 추상 클래스
│   │   ├── registry.py        # 어댑터 레지스트리
│   │   ├── gemini.py          # Google Gemini
│   │   ├── claude.py          # Anthropic Claude
│   │   └── openai_compat.py   # OpenAI-compatible (Kimi, DeepSeek, OpenAI, Grok 등)
│   │
│   ├── transcription/         # 도메인 1: 오디오 → 전사문
│   │   ├── __init__.py
│   │   ├── engine.py          # TranscriptionEngine (어댑터 주입)
│   │   ├── prompt.py          # 전사 프롬프트
│   │   └── formatter.py       # 출력 포맷: JSON, TXT, SRT
│   │
│   ├── minutes/               # 도메인 2: 전사문 → 회의록/강의록
│   │   ├── __init__.py
│   │   ├── engine.py          # MinutesEngine (어댑터 주입)
│   │   ├── prompt.py          # 회의록/강의록 프롬프트 템플릿
│   │   ├── corrector.py       # 오타 보정 + 용어 정규화
│   │   ├── context_builder.py # 옵시디언 볼트 문맥 조립
│   │   └── formatter.py       # 마크다운 출력 포맷팅
│   │
│   ├── vault/                 # 옵시디언 MainVault 연동
│   │   ├── __init__.py
│   │   ├── client.py          # 파일 시스템 접근
│   │   ├── glossary.py        # 용어 사전 추출 & 빌드
│   │   ├── retriever.py       # 관련 노트 검색 (TF-IDF / 벡터 검색)
│   │   └── context.py         # 이전 회의록, 프로젝트 상태 수집
│   │
│   ├── cli/
│   │   ├── __init__.py
│   │   ├── transcribe.py
│   │   ├── minutes.py
│   │   └── pipeline.py
│   │
│   ├── prompts/               # 외부 프롬프트 파일 (.txt)
│   │   ├── transcribe_meeting.txt
│   │   ├── transcribe_lecture.txt
│   │   ├── minutes_meeting.txt
│   │   ├── minutes_lecture.txt
│   │   └── minutes_vault_context.txt   # ← 볼트 참고용 시스템 프롬프트
│   │
│   └── utils/
│       ├── __init__.py
│       ├── config.py          # 통합 설정 관리
│       └── audio.py           # ffmpeg 변환 등
│
├── config/
│   ├── models.yaml            # 어댑터별 설정
│   └── settings.yaml          # 앱 설정 (output_dir, vault_path 등)
│
├── tests/
├── scripts/
├── audio/
└── output/
```

## 핵심 설계 결정 7가지

### 1. 어댑터 패턴 (Adapter Pattern)

모든 LLM은 `BaseAdapter`를 구현합니다.

```python
# src/adapters/base.py
class BaseAdapter(ABC):
    @abstractmethod
    def generate(self, prompt: str, system_prompt: str | None = None, **kwargs) -> str:
        """텍스트 생성 (전사+분석 모두 사용)"""
        pass

    @abstractmethod
    def upload_file(self, file_path: str, mime_type: str) -> str:
        """파일 업로드 (전사용). 텍스트 전용 모델은 No-op """
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @property
    @abstractmethod
    def default_model(self) -> str:
        pass
```

레지스트리:
```python
# src/adapters/registry.py
ADAPTERS = {
    "gemini":   "src.adapters.gemini.GeminiAdapter",
    "claude":   "src.adapters.claude.ClaudeAdapter",
    "kimi":     "src.adapters.openai_compat.OpenAICompatAdapter",
    "deepseek": "src.adapters.openai_compat.OpenAICompatAdapter",
    "openai":   "src.adapters.openai_compat.OpenAICompatAdapter",
}
```

### 2. 전사 엔진 (Transcription Engine)

전사는 순수하게 "오디오 → 텍스트 세그먼트"만 담당.

```python
# src/transcription/engine.py
class TranscriptionEngine:
    def __init__(self, adapter: BaseAdapter, mode: str = "meeting"):
        self.adapter = adapter
        self.prompt = load_prompt(f"transcribe_{mode}.txt")

    def transcribe(self, audio_path: Path, event_meta: dict | None = None) -> list[dict]:
        # 오디오 업로드 → 텍스트 생성 → JSON 파싱
        pass
```

출력: `{stem}_transcript.json` + `{stem}_transcript.txt`

### 3. 회의록 엔진 (Minutes Engine)

전사문 + 옵시디언 문맥 → 회의록 생성.

```python
# src/minutes/engine.py
class MinutesEngine:
    def __init__(self, adapter: BaseAdapter, mode: str = "meeting", vault: VaultConnector | None = None):
        self.adapter = adapter
        self.prompt = load_prompt(f"minutes_{mode}.txt")
        self.vault = vault
    
    def generate(self, transcript_path: Path, event_meta: dict | None = None) -> str:
        transcript = load_transcript(transcript_path)
        
        # 1. 옵시디언 볼트에서 문맥 수집
        vault_context = None
        if self.vault:
            vault_context = self.vault.build_context(
                transcript=transcript,
                meeting_date=event_meta.get("date"),
                participants=event_meta.get("participants"),
                topics=event_meta.get("topics"),
            )
        
        # 2. 오타 보정
        corrector = VaultCorrector(self.vault) if self.vault else None
        if corrector:
            transcript, corrections = corrector.correct(transcript)
        
        # 3. LLM에 전달 (프롬프트 + 볼트 문맥)
        final_prompt = self._assemble_prompt(transcript, vault_context, event_meta)
        return self.adapter.generate(final_prompt, system_prompt=self.prompt)
```

### 4. 옵시디언 볼트 연동 (VaultConnector)

회의록 작성 시 볼트의 정보를 **3단계로** 참고합니다.

#### 4-A. 용어 사전 기반 보정 (Corrector)

```python
# src/vault/glossary.py + src/minutes/corrector.py
class VaultCorrector:
    """
    볼트에서 고유명사 사전을 추출해 전사문의 오타를 보정.
    예: "파피로스" → "파피루스", "모자익" → "모자이크", "메러버스트" → "메러모스트"
    """
    def __init__(self, vault: VaultConnector):
        self.glossary = vault.build_glossary()
    
    def correct(self, text: str) -> tuple[str, list[Correction]]:
        # 볼트의 프로젝트 노트, 회의록, 제품 문서에서
        # 제품명/회사명/코드명을 추출 → 사전 구축 → 치환
        pass
```

#### 4-B. 관련 노트 검색 (Retriever)

```python
# src/vault/retriever.py
class VaultRetriever:
    """
    현재 회의와 관련된 이전 회의록/프로젝트 노트를 검색.
    """
    def search(
        self,
        query: str,               # 현재 전사문 요약 또는 키워드
        meeting_date: str | None = None,
        participants: list[str] | None = None,
        limit: int = 5,
    ) -> list[VaultNote]:
        # 1) 날짜 기반: 최근 N일 내 회의록 검색
        # 2) 참석자 기반: 같은 참석자가 있는 회의록 검색
        # 3) 키워드 기반: TF-IDF 또는 간단한 키워드 매칭으로 관련 노트 검색
        pass
```

#### 4-C. 문맥 조립 (Context Builder)

```python
# src/minutes/context_builder.py
class VaultContextBuilder:
    """
    검색된 노트들을 LLM 프롬프트에 주입할 수 있는 형태로 조립.
    """
    def build(
        self,
        retriever: VaultRetriever,
        transcript: str,
        event_meta: dict,
    ) -> VaultContext:
        # 1. 관련 노트 검색
        notes = retriever.search(transcript, event_meta)
        
        # 2. 토큰 예산 내에서 요약/추출
        context = VaultContext()
        for note in notes:
            context.add_related_meeting(
                title=note.title,
                date=note.date,
                summary=self._summarize(note.content, max_tokens=200),
                key_decisions=note.extract_decisions(),
            )
        
        # 3. 프로젝트 상태 맥락 추가
        context.add_project_state(
            projects=retriever.find_active_projects(event_meta.get("participants")),
        )
        
        return context
    
    def to_prompt_text(self, ctx: VaultContext) -> str:
        """LLM 프롬프트에 삽입할 텍스트로 변환"""
        return f"""
# 참고 문맥 (옵시디언 볼트 기준)

## 관련 이전 회의
{ctx.format_related_meetings()}

## 활성 프로젝트 상태
{ctx.format_project_states()}

## 용어 정의
{ctx.format_glossary()}

---
위 문맥을 참고하여 아래 회의록을 작성하세요.
이전 회의에서 논의되었던 내용과 연결되는 지점이 있다면 명시적으로 언급하세요.
"""
```

### 5. 프롬프트 외부화

프롬프트는 `.txt` 파일로 분리, 런타임에 로드:

```
src/prompts/
├── transcribe_meeting.txt
├── transcribe_lecture.txt
├── minutes_meeting.txt           # 기본 회의록 프롬프트
├── minutes_lecture.txt
└── minutes_vault_context.txt     # 볼트 참고용 추가 지시
```

`minutes_vault_context.txt` 내용 예시:
```
추가 규칙 (옵시디언 볼트 기반 문맥 참고):
1. 관련 이전 회의록이 제공된 경우, 이번 회의 내용이 이전 논의의 연장/변경/확정인지 표기하세요.
   예: "→ [2026-06-22 회의]에서 논의한 Papyrus vs Arena 비교 실험이 이번에 확정됨"
2. 프로젝트 상태가 제공된 경우, 현재 진행 중인 프로젝트의 최신 상태를 반영하세요.
3. 고유명사는 제공된 용어 정의를 우선적으로 사용하세요.
4. Action Item이 이전 회의의 Action Item과 연결된다면 연결 번호를 표기하세요.
```

### 6. 설정 통합

```yaml
# config/models.yaml
adapters:
  gemini:
    provider: google
    env_key: GEMINI_API_KEY
    default_model: gemini-2.5-flash
    supports_native_audio: true

  claude:
    provider: anthropic
    env_key: CLAUDE_API_KEY
    default_model: claude-sonnet-4
    supports_native_audio: false

  kimi:
    provider: openai_compat
    env_key: KIMI_API_KEY
    base_url: https://ai.sndworks.ai/kimi/v1
    default_model: kimi-k2

  deepseek:
    provider: openai_compat
    env_key: DEEPSEEK_API_KEY
    base_url: https://api.deepseek.com
    default_model: deepseek-chat

# config/settings.yaml
app:
  output_dir: ./output
  default_vault_path: /Users/marksnd/Documents/MainVault
  
vault:
  meeting_paths:            # 회의록이 있는 폴더들
    - "SND/회의"
    - "SND/Projects"
  project_paths:            # 프로젝트 노트가 있는 폴더들
    - "SND/Projects"
    - "SND"
  glossary_paths:           # 용어 정의가 있는 폴더들
    - "SND/Projects"
    - "AI"
  max_context_tokens: 4000  # 볼트 문맥 최대 토큰 수
  max_related_meetings: 5   # 참고할 관련 회의 최대 개수
```

### 7. 보정 파이프라인 (Corrector)

```python
# src/minutes/corrector.py
class VaultCorrector:
    def __init__(self, vault: VaultConnector):
        self.glossary = vault.build_glossary()  # {"파피로스": "파피루스", ...}

    def correct(self, text: str) -> tuple[str, list[dict]]:
        changes = []
        for variant, correct in self.glossary.items():
            if variant in text:
                text = text.replace(variant, correct)
                changes.append({"from": variant, "to": correct})
        return text, changes
```

보정은 **회의록 생성 직전**에 적용 (전사문 원본은 보존).
보정 이력은 회의록 하단에 "## 용어 보정 내역"으로附录.

## 옵시디언 볼트 활용 시나리오

### 시나리오 1: 부회장님 회의 (07-06)

```
[입력] transcript.txt (07-06 VIP meeting)
↓
[볼트 검색]
  - 최근 2주 회의록: 2026-07-02 한세실업.md, 2026-06-22 부회장님 회의.md
  - 참석자 기반: Patrick, 부회장님 관련 회의
  - 키워드: Papyrus, 한세실업, 모자이크
↓
[문맥 조립]
  → 이전 회의에서 논의한 "Papyrus 예측 모델 for 한세실업"이 이번 회의에서
    "SKU 단위 예측 엑셀 자동화"로 구체화됨
  → 06-22 회의의 "Action: 한세실업 실무 회의 잡기"가 이번에 완료됨
↓
[회의록 출력]
  - 각 안건에 "→ [이전 회의] 연결" 표기
  - Action Item에 이전 번호 참조
```

### 시나리오 2: 용어 보정

```
원문: "포피로스로 예측 모델을 만들고 메러버스트로 공유합니다"
↓
[보정]
  "포피로스" → "파피루스" (볼트의 VIP meeting.md 참고)
  "메러버스트" → "메러모스트" (볼트에서 Mattermost로 정정)
↓
출력: "파피루스로 예측 모델을 만들고 메러모스트로 공유합니다"
```

## CLI 인터페이스

### 전사만
```bash
python -m src transcribe audio/meeting.ogg --model gemini --mode meeting -o output/
```

### 회의록만 (볼트 참고 O)
```bash
python -m src minutes output/transcript.txt --model claude --mode meeting \
  --vault /Users/marksnd/Documents/MainVault \
  --vault-depth deep          # shallow(용어만) / deep(관련 노트 검색 포함)
```

### 전체 파이프라인
```bash
python -m src pipeline audio/meeting.ogg \
  --transcribe-model gemini \
  --minutes-model claude \
  --mode meeting \
  --vault /Users/marksnd/Documents/MainVault \
  --vault-depth deep \
  -o output/
```

### 볼트 명령어
```bash
# 용어 사전 재빌드
python -m src vault build-glossary --vault /Users/marksnd/Documents/MainVault

# 관련 노트 검색 테스트
python -m src vault search "Papyrus 한세실업 예측" --vault ~/Documents/MainVault

# 볼트 통계
python -m src vault stats --vault ~/Documents/MainVault
```

## 마이그레이션 계획

| 단계 | 작업 | 기존 파일 |
|------|------|-----------|
| 1 | 디렉토리 구조 생성 | — |
| 2 | BaseAdapter + Registry | — |
| 3 | GeminiAdapter | `trans_gemini.py` |
| 4 | ClaudeAdapter | `meeting_minutes.py` |
| 5 | OpenAICompatAdapter | `kimimi_minutes.py` |
| 6 | TranscriptionEngine | `trans_gemini.py` |
| 7 | MinutesEngine | `gemini_minutes.py` |
| 8 | 프롬프트 외부화 | 프롬프트 하드코딩 부분 |
| 9 | **VaultConnector + Glossary** | **신규** |
| 10 | **VaultRetriever** | **신규** |
| 11 | **VaultContextBuilder** | **신규** |
| 12 | **VaultCorrector 통합** | **신규** |
| 13 | CLI 통합 | 모든 기존 진입점 |
| 14 | 기존 파일 deprecation | `gemini_minutes.py`, ... |
| 15 | 테스트 작성 | — |

## 기존 파일 처리

| 기존 파일 | 새 위치/처리 |
|-----------|-------------|
| `src/gemini_minutes.py` | `backup/` (deprecated) |
| `src/trans_gemini.py` | `src/adapters/gemini.py` + `src/transcription/engine.py` |
| `src/meeting_minutes.py` | `src/adapters/claude.py` + `src/minutes/engine.py` |
| `src/kimimi_minutes.py` | `src/adapters/openai_compat.py` |
| `src/gemini_claude_minutes.py` | `backup/` (deprecated) |
| `src/config.py` | `config/models.yaml` + `src/utils/config.py` |
| `src/refine_text_claude.py` | 기능 분리 → `corrector.py` + `context_builder.py` |

## 검토 요청 사항

1. **어댑터 구분粒度**: OpenAI-compatible은 하나의 클래스로 묶되, 설정으로 `base_url`만 바꾸는 방식이 적절한가?
2. **보정 타이밍**: 전사 직후 vs 회의록 생성 직전 — 전사 원본 보존을 위해 "회의록 생성 직전"으로 결정했는데 괜찮은가?
3. **프롬프트 외부화**: `.txt` vs `.md` vs `.yaml` — 프롬프트에 변수 치환이 필요하면 Jinja2 템플릿을 고려해야 함
4. **파일 업로드**: Claude/Kimi는 native audio를 지원하지 않음. ffmpeg + chunked audio 처리를 어댑터 내부 vs transcription engine 중 어디서?
5. **볼트 검색 방식**: TF-IDF 간단 구현 vs 외부 벡터 DB (ChromaDB 등) — 현재는 파일 기반 간단 검색으로 시작?
6. **프라이버시**: 볼트 전체 스캔 시 민감한 개인 노트까지 포함될 수 있음. 특정 폴더(SND/, 회의/ 등)만 스캔하도록 제한할 것
