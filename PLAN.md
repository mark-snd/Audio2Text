# 웹 기반 오디오-회의록 변환 서비스 구현 계획

## 개요

오디오 파일을 업로드하면 Whisper로 전사하고 Claude로 정제하여 회의록을 생성하는 웹 서비스

## 1. 기술 스택

| 구분 | 기술 |
|------|------|
| Backend | FastAPI (Python 3.11) |
| Frontend | React + Vite + TypeScript |
| 전사 엔진 | Whisper (로컬) |
| 텍스트 정제 | Claude API |
| 스타일링 | TailwindCSS |

## 2. 프로젝트 구조

```
Audio2Text/
├── backend/
│   ├── app.py                  # FastAPI 메인 앱
│   ├── routers/
│   │   └── transcription.py    # 전사 관련 API 라우트
│   ├── services/
│   │   ├── whisper_service.py  # Whisper 전사 로직
│   │   └── claude_service.py   # Claude 정제 로직
│   ├── models/
│   │   └── schemas.py          # Pydantic 모델
│   └── utils/
│       └── file_handler.py     # 파일 처리 유틸
│
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── main.tsx
│   │   ├── components/
│   │   │   ├── FileUpload.tsx      # 파일 업로드 (드래그앤드롭)
│   │   │   ├── ProgressTracker.tsx # 진행 상황 표시
│   │   │   ├── ResultViewer.tsx    # 회의록 결과 표시
│   │   │   └── Header.tsx          # 헤더
│   │   ├── hooks/
│   │   │   └── useTranscription.ts # 전사 API 훅
│   │   ├── api/
│   │   │   └── client.ts           # Axios 클라이언트
│   │   └── types/
│   │       └── index.ts            # 타입 정의
│   ├── index.html
│   ├── package.json
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   └── tsconfig.json
│
├── uploads/                    # 임시 업로드 폴더
├── outputs/                    # 결과물 저장
├── requirements.txt            # Python 의존성
└── .env                        # 환경변수
```

## 3. API 설계

### 3.1 엔드포인트

| 엔드포인트 | 메서드 | 설명 | 요청 | 응답 |
|-----------|--------|------|------|------|
| `/api/upload` | POST | 오디오 파일 업로드 | `multipart/form-data` | `{ job_id, filename, status }` |
| `/api/transcribe/{job_id}` | POST | 전사 작업 시작 | `{ refine: boolean }` | `{ job_id, status }` |
| `/api/status/{job_id}` | GET | 작업 상태 조회 | - | `{ status, progress, step }` |
| `/api/result/{job_id}` | GET | 회의록 결과 조회 | - | `{ transcript, refined_text }` |
| `/api/download/{job_id}` | GET | 결과 파일 다운로드 | `?format=txt` | 파일 스트림 |

### 3.2 작업 상태 (Status)

```
pending → processing → refining → completed
                   ↘         ↘
                    → error   → error
```

| 상태 | 설명 |
|------|------|
| `pending` | 업로드 완료, 대기 중 |
| `processing` | Whisper 전사 진행 중 |
| `refining` | Claude 정제 진행 중 |
| `completed` | 완료 |
| `error` | 오류 발생 |

### 3.3 SSE (Server-Sent Events) 진행 상황

```
GET /api/stream/{job_id}

event: progress
data: { "step": "transcribing", "progress": 45, "message": "음성 인식 중..." }

event: progress
data: { "step": "refining", "progress": 80, "message": "텍스트 정제 중..." }

event: complete
data: { "job_id": "xxx", "status": "completed" }
```

## 4. 프론트엔드 화면 설계

### 4.1 메인 화면 (업로드)

```
┌─────────────────────────────────────────────┐
│  🎙️ 오디오 → 회의록 변환                    │
├─────────────────────────────────────────────┤
│                                             │
│  ┌─────────────────────────────────────┐    │
│  │                                     │    │
│  │     📁 파일을 드래그하거나          │    │
│  │        클릭하여 업로드              │    │
│  │                                     │    │
│  │   지원 포맷: m4a, mp3, wav, ogg     │    │
│  │   최대 크기: 100MB                   │    │
│  │                                     │    │
│  └─────────────────────────────────────┘    │
│                                             │
│  ☑️ Claude로 텍스트 정제 (권장)             │
│                                             │
│           [ 변환 시작 ]                      │
│                                             │
└─────────────────────────────────────────────┘
```

