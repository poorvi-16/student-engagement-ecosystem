# Plan: Unified Student Engagement Ecosystem ("SoFi for Indian students")

## Context
Hackathon-style project. Indian UG / young professionals planning PG studies (abroad or in India) face a fragmented journey: discovery → applications → visa → finances → loan. Build an **AI-first platform** that moves users **awareness → engagement → trust → conversion (education loan)**, plus a solution deck. The folder `student_engagement_ecosystem/` is currently empty except `.venv` (Python 3.14, Node 24 available).

Judging weights to design for: Innovation, depth of AI, UX/stickiness, conversion and NBFC thinking, prototype quality. Bonus: a zero-human AI growth loop, live deployment, simulated user data.

Working name: **PathPilot** (placeholder; can be renamed).

---

## 1. Architecture (recommended stack)

| Layer | Choice | Why |
|---|---|---|
| Frontend | **Next.js 15 (App Router) + TypeScript + Tailwind + shadcn/ui + Recharts** | Polished UI fast, easy Vercel deploy |
| Backend | **FastAPI (Python, uses existing `.venv`)** | ML + LLM code in one language |
| DB | **Postgres (Supabase) via SQLModel + Alembic**; SQLite for tests only | Multi-user, survives deploys |
| LLM | **Claude API**: `claude-sonnet-5-5` for mentor/agents, `claude-haiku-5-5` for cheap content and classification | Tool use + streaming |
| RAG | **pgvector (Supabase) + embeddings** over a curated knowledge base (universities, visas, loan FAQs, scholarships) | Grounded, cited answers |
| ML | **scikit-learn** (logistic regression / gradient boosting) on a synthetic dataset | Admission probability, lead scoring |
| Rules | Python rule engine for loan eligibility / offers | Mirrors real NBFC policy |
| Agents / automation | Claude tool-use agents + **APScheduler** jobs | Growth loop and nudges |
| Mock APIs | FastAPI routes simulating CIBIL, bank statement, NBFC LOS, WhatsApp/email | Realistic loan flow without real integrations |
| Deploy | Vercel (web) + Render/Railway (API) | Bonus live link |

```
student_engagement_ecosystem/
  frontend/            Next.js app
  backend/
    app/
      api/             routers: auth, profile, navigator, roi, admit, timeline, mentor, sop, loan, growth, admin
      agents/          mentor_agent, content_agent, nudge_agent, loan_copilot, growth_orchestrator
      ml/              admit_model.py, lead_score.py, train.py, models/*.pkl
      rules/           loan_eligibility.py, offers.py
      rag/             ingest.py, retriever.py
      mocks/           cibil, nbfc_los, notifications
      db/              models.py, session.py, seed.py
    data/              universities.csv, courses.csv, salaries.csv, visa.json, loan_products.json, kb/*.md
  deck/                solution deck
  CLAUDE.md
```

---

## 2. Feature modules

### A. Engagement layer (top of funnel)
1. **Onboarding quiz (2 min, gamified)** → builds a `StudentProfile` (degree, CGPA, test scores, budget, target countries, career goal, work exp). Ends with a "Profile Strength" score; this is the first hook.
2. **AI Career Navigator**: hybrid scoring (rule filter + weighted similarity over the university/course dataset), with Claude explaining each "why this fits you". Outputs country → university → course shortlist, tagged Ambitious, Target or Safe.
3. **Admission Probability Predictor**: sklearn model trained on synthetic applicant data (GRE/IELTS/CGPA/work-exp/univ tier). Shows %, top factors, and "what if" sliders (e.g. "+10 GRE → +8%").
4. **ROI Calculator**: total cost (tuition + living + FX) vs predicted salary by country/course, with payback period, 10-yr NPV, and India-vs-abroad comparison. *Feeds directly into the loan module* ("You need ₹38L; here's how to fund it").
5. **Application Timeline Generator**: Claude produces a personalised month-by-month plan (tests, SOP, LORs, deadlines, visa, loan sanction date) as an interactive checklist; completing tasks earns XP.
6. **Conversational Mentor (Copilot)**: streaming chat with RAG + tool use (can call navigator, ROI, admit-predictor, loan-estimator inline) and memory of the profile and past chats. Shows sources.
7. **GenAI tools**: SOP/essay drafter and reviewer, visa interview mock simulator (role-play), and an "A day in your life at <University>" simulation.

