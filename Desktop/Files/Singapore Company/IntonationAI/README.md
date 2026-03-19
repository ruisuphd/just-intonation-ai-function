# IntonationAI

AI-powered vocal and music coaching platform on Google Cloud. Vocal coach first; piano and guitar coaches coming next.

## Stack

- **Frontend**: Next.js 15, TypeScript, Tailwind CSS
- **Backend**: Python FastAPI, SQLAlchemy (async), PostgreSQL (Cloud SQL)
- **AI/ML**: Claude on Vertex AI (LLM), librosa/pYIN (audio analysis)
- **Voice**: Google Cloud TTS Chirp 3 HD (TTS), Google Cloud Speech-to-Text Chirp (STT)
- **Real-time**: Firestore for live coaching chat sync
- **Auth**: Firebase Auth
- **Payments**: Stripe
- **Storage**: Google Cloud Storage
- **Deploy**: Cloud Run + Cloud Build

## Quick Start

```bash
# 1. Copy env and fill in credentials
cp .env.example .env

# 2. Start PostgreSQL + Firestore emulator + backend + frontend
docker compose up

# Or run services individually:

# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload

# Frontend
cd frontend
pnpm install
pnpm dev
```

## Project Structure

```
├── frontend/          Next.js 15 app (TypeScript + Tailwind)
├── backend/           FastAPI app (Python)
│   ├── app/services/  LLM, TTS, STT, audio, coach, RAG, warmup, payment
│   ├── app/db/        SQLAlchemy + Firestore
│   └── data/          RAG knowledge base materials
├── cloudbuild.yaml    Cloud Build → Cloud Run deployment
└── docker-compose.yml Local dev environment
```

## Environment Setup

1. **GCP Project**: Create a project in Google Cloud Console
2. **Firebase**: Enable Auth (email + Google sign-in)
3. **Vertex AI**: Enable API, request Claude model access
4. **Cloud SQL**: Create PostgreSQL instance (or use local Docker)
5. **Stripe**: Create test-mode account and products

Frontend: `http://localhost:3000` | Backend: `http://localhost:8000` | API docs: `http://localhost:8000/docs`
