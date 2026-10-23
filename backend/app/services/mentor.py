"""AI Mentor: RAG over the knowledge base + tools that wrap the same services the REST routers use.

The LLM decides when to search the guides (`search_knowledge`) and when to look up programs
(`find_programs`, which reuses navigator.make_match, so chances/costs match the Navigator screen).
Facts must be cited as [S1], [S2]...; we return only the sources the answer actually cites.
If the LLM is unavailable, the reply is built from the top search results instead.
"""

import json
import re
from dataclasses import dataclass, field
from datetime import date

from sqlmodel import Session, col, select

from app import llm
from app.catalog import get_catalog
from app.db.models import ChatMessage, StudentProfile, User
from app.rag.kb import Chunk, get_kb
from app.rules.roi import RoiAssumptions
from app.services import programs, timeline
from app.services.navigator import MONTHS, _profile_brief, build_matches, make_matches

HISTORY_TURNS = 10  # past messages sent to the model as memory
MAX_PROGRAMS = 6
FULLWIDTH_CITE_RE = re.compile(r"【([^】]*)】")  # gpt-oss style: 【S1】 or 【S1†L2】
CITATION_RE = re.compile(r"\s*\[S\d+(?:\s*,\s*S\d+)*\]")

SYSTEM = """You are PathPilot Mentor, a friendly and honest guide for Indian students planning postgraduate study abroad or in India and how to fund it. Today is {today}.

Tools:
- Guide passages relevant to the question are usually attached to it already. Use them first; call search_knowledge only if they don't cover the question.
- search_knowledge: PathPilot's guides on visas, post-study work, tests, SOPs/LORs, application timelines, scholarships, costs, education loans, documents, Section 80E/TCS, and study in India. Write specific keyword queries (e.g. "UK graduate route post-study work"). Search again with different words if results are off-topic.
- find_programs: admit chance, total cost, expected salary and payback for programs in PathPilot's catalogue, filtered by university, country or field. Call it with no arguments for this student's best matches.
- analyze_program: one program in depth (needs a course_id from find_programs): what drives the admit chance, which score improvements help most, "what if" chances with different scores, and ROI (cost, funding gap, indicative EMI, payback, India-vs-abroad comparison).

Rules:
- For any fact about rules, fees, amounts, tests, deadlines, loans or scholarships, call search_knowledge first and cite the result id in square brackets right after the sentence, like [S1]. Only cite ids returned by search_knowledge.
- State only what the search results or tool outputs say; don't add outside figures, limits, dates or lender names. If the guides don't cover something, say so and suggest the official website.
- For chances, costs, salaries or payback, call find_programs (and analyze_program for "what if", ROI or EMI questions) and use their numbers exactly (no citation needed). Admit chances are estimates, not guarantees.
- Never decide loan eligibility, approve loans or quote specific interest rates. Explain how lenders assess loans and point to PathPilot's loan planner; final decisions are made by the lender after a credit review.
- Personalise with the student profile below. Mention a relevant gap (e.g. missing test score) when it matters.
- Keep answers under 170 words: plain text, short paragraphs or lines starting with "- ", no headings, tables, bold or asterisks. Use ₹ lakhs (L) for Indian amounts.
- End with one concrete next step when useful.
- Only help with higher education, careers and study finance. Politely decline anything else.

Student profile (JSON): {profile}
The student's next open tasks from their PathPilot application timeline (JSON; empty if they haven't made one, in which case suggest the Timeline page for planning questions): {next_tasks}"""

