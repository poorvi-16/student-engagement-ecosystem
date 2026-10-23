# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Status
In progress — see the build schedule checkboxes. Sections describe the target design; update them as pieces become real. Full plan: `docs/PLAN.md`.
**Work day-wise: complete all steps of a build day without pausing (commit + push after each step), stop mid-day only if the user must do something, then give a full briefing and get the go-ahead before the next day.**

## Git workflow (required after every completed step)
Remote: `origin` → https://github.com/poorvi-16/student-engagement-ecosystem (branch `main`). Render and Vercel deploy from it.
1. When a step is done and tests/lint pass, commit and **push to `origin main`** so a saved version always exists on GitHub.
2. Commit messages must be detailed and clear:
   - Subject: imperative, ≤72 chars, names the step (e.g. `Step 1.5: Add Claude wrapper and AI Career Navigator`).
   - Body: what was added/changed, grouped by **Backend / Frontend / Database / Tests / Docs**, noting new migrations, env vars, and anything the user must do manually.
3. Before committing, confirm no secrets are staged: `git ls-files --cached | grep -E "\.env($|\.local)"` must print nothing.
4. Never force-push or rewrite pushed history.

## Project
AI-first student engagement platform ("SoFi for Indian students") for UG students and young professionals planning PG study abroad or in India. The funnel is **awareness → engagement → trust → education-loan conversion**. Deliverables: a working prototype **deployed publicly for real testers** and a solution deck. It is judged on innovation, depth of AI usage, UX/stickiness, NBFC-aware conversion thinking, and prototype quality. Bonus: a zero-human AI growth loop.

Timeline: **4 days**, solo developer. Keep every module, but build each one lean: one good working flow per feature, not exhaustive options.