### B. AI marketing and growth engine
- **Content agent**: generates blogs, reel scripts, newsletters, and LinkedIn/Instagram posts per persona segment and topic; publishes to an in-app "Discover" feed plus SEO pages (`/guides/[slug]`).
- **Personalisation engine**: event tracking (`events` table) → journey stage (Explorer → Shortlister → Applicant → Admitted → Funding) plus interest tags, driving home-feed ordering and recommended next action.
- **Gamification**: XP, streaks, badges, levels, leaderboard by college/city.
- **Referral loop**: invite code, both sides get rewards (e.g. free SOP review, loan processing-fee waiver). Shareable "My Study-Abroad Card" image (profile + admit odds) for viral sharing.
- **Smart nudges**: a rule plus LLM nudge agent picks message, channel (in-app, email, or mock WhatsApp) and timing per stage. Example: "Fall deadlines in 21 days; your SOP is 40% done."
- **Lead scoring**: an ML model predicts loan-conversion propensity and feeds the admin dashboard.

### C. Conversion layer (loan funnel)
1. **Soft eligibility estimator** (no CIBIL hit): inputs are course, university tier, co-applicant income, collateral, and admit status. Outputs an indicative amount, rate band, and secured vs unsecured.
2. **Dynamic offers**: rule engine over mock NBFC products (rate/limit vary by univ tier, course, co-applicant income, collateral), plus pre-approved-style cards that improve as the profile strengthens.
3. **Financial planner**: EMI calculator, moratorium (course + 6–12 months) with simple interest during study, prepayment scenarios, Sec 80E tax-benefit view, and EMI as a % of predicted salary (from ROI).
4. **AI loan application copilot**: conversational, multi-step form that pre-fills from the profile. Document checklist generated per case; upload with **Claude vision extraction** (PAN, Aadhaar-masked, admit letter, ITR/salary slip) to auto-fill fields. Then a mock CIBIL check, mock submission to NBFC LOS, and a status tracker.
5. **NBFC-aware design** (shown in the deck and UI): co-applicant mandatory, collateral thresholds, approved-university lists, FOIR checks, KYC/consent capture (DPDP Act), RBI fair-practice disclosures (no hidden fees, clear APR), and human-in-the-loop for final credit decisions.

### D. Bonus: zero-human growth loop
A **Growth Orchestrator agent** runs on a schedule:
Acquire (content agent publishes SEO and social posts and tracks UTM sign-ups) → Engage (personalisation plus streaks) → Nurture (nudge agent sends stage-based messages) → Convert (loan copilot is triggered when lead score exceeds a threshold) → Learn (reads funnel metrics and adjusts content topics and nudge copy via A/B results).
All agent actions are logged and visible in an **Admin "Agent Console"** with a funnel dashboard, running on a **simulated user cohort** (seed script plus a simulator that generates daily events).

---

## 3. Build phases: 1 week, solo (user confirmed: Next.js + FastAPI, Claude API, full scope)
Keep every module, but build "thin but working" first, then deepen. Each day ends with a runnable demo.
- **Day 1**: Phase 1 (scaffold, DB, seed data, onboarding quiz)
- **Day 2**: Phase 2 (mentor chat + RAG + navigator)
- **Day 3**: Phase 3 (admit model, ROI)
- **Day 4**: Phase 4 (full loan funnel)
- **Day 5**: Phase 5 (growth engine)
- **Day 6**: Phase 6 lean (orchestrator + simulator + admin console) and Phase 7 (timeline, SOP/visa simulators, deploy)
- **Day 7**: Phase 8 deck, demo script, bug fixes

