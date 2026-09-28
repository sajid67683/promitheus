# Promitheus

Turn lecture PDFs and text files into Duolingo-style interactive lessons. Gemini generates a
six-level quiz (free recall → fill in the blank → multiple choice → true/false → rearrange →
explain), and learners earn XP, keep streaks, complete daily quests, and compete in weekly leagues.

**Stack:** FastAPI · SQLAlchemy + PostgreSQL · Alembic · Jinja templates + vanilla JS · Gemini (`google-genai`) · Vercel

## Features

- **Learn:** a lesson path per uploaded lecture, six question types, instant feedback with explanations,
  typo-tolerant grading (plus an AI double-check for free-text answers), results screen with a mistakes review.
- **Practice:** every wrong answer goes into a review queue; practice rounds clear it (5 XP per first fix).
- **Library:** rename, delete or regenerate units; drag-and-drop uploads with progress.
- **Progress:** daily goal (chosen during onboarding), streak calendar, daily/monthly quests, weekly leagues.
- **Account:** settings for profile and avatar, daily goal, theme, sound, password, sign out everywhere,
  delete account, and forgot-password emails (when Resend is configured).
- **Accessible by default:** keyboard shortcuts in quizzes (1–6 to pick, Enter to check/continue),
  visible focus, WCAG AA contrast in light and dark themes, reduced-motion support, mobile tab bar.

## How it fits together

| Piece | Where |
| --- | --- |
| App entrypoint (Vercel + local) | `app.py` → `backend/main.py` |
| API routes | `backend/routers/` (`auth`, `upload`, `lessons`, `users`, `cron`, `pages`) |
| XP, streak, quest & league rules | `backend/gamification.py` |
| Answer checking (server-side only) | `backend/grading.py` |
| Gemini calls | `backend/ai_service.py` |
| Database models / migrations | `backend/models.py`, `migrations/` |
| Pages (server-rendered) | `backend/routers/pages.py`, `frontend/templates/` |
| Design system (Tailwind v4) | `frontend/tailwind/app.css` → built to `frontend/static/css/app.css` |
| Browser scripts (ES modules) | `frontend/static/js/` |

Quizzes are graded on the server: the browser only receives prompts and choices, submits each
answer to `/attempts/{id}/answers`, and XP is calculated by `/attempts/{id}/complete`. XP is
awarded the first time a lesson is completed; replays are practice.

## Local development

Requires Python 3.12+ and PostgreSQL.

```bash
python -m venv venv
venv\Scripts\activate            # macOS/Linux: source venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env             # then fill in the values
alembic upgrade head             # create the tables
uvicorn app:app --reload         # http://127.0.0.1:8000
```

After changing templates, JS or `frontend/tailwind/app.css`, rebuild the stylesheet (commit the result):

```bash
cd frontend && npm install && npm run build   # or: npm run watch
```

Run the tests (they use a temporary SQLite database and a fake Gemini, so no setup needed):

```bash
pytest
```

> **Upgrading an old local database** (one created before migrations existed): run
> `python scripts/reset_local_db.py --yes`. This **deletes all local data** and rebuilds the
> schema. It refuses to run against non-local hosts or in production.

### Changing the database schema

Edit `backend/models.py`, then:

```bash
alembic revision --autogenerate -m "describe the change"
alembic upgrade head
```

## Deploying to Vercel

1. **Create a Postgres database.** In Vercel, open *Storage → Marketplace* and add **Neon**
   (or use Supabase or any hosted Postgres). Use the **pooled** connection string as
   `DATABASE_URL`.
2. **Import the GitHub repo** in Vercel (*Add New → Project*). Vercel detects FastAPI from
   `requirements.txt` and `app.py`; no build settings needed.
3. **Set environment variables** (*Project → Settings → Environment Variables*):

   | Variable | Value |
   | --- | --- |
   | `DATABASE_URL` | pooled Postgres URL (added automatically by the Neon integration) |
   | `SECRET_KEY` | new random value: `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
   | `GEMINI_API_KEY` | from [Google AI Studio](https://aistudio.google.com/) |
   | `CRON_SECRET` | another random value (Vercel sends it to the cron endpoint) |
   | `GOOGLE_CLIENT_ID` | optional, enables "Continue with Google" |
   | `RESEND_API_KEY`, `EMAIL_FROM`, `APP_URL` | optional, enable "Forgot password?" emails |

4. **Create the tables** once, from your machine, against the production database:

   ```bash
   # PowerShell: $env:DATABASE_URL="postgresql://..."; alembic upgrade head
   DATABASE_URL="postgresql://..." alembic upgrade head
   ```

   Repeat this whenever you add a new migration.
5. **Google sign-in (optional):** in Google Cloud Console → *Credentials* → your OAuth client,
   add `https://<your-app>.vercel.app` to **Authorized JavaScript origins**.
6. **Deploy.** Every push to `main` redeploys.

### What `vercel.json` sets up

- **Function timeout of 300 s** so lecture generation (usually 20–60 s) never gets cut off.
- **Weekly league cron**: `GET /api/cron/weekly-reset` every Monday 00:00 UTC. It is protected
  by `CRON_SECRET` and processes each week only once, so retries are harmless. To run it by hand:
  `python -m backend.weekly_reset`.
- **Security headers** on every response.

### Limits worth knowing

- Vercel caps request bodies at 4.5 MB, so uploads are limited to **4 MB** (`MAX_UPLOAD_MB`).
- Per-user limits: 10 uploads/day (`DAILY_UPLOAD_LIMIT`) and 200 AI-graded answers/day
  (`DAILY_AI_GRADING_LIMIT`) protect your Gemini quota.
- If the main Gemini model is overloaded, the app retries on `GEMINI_FALLBACK_MODELS`
  (default `gemini-flash-latest,gemini-flash-lite-latest`).
- Scanned PDFs (images of text) aren't supported yet; there's no OCR.