### 4.2 진행 화면

```
┌─────────────────────────────────────────────┐
│  🎙️ 오디오 → 회의록 변환                    │
├─────────────────────────────────────────────┤
│                                             │
│  📄 meeting_recording.m4a                   │
│                                             │
│  ● 업로드 완료 ✓                            │
│  ● 음성 인식 중... (45%)                    │
│    ████████████░░░░░░░░░░░░                 │
│  ○ 텍스트 정제                              │
│  ○ 완료                                     │
│                                             │
│           [ 취소 ]                          │
│                                             │
└─────────────────────────────────────────────┘
```

### 4.3 결과 화면

```
┌─────────────────────────────────────────────┐
│  🎙️ 오디오 → 회의록 변환                    │
├─────────────────────────────────────────────┤
│                                             │
│  ✅ 변환 완료!                               │
│                                             │
│  ┌─────────────────────────────────────┐    │
│  │ [00:00] 안녕하세요, 오늘 회의를     │    │
│  │ 시작하겠습니다.                     │    │
│  │                                     │    │
│  │ [00:15] 첫 번째 안건은 신규         │    │
│  │ 프로젝트 일정 검토입니다.           │    │
│  │ ...                                 │    │
│  └─────────────────────────────────────┘    │
│                                             │
│     [ 📋 복사 ]  [ ⬇️ 다운로드 ]  [ 🔄 새로 ]│
│                                             │
└─────────────────────────────────────────────┘
```

## 5. 구현 단계

### 5.1 Phase 1: 백엔드 기반 구축

- [ ] FastAPI 프로젝트 초기화
- [ ] 파일 업로드 API 구현
- [ ] 기존 transcribe.py 로직 서비스로 분리
- [ ] 기존 refine_text_claude.py 로직 서비스로 분리
- [ ] 작업 상태 관리 (in-memory 또는 Redis)

### 5.2 Phase 2: 백엔드 API 완성

- [ ] 전사 시작 API 구현
- [ ] SSE 진행 상황 스트리밍 구현
- [ ] 결과 조회/다운로드 API 구현
- [ ] 에러 핸들링 및 로깅

### 5.3 Phase 3: 프론트엔드 기반 구축

- [ ] Vite + React + TypeScript 프로젝트 초기화
- [ ] TailwindCSS 설정
- [ ] API 클라이언트 설정 (Axios)
- [ ] 기본 레이아웃 및 라우팅

### 5.4 Phase 4: 프론트엔드 기능 구현

- [ ] FileUpload 컴포넌트 (react-dropzone)
- [ ] ProgressTracker 컴포넌트 (SSE 연동)
- [ ] ResultViewer 컴포넌트
- [ ] 복사/다운로드 기능

### 5.5 Phase 5: 통합 및 마무리

- [ ] 프론트엔드-백엔드 통합 테스트
- [ ] CORS 설정
- [ ] 에러 처리 UI
- [ ] 반응형 디자인 적용

## 6. 추가 패키지

### Backend (requirements.txt 추가)

```
fastapi>=0.109.0
uvicorn[standard]>=0.27.0
python-multipart>=0.0.6
aiofiles>=23.2.1
sse-starlette>=1.8.2
```

### Frontend (package.json)

```json
{
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "axios": "^1.6.0",
    "react-dropzone": "^14.2.3"
  },
  "devDependencies": {
    "@types/react": "^18.2.0",
    "@types/react-dom": "^18.2.0",
    "@vitejs/plugin-react": "^4.2.0",
    "autoprefixer": "^10.4.0",
    "postcss": "^8.4.0",
    "tailwindcss": "^3.4.0",
    "typescript": "^5.3.0",
    "vite": "^5.0.0"
  }
}
```

## 7. 환경 변수

```env
# 기존 변수
ANTHROPIC_API_KEY=your_api_key
CLAUDE_MODEL=claude-sonnet-4-5

# 새로 추가
MAX_UPLOAD_SIZE_MB=100
UPLOAD_DIR=./uploads
OUTPUT_DIR=./outputs
WHISPER_MODEL=small
CORS_ORIGINS=http://localhost:5173
```

## 8. 실행 방법 (예정)

```bash
# 백엔드 실행
cd backend
uvicorn app:app --reload --port 8000

# 프론트엔드 실행
cd frontend
npm install
npm run dev
```

접속: http://localhost:5173
