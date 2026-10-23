"""Deterministic SOP checks: run on every review and are the whole review when the LLM is unavailable."""

import re
from dataclasses import asdict, dataclass

CLICHES = [
    "since my childhood", "since childhood", "from a young age", "ever since i was", "i have always been passionate",
    "i have always been fascinated", "passionate about", "burning desire", "dream come true", "in today's world",
    "in this fast-paced world", "in the modern era", "technology is changing the world", "hard-working", "hardworking",
    "quick learner", "team player", "esteemed university", "prestigious university", "world-class faculty",
    "renowned faculty", "state-of-the-art", "i want to make a difference", "give back to society", "last but not least",
    "it is my firm belief", "i would like to take this opportunity", "thirst for knowledge", "a perfect fit",
]
CAREER_WORDS = ["career", "goal", "aim", "aspire", "plan", "long-term", "short-term", "after graduation", "role", "become"]
WORDS = re.compile(r"[A-Za-z0-9][A-Za-z0-9'’\-]*")


@dataclass
class Check:
    key: str
    label: str
    ok: bool
    detail: str


def analyze(text: str, university: str | None = None) -> dict:
    words = WORDS.findall(text)
    n = len(words)
    paragraphs = [p for p in re.split(r"\n\s*\n|\r\n\s*\r\n", text.strip()) if p.strip()]
    if len(paragraphs) == 1:  # pasted with single newlines
        paragraphs = [p for p in text.strip().splitlines() if p.strip()]
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if WORDS.search(s)]
    avg_sentence = n / max(1, len(sentences))
    lower = text.lower()
    cliches = [c for c in CLICHES if c in lower]
    evidence = len(re.findall(r"\b\d+(?:\.\d+)?\s*(?:%|percent|x|k|lakh|users|students|papers?|projects?|months?|years?)?", text))
    i_starts = sum(1 for s in sentences if re.match(r"^\W*I\b", s.strip()))
    i_ratio = i_starts / max(1, len(sentences))
    uni_words = [w for w in re.findall(r"[A-Za-z]{4,}", university or "") if w.lower() not in {"university", "institute", "technology", "college", "school"}]
    names_school = bool(university) and (university.lower() in lower or any(w.lower() in lower for w in uni_words))
    mentions_goal = any(w in lower for w in CAREER_WORDS)

    checks = [
        Check("length", "Length", 600 <= n <= 1100,
              f"{n} words. Most programs expect 800–1,000 (always follow each program's own limit)."
              if not 600 <= n <= 1100 else f"{n} words: a good length for most programs."),
        Check("structure", "Paragraphs", 4 <= len(paragraphs) <= 8,
              f"{len(paragraphs)} paragraph(s). Aim for 5–7: hook, background, experience, why this program, goals."),
        Check("sentences", "Sentence length", 12 <= avg_sentence <= 26,
              f"Average sentence is {avg_sentence:.0f} words" + (" — split long sentences." if avg_sentence > 26 else
                                                                   " — combine some short ones." if avg_sentence < 12 else ".")),
        Check("cliches", "Clichés", not cliches,
              "None found." if not cliches else "Replace with specifics: " + ", ".join(f'"{c}"' for c in cliches[:5])),
        Check("evidence", "Evidence & numbers", evidence >= 3,
              f"{evidence} concrete figures: good." if evidence >= 3 else
              f"{evidence} concrete figure(s). Add results: scores, rankings, users, % improvements, durations."),
        Check("i_start", "Sentence openings", i_ratio <= 0.35,
              f"{round(i_ratio * 100)}% of sentences start with \"I\"" + (" — vary your openings." if i_ratio > 0.35 else ".")),
        Check("goals", "Career goals", mentions_goal, "States career goals." if mentions_goal else "Say what role you want after the degree and why."),
    ]
    if university:
        checks.append(Check("program_fit", "Program-specific", names_school,
                            f"Mentions {university}." if names_school else
                            f"Doesn't mention {university}. Name courses, labs or faculty that fit your goals."))
    score = round(100 * sum(c.ok for c in checks) / len(checks))
    return {"word_count": n, "paragraphs": len(paragraphs), "avg_sentence_words": round(avg_sentence, 1),
            "cliches": cliches, "checks": [asdict(c) for c in checks], "rule_score": score}
