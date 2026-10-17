# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Status
In progress — see the build schedule checkboxes. Sections describe the target design; update them as pieces become real. Full plan: `docs/PLAN.md`.
**Work phase-wise: finish one step, report, and get the user's explicit go-ahead before starting the next.**

## Project
AI-first student engagement platform ("SoFi for Indian students") for UG students and young professionals planning PG study abroad or in India. The funnel is **awareness → engagement → trust → education-loan conversion**. Deliverables: a working prototype **deployed publicly for real testers** and a solution deck. It is judged on innovation, depth of AI usage, UX/stickiness, NBFC-aware conversion thinking, and prototype quality. Bonus: a zero-human AI growth loop.

Timeline: **4 days**, solo developer. Keep every module, but build each one lean: one good working flow per feature, not exhaustive options.

## Stack
- `frontend/`: Next.js 15 (App Router) + TypeScript + Tailwind + shadcn/ui + Recharts, deployed on **Vercel**
- `backend/`: FastAPI + SQLModel + Alembic, deployed on **Render** (Docker, single instance)
- DB / auth / storage / vectors: **Supabase** (Postgres, Auth, private Storage bucket, pgvector). SQLite is used only in tests.
- LLM: Claude API. `claude-sonnet-5-5` handles mentor, agents, and doc extraction (vision); `claude-haiku-5-5` handles cheap content, classification, and nudges.
- ML: scikit-learn models trained on synthetic data, saved under `backend/app/ml/models/*.pkl`
- Scheduling: APScheduler runs in the API process. This relies on the single-instance deploy; don't scale horizontally without moving the jobs.

## Commands (once scaffolded)
```powershell
# backend (from backend/, with .venv active)
uvicorn app.main:app --reload
alembic upgrade head            # uses DATABASE_URL from backend/.env
alembic revision --autogenerate -m "msg"   # after changing app/db/models.py; review the generated file
python -m app.db.seed           # load universities/courses/salaries/loan products + KB embeddings
python -m app.ml.train          # regenerate synthetic data + retrain models
pytest                          # all tests
pytest tests/test_loan_rules.py::test_emi -q   # single test

# frontend (from frontend/)
npm run dev
npm run lint
npm run build
```
Env vars: `ANTHROPIC_API_KEY`, `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_JWT_SECRET`, `FRONTEND_ORIGIN`, `DAILY_LLM_LIMIT`, `MONTHLY_LLM_BUDGET`. The frontend uses `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_SUPABASE_URL`, and `NEXT_PUBLIC_SUPABASE_ANON_KEY`.

## Architecture
Backend layout under `backend/app/`: `api/` (one router per module), `agents/`, `ml/`, `rules/`, `rag/`, `mocks/`, `db/`. Seed data and the RAG knowledge base live in `backend/data/`.

**Profile → everything.** The onboarding quiz creates a `StudentProfile`. Navigator, admit predictor, ROI, timeline, mentor, and the loan estimator all read it, and the loan application form pre-fills from it. Keep the profile the single source of truth.

**Module chain (the conversion path).** Navigator shortlist → admit probability → ROI (total cost vs predicted salary) → the ROI "funding gap" feeds the loan eligibility estimator → dynamic offers → EMI/moratorium planner (EMI shown as a % of predicted salary) → loan copilot application → mock CIBIL → mock NBFC LOS → status tracker. Changing an upstream output shape breaks downstream screens.

**Mentor = RAG + tools.** The mentor agent retrieves from pgvector (cited sources) and calls the other modules as Claude tools (navigator, ROI, admit, loan estimate) instead of re-implementing their logic. Agent tools must wrap the same service functions the REST routers use.

**Auth.** Frontend uses supabase-js (implicit flow; email+password primary, magic link/Google secondary) and sends the access token as `Bearer` to the API. `app/auth.py:current_user` verifies it (HS256 via `SUPABASE_JWT_SECRET`, or ES256/RS256 via the project JWKS — this project uses ES256) and lazily creates the `User` row on first request; `ADMIN_EMAILS` grants admin. Frontend never talks to Supabase tables directly.

**Deterministic vs LLM.** Loan eligibility, offers, EMI, and FOIR are **pure rule code** in `rules/` and are unit-tested; never let the LLM compute money or decide eligibility. ML gives scores. The LLM explains, converses, generates content, and extracts documents.

**Growth engine.** Every user action is written to an `events` table. Journey stage (Explorer → Shortlister → Applicant → Admitted → Funding), interest tags, and lead score are derived from events. This drives feed ordering, nudges, and when the loan copilot is triggered. The Growth Orchestrator (scheduled) chains content agent → nudge agent → loan copilot trigger → metrics/A-B feedback. Every agent action is logged to an `agent_runs` table that the admin Agent Console displays. A user simulator generates a synthetic cohort so the loop has data to act on.

