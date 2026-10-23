// Builds deck/PathPilot-solution-deck.pptx:  node deck/build.js   (needs pptxgenjs)
const path = require("path");
const pptxgen = require("pptxgenjs");
const SKILL = process.env.PPTX_SKILL_DIR; // optional: folder of the pptx skill, to apply the theme colours
const OUT = path.join(__dirname, "PathPilot-solution-deck.pptx");

const THEME = {
  name: "PathPilot",
  headFontFace: "Cambria",
  bodyFontFace: "Calibri",
  colors: {
    dk1: "1B1F3B", lt1: "FFFFFF", dk2: "2A2F6B", lt2: "EEF0FB",
    accent1: "4F46E5", accent2: "D97706", accent3: "047857", accent4: "EF4444", accent5: "6366F1", accent6: "64748B",
    hlink: "4F46E5", folHlink: "6D28D9",
  },
};

const pres = new pptxgen();
pres.layout = "LAYOUT_16x9"; // 10 x 5.625 in
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
pres.title = "PathPilot: solution deck";
const C = pres.SchemeColor;

pres.defineSlideMaster({
  title: "DARK", background: { color: C.text1 },
  slideNumber: { x: 9.2, y: 5.25, color: "A5B4FC", fontSize: 10 },
});
pres.defineSlideMaster({
  title: "CONTENT", background: { color: C.background1 },
  slideNumber: { x: 9.2, y: 5.25, color: "64748B", fontSize: 10 },
  objects: [{ text: { text: "PathPilot", options: { x: 0.5, y: 5.25, w: 3, h: 0.25, fontSize: 10, color: "64748B", margin: 0 } } }],
  margin: [0.5, 0.5, 0.5, 0.5],
});

const title = (s, t) => s.addText(t, { x: 0.5, y: 0.35, w: 9, h: 0.7, fontSize: 28, bold: true, fontFace: THEME.headFontFace, color: C.text1, margin: 0, isTextBox: true, objectName: "Title" });
const card = (s, x, y, w, h, fill = C.background2) => s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.08, fill: { color: fill }, line: { color: fill }, objectName: "Card" });
const txt = (s, t, o) => s.addText(t, { isTextBox: true, margin: 0, color: C.text1, fontSize: 14, valign: "top", ...o });

// 1. Title
let s = pres.addSlide({ masterName: "DARK" });
txt(s, "PathPilot", { x: 0.7, y: 1.4, w: 8.6, h: 1, fontSize: 54, bold: true, fontFace: THEME.headFontFace, color: C.background1 });
txt(s, "SoFi for Indian students: from \"where should I study?\" to a funded loan application, in one AI-first product", { x: 0.7, y: 2.5, w: 7.6, h: 1.0, fontSize: 20, color: "C7D2FE" });
txt(s, "Live prototype: student-engagement-ecosystem.vercel.app", { x: 0.7, y: 4.4, w: 8, h: 0.4, fontSize: 14, color: "A5B4FC" });
s.addNotes("One line: we built the whole funnel, awareness to loan, and an AI growth loop that runs the marketing with no human in it.");

// 2. Problem
s = pres.addSlide({ masterName: "CONTENT" });
title(s, "Fragmented journey, loan comes last");
const steps = [["Discover", "Which country, which university, which course?"], ["Decide", "Will I get in? What will it really cost?"], ["Apply", "Tests, SOPs, deadlines, visa interview"], ["Fund", "Paperwork, co-applicant, collateral, EMIs"]];
steps.forEach(([h, d], i) => {
  const x = 0.5 + i * 2.3;
  card(s, x, 1.5, 2.1, 2.1);
  s.addShape(pres.shapes.OVAL, { x: x + 0.15, y: 1.65, w: 0.5, h: 0.5, fill: { color: C.accent1 }, line: { color: C.accent1 }, objectName: "Step badge" });
  txt(s, String(i + 1), { x: x + 0.15, y: 1.65, w: 0.5, h: 0.5, fontSize: 18, bold: true, color: C.background1, align: "center", valign: "middle" });
  txt(s, h, { x: x + 0.15, y: 2.3, w: 1.8, h: 0.35, fontSize: 18, bold: true });
  txt(s, d, { x: x + 0.15, y: 2.7, w: 1.8, h: 0.8, fontSize: 14 });
});
txt(s, "Each step lives in a different tool, so students drop off before funding, exactly when a lender needs them. Trust is built early or not at all.", { x: 0.5, y: 4.0, w: 9, h: 0.8, fontSize: 16 });