WHAT_IF_FIELDS = ("cgpa", "gre", "gmat", "ielts", "toefl", "entrance_percentile", "work_exp_months")
WHAT_IF_RANGES = {"cgpa": (4, 10), "gre": (260, 340), "gmat": (200, 800), "ielts": (4, 9), "toefl": (0, 120),
                  "entrance_percentile": (0, 100), "work_exp_months": (0, 240)}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_knowledge",
            "description": "Search PathPilot's guides. Returns passages with ids like S1 to cite.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Specific keywords, e.g. 'Germany blocked account amount'"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_programs",
            "description": "Look up programs with this student's estimated admit chance, total cost (₹ lakhs), median salary (₹ lakhs/yr) and payback years. No arguments = the student's best matches.",
            "parameters": {
                "type": "object",
                "properties": {
                    "university": {"type": "string", "description": "Part of a university name, e.g. 'Carnegie' or 'Toronto'"},
                    "country": {"type": "string", "description": "One of: USA, UK, Canada, Germany, Australia, Ireland, Netherlands, India"},
                    "field": {"type": "string", "description": "Field key, e.g. computer_science, data_science, mba, finance"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_program",
            "description": "Deep-dive one program for this student: admit-chance factors, best score improvements, what-if chance with "
                           "hypothetical scores, and ROI (₹ lakhs: cost, funding gap, indicative EMI, payback, India-vs-abroad).",
            "parameters": {
                "type": "object",
                "properties": {
                    "course_id": {"type": "integer", "description": "From find_programs"},
                    "what_if": {
                        "type": "object",
                        "description": "Hypothetical scores to test, e.g. {\"gre\": 330}",
                        "properties": {k: {"type": "number"} for k in WHAT_IF_FIELDS},
                    },
                    "scholarship_lakhs": {"type": "number"},
                    "work_in": {"type": "string", "enum": ["abroad", "india"], "description": "Where they work after graduating"},
                },
                "required": ["course_id"],
            },
        },
    },
]


@dataclass
class TurnContext:
    """Per-turn state: numbered search results, so citations can be resolved after the answer."""

    profile: StudentProfile | None
    refs: dict[str, Chunk] = field(default_factory=dict)

    def search(self, query: str, k: int = 4) -> list[dict]:
        out = []
        for chunk, _ in get_kb().search(query, k=k):
            ref = next((r for r, c in self.refs.items() if c.id == chunk.id), None)
            if ref is None:
                ref = f"S{len(self.refs) + 1}"
                self.refs[ref] = chunk
            out.append({"id": ref, "guide": chunk.title, "section": chunk.section, "text": chunk.text})
        return out or [{"note": "No matching guide. Try other keywords or tell the student to check the official website."}]


def _field_key(field: str | None) -> str | None:
    """Accepts a key ("computer_science") or a label ("Computer Science") from the model."""
    if not field:
        return None
    labels = {v.lower(): k for k, v in get_catalog().meta["fields"].items()}
    f = field.strip().lower()
    return labels.get(f, f.replace(" ", "_").replace("-", "_"))


def _catalog_rows(university: str | None, country: str | None, field: str | None) -> list:
    cat = get_catalog()
    rows = []
    for c in cat.courses:
        u = cat.universities[c.university_id]
        if university and university.lower() not in u.name.lower():
            continue
        if country and country.lower() != u.country.lower():
            continue
        if field and field != c.field:
            continue
        rows.append((c, u))
    return rows


def find_programs(p: StudentProfile | None, university: str | None = None, country: str | None = None,
                  field: str | None = None) -> dict:
    if p is None:
        return {"error": "The student hasn't completed the onboarding quiz, so chances can't be estimated yet."}
    field = _field_key(field)
    if not (university or country or field):
        matches = build_matches(p)[:MAX_PROGRAMS]
    else:
        rows = _catalog_rows(university, country, field)
        if not rows and university and field:  # wrong field guess: show what that university offers
            rows = _catalog_rows(university, country, None)
        if university and not field:  # prefer the student's own field at that university
            own = [(c, u) for c, u in rows if c.field == p.target_field or (p.target_level == "mba" and c.level == "mba")]
            rows = own or rows
        matches = make_matches(p, rows)
        matches.sort(key=lambda m: (m.university, -m.chance))
        matches = matches[:MAX_PROGRAMS]
    if not matches:
        return {"programs": [], "note": "Not in PathPilot's catalogue. Say so; don't guess numbers."}
    return {
        "programs": [
            {
                "course_id": m.course_id, "university": m.university, "country": m.country, "program": m.program,
                "admit_chance_pct": round(m.chance * 100), "bucket": m.bucket, "total_cost_lakhs": m.total_cost_lakhs,
                "median_salary_lakhs_per_year": m.salary_lakhs, "payback_years": m.payback_years,
                "funding_gap_lakhs": m.funding_gap_lakhs, "stem": m.stem, "usual_deadline": MONTHS[m.deadline_month - 1],
            }
            for m in matches
        ],
        "note": "Indicative figures from PathPilot's models.",
    }


