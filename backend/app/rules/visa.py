"""Visa mock interview: per-country question banks and a rule-based answer check (the no-LLM fallback)."""

import re
from dataclasses import dataclass

COUNTRIES = {
    "USA": "US F-1 student visa interview",
    "UK": "UK Student visa credibility interview",
    "Canada": "Canada study permit (SDS) officer questions",
    "Germany": "German national student visa interview",
    "Australia": "Australian Student visa (Genuine Student) interview",
}


@dataclass(frozen=True)
class Question:
    id: str
    text: str
    looks_for: str  # what the officer is checking; shown after answering and given to the LLM
    keywords: tuple[str, ...]  # fallback: answer should touch at least one


COMMON_FUNDING = Question(
    "funding", "How will you fund your studies? Who is sponsoring you, and how much will the whole course cost?",
    "A clear total cost, who pays what (savings, sponsor, education loan) and documents to prove it.",
    ("loan", "sanction", "sponsor", "father", "mother", "parents", "savings", "lakh", "scholarship", "fund"),
)
SPONSOR = Question(
    "sponsor", "What do your sponsors do, and what is their annual income?",
    "Sponsor occupation and income that plausibly support the costs and any loan EMIs.",
    ("income", "salary", "business", "lakh", "per annum", "works", "job", "farmer", "engineer", "doctor"),
)
RETURN = Question(
    "after", "What are your plans after you graduate?",
    "A specific career plan and genuine reasons to return (or to follow the legal post-study route), not vague intent to settle.",
    ("return", "india", "career", "role", "company", "job", "work", "plan", "engineer", "analyst"),
)

BANKS: dict[str, list[Question]] = {
    "USA": [
        Question("why_country", "Why do you want to study in the United States?",
                 "Specific academic reasons tied to your field, not generic praise.", ("course", "research", "curriculum", "program", "specialis", "industry")),
        Question("why_uni", "Why did you choose this university? Which other universities did you apply to?",
                 "Real knowledge of the program (courses, labs, faculty) and an honest list of other admits/rejects.",
                 ("course", "professor", "lab", "faculty", "curriculum", "admit", "applied", "research")),
        Question("background", "What will you study, and how does it connect to what you've done so far?",
                 "A logical link between degree, experience and the chosen program.", ("degree", "b.tech", "bachelor", "project", "internship", "experience", "worked")),
        COMMON_FUNDING, SPONSOR, RETURN,
    ],
    "UK": [
        Question("why_course", "Why have you chosen this course and this university?",
                 "Course modules and why they fit your background and goals.", ("module", "course", "curriculum", "university", "research", "ranking")),
        Question("why_uk", "Why study in the UK rather than in India?",
                 "Concrete advantages (course structure, duration, specialisation) without disparaging India.", ("one year", "duration", "specialis", "course", "industry", "exposure")),
        Question("background", "Tell me about your education and any work experience.",
                 "A clear, consistent academic history and any gaps explained.", ("degree", "graduated", "cgpa", "worked", "internship", "college")),
        COMMON_FUNDING,
        Question("accommodation", "Where will you live, and what will your monthly living costs be?",
                 "Awareness of accommodation and realistic living costs (London vs outside London).", ("accommodation", "hall", "rent", "pounds", "£", "month", "living")),
        RETURN,
    ],
    "Canada": [
        Question("why_canada", "Why did you choose Canada and this institution?",
                 "Program-specific reasons and awareness of the institution, not just immigration.", ("program", "college", "university", "course", "co-op", "industry")),
        Question("background", "How does this program relate to your previous studies or work?",
                 "A logical progression; a study plan that makes sense.", ("degree", "bachelor", "project", "experience", "worked", "field")),
        COMMON_FUNDING,
        Question("gic", "Have you purchased a GIC and paid your first-year tuition?",
                 "GIC purchased and tuition paid (SDS requirement) with receipts.", ("gic", "paid", "tuition", "receipt", "deposit")),
        SPONSOR, RETURN,
    ],
    "Germany": [
        Question("why_germany", "Why do you want to study in Germany?",
                 "Academic reasons: program quality, research, industry links; not just low tuition.", ("research", "program", "industry", "engineering", "university", "quality")),
        Question("why_uni", "Why this university and this program? What modules interest you?",
                 "Knowledge of specific modules or research groups.", ("module", "course", "research", "professor", "lab", "curriculum")),
        Question("blocked", "How will you finance your stay? Have you opened a blocked account?",
                 "Blocked account with the required yearly amount, plus how tuition/semester fees are paid.", ("blocked", "account", "euro", "€", "11", "sponsor", "loan")),
        Question("language", "Do you speak any German? How will you manage daily life?",
                 "Honest level and a plan to learn (courses, A1/A2).", ("german", "a1", "a2", "learning", "course", "language")),
        Question("background", "Tell me about your academic background.", "Consistent history matching the program.",
                 ("degree", "bachelor", "cgpa", "college", "project")),
        RETURN,
    ],
    "Australia": [
        Question("why_australia", "Why did you choose to study in Australia?",
                 "Genuine academic reasons for Australia over India and other countries.", ("course", "university", "research", "industry", "program", "quality")),
        Question("why_course", "Why this course, and how will it help your career?",
                 "A clear link between course and career plan.", ("career", "course", "skills", "role", "industry", "job")),
        Question("circumstances", "Tell me about your current situation: studies, work and family in India.",
                 "Ties to India and a coherent personal situation (Genuine Student requirement).", ("family", "parents", "work", "job", "studied", "india")),
        COMMON_FUNDING, SPONSOR, RETURN,
    ],
}

MIN_WORDS = 12


def questions(country: str) -> list[Question]:
    return BANKS.get(country, BANKS["USA"])


def find_question(country: str, qid: str) -> Question | None:
    return next((q for q in questions(country) if q.id == qid), None)


def rule_evaluate(q: Question | None, answer: str, program: str | None = None) -> dict:
    """Basic feedback without the LLM: length, relevant keywords, specifics (numbers/names)."""
    words = re.findall(r"\w+", answer)
    lower = answer.lower()
    hits = [k for k in (q.keywords if q else ()) if k in lower]
    has_specifics = bool(re.search(r"\d", answer)) or (program is not None and any(
        w.lower() in lower for w in re.findall(r"[A-Za-z]{5,}", program)))
    rating = 1 + (len(words) >= MIN_WORDS) + (len(words) >= 25) + bool(hits) + has_specifics
    if len(words) > 120:
        rating -= 1  # officers want concise answers
    rating = max(1, min(5, rating))
    if len(words) < MIN_WORDS:
        feedback = "Too short. Officers expect a clear, complete answer in 2–4 sentences."
    elif not hits:
        feedback = "Doesn't address what the officer is checking. Answer the question directly."
    elif len(words) > 120:
        feedback = "Too long. Keep answers to about 30–60 seconds when spoken."
    else:
        feedback = "Covers the question. Add specifics (names, numbers, dates) to sound confident and prepared."
    return {"rating": rating, "feedback": feedback, "tip": q.looks_for if q else "", "red_flags": [], "follow_up": None}
