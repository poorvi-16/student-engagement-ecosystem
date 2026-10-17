"""Read-only reference data (universities, courses, loan products) loaded once from backend/data.

Static and identical for every user, so it lives in memory rather than in Postgres.
Regenerate the CSVs with `python data/generate_catalog.py`.
"""

import csv
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _num(v: str) -> float | None:
    return float(v) if v not in ("", None) else None


@dataclass(frozen=True)
class University:
    id: int
    name: str
    country: str
    city: str
    tier: int
    qs_rank: int | None
    currency: str


@dataclass(frozen=True)
class Course:
    id: int
    university_id: int
    program: str
    field: str
    level: str
    duration_months: int
    tuition_total_local: float
    living_total_local: float
    acceptance_rate: float
    avg_gre: float | None
    avg_gmat: float | None
    avg_cgpa: float
    min_ielts: float | None
    entrance_exam: str | None
    avg_entrance_percentile: float | None
    min_work_exp_months: int
    median_salary_local: float
    stem: bool
    deadline_month: int


@dataclass(frozen=True)
class Catalog:
    universities: dict[int, University]
    courses: list[Course]
    meta: dict
    loan_products: dict

    def fx(self, currency: str) -> float:
        return self.meta["fx_inr"][currency]

    def to_inr(self, amount_local: float, currency: str) -> float:
        return amount_local * self.fx(currency)


@lru_cache
def get_catalog() -> Catalog:
    with open(DATA_DIR / "universities.csv", encoding="utf-8") as f:
        unis = {
            int(r["id"]): University(
                id=int(r["id"]), name=r["name"], country=r["country"], city=r["city"], tier=int(r["tier"]),
                qs_rank=int(r["qs_rank"]) if r["qs_rank"] else None, currency=r["currency"],
            )
            for r in csv.DictReader(f)
        }
    with open(DATA_DIR / "courses.csv", encoding="utf-8") as f:
        courses = [
            Course(
                id=int(r["id"]), university_id=int(r["university_id"]), program=r["program"], field=r["field"],
                level=r["level"], duration_months=int(r["duration_months"]),
                tuition_total_local=float(r["tuition_total_local"]), living_total_local=float(r["living_total_local"]),
                acceptance_rate=float(r["acceptance_rate"]), avg_gre=_num(r["avg_gre"]), avg_gmat=_num(r["avg_gmat"]),
                avg_cgpa=float(r["avg_cgpa"]), min_ielts=_num(r["min_ielts"]), entrance_exam=r["entrance_exam"] or None,
                avg_entrance_percentile=_num(r["avg_entrance_percentile"]),
                min_work_exp_months=int(r["min_work_exp_months"]), median_salary_local=float(r["median_salary_local"]),
                stem=r["stem"] == "True", deadline_month=int(r["deadline_month"]),
            )
            for r in csv.DictReader(f)
        ]
    meta = json.loads((DATA_DIR / "catalog_meta.json").read_text(encoding="utf-8"))
    loans = json.loads((DATA_DIR / "loan_products.json").read_text(encoding="utf-8"))
    return Catalog(universities=unis, courses=courses, meta=meta, loan_products=loans)
