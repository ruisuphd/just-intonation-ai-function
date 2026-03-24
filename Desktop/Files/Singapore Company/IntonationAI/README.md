# IntonationAI

AI music coach: vocal, piano, and guitar feedback with real-time analysis.

## Stack

- **Frontend:** Next.js 16, React 19, Firebase Auth/Firestore (client SDK)
- **Backend:** FastAPI on Cloud Run
- **Database:** Postgres (Cloud SQL), Firestore (realtime messages)
- **Services:** Vertex AI/Gemini, Stripe, GCS

## Production Project

All Firebase and GCP resources use project **intonationai**. See `.firebaserc` and `cloudbuild.yaml`.

## Env Contract

**Root `.env`** (backend + docker-compose):

- `FIREBASE_PROJECT_ID`, `GOOGLE_CLOUD_PROJECT`: intonationai
- `FIREBASE_WEB_API_KEY`: Firebase web API key (public, used by frontend)
- `GOOGLE_APPLICATION_CREDENTIALS`: path to service account JSON
- `DATABASE_URL`, `GCS_BUCKET`, Stripe vars, `FRONTEND_URL`, `BACKEND_URL`
- `ENVIRONMENT` (`development` | `production`; production requires `FIREBASE_PROJECT_ID` at startup)
- `DATABASE_AUTO_CREATE` (`true` for local SQLAlchemy `create_all`; `false` in production — use Alembic)

**Frontend `.env.local`** (or build-time env):

- `NEXT_PUBLIC_BACKEND_URL`: production API URL
- `NEXT_PUBLIC_FIREBASE_API_KEY`: same as FIREBASE_WEB_API_KEY
- `NEXT_PUBLIC_FIREBASE_PROJECT_ID`: intonationai

## Local

```bash
cp .env.example .env   # fill values
cp frontend/.env.example frontend/.env.local
docker compose up
```

Frontend: http://localhost:3000  
Backend: http://localhost:8000

## Deploy

See [DEPLOY.md](DEPLOY.md) for Firebase Hosting, Cloud Run, Firestore, rollback, and URLs.

## Backend tests

```bash
cd backend
pip install -r requirements-dev.txt
pytest tests -q
```