## Rules specific to this project
- **RLS on every table:** Supabase exposes `public` tables to the anon key via REST. Every new table must get `ENABLE ROW LEVEL SECURITY` (no policies) in its migration — see `migrations/versions/d2a058d4850b_enable_rls_on_app_tables.py`. The backend connects as the owner and bypasses RLS.
- **DB connection:** use the Supabase **Session pooler** URL (`postgres.<ref>@aws-…pooler.supabase.com:5432`); the direct `db.<ref>.supabase.co` host is IPv6-only and fails on this machine. Project region is ap-northeast-2 → deploy Render in Singapore.
- **Local dev ports:** frontend must run on `localhost:3000` (CORS `FRONTEND_ORIGIN`). If Next says the port is in use, kill the stale `next dev` process rather than continuing on 3001.
- **Multi-user and public:** every DB query is scoped by the `user_id` from the verified Supabase JWT. Admin routes require the admin role.
- **Simulated finance:** CIBIL, NBFC, WhatsApp, and email are mocks in `mocks/`. The UI must label loan offers as simulated/indicative. No real credit decisions; final approval is shown as "human credit review".
- **NBFC realism:** co-applicant required, collateral thresholds, approved-university tiers, FOIR check, moratorium with simple interest during study, Sec 80E view, transparent APR/fees.
- **PII:** masked Aadhaar only, consent capture (DPDP Act), uploads go to the private bucket via signed URLs and are auto-deleted after 30 days.
- **LLM cost control:** all Claude calls go through one client wrapper that enforces per-user daily limits, the monthly budget kill-switch, max_tokens caps, and prompt caching. Use Haiku unless quality needs Sonnet.

## Deployment (the app is shared publicly with real testers)
Deploy early and continuously. The skeleton goes live on Day 1, and every push to `main` auto-deploys.

1. **GitHub**: push the repo with `.env*` in `.gitignore`. Provide `backend/.env.example` and `frontend/.env.example`.
2. **Supabase**: create the project, enable the `vector` extension, enable Email (magic link) + Google auth, and create a private `loan-docs` bucket. Run `alembic upgrade head` and `python -m app.db.seed` against the Supabase `DATABASE_URL`.
3. **Backend on Render**: Web Service from `backend/Dockerfile`, start command `uvicorn app.main:app --host 0.0.0.0 --port $PORT`, health check `/health`, all backend env vars set in the dashboard, **1 instance only** (because of APScheduler). Commit trained `.pkl` models so the container doesn't need to train.
4. **Frontend on Vercel**: import the repo with root `frontend/`, and set the `NEXT_PUBLIC_*` vars, with `NEXT_PUBLIC_API_URL` pointing to the Render URL.
5. **Wire up**: set the backend `FRONTEND_ORIGIN` to the Vercel URL (CORS), and add the Vercel URL to Supabase Auth redirect URLs.
6. **Auth emails**: Supabase's built-in mailer allows only ~2–3 emails/hour. Before sharing, either keep "Confirm email" OFF (password sign-up works instantly) or configure custom SMTP (Resend free tier) in Auth → Emails → SMTP. Add the production URL to Auth → URL Configuration.
7. **Pre-share checklist**:
   - rate limits and the budget kill-switch are on;
   - the simulated-loan banner and privacy/consent page are visible;
   - an admin account is set;
   - Sentry DSN is set;
   - sign-up → loan-application has been tested end-to-end on the live URL with 2–3 separate accounts, confirming no data leaks between users.
8. Share the Vercel link. The in-app feedback button collects tester issues.

Free-tier note: the Render free instance sleeps when idle, so the first request takes about 30–60s. Hit `/health` before a demo.

## Build schedule (4 days)
- [ ] **Day 1 – Foundation** (✅ 1.1 scaffold · ✅ 1.2 Supabase DB + auth · ⬜ 1.3 quiz + seed data · ⬜ 1.4 deploy · ⬜ 1.5 Claude wrapper + navigator)
  - Original scope: **Day 1 – Foundation + deploy + engagement core**: scaffold both apps, Supabase setup, DB models + Alembic, auth, seed data, onboarding quiz + profile strength. **Deploy to Render + Vercel by end of day.** Claude client wrapper (limits/budget) and career navigator.
- [ ] **Day 2 – AI modules**: RAG ingest + mentor chat (streaming, tools, citations), synthetic data + admit model with what-if sliders, ROI calculator, timeline generator, SOP reviewer + visa mock interview (single prompt flows).
- [ ] **Day 3 – Loan funnel + growth**: eligibility rules, dynamic offers, EMI/moratorium planner, loan copilot with doc upload + vision auto-fill, mock CIBIL/LOS + status tracker. Events table, journey stage, XP/streaks/badges, referral code + share card, nudges.
- [ ] **Day 4 – Bonus loop + ship**: content agent + Discover feed, lead score, growth orchestrator + user simulator, admin Agent Console. Run the pre-share checklist on the live URL, then the solution deck (`deck/`) and demo script.