// 3. Solution funnel
s = pres.addSlide({ masterName: "CONTENT" });
title(s, "One product for the whole funnel");
const funnel = [["Awareness", "SEO guides written by a content agent"], ["Engagement", "Navigator, admit odds, ROI, timeline, mentor"], ["Trust", "Sourced answers, SOP and visa coaching, privacy controls"], ["Conversion", "Loan planner, document copilot, lender tracker"]];
funnel.forEach(([h, d], i) => {
  const w = 9 - i * 1.1;
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 0.5 + (9 - w) / 2, y: 1.3 + i * 0.95, w, h: 0.8, rectRadius: 0.08, fill: { color: [C.accent1, C.accent5, C.text2, C.accent2][i] }, line: { color: C.background1 }, objectName: "Funnel band" });
  txt(s, [{ text: h + "  ", options: { bold: true } }, { text: d }], { x: 0.5 + (9 - w) / 2 + 0.2, y: 1.3 + i * 0.95, w: w - 0.4, h: 0.8, fontSize: 15, color: C.background1, valign: "middle" });
});
txt(s, "One profile from a 2-minute quiz feeds every module, so each step makes the next one easier.", { x: 0.5, y: 4.95, w: 8.5, h: 0.3, fontSize: 13, color: "64748B" });

// 4. Product tour
s = pres.addSlide({ masterName: "CONTENT" });
title(s, "What students get");
const mods = [["🧭", "Career Navigator", "Ambitious, Target, Safe matches with cost and payback"], ["🎯", "Admit odds + ROI", "What-if sliders, cost vs salary, India vs abroad"], ["🗓️", "Timeline", "Dated plan from intake, deadlines, visa and loan"], ["✍️", "SOP reviewer", "Rubric score, fixes, honest rewrite"], ["🛂", "Visa interview", "AI officer, spoken answers, readiness score"], ["🧑‍🏫", "Mentor", "RAG with citations and live tools"], ["💰", "Loan planner", "Soft check, offers, EMI, moratorium, 80E"], ["📄", "Loan copilot", "Reads documents, fills forms, tracks status"]];
mods.forEach(([ic, h, d], i) => {
  const x = 0.5 + (i % 4) * 2.3, y = 1.3 + Math.floor(i / 4) * 1.95;
  card(s, x, y, 2.1, 1.75);
  txt(s, ic, { x: x + 0.15, y: y + 0.1, w: 0.6, h: 0.5, fontSize: 24 });
  txt(s, h, { x: x + 0.15, y: y + 0.6, w: 1.85, h: 0.3, fontSize: 14, bold: true });
  txt(s, d, { x: x + 0.15, y: y + 0.92, w: 1.85, h: 0.75, fontSize: 12 });
});

// 5. AI depth
s = pres.addSlide({ masterName: "CONTENT" });
title(s, "Rules decide money; the LLM explains");
const cols = [["Rules", C.accent3, ["Loan eligibility, FOIR, offers", "EMI, APR, Section 80E", "ROI and timeline dates", "Unit-tested, auditable"]], ["Machine learning", C.accent1, ["Admit model: monotonic gradient boosting, AUC 0.83 on unseen programs", "Lead score: AUC 0.80, shows why", "Trained on synthetic data, labelled as such"]], ["LLM", C.accent2, ["Gemini first, Groq as fallback", "Explains, converses, reviews, extracts", "Reads PAN and income documents (vision)", "Writes content from reviewed sources", "Free tiers, cached, always a non-AI fallback"]]];
cols.forEach(([h, col, items], i) => {
  const x = 0.5 + i * 3.05;
  card(s, x, 1.3, 2.85, 3.5);
  s.addShape(pres.shapes.OVAL, { x: x + 0.2, y: 1.5, w: 0.35, h: 0.35, fill: { color: col }, line: { color: col }, objectName: "Marker" });
  txt(s, h, { x: x + 0.7, y: 1.5, w: 2.0, h: 0.4, fontSize: 15, bold: true, valign: "middle" });
  txt(s, items.map((t, j) => ({ text: t, options: { bullet: true, breakLine: j < items.length - 1, paraSpaceAfter: 6 } })), { x: x + 0.2, y: 2.1, w: 2.5, h: 2.6, fontSize: 13 });
});
s.addNotes("This split is deliberate: a model never computes money or decides eligibility. That is what makes the loan side defensible to an NBFC.");