## Stack
- `frontend/`: Next.js 15 (App Router) + TypeScript + Tailwind + shadcn/ui + Recharts, deployed on **Vercel**
- `backend/`: FastAPI + SQLModel + Alembic, deployed on **Render** (Docker, single instance)
- DB / auth / storage: **Supabase** (Postgres, Auth, private Storage bucket). SQLite is used only in tests.
- LLM: **free tiers only** (user decision: no paid key). **Gemini** (`gemini-3.5-flash`, `gemini-flash-lite-latest`; `reasoning_effort=minimal`, via Google's OpenAI-compatible endpoint) first, **Groq** (`openai/gpt-oss-120b`, `gpt-oss-20b`) as automatic fallback. Free quotas are **per model** (Gemini ≈5 requests/min/model; Groq gpt-oss-120b 8k tokens/min), so each tier is a comma-separated model list and every model is tried in turn. Gemini is needed for doc extraction (vision; Groq lacks it). Anthropic remains an optional paid provider for structured calls only. These limits are shared by all users, so minimise requests per feature, cache results, and always keep the non-AI fallback. `gemini-flash-latest` rejects `minimal` reasoning, so don't add it to the list.
- ML: scikit-learn models trained on synthetic data, saved under `backend/app/ml/models/*.pkl` and committed. `scikit-learn`/`numpy` are pinned in `requirements.txt` because the .pkl must load with the version it was trained with; bump both together and retrain.
- Scheduling: APScheduler runs in the API process. This relies on the single-instance deploy; don't scale horizontally without moving the jobs.

## Commands (once scaffolded)
```powershell
# backend (from backend/, with .venv active)
uvicorn app.main:app --reload
alembic upgrade head            # uses DATABASE_URL from backend/.env
alembic revision --autogenerate -m "msg"   # after changing app/db/models.py; review the generated file
python data/generate_catalog.py # regenerate universities.csv / courses.csv / catalog_meta.json (indicative data)
python -m app.ml.train          # regenerate synthetic applicants + retrain the admit model (~30s); commit the new .pkl + .json
pytest                          # all tests
pytest tests/test_loan_rules.py::test_emi -q   # single test

# frontend (from frontend/)
npm run dev
npm run lint
npm run build
```
Env vars: `LLM_PROVIDERS` (default `gemini,groq`), `GEMINI_API_KEY`, `GROQ_API_KEY` (optional: `ANTHROPIC_API_KEY`, `GEMINI_MODEL_FAST/SMART`, `GROQ_MODEL_FAST/SMART`), `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_JWT_SECRET`, `FRONTEND_ORIGIN`, `DAILY_LLM_LIMIT`, `MONTHLY_LLM_BUDGET`. The frontend uses `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_SUPABASE_URL`, and `NEXT_PUBLIC_SUPABASE_ANON_KEY`.

## Architecture
Backend layout under `backend/app/`: `api/` (one router per module), `agents/`, `ml/`, `rules/`, `rag/`, `mocks/`, `db/`. Seed data and the RAG knowledge base live in `backend/data/`.

**Reference data vs user data.** Universities, courses, salaries, FX and loan products are static CSV/JSON in `backend/data/`, loaded once into memory by `app/catalog.py:get_catalog()` (amounts in local currency; convert with `catalog.to_inr`). Only per-user data lives in Postgres. Loan products and lenders are fictional.

**Events + XP.** Record user actions with `app/events.py:log_event(session, user, type, payload, xp=, once=)`; it also awards XP (once=True → first occurrence only).

**Profile → everything.** The onboarding quiz creates a `StudentProfile`. Navigator, admit predictor, ROI, timeline, mentor, and the loan estimator all read it, and the loan application form pre-fills from it. Keep the profile the single source of truth.

**Module chain (the conversion path).** Navigator shortlist → admit probability → ROI (total cost vs predicted salary) → the ROI "funding gap" feeds the loan eligibility estimator → dynamic offers → EMI/moratorium planner (EMI shown as a % of predicted salary) → loan copilot application → mock CIBIL → mock NBFC LOS → status tracker. Changing an upstream output shape breaks downstream screens.

**Mentor = RAG + tools.** Knowledge base = curated guides in `backend/data/kb/*.md` (front matter: title, sources, reviewed), chunked by `## ` section and searched with in-memory BM25 (`app/rag/kb.py`); no embeddings provider. `services/mentor.py` gives the LLM tools (`search_knowledge`, `find_programs`, `analyze_program`, `estimate_loan`) and resolves `[S1]` citations to sources. Tools must wrap the same service functions the REST routers use (e.g. `navigator.make_matches`, `services/programs.py`). The top 3 KB passages are pre-attached to each question so most answers take one LLM request. History lives in `chatmessage` (last 10 turns sent as memory, old citation ids stripped). gpt-oss writes `【S1】` citations; `normalize_citations` converts them. Non-streaming; if the LLM is unavailable the reply is built from top search hits. When you edit KB facts that change often (visa fees, fund amounts), keep the official source URL and update `reviewed`.

**Auth.** Frontend uses supabase-js (implicit flow; email+password primary, magic link/Google secondary) and sends the access token as `Bearer` to the API. `app/auth.py:current_user` verifies it (HS256 via `SUPABASE_JWT_SECRET`, or ES256/RS256 via the project JWKS — this project uses ES256) and lazily creates the `User` row on first request; `ADMIN_EMAILS` grants admin. Frontend never talks to Supabase tables directly.

**LLM calls.** Always go through `app/llm.py` (`llm.parse(session, user, feature=, system=, prompt=, output=PydanticModel, tier="fast"|"smart")`): or `llm.chat(..., messages=, tools=, run_tool=)` for tool loops. It tries providers in `LLM_PROVIDERS` order (429/5xx/invalid JSON → next provider), enforces `DAILY_LLM_LIMIT` per user and `MONTHLY_LLM_BUDGET` globally, and logs every call to `llmusage` (model stored as `provider/model`; free models cost 0). Structured output = JSON mode + the Pydantic schema in the system prompt, validated with Pydantic. It raises `LLMUnavailable` (with a user-facing message) — every feature must catch it and fall back to non-AI output. Cache deterministic-input results in `AiCache` keyed by a hash of the inputs + a prompt version (see `services/navigator.py`). Send no names/emails to the model.

**Navigator.** `services/navigator.py:build_matches` filters the catalog by target countries/field/level, scores with the admit model (batched via `navigator.make_matches`), takes cost/payback/funding gap from `rules/roi.py` with default assumptions (so cards match the program page), buckets Ambitious <25% / Target <60% / Safe, ranks by tier-weighted salary/cost, one program per university. The LLM only writes `why`/`watch_out` text. Shortlist (`shortlist` table) moves journey stage explorer → shortlister.

**Admit model.** `ml/synth.py` samples ~400 applicants per catalog program around its admitted-class averages and labels them with a hidden process (diminishing returns, English minimum, MBA work-ex, unseen SOP factor), calibrated to each program's acceptance rate. `ml/features.py:featurize` makes program-relative features (CGPA gap, test gap, ...); `ml/train.py` fits a `HistGradientBoostingClassifier` with **monotonic constraints** (better scores never lower odds, which keeps the sliders sane), evaluates on held-out *programs* vs logistic regression / the old heuristic / the oracle, and writes `admit-v1.pkl` + a metrics `.json`. `ml/admit.py` loads it at startup (`/health` shows `admit_model`), clips chances to 3–90%, falls back to the heuristic if the pkl can't load, and `explain()` returns factor impacts (vs a typical admit) and what-if levers in one batched predict. Changing `FEATURES` means bumping `MODEL_VERSION` and retraining.

**Program page = admit + ROI.** `/programs/{id}` (frontend `app/programs/[id]`) combines what-if sliders (`POST /programs/{id}/admit` with score overrides) and the ROI calculator (`POST /programs/{id}/roi` with assumptions). `rules/roi.py` is pure: tuition + living (lifestyle) + rupee-depreciation buffer + one-time costs (`catalog_meta.json` `one_time_lakhs`) − scholarship; own funds are spent first and the rest is a loan with simple interest during course + 6 months, then EMIs (`rules/finance.py`, reused by the Day 3 planner); payback = years of savings (35% of a 7%-growing salary) to recover cost + all interest; "work in India" uses the India field median × 1.25. It also compares against the best-value India program (or the best abroad one for an India program). The `roi_calc` event stores the funding gap for the loan funnel. Slider endpoints log events via `events.log_event_daily` (one row per program per day).

**Timeline.** `rules/timeline.py:build_plan` builds every dated task from intake (season start month per country), program deadlines (shortlist, else navigator picks; Spring intakes close ~4 months before start), missing tests (GRE only for US programs), SOP/LOR/docs, per-country visa steps (`VISA_STEPS`), loan apply → sanction letter before the visa, and travel. Fixed tasks (deadlines, CAT/GATE dates) keep their date; overdue prep tasks are re-spaced in order before the first deadline. `services/timeline.py` makes one `llm.parse` call (cached in AiCache) for a summary, per-task tips and ≤3 extra tasks. It never changes dates. Tasks live in `timelinetask` with stable `key`s (regenerating keeps ticks); `timelineplan.input_hash` flags a stale plan. +40 XP for the first plan, +10 XP once per task (`xp_awarded`); ticking an `apply:*` task moves the journey stage to applicant. The mentor's system prompt includes the next 3 open tasks.

**SOP reviewer.** `rules/sop.py:analyze` runs deterministic checks (length, paragraphs, sentence length, cliché list, numbers as evidence, "I"-openings, career goals, names the university). `services/sop.py` makes one `llm.parse` call (smart tier, cached by text + program hash) for a 6-criterion rubric, strengths, improvements and a rewritten opening; `_clean` clamps scores, normalises criteria and drops quotes not found verbatim in the SOP. The rewrite must use only facts from the SOP (placeholders otherwise). gpt-oss tends to invent anecdotes, so that rule is in both the system prompt and the field description. Submissions (text + result) are stored in `sopsubmission`; a review auto-completes the `sop:review` timeline task.

**Visa mock interview.** `rules/visa.py` holds the question banks (USA, UK, Canada, Germany, Australia; 6 questions each, each with what the officer `looks_for` and fallback keywords). `services/visa.py` makes one `llm.parse` call per answer (fast tier). The officer's system prompt includes the applicant file: profile plus the ROI cost and loan needed, so inconsistent funding answers get flagged. It returns rating 1-5, feedback, a tip, red flags and an optional follow-up; there are at most 2 follow-ups per interview and follow-ups never chain. The readiness score is computed from the ratings, with no extra call. Without the LLM, `rule_evaluate` checks length, keywords and specifics. Sessions live in `visainterview` (`queue` = questions left, `turns` = answered; reassign the lists so JSON changes save). Starting a new one abandons any active session. +50 XP for the first completed interview, and completion ticks the timeline's `visa:practice` task. The frontend can read questions aloud (speechSynthesis) and take spoken answers (webkitSpeechRecognition, when available).

**Loan planner (`/loan`).** `rules/loan.py` is pure and unit-tested. For each product in `loan_products.json`, `evaluate()` checks:
- country and university tier, and the co-applicant income floor;
- secured: collateral value ÷ cover %; unsecured: co-applicant income × tier multiple;
- margin money and the minimum amount;
- FOIR = (existing EMIs + this EMI) ÷ (co-applicant income + 50%/35%/0% of the student's expected salary for tier 1/2/3); limit 70% secured, 60% unsecured.

Pricing is the product floor plus visible premiums (tier, non-STEM, income band, collateral discount). Simple interest during the moratorium is capitalised; APR is KFS-style (the fee is included, so APR ≥ rate). `schedule()` does year-by-year repayment with optional interest servicing during study, prepayment, and Sec 80E (old regime only, 8 years at 31.2%). `services/loan.build_case` starts the amount from the ROI funding gap. API `/loan`, `/loan/offers` (can save co-applicant income/collateral to the profile), `/loan/plan`. The UI always says soft check / simulated lenders.

**Loan copilot (`/loan/apply`).** There is one active `loanapplication` per student, created from an offer and pre-filled from the profile; re-applying resumes the draft. Documents (`POST /loan/applications/{id}/documents`, multipart, JPG/PNG/WebP/PDF ≤ 5 MB):
- `services/documents.extract` renders PDFs to JPEG (pypdfium2) and calls `llm.parse(..., images=[...])`, which tries only `VISION_PROVIDERS` (Gemini, Anthropic; Groq is text-only).
- `rules/loan_docs`:
  - `clean_extracted` keeps only the Aadhaar's last 4 digits (and passport last 4);
  - `autofill` fills only empty fields;
  - `checklist`, `missing` and `cross_checks` give the deterministic "copilot check": PAN format, name vs PAN, admit-letter university, declared vs slip income, passport expiry, age.
- Files go to the private Supabase Storage bucket `loan-docs` (`app/storage.py`, service-role REST, created on first use); they're viewed only through 5-minute signed URLs and deleted after 30 days by `scheduler.cleanup_documents` (APScheduler, started in the FastAPI lifespan; tests never start it). Aadhaar images are never stored.

Submitting needs all required fields and documents, no copilot errors, and 3 consents (KYC, bureau, DPDP). It then runs `mocks/cibil.pull` (deterministic per PAN; ~70% of students have no history) and `mocks/nbfc_los.submit`, which re-evaluates the offer with document-verified income. The decision is sanctioned, revised or declined, with declined for a co-applicant score below 650. The decision is fixed at submission but revealed by `nbfc_los.status` as time passes (stages at 0/1/2/4/7/10 minutes, ending in "Human credit review" → a provisional, simulated sanction letter). Submitting moves the journey stage to `funding`.

**Deterministic vs LLM.** Loan eligibility, offers, EMI, and FOIR are **pure rule code** in `rules/` and are unit-tested; never let the LLM compute money or decide eligibility. ML gives scores. The LLM explains, converses, generates content, and extracts documents.

**Growth engine.** Every user action is written to the `event` table, and `services/growth.py` derives everything from it plus current state:
- **Streaks:** `touch` runs on GET /me; +5 XP per visit day; a gap resets the streak.
- **Journey stage:** `derive_stage` moves explorer → shortlister (shortlist) → applicant (an `apply:*` task done) → admitted (`decide:accept` done or admit letter uploaded) → funding (loan submitted), and never moves backwards. Interest tags (`country:`/`field:`/`topic:`) are refreshed on /me.
- **Levels and badges:** levels (`rules/gamification.LEVELS`); 14 badges evaluated from event counts and persisted in `userbadge` (no XP for badges).
- **Nudges:** `rules/nudges.candidates(State)` returns prioritised next actions, with the loan triggers on top (funding gap → offers → copilot → finish → decision). `refresh_nudges` syncs the `nudge` table on GET /growth: max 3 active, expired when no longer true, 7-day cooldown after click/dismiss. `push_nudges` (daily 10:00 IST via APScheduler) sends one ≥80-priority nudge per opted-in (`consent_marketing`) student every ≤3 days on the mock email/WhatsApp gateway (`mocks/notifications.py`).
- **Referrals:** `?ref=CODE` on the landing page goes to localStorage, and the dashboard claims it (first week only, not your own code): +50 XP for the referee, then +100 XP for the referrer when the referee completes the quiz.
- **Share card:** opt-in public card at `/card/{code}` with first name, goals, level and badges only, via GET /public/card/{code} (no auth), plus an OG image for WhatsApp/LinkedIn previews.

The Day 4 Growth Orchestrator chains content agent → nudge agent → loan copilot trigger → metrics/A-B feedback and logs to `agent_runs`; a user simulator generates a synthetic cohort.

## Rules specific to this project
- **RLS on every table:** Supabase exposes `public` tables to the anon key via REST. Every new table must get `ENABLE ROW LEVEL SECURITY` (no policies) in its migration — see `migrations/versions/d2a058d4850b_enable_rls_on_app_tables.py`. The backend connects as the owner and bypasses RLS.
- **DB connection:** use the Supabase **Session pooler** URL (`postgres.<ref>@aws-…pooler.supabase.com:5432`); the direct `db.<ref>.supabase.co` host is IPv6-only and fails on this machine. Project region is ap-northeast-2 → deploy Render in Singapore.
- **Memory:** Render free has 512 MB and dev machines may be tight; `OPENBLAS_NUM_THREADS=1` is set in the Dockerfile and tests (numpy/scikit-learn otherwise spawn a thread pool per core).
- **Env changes need a backend restart:** settings are cached and `--reload` only watches `.py` files.
- **Local dev ports:** frontend must run on `localhost:3000` (CORS `FRONTEND_ORIGIN`). If Next says the port is in use, kill the stale `next dev` process rather than continuing on 3001. Don't run `npm run build` while `npm run dev` is running: both write `.next/` and the dev server starts returning 500s until it's restarted.
- **Multi-user and public:** every DB query is scoped by the `user_id` from the verified Supabase JWT. Admin routes require the admin role.
- **Simulated finance:** CIBIL, NBFC, WhatsApp, and email are mocks in `mocks/`. The UI must label loan offers as simulated/indicative. No real credit decisions; final approval is shown as "human credit review".
- **NBFC realism:** co-applicant required, collateral thresholds, approved-university tiers, FOIR check, moratorium with simple interest during study, Sec 80E view, transparent APR/fees.
- **PII:** masked Aadhaar only, consent capture (DPDP Act), uploads go to the private bucket via signed URLs and are auto-deleted after 30 days.
- **LLM usage control:** every LLM call goes through `app/llm.py` (`parse` for structured output, `chat` for tool-using conversations), which enforces the per-user daily call limit and monthly budget, max_tokens caps, and provider fallback. Each tool round counts as one call. Tests never hit real providers (autouse fixture blanks keys; use `httpx.MockTransport` or monkeypatch `llm.parse`/`llm.chat`).

## Deployment (the app is shared publicly with real testers)
Deploy early and continuously. The skeleton goes live on Day 1, and every push to `main` auto-deploys.

1. **GitHub**: push the repo with `.env*` in `.gitignore`. Provide `backend/.env.example` and `frontend/.env.example`.
2. **Supabase**: create the project and enable Email (magic link) + Google auth. The private `loan-docs` bucket is created by the backend on first upload (`/health` shows `storage: true` when the service-role key is set). Run `alembic upgrade head` against the Supabase `DATABASE_URL`.
3. **Backend on Render**: deployed from `render.yaml` (Blueprint) → Docker service `pathpilot-api`, root `backend/`, region Singapore, free plan, **1 instance**, health check `/health`, auto-deploy on push. `backend/start.sh` runs `alembic upgrade head` before starting uvicorn, so migrations apply on every deploy. Secrets are `sync: false` and entered in the Render dashboard. Commit trained `.pkl` models so the container doesn't need to train.
4. **Frontend on Vercel**: import the repo with root `frontend/`, and set the `NEXT_PUBLIC_*` vars, with `NEXT_PUBLIC_API_URL` pointing to the Render URL.
5. **Wire up**: set the backend `FRONTEND_ORIGIN` to the Vercel production URL and `FRONTEND_ORIGIN_REGEX` to match preview URLs (CORS); add the Vercel URL to Supabase Auth → URL Configuration (Site URL + Redirect URLs).
6. **Auth emails**: Supabase's built-in mailer allows only ~2–3 emails/hour. Before sharing, either keep "Confirm email" OFF (password sign-up works instantly) or configure custom SMTP (Resend free tier) in Auth → Emails → SMTP. Add the production URL to Auth → URL Configuration.
7. **Pre-share checklist**:
   - rate limits and the budget kill-switch are on;
   - the simulated-loan banner and privacy/consent page are visible;
   - an admin account is set;
   - Sentry DSN is set;
   - sign-up → loan-application has been tested end-to-end on the live URL with 2–3 separate accounts, confirming no data leaks between users.
8. Share the Vercel link. The in-app feedback button collects tester issues.

**Live:** frontend https://student-engagement-ecosystem.vercel.app · API https://pathpilot-api-n4ox.onrender.com (`/health`). Steps 1–6 are done (the `loan-docs` bucket exists, created by the backend); step 7 runs on Day 4.

Free-tier note: the Render free instance sleeps when idle, so the first request takes about 30–60s. Hit `/health` before a demo.

## Build schedule (4 days)
- [x] **Day 1 – Foundation** (✅ 1.1 scaffold · ✅ 1.2 Supabase DB + auth · ✅ 1.3 quiz + profile strength + catalog · ✅ 1.4 deploy · ✅ 1.5 Claude wrapper + navigator)
  - Original scope: **Day 1 – Foundation + deploy + engagement core**: scaffold both apps, Supabase setup, DB models + Alembic, auth, seed data, onboarding quiz + profile strength. **Deploy to Render + Vercel by end of day.** Claude client wrapper (limits/budget) and career navigator.
- [x] **Day 2 – AI modules** (✅ 2.1 RAG + mentor chat with tools/citations, Gemini→Groq · ✅ 2.2 synthetic data + admit model with what-if sliders + ROI calculator · ✅ 2.3 timeline generator · ✅ 2.4 SOP reviewer · ✅ 2.5 visa mock interview)
- [x] **Day 3 – Loan funnel + growth**: ✅ 3.1 eligibility rules + dynamic offers + EMI/moratorium planner · ✅ 3.2 loan copilot with doc upload + vision auto-fill, mock CIBIL/LOS + status tracker · ✅ 3.3 journey stage, XP levels/streaks/badges, referral code + share card, nudges
- [ ] **Day 4 – Bonus loop + ship**: content agent + Discover feed, lead score, growth orchestrator + user simulator, admin Agent Console. Run the pre-share checklist on the live URL, then the solution deck (`deck/`) and demo script.
