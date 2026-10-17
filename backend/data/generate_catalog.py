"""Generates the indicative university/course catalog used by the navigator, admit model and ROI.

Figures are approximate, hand-tuned estimates for a prototype — NOT official data.
Re-run after editing:  python data/generate_catalog.py   (from backend/)
"""

import csv
import json
import random
from pathlib import Path

OUT = Path(__file__).parent
random.seed(42)

# INR per unit of local currency (indicative)
FX = {"USD": 88.0, "GBP": 115.0, "CAD": 64.0, "EUR": 100.0, "AUD": 58.0, "INR": 1.0}

COUNTRIES = {
    # currency, annual living cost (local), typical MS duration (months), MBA duration, deadline month for fall/main intake
    "USA": {"currency": "USD", "living": 20000, "ms_months": 24, "mba_months": 24, "deadline_month": 12},
    "UK": {"currency": "GBP", "living": 15000, "ms_months": 12, "mba_months": 12, "deadline_month": 2},
    "Canada": {"currency": "CAD", "living": 20000, "ms_months": 20, "mba_months": 20, "deadline_month": 1},
    "Germany": {"currency": "EUR", "living": 12000, "ms_months": 24, "mba_months": 18, "deadline_month": 5},
    "Ireland": {"currency": "EUR", "living": 15000, "ms_months": 12, "mba_months": 12, "deadline_month": 3},
    "Australia": {"currency": "AUD", "living": 28000, "ms_months": 24, "mba_months": 24, "deadline_month": 10},
    "Netherlands": {"currency": "EUR", "living": 14000, "ms_months": 18, "mba_months": 12, "deadline_month": 2},
    "India": {"currency": "INR", "living": 150000, "ms_months": 24, "mba_months": 24, "deadline_month": 11},
}

# Median starting salary (local currency) by field
SALARY = {
    "USA": {"computer_science": 120000, "data_science": 110000, "electrical": 100000, "mechanical": 80000, "mba": 140000, "finance": 95000, "business_analytics": 90000, "public_health": 70000, "civil": 70000},
    "UK": {"computer_science": 50000, "data_science": 45000, "electrical": 40000, "mechanical": 35000, "mba": 85000, "finance": 50000, "business_analytics": 40000, "public_health": 35000, "civil": 32000},
    "Canada": {"computer_science": 90000, "data_science": 85000, "electrical": 80000, "mechanical": 70000, "mba": 100000, "finance": 75000, "business_analytics": 72000, "public_health": 60000, "civil": 65000},
    "Germany": {"computer_science": 58000, "data_science": 56000, "electrical": 55000, "mechanical": 52000, "mba": 75000, "finance": 55000, "business_analytics": 52000, "public_health": 45000, "civil": 48000},
    "Ireland": {"computer_science": 55000, "data_science": 52000, "electrical": 48000, "mechanical": 42000, "mba": 80000, "finance": 52000, "business_analytics": 48000, "public_health": 42000, "civil": 40000},
    "Australia": {"computer_science": 95000, "data_science": 90000, "electrical": 85000, "mechanical": 80000, "mba": 120000, "finance": 85000, "business_analytics": 82000, "public_health": 70000, "civil": 75000},
    "Netherlands": {"computer_science": 55000, "data_science": 52000, "electrical": 50000, "mechanical": 47000, "mba": 75000, "finance": 52000, "business_analytics": 48000, "public_health": 42000, "civil": 45000},
    "India": {"computer_science": 2500000, "data_science": 2000000, "electrical": 1800000, "mechanical": 1200000, "mba": 3000000, "finance": 1800000, "business_analytics": 1500000, "public_health": 900000, "civil": 1000000},
}

FIELD_NAMES = {
    "computer_science": "MS Computer Science",
    "data_science": "MS Data Science",
    "electrical": "MS Electrical Engineering",
    "mechanical": "MS Mechanical Engineering",
    "mba": "MBA",
    "finance": "MS Finance",
    "business_analytics": "MS Business Analytics",
    "public_health": "Master of Public Health",
    "civil": "MS Civil Engineering",
}
INDIA_NAMES = {
    "computer_science": "M.Tech Computer Science",
    "data_science": "M.Tech Data Science & AI",
    "electrical": "M.Tech Electrical Engineering",
    "mechanical": "M.Tech Mechanical Engineering",
    "mba": "MBA / PGP",
    "business_analytics": "PG Diploma Business Analytics",
    "finance": "MBA Finance",
}

ENG = ["computer_science", "data_science", "electrical", "mechanical", "civil"]
BIZ = ["mba", "finance", "business_analytics"]