// 6. NBFC-aware
s = pres.addSlide({ masterName: "CONTENT" });
title(s, "Built like an NBFC would underwrite it");
const left = ["Co-applicant mandatory; income counted in FOIR", "Secured vs unsecured limits, collateral cover", "Approved-university tiers and country rules", "Moratorium with simple interest, capitalised", "Transparent APR including processing fee", "Section 80E tax view (old regime)"];
txt(s, left.map((t, i) => ({ text: t, options: { bullet: true, breakLine: i < left.length - 1, paraSpaceAfter: 8 } })), { x: 0.5, y: 1.3, w: 4.4, h: 3.6, fontSize: 15 });
card(s, 5.2, 1.3, 4.3, 3.6);
txt(s, "Copilot flow", { x: 5.4, y: 1.45, w: 3.9, h: 0.3, fontSize: 16, bold: true });
["Soft check: no credit-score impact", "Upload PAN, Aadhaar, income proof: vision reads them", "Cross-checks: PAN format, name, income vs slip", "Three consents: KYC, bureau, DPDP", "Mock bureau and lender system: live tracker", "Final approval shown as human credit review"].forEach((t, i) => {
  s.addShape(pres.shapes.OVAL, { x: 5.4, y: 1.95 + i * 0.47, w: 0.3, h: 0.3, fill: { color: C.accent1 }, line: { color: C.accent1 }, objectName: "Flow dot" });
  txt(s, String(i + 1), { x: 5.4, y: 1.95 + i * 0.47, w: 0.3, h: 0.3, fontSize: 11, bold: true, color: C.background1, align: "center", valign: "middle" });
  txt(s, t, { x: 5.85, y: 1.92 + i * 0.47, w: 3.5, h: 0.4, fontSize: 12.5, valign: "middle" });
});

// 7. Stickiness
s = pres.addSlide({ masterName: "CONTENT" });
title(s, "Stickiness without gimmicks");
[["Next best action", "Up to 3 nudges ranked by funnel value; loan steps first"], ["XP, levels, streaks", "7 levels, daily streak, 15 badges earned from real actions"], ["Invites", "+50 XP for the friend, +100 for you when they finish the quiz"], ["Share card", "Opt-in public study card with a link preview for WhatsApp and LinkedIn"], ["Journey stage", "Explorer to Funding, derived from behaviour, never set by hand"], ["Discover feed", "Guides ranked by interests, stage and freshness, with the reason shown"]].forEach(([h, d], i) => {
  const x = 0.5 + (i % 3) * 3.05, y = 1.3 + Math.floor(i / 3) * 1.85;
  card(s, x, y, 2.85, 1.65);
  txt(s, h, { x: x + 0.2, y: y + 0.15, w: 2.5, h: 0.35, fontSize: 16, bold: true });
  txt(s, d, { x: x + 0.2, y: y + 0.6, w: 2.5, h: 0.95, fontSize: 13 });
});

