# PathPilot demo script (7 minutes)

**Live:** https://student-engagement-ecosystem.vercel.app · API https://pathpilot-api-n4ox.onrender.com/health

## Before you start (2 minutes, once)
1. Open `/health` on the API so the free Render instance is awake (the first request takes 30-60 s). It should show `admit_model`, `lead_model` and `storage: true`.
2. Sign in as the **admin** account (its email is in `ADMIN_EMAILS` on Render) in one window, and as a fresh **student** in a second window.
3. In the Agent Console press **Add cohort** (120 students, 21 days) once, then **Run the loop now**, so the dashboards have data.
4. Have a sample, redacted PAN image ready for the loan copilot. Do not use real documents.

## The story
*"A student in Pune wants an MS abroad and doesn't know what it costs, whether she'll get in, or how to fund it. PathPilot takes her from curiosity to a loan application in one product, and an AI growth loop runs the marketing behind it with no human in it."*

## Part 1: the student journey (4 minutes)
| Min | Screen | Say | Show |
|---|---|---|---|
| 0:00 | Landing + a guide (`/guides`) | "Acquisition: these SEO guides are written by our content agent from a reviewed knowledge base, with sources." | Open one guide, point at sources and the sign-up CTA tagged with its campaign |
| 0:30 | Quiz → dashboard | "Two minutes of questions create one profile that every module reads." | Profile strength ring, XP, level, streak |
| 1:00 | Career Navigator | "Matches in Ambitious, Target and Safe, scored by an ML model with monotonic constraints, plus the money view." | Cost, payback, funding gap on each card |
| 1:40 | Program page | "What-if: raise GRE by 10 and see odds move. ROI is total cost vs predicted salary." | Drag a slider; open the India-vs-abroad comparison |
| 2:20 | Loan planner `/loan` | "The funding gap feeds a soft eligibility check. No credit-score impact. Four simulated lenders with transparent APR." | Offers, FOIR, EMI as % of salary, moratorium chart, Section 80E |
| 3:00 | Loan copilot `/loan/apply` | "Upload a PAN and the copilot reads it, fills the form and cross-checks it. Three consents before submit." | Auto-filled fields, copilot warnings, tracker moving through stages |
| 3:40 | Mentor | "RAG over our guides with tools: it calls the same ROI and loan functions as the screens." | Ask "How much is the F-1 visa fee and how do I show funds?" and point at the citations |

Optional if time allows: timeline (`/timeline`), SOP reviewer, visa mock interview with speech.

## Part 2: the growth loop (2.5 minutes)
| Min | Screen | Say | Show |
|---|---|---|---|
| 4:00 | Dashboard growth panel | "Smart nudges are ranked by value to the funnel. Loan steps come first." | Next-step cards, badges, invite code, opt-in share card |
| 4:40 | `/admin` Agent Console | "Every day the orchestrator runs simulate → learn → acquire → nurture → convert → measure, and logs every decision." | Open a run; read the six step lines |
| 5:30 | Funnel + lead scores | "A gradient-boosted lead score tells us who is ready for a loan, and why." | Switch Real / Simulated; hot leads and their reasons |
| 6:00 | A/B card | "Two nudge wordings compete. The loop learned that benefit-led copy wins and now serves it to about 80% of students." | CTR for A and B, z-score |
| 6:30 | Safety switches | "Rate limits, a daily AI cap and a one-click pause keep the shared free quota safe." | The Pause button, feedback inbox |

## Close (30 seconds)
"Everything about money is simulated and clearly labelled. Students can export or delete all their data. Next: real lender sandbox, a real bureau, and retraining the models on real outcomes."

## If something goes wrong
- **AI says it is busy:** free-tier quotas are shared. Every feature has a non-AI fallback; say so and carry on.
- **First load is slow:** the Render free instance was asleep. Hit `/health` and wait 30 s.
- **Console shows no data:** press Add cohort, then Run the loop now.
- **Loan tracker is slow:** the simulated lender takes about 10 minutes end to end; show the stages that are already visible.