# name, country, city, tier (1 = elite .. 3), approx QS rank, MS tuition per year (local), fields offered
UNIVERSITIES = [
    ("Massachusetts Institute of Technology", "USA", "Cambridge, MA", 1, 1, 62000, ENG + ["mba", "finance", "business_analytics"]),
    ("Stanford University", "USA", "Stanford, CA", 1, 6, 63000, ENG + ["mba", "public_health"]),
    ("Carnegie Mellon University", "USA", "Pittsburgh, PA", 1, 58, 58000, ["computer_science", "data_science", "electrical", "mechanical", "business_analytics", "mba"]),
    ("University of California, Berkeley", "USA", "Berkeley, CA", 1, 10, 45000, ENG + ["mba", "public_health"]),
    ("Georgia Institute of Technology", "USA", "Atlanta, GA", 1, 97, 32000, ENG + ["business_analytics"]),
    ("University of Illinois Urbana-Champaign", "USA", "Champaign, IL", 1, 69, 38000, ENG + ["finance", "business_analytics", "mba"]),
    ("University of Texas at Austin", "USA", "Austin, TX", 1, 66, 36000, ENG + ["mba", "business_analytics"]),
    ("University of Michigan", "USA", "Ann Arbor, MI", 1, 44, 54000, ENG + ["mba", "public_health"]),
    ("Columbia University", "USA", "New York, NY", 1, 34, 66000, ["computer_science", "data_science", "electrical", "mba", "finance", "public_health"]),
    ("Cornell University", "USA", "Ithaca, NY", 1, 16, 60000, ["computer_science", "electrical", "mechanical", "civil", "mba"]),
    ("University of California, San Diego", "USA", "San Diego, CA", 2, 62, 32000, ["computer_science", "data_science", "electrical", "mechanical", "public_health"]),
    ("University of Washington", "USA", "Seattle, WA", 2, 63, 34000, ENG + ["public_health", "mba"]),
    ("Purdue University", "USA", "West Lafayette, IN", 2, 89, 30000, ENG + ["business_analytics", "mba"]),
    ("University of Southern California", "USA", "Los Angeles, CA", 2, 125, 58000, ENG + ["business_analytics", "mba", "public_health"]),
    ("New York University", "USA", "New York, NY", 2, 43, 55000, ["computer_science", "data_science", "electrical", "mba", "finance", "public_health"]),
    ("Northeastern University", "USA", "Boston, MA", 2, 375, 50000, ["computer_science", "data_science", "electrical", "mechanical", "business_analytics"]),
    ("Texas A&M University", "USA", "College Station, TX", 2, 154, 28000, ENG + ["business_analytics", "mba"]),
    ("Virginia Tech", "USA", "Blacksburg, VA", 2, 380, 30000, ENG + ["mba"]),
    ("University of Florida", "USA", "Gainesville, FL", 2, 167, 28000, ENG + ["mba", "public_health"]),
    ("Rutgers University", "USA", "New Brunswick, NJ", 2, 328, 32000, ENG + ["business_analytics", "finance"]),
    ("Arizona State University", "USA", "Tempe, AZ", 3, 200, 30000, ENG + ["business_analytics", "mba"]),
    ("University of Texas at Dallas", "USA", "Richardson, TX", 3, 300, 28000, ["computer_science", "data_science", "electrical", "business_analytics", "finance"]),
    ("Stony Brook University", "USA", "Stony Brook, NY", 3, 380, 27000, ["computer_science", "data_science", "electrical", "mechanical"]),
    ("North Carolina State University", "USA", "Raleigh, NC", 3, 260, 30000, ENG),
    ("University at Buffalo", "USA", "Buffalo, NY", 3, 400, 27000, ENG + ["mba"]),
    ("Syracuse University", "USA", "Syracuse, NY", 3, 600, 45000, ["computer_science", "data_science", "electrical", "business_analytics"]),
    ("Indiana University Bloomington", "USA", "Bloomington, IN", 3, 350, 30000, ["computer_science", "data_science", "business_analytics", "public_health"]),
    ("University of Oxford", "UK", "Oxford", 1, 3, 38000, ["computer_science", "mba", "finance", "public_health"]),
    ("University of Cambridge", "UK", "Cambridge", 1, 5, 40000, ["computer_science", "electrical", "mechanical", "mba", "finance"]),
    ("Imperial College London", "UK", "London", 1, 2, 40000, ENG + ["business_analytics", "finance", "mba", "public_health"]),
    ("University College London", "UK", "London", 1, 9, 36000, ENG + ["business_analytics", "finance", "public_health"]),
    ("London School of Economics", "UK", "London", 1, 50, 34000, ["data_science", "finance", "business_analytics", "public_health"]),
    ("University of Edinburgh", "UK", "Edinburgh", 1, 27, 34000, ENG + ["business_analytics", "finance"]),
    ("University of Manchester", "UK", "Manchester", 2, 34, 31000, ENG + ["business_analytics", "finance", "mba"]),
    ("King's College London", "UK", "London", 2, 31, 33000, ["computer_science", "data_science", "finance", "public_health"]),
    ("University of Warwick", "UK", "Coventry", 2, 74, 32000, ["computer_science", "data_science", "business_analytics", "finance", "mba"]),
    ("University of Bristol", "UK", "Bristol", 2, 51, 30000, ENG + ["finance"]),
    ("University of Glasgow", "UK", "Glasgow", 2, 79, 28000, ENG + ["finance", "business_analytics"]),
    ("University of Southampton", "UK", "Southampton", 2, 87, 28000, ENG + ["business_analytics"]),
    ("University of Birmingham", "UK", "Birmingham", 2, 76, 28000, ENG + ["business_analytics", "finance", "mba"]),
    ("University of Leeds", "UK", "Leeds", 3, 82, 27000, ENG + ["business_analytics", "finance"]),
    ("University of Toronto", "Canada", "Toronto", 1, 25, 62000, ENG + ["mba", "finance", "public_health"]),
    ("University of British Columbia", "Canada", "Vancouver", 1, 38, 48000, ENG + ["mba", "business_analytics", "public_health"]),
    ("McGill University", "Canada", "Montreal", 1, 29, 40000, ENG + ["mba", "finance"]),
    ("University of Waterloo", "Canada", "Waterloo", 1, 115, 45000, ["computer_science", "data_science", "electrical", "mechanical", "civil"]),
    ("University of Alberta", "Canada", "Edmonton", 2, 96, 30000, ENG + ["mba"]),
    ("McMaster University", "Canada", "Hamilton", 2, 176, 32000, ENG + ["mba", "public_health"]),
    ("Concordia University", "Canada", "Montreal", 3, 400, 28000, ENG + ["business_analytics", "finance"]),
    ("Dalhousie University", "Canada", "Halifax", 3, 300, 26000, ["computer_science", "data_science", "electrical", "mechanical", "mba"]),
    ("Technical University of Munich", "Germany", "Munich", 1, 26, 12000, ENG + ["business_analytics", "mba"]),
    ("RWTH Aachen University", "Germany", "Aachen", 1, 99, 1500, ENG + ["business_analytics"]),
    ("Karlsruhe Institute of Technology", "Germany", "Karlsruhe", 2, 102, 3000, ENG),
    ("Technical University of Berlin", "Germany", "Berlin", 2, 147, 1500, ENG + ["business_analytics"]),
    ("LMU Munich", "Germany", "Munich", 2, 59, 1500, ["data_science", "finance", "public_health", "business_analytics"]),
    ("Trinity College Dublin", "Ireland", "Dublin", 1, 87, 28000, ["computer_science", "data_science", "electrical", "mba", "finance"]),
    ("University College Dublin", "Ireland", "Dublin", 2, 126, 27000, ENG + ["business_analytics", "finance", "mba", "public_health"]),
    ("University of Melbourne", "Australia", "Melbourne", 1, 13, 52000, ENG + ["mba", "business_analytics", "finance", "public_health"]),
    ("University of Sydney", "Australia", "Sydney", 1, 18, 54000, ENG + ["business_analytics", "finance", "public_health"]),
    ("UNSW Sydney", "Australia", "Sydney", 1, 19, 52000, ENG + ["mba", "business_analytics", "finance", "public_health"]),
    ("Monash University", "Australia", "Melbourne", 2, 37, 48000, ENG + ["business_analytics", "finance", "public_health"]),
    ("Australian National University", "Australia", "Canberra", 2, 30, 50000, ["computer_science", "data_science", "electrical", "finance", "public_health"]),
    ("Delft University of Technology", "Netherlands", "Delft", 1, 47, 21000, ENG),
    ("University of Amsterdam", "Netherlands", "Amsterdam", 2, 53, 20000, ["data_science", "computer_science", "finance", "business_analytics", "public_health"]),
    ("Indian Institute of Technology Bombay", "India", "Mumbai", 1, 118, 120000, ENG),
    ("Indian Institute of Technology Delhi", "India", "New Delhi", 1, 123, 120000, ENG),
    ("Indian Institute of Technology Madras", "India", "Chennai", 1, 180, 120000, ENG),
    ("Indian Institute of Science", "India", "Bengaluru", 1, 211, 50000, ["computer_science", "data_science", "electrical", "mechanical"]),
    ("Indian Institute of Management Ahmedabad", "India", "Ahmedabad", 1, None, 1300000, ["mba", "business_analytics"]),
    ("Indian Institute of Management Bangalore", "India", "Bengaluru", 1, None, 1250000, ["mba", "business_analytics"]),
    ("Indian School of Business", "India", "Hyderabad", 1, None, 4000000, ["mba"]),
    ("IIIT Hyderabad", "India", "Hyderabad", 2, None, 300000, ["computer_science", "data_science"]),
    ("BITS Pilani", "India", "Pilani", 2, None, 350000, ["computer_science", "data_science", "electrical", "mechanical", "finance"]),
    ("NIT Tiruchirappalli", "India", "Tiruchirappalli", 2, None, 150000, ENG),
    ("Narsee Monjee Institute of Management Studies", "India", "Mumbai", 3, None, 1100000, ["mba", "finance", "business_analytics"]),
]