// 8. Growth loop
s = pres.addSlide({ masterName: "DARK" });
txt(s, "A zero-human growth loop", { x: 0.5, y: 0.35, w: 9, h: 0.7, fontSize: 28, bold: true, fontFace: THEME.headFontFace, color: C.background1 });
const loop = [["Simulate", "synthetic cohort acts"], ["Learn", "A/B results, hot topics"], ["Acquire", "content agent publishes"], ["Nurture", "A/B nudges, mock WhatsApp/email"], ["Convert", "lead score triggers loan copilot"], ["Measure", "funnel snapshot, run log"]];
loop.forEach(([h, d], i) => {
  const x = 0.5 + (i % 3) * 3.05, y = 1.4 + Math.floor(i / 3) * 1.5;
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w: 2.85, h: 1.25, rectRadius: 0.08, fill: { color: C.text2 }, line: { color: C.accent5 }, objectName: "Loop step" });
  txt(s, `${i + 1}  ${h}`, { x: x + 0.2, y: y + 0.15, w: 2.5, h: 0.4, fontSize: 18, bold: true, color: C.background1 });
  txt(s, d, { x: x + 0.2, y: y + 0.6, w: 2.5, h: 0.55, fontSize: 14, color: "C7D2FE" });
});
txt(s, "Runs daily on a schedule. Every decision is logged and visible in the admin Agent Console.", { x: 0.5, y: 4.55, w: 9, h: 0.5, fontSize: 15, color: "C7D2FE" });

// 9. Results on the simulated cohort
s = pres.addSlide({ masterName: "CONTENT" });
title(s, "Does the loop learn? A simulated test");
s.addChart(pres.charts.BAR, [{ name: "Click-through", labels: ["Copy A (control)", "Copy B (benefit-led)"], values: [12.1, 18.0] }], {
  x: 0.5, y: 1.3, w: 4.6, h: 3.4, barDir: "col", chartColors: ["4F46E5"], showTitle: true, title: "Nudge click-through, %", titleFontSize: 14, titleColor: "1B1F3B",
  showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: "0.0", dataLabelColor: "1B1F3B", dataLabelFontSize: 12, showLegend: false,
  catAxisLabelColor: "1B1F3B", catAxisLabelFontSize: 12, valAxisLabelColor: "64748B", valAxisLabelFontSize: 11, valGridLine: { color: "E2E8F0", size: 0.5 }, catGridLine: { style: "none" }, valAxisMaxVal: 25,
});
txt(s, "300 simulated students, 30 days", { x: 5.4, y: 1.3, w: 4.1, h: 0.35, fontSize: 16, bold: true });
txt(s, [
  { text: "We planted a 40% lift for copy B in the simulator.", options: { bullet: true, breakLine: true, paraSpaceAfter: 8 } },
  { text: "The A/B step recovered +48% (z = 2.5, significant at 95%) and now serves B to about 80% of students.", options: { bullet: true, breakLine: true, paraSpaceAfter: 8 } },
  { text: "Lead scores flagged the students most likely to apply; the top decile converts about 5x the average.", options: { bullet: true, breakLine: true, paraSpaceAfter: 8 } },
  { text: "Simulated data validates the machinery, not real-world performance. Real testers come next.", options: { bullet: true, italic: true } },
], { x: 5.4, y: 1.8, w: 4.1, h: 3.0, fontSize: 14 });

// 10. Architecture
s = pres.addSlide({ masterName: "CONTENT" });
title(s, "Architecture and deployment");
const layers = [["Vercel", "Next.js 15, TypeScript, Tailwind, Recharts", C.accent1], ["Render (Docker, single instance)", "FastAPI, SQLModel, Alembic, APScheduler, scikit-learn models", C.accent5], ["Supabase", "Postgres with RLS on every table, Auth, private Storage", C.accent3], ["LLMs, free tiers", "Gemini then Groq, per-user and global caps, cached, always a fallback", C.accent2]];
layers.forEach(([h, d, col], i) => {
  const y = 1.3 + i * 0.95;
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 0.5, y, w: 9, h: 0.8, rectRadius: 0.08, fill: { color: C.background2 }, line: { color: C.background2 }, objectName: "Layer" });
  s.addShape(pres.shapes.OVAL, { x: 0.7, y: y + 0.22, w: 0.36, h: 0.36, fill: { color: col }, line: { color: col }, objectName: "Layer marker" });
  txt(s, h, { x: 1.3, y, w: 3.0, h: 0.8, fontSize: 15, bold: true, valign: "middle" });
  txt(s, d, { x: 4.3, y, w: 5.0, h: 0.8, fontSize: 13, valign: "middle" });
});
txt(s, "Push to GitHub deploys both sides; migrations run on start. 127 automated tests.", { x: 0.5, y: 5.0, w: 8, h: 0.3, fontSize: 12, color: "64748B" });