def analyze_program(p: StudentProfile | None, course_id, what_if: dict | None = None,
                    scholarship_lakhs: float | None = None, work_in: str | None = None) -> dict:
    if p is None:
        return {"error": "The student hasn't completed the onboarding quiz yet."}
    try:
        prog = programs.get_program(int(course_id))
    except (TypeError, ValueError):
        prog = None
    if prog is None:
        return {"error": "Unknown course_id. Call find_programs first to get one."}
    c, u = prog
    overrides = {}
    for k, v in (what_if or {}).items():
        if k in WHAT_IF_RANGES and isinstance(v, (int, float)):
            lo, hi = WHAT_IF_RANGES[k]
            overrides[k] = max(lo, min(hi, v))
    admit = programs.admit_view(p, c, u, overrides)
    a = RoiAssumptions(scholarship_lakhs=max(0.0, float(scholarship_lakhs or 0)),
                       work_in="india" if work_in == "india" else "abroad")
    rois = programs.roi_with_alternative(p, c, u, a)

    def roi_brief(r: dict) -> dict:
        return {"total_cost_lakhs": r["cost"]["total_lakhs"], "funding_gap_lakhs": r["funding"]["gap_lakhs"],
                "indicative_emi_lakhs_per_month": r["loan"]["emi_lakhs"], "emi_pct_of_salary": r["loan"]["emi_pct_of_salary"],
                "starting_salary_lakhs": r["salary"]["start_lakhs"], "works_in": r["salary"]["location"],
                "payback_years": r["outcome"]["payback_years"] or "over 10", "ten_year_net_gain_lakhs": r["outcome"]["ten_year_net_lakhs"]}

    alt = rois["alternative"]
    return {
        "program": f"{c.program}, {u.name} ({u.country})",
        "admit_chance_pct": round(admit["chance"] * 100),
        **({"what_if": overrides, "current_chance_pct": round(admit["baseline_chance"] * 100)} if overrides else {}),
        "factors": [f"{f['factor']}: yours {f['yours']} vs typical admit {f['typical']} ({f['impact_pct']:+d} pts)"
                    for f in admit["factors"][:3]],
        "best_improvements": [f"{lv['label']}: {lv['delta_pct']:+d} pts" for lv in admit["levers"][:3]],
        "roi": roi_brief(rois["roi"]),
        **({"comparison": {"program": f"{alt['program']['program']}, {alt['program']['university']}",
                           "admit_chance_pct": round(alt["chance"] * 100), **roi_brief(alt["roi"])}} if alt else {}),
        "note": "Indicative figures from PathPilot's models; EMI uses an illustrative 11% rate, not a loan offer.",
    }


def normalize_citations(text: str) -> str:
    text = FULLWIDTH_CITE_RE.sub(lambda m: "[" + re.sub(r"†[^,\]]*", "", m.group(1)) + "]", text)
    return text.replace("**", "")


def _cited_sources(text: str, refs: dict[str, Chunk]) -> list[dict]:
    cited = []
    for n in re.findall(r"S(\d+)", " ".join(re.findall(r"\[([^\]]*)\]", text))):
        ref = f"S{n}"
        if ref in refs and ref not in [c["ref"] for c in cited]:
            ch = refs[ref]
            cited.append({"ref": ref, "title": ch.title, "section": ch.section, "url": ch.url})
    return cited


