"""Knowledge base for the mentor: curated Markdown guides in backend/data/kb, searched with BM25.

The KB is static reference data (like the catalog), so it is chunked by `## ` section and indexed in
memory at first use: free, no embeddings provider, identical in tests. The mentor's LLM writes the
search queries itself (tool call), which compensates for keyword search not knowing synonyms.

Each guide starts with a front-matter block: title, sources (" | "-separated URLs), reviewed (YYYY-MM).
"""

import math
import re
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

KB_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "kb"

STOPWORDS = set(
    "a an and are as at be by can do does for from has have how i if in into is it its me my of on or our so "
    "than that the their them then there these they this to was we what when where which who why will with "
    "you your about should would could after before also any each more most much not only per some such".split()
)
# Map common variants onto one token so "US", "America" and "USA" match each other
ALIASES = {
    "us": "usa", "america": "usa", "american": "usa", "states": "usa",
    "britain": "uk", "england": "uk", "british": "uk",
    "canadian": "canada", "german": "germany", "australian": "australia", "irish": "ireland",
    "dutch": "netherlands", "holland": "netherlands",
    "visas": "visa", "fees": "fee", "loans": "loan", "costs": "cost", "scholarship": "scholarships",
    "pgwp": "pgwp", "opt": "opt", "emi": "emi", "ielts": "ielts", "toefl": "toefl",
    "mba": "mba", "ms": "masters", "master": "masters", "msc": "masters",
}


def tokenize(text: str) -> list[str]:
    out = []
    for t in re.findall(r"[a-z0-9]+", text.lower()):
        t = ALIASES.get(t, t)
        if t in STOPWORDS:
            continue
        if len(t) > 4 and t.endswith("s") and not t.endswith("ss"):
            t = t[:-1]
        out.append(t)
    return out


@dataclass(frozen=True)
class Chunk:
    id: str  # "<slug>#<n>"
    slug: str
    title: str
    section: str
    text: str
    url: str  # first source URL
    reviewed: str
    urls: tuple[str, ...] = ()  # every source URL of the guide


def _parse_doc(path: Path) -> list[Chunk]:
    raw = path.read_text(encoding="utf-8")
    meta: dict[str, str] = {}
    m = re.match(r"^---\n(.*?)\n---\n", raw, re.S)
    if m:
        for line in m.group(1).splitlines():
            k, _, v = line.partition(":")
            meta[k.strip()] = v.strip()
        raw = raw[m.end():]
    title = meta.get("title", path.stem)
    urls = tuple(u.strip() for u in meta.get("sources", "").split("|") if u.strip())
    url = urls[0] if urls else ""
    chunks = []
    for n, part in enumerate(re.split(r"^## ", raw, flags=re.M)[1:]):
        section, _, body = part.partition("\n")
        chunks.append(Chunk(f"{path.stem}#{n}", path.stem, title, section.strip(), body.strip(), url, meta.get("reviewed", ""), urls))
    return chunks


class KnowledgeBase:
    K1, B = 1.5, 0.75

    def __init__(self, chunks: list[Chunk]):
        self.chunks = chunks
        # Title and section heading count twice: they summarise the chunk
        self.docs = [Counter(tokenize(f"{c.title} {c.section} " * 2 + c.text)) for c in chunks]
        self.lengths = [sum(d.values()) for d in self.docs]
        self.avg_len = sum(self.lengths) / max(1, len(self.lengths))
        df = Counter(t for d in self.docs for t in d)
        n = len(chunks)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def search(self, query: str, k: int = 4) -> list[tuple[Chunk, float]]:
        terms = set(tokenize(query))
        scored = []
        for chunk, doc, length in zip(self.chunks, self.docs, self.lengths):
            score = 0.0
            for t in terms:
                f = doc.get(t)
                if f:
                    score += self.idf[t] * f * (self.K1 + 1) / (f + self.K1 * (1 - self.B + self.B * length / self.avg_len))
            if score > 0:
                scored.append((chunk, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:k]


@lru_cache
def get_kb() -> KnowledgeBase:
    chunks = [c for p in sorted(KB_DIR.glob("*.md")) for c in _parse_doc(p)]
    return KnowledgeBase(chunks)