// 11. Trust and safety
s = pres.addSlide({ masterName: "CONTENT" });
title(s, "Trust and safety by design");
const safe = [["Simulated finance, labelled", "Every lender, score and decision is fictional and says so on every page."], ["Privacy and DPDP", "Three consents, Aadhaar last 4 only, files private with 5-minute links and 30-day deletion."], ["Data rights", "Download everything or delete the account and all data in one click."], ["Isolation", "Every query is scoped to the verified user; three-account tests check every by-id route."], ["Abuse control", "Rate limits, per-user and global AI caps, and an admin pause switch."], ["Honest AI", "Sources cited, quotes verified, rewrites may not invent facts, non-AI fallbacks."]];
safe.forEach(([h, d], i) => {
  const x = 0.5 + (i % 2) * 4.6, y = 1.25 + Math.floor(i / 2) * 1.2;
  card(s, x, y, 4.4, 1.05);
  txt(s, h, { x: x + 0.2, y: y + 0.1, w: 4.0, h: 0.3, fontSize: 14.5, bold: true });
  txt(s, d, { x: x + 0.2, y: y + 0.42, w: 4.0, h: 0.6, fontSize: 12 });
});

// 12. Business
s = pres.addSlide({ masterName: "CONTENT" });
title(s, "How it earns, and why lenders care");
const biz = [["Qualified loan leads", "Lenders pay per sanctioned lead or DSA commission; students arrive pre-checked, documented and consented."], ["Lower acquisition cost", "SEO guides and referrals bring students in; the loop nurtures them with no sales team."], ["Cross-sell", "Forex, insurance, accommodation, SIM and travel at the point of need."], ["Premium", "Human counselling and priority SOP review for students who want it."]];
biz.forEach(([h, d], i) => {
  const y = 1.3 + i * 0.9;
  s.addShape(pres.shapes.OVAL, { x: 0.5, y: y + 0.12, w: 0.5, h: 0.5, fill: { color: [C.accent1, C.accent3, C.accent2, C.accent5][i] }, line: { color: C.background1 }, objectName: "Revenue marker" });
  txt(s, String(i + 1), { x: 0.5, y: y + 0.12, w: 0.5, h: 0.5, fontSize: 16, bold: true, color: C.background1, align: "center", valign: "middle" });
  txt(s, h, { x: 1.2, y, w: 2.6, h: 0.75, fontSize: 15, bold: true, valign: "middle" });
  txt(s, d, { x: 3.9, y, w: 5.6, h: 0.75, fontSize: 13.5, valign: "middle" });
});
txt(s, "Unit economics to be validated with real conversions; none are claimed here.", { x: 0.5, y: 4.95, w: 9, h: 0.3, fontSize: 12, color: "64748B" });

// 13. Next + close
s = pres.addSlide({ masterName: "DARK" });
txt(s, "Next steps", { x: 0.7, y: 0.6, w: 8, h: 0.7, fontSize: 36, bold: true, fontFace: THEME.headFontFace, color: C.background1 });
txt(s, ["Pilot with an NBFC sandbox: real lender products, bureau and LOS", "Retrain admit and lead models on real outcomes", "WhatsApp Business API and email through approved providers", "Regional-language support and counsellor handoff"].map((t, i, a) => ({ text: t, options: { bullet: true, breakLine: i < a.length - 1, paraSpaceAfter: 10 } })), { x: 0.7, y: 1.6, w: 8.4, h: 2.2, fontSize: 18, color: "E0E7FF" });
txt(s, "Try it: student-engagement-ecosystem.vercel.app", { x: 0.7, y: 4.4, w: 8.4, h: 0.5, fontSize: 20, bold: true, color: C.accent2 });

(async () => {
  await pres.writeFile({ fileName: OUT });
  if (SKILL) await require(path.join(SKILL, "scripts", "apply_theme.js")).applyTheme(OUT, THEME);
  console.log("wrote", OUT);
})();