def _fallback_reply(question: str, notice: str) -> tuple[str, list[dict]]:
    hits = get_kb().search(question, k=2)
    if not hits:
        return f"{notice} I couldn't find a guide on that yet; try rephrasing, or check the official website.", []
    parts, sources = [f"{notice} Here's what PathPilot's guides say:"], []
    for i, (ch, _) in enumerate(hits, start=1):
        snippet = ch.text if len(ch.text) <= 420 else ch.text[:420].rsplit(" ", 1)[0] + "…"
        parts.append(f"- {ch.section}: {snippet} [S{i}]")
        sources.append({"ref": f"S{i}", "title": ch.title, "section": ch.section, "url": ch.url})
    return "\n".join(parts), sources


def history(session: Session, user: User, limit: int = 50) -> list[ChatMessage]:
    rows = session.exec(
        select(ChatMessage).where(ChatMessage.user_id == user.id).order_by(col(ChatMessage.id).desc()).limit(limit)
    ).all()
    return list(reversed(rows))


def answer(session: Session, user: User, question: str) -> tuple[ChatMessage, str | None]:
    """Stores the user message and the reply; returns (assistant message, notice)."""
    p = session.get(StudentProfile, user.id)
    past = history(session, user, HISTORY_TURNS)
    session.add(ChatMessage(user_id=user.id, role="user", content=question))
    session.commit()

    ctx = TurnContext(profile=p)

    def run_tool(name: str, args: dict):
        if name == "search_knowledge":
            return ctx.search(str(args.get("query", "")))
        if name == "find_programs":
            return find_programs(p, args.get("university"), args.get("country"), args.get("field"))
        if name == "analyze_program":
            return analyze_program(p, args.get("course_id"), args.get("what_if"), args.get("scholarship_lakhs"),
                                   args.get("work_in"))
        return {"error": f"Unknown tool {name}"}

    system = SYSTEM.format(
        today=date.today().isoformat(),
        profile=json.dumps(_profile_brief(p) if p else {"note": "quiz not completed"}, ensure_ascii=False, default=str),
        next_tasks=json.dumps([{"task": t.title, "due": t.due_date.isoformat()} for t in timeline.upcoming(session, user, 3)],
                              ensure_ascii=False),
    )
    # Old citation ids belong to old turns' search results; drop them so the model doesn't reuse them
    messages = [{"role": m.role, "content": CITATION_RE.sub("", m.content)} for m in past]
    # Pre-retrieve guide passages so most answers need a single LLM request (free tiers limit requests/min)
    passages = ctx.search(question, k=3)
    attached = json.dumps(passages, ensure_ascii=False)
    messages.append({"role": "user", "content": f"{question}\n\n<guide_passages>\n{attached}\n</guide_passages>"})
    notice = None
    try:
        result = llm.chat(session, user, feature="mentor", system=system, messages=messages, tools=TOOLS,
                          run_tool=run_tool, tier="smart")
        text = normalize_citations(result.text)
        reply = ChatMessage(user_id=user.id, role="assistant", content=text, sources=_cited_sources(text, ctx.refs),
                            tools=list(dict.fromkeys(t["name"] for t in result.tool_calls)), ai=True)
    except llm.LLMUnavailable as e:
        notice = e.user_message
        text, sources = _fallback_reply(question, e.user_message)
        reply = ChatMessage(user_id=user.id, role="assistant", content=text, sources=sources, tools=[], ai=False)
    session.add(reply)
    session.commit()
    session.refresh(reply)
    return reply, notice


def suggestions(p: StudentProfile | None) -> list[str]:
    if p is None:
        return ["What should I do first if I want to study abroad?", "How do education loans work?",
                "Which tests do I need for a master's abroad?"]
    country = (p.target_countries or ["USA"])[0]
    out = []
    matches = build_matches(p)
    if matches:
        out.append(f"What are my chances at {matches[0].university}?")
    out.append(f"Explain the {country} student visa process" if country != "India" else "How do IIM / IIT admissions work?")
    out.append("How much loan might I need, and do I need collateral?")
    out.append(f"Make a month-by-month plan for {p.target_intake}" if p.target_intake else "What's a good application timeline?")
    return out