Phase detail:
1. **Foundation**: repo scaffold, FastAPI and Next.js, DB models, auth (simple email/OTP mock), onboarding quiz, seed datasets (about 150 universities, courses, salary data, loan products).
2. **Core AI**: Claude client wrapper, Mentor chat with RAG and tool use, Career Navigator.
3. **Predictive**: synthetic data plus training for the admit model and lead score; Admission Predictor UI; ROI calculator.
4. **Loan funnel**: eligibility, offers, EMI/planner, loan copilot, document upload and extraction, status tracker.
5. **Growth engine**: events, journey stage, gamification, referrals, share cards, content agent, nudges.
6. **Bonus loop**: orchestrator, user simulator, Admin Agent Console, funnel analytics.
7. **Polish and ship**: timeline generator, SOP/visa simulators, responsive UI, deploy, demo script.
8. **Solution deck**: problem, persona, platform design, AI architecture, growth, monetisation (NBFC lead fees/DSA commission, cross-sell of forex/insurance/accommodation, premium counselling), and impact metrics.

---

## 3b. Production deployment for real users (required, not bonus)
The app will be deployed and shared with other people, so it is designed multi-user and deploy-ready **from Day 1**:
- **Database**: **Postgres on Supabase** (free tier) from the start; SQLite is only for local tests. Alembic migrations.
- **Vectors**: **pgvector** in the same Supabase DB instead of local Chroma, because ephemeral hosting disks lose local files.
- **Auth**: Supabase Auth (email magic link + Google login). FastAPI verifies the Supabase JWT, and every query is scoped by `user_id`.
- **File uploads** (loan docs): Supabase Storage private bucket, signed URLs, auto-delete after 30 days.
- **Hosting**: frontend on **Vercel**, backend on **Render** (Docker, single instance; APScheduler runs in-process). Env vars live in the platform dashboards; nothing is committed. Custom domain optional.
- **Cost and abuse control** (shared Claude key): per-user daily message/token limits (`slowapi` + DB counter), Haiku for cheap calls, prompt caching, max_tokens caps, and a global monthly budget kill-switch.
- **Safety and compliance**: consent checkbox + privacy page (DPDP Act), a clear banner that loan offers, CIBIL and NBFC are **simulated/demo**, masked Aadhaar only, and no real credit decisions.
- **Reliability**: CORS locked to the Vercel domain, health endpoint, Sentry (free) for errors, basic structured logging, and a `seed` command for demo data on a fresh DB.
- **Ops for testers**: a feedback button (stored in DB), an admin role for the Agent Console, and a README "how to use" page.
- **Schedule impact**: Day 1 sets up Supabase + Render + Vercel with a "hello world" deployed, then every day's work is auto-deployed on push to GitHub (`main` → prod).
- **Verification**: an end-to-end walkthrough on the **live URL** with 2–3 separate test accounts (data isolation check), plus rate-limit and upload tests.

## 4. CLAUDE.md (first thing created after plan approval)
A single `CLAUDE.md` file (not a folder) at the project root, plus a `docs/PLAN.md` copy of this plan, containing: project goal and judging criteria, stack, folder map, run commands (backend `uvicorn`, frontend `npm run dev`), env vars (`ANTHROPIC_API_KEY`), model IDs, coding conventions (typed Pydantic schemas, routers per module, agents in `agents/`, no real PII, mock external APIs), and the phase checklist.

## 5. Verification
- `pytest` for rules (eligibility/EMI math), ML model loading, and API routes.
- Run both servers; walk the demo path: sign up → quiz → navigator → admit odds → ROI → mentor chat → loan estimate → apply with doc upload → status. Then check the admin console showing orchestrator runs on the simulated cohort.
- Lighthouse/mobile check and the deployed URL working.
