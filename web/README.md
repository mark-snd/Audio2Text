# Audio to Minutes - Web Service

Web-based meeting minutes generation powered by Gemini (transcription) + Claude (minutes), deployed on Cloudflare Workers & Pages.

## Architecture

```
Frontend (Cloudflare Pages)  →  Worker API (Cloudflare Workers)
                                    ├── R2 (audio & results storage)
                                    ├── KV (job status)
                                    └── Durable Objects (pipeline orchestration)
```

## Prerequisites

- Node.js 18+
- Cloudflare account with Workers Paid plan ($5/mo for Durable Objects)
- API keys: `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`

## Setup

### 1. Create Cloudflare Resources

```bash
cd worker

# Login to Cloudflare
npx wrangler login

# Create R2 bucket
npx wrangler r2 bucket create minutes-audio

# Create KV namespace
npx wrangler kv namespace create JOB_STATUS
# Copy the id from the output and update wrangler.toml

npx wrangler kv namespace create JOB_STATUS --preview
# Copy the preview_id from the output and update wrangler.toml

# Set API key secrets
npx wrangler secret put GEMINI_API_KEY
npx wrangler secret put ANTHROPIC_API_KEY
```

### 2. Update wrangler.toml

Replace the placeholder KV namespace IDs with the real ones from step 1.

### 3. Local Development

```bash
# Terminal 1: Worker (port 8787)
cd worker
# Create .dev.vars with API keys for local dev
echo "GEMINI_API_KEY=your_key_here" > .dev.vars
echo "ANTHROPIC_API_KEY=your_key_here" >> .dev.vars
npx wrangler dev

# Terminal 2: Frontend (port 5173, proxies /api to 8787)
cd frontend
npm run dev
```

Open http://localhost:5173

### 4. Deploy

```bash
# Deploy worker
cd worker
npx wrangler deploy

# Deploy frontend (update API_BASE in client.ts to your worker URL first)
cd frontend
npm run build
npx wrangler pages deploy dist --project-name=minutes-app
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/upload` | POST | Upload audio file (multipart/form-data) |
| `/api/process/:jobId` | POST | Start transcription + minutes pipeline |
| `/api/status/:jobId` | GET | Poll job progress |
| `/api/result/:jobId` | GET | Get transcript + minutes |
| `/api/download/:jobId` | GET | Download minutes as .md file |

## Supported Audio Formats

wav, mp3, aiff, aac, ogg, flac, m4a (max 100MB)