# Typical admitted-student stats by tier (abroad uses GRE/GMAT, India uses entrance percentile: GATE/CAT)
TIER_STATS = {
    1: {"acceptance": (0.06, 0.15), "gre": 325, "gmat": 720, "cgpa": 8.8, "ielts": 7.0, "pct": 99.0},
    2: {"acceptance": (0.20, 0.40), "gre": 315, "gmat": 660, "cgpa": 8.0, "ielts": 6.5, "pct": 95.0},
    3: {"acceptance": (0.45, 0.70), "gre": 305, "gmat": 600, "cgpa": 7.3, "ielts": 6.5, "pct": 85.0},
}
TIER_SALARY_MULT = {1: 1.15, 2: 1.0, 3: 0.9}
FIELD_TUITION_MULT = {"mba": 1.6, "finance": 1.15, "business_analytics": 1.1, "public_health": 0.95}


def main() -> None:
    uni_rows, course_rows = [], []
    course_id = 1
    for uni_id, (name, country, city, tier, qs, ms_tuition, fields) in enumerate(UNIVERSITIES, start=1):
        c = COUNTRIES[country]
        uni_rows.append({
            "id": uni_id, "name": name, "country": country, "city": city, "tier": tier,
            "qs_rank": qs or "", "currency": c["currency"],
        })
        for field in fields:
            if country == "India" and field not in INDIA_NAMES:
                continue
            is_mba = field == "mba"
            months = c["mba_months"] if is_mba else c["ms_months"]
            if country == "India":
                months = 24 if is_mba or field != "business_analytics" else 12
                if "School of Business" in name:
                    months = 12
            # Indian institutes list their own per-year fee directly (IIM/ISB fees are already MBA fees)
            tuition_year = ms_tuition * (1 if country == "India" else FIELD_TUITION_MULT.get(field, 1.0))
            tuition_total = round(tuition_year * months / 12, -2)
            living_total = round(c["living"] * months / 12 * (1.25 if city in ("New York, NY", "London", "Stanford, CA", "Cambridge, MA", "Los Angeles, CA", "Sydney", "Mumbai") else 1.0), -2)
            ts = TIER_STATS[tier]
            acc = round(random.uniform(*ts["acceptance"]), 2)
            salary = round(SALARY[country][field] * TIER_SALARY_MULT[tier] * random.uniform(0.95, 1.05), -3)
            course_rows.append({
                "id": course_id,
                "university_id": uni_id,
                "program": (INDIA_NAMES if country == "India" else FIELD_NAMES)[field],
                "field": field,
                "level": "mba" if is_mba else "masters",
                "duration_months": months,
                "tuition_total_local": tuition_total,
                "living_total_local": living_total,
                "acceptance_rate": acc,
                "avg_gre": "" if country == "India" or is_mba else ts["gre"] + random.randint(-3, 3),
                "avg_gmat": ts["gmat"] + random.randint(-15, 15) if is_mba and country != "India" else "",
                "avg_cgpa": round(ts["cgpa"] + random.uniform(-0.2, 0.2), 1),
                "min_ielts": "" if country == "India" else ts["ielts"],
                "entrance_exam": ("CAT" if field in BIZ else "GATE") if country == "India" else "",
                "avg_entrance_percentile": ts["pct"] if country == "India" else "",
                "min_work_exp_months": (24 if tier == 1 else 12) if is_mba else 0,
                "median_salary_local": salary,
                "stem": field in ENG + ["data_science", "business_analytics"],
                "deadline_month": c["deadline_month"],
            })
            course_id += 1

    for fname, rows in (("universities.csv", uni_rows), ("courses.csv", course_rows)):
        with open(OUT / fname, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)

    meta = {
        "fx_inr": FX,
        "countries": {k: {"currency": v["currency"], "living_per_year_local": v["living"]} for k, v in COUNTRIES.items()},
        "fields": {k: FIELD_NAMES[k].replace("MS ", "").replace("Master of ", "") for k in FIELD_NAMES},
        "disclaimer": "Indicative estimates for a prototype. Verify fees, deadlines and salaries on official sources.",
    }
    (OUT / "catalog_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"{len(uni_rows)} universities, {len(course_rows)} courses")


if __name__ == "__main__":
    main()
