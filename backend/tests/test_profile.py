from app.db.models import StudentProfile
from app.rules.profile_strength import compute_profile_strength
from tests.conftest import auth, make_token

QUIZ = {
    "full_name": "Asha Rao",
    "current_status": "ug_final_year",
    "degree": "B.Tech",
    "field_of_study": "Computer Science",
    "graduation_year": 2027,
    "cgpa": 8.6,
    "college_tier": 2,
    "work_exp_months": 0,
    "gre": 320,
    "ielts": 7.5,
    "target_level": "masters",
    "target_field": "computer_science",
    "target_countries": ["USA", "Canada"],
    "target_intake": "Fall 2027",
    "budget_lakhs": 10,
    "co_applicant_income_lpa": 12,
    "has_collateral": False,
    "consent_data_processing": True,
}


def test_quiz_saves_profile_scores_and_awards_xp_once(client):
    h = auth(make_token())
    body = client.put("/me/profile", json=QUIZ, headers=h).json()
    assert body["user"]["full_name"] == "Asha Rao"
    assert body["user"]["xp"] == 100
    assert body["profile"]["study_in_india"] is False
    assert 0 < body["strength"]["score"] <= 100
    assert body["profile"]["profile_strength"] == body["strength"]["score"]
    assert {d["key"] for d in body["strength"]["dimensions"]} == {"academics", "tests", "experience", "goals", "finance"}

    again = client.put("/me/profile", json={**QUIZ, "cgpa": 9.2}, headers=h).json()
    assert again["user"]["xp"] == 100  # no XP for edits
    assert again["strength"]["score"] > body["strength"]["score"]

    me = client.get("/me", headers=h).json()
    assert me["profile"]["cgpa"] == 9.2 and me["strength"] is not None


def test_quiz_requires_consent_and_valid_countries(client):
    h = auth(make_token())
    assert client.put("/me/profile", json={**QUIZ, "consent_data_processing": False}, headers=h).status_code == 422
    assert client.put("/me/profile", json={**QUIZ, "target_countries": ["Narnia"]}, headers=h).status_code == 422
    assert client.put("/me/profile", json={**QUIZ, "cgpa": 11}, headers=h).status_code == 422


def test_profiles_are_per_user(client):
    a, b = auth(make_token(email="a@t.dev")), auth(make_token(email="b@t.dev"))
    client.put("/me/profile", json=QUIZ, headers=a)
    assert client.get("/me", headers=b).json()["profile"] is None


def test_strength_rules():
    strong = StudentProfile(
        user_id="00000000-0000-0000-0000-000000000001", cgpa=9.5, college_tier=1, gre=335, ielts=8.5,
        work_exp_months=36, target_level="masters", target_field="cs", target_countries=["USA"],
        target_intake="Fall 2027", budget_lakhs=20, co_applicant_income_lpa=20, has_collateral=True,
    )
    weak = StudentProfile(user_id="00000000-0000-0000-0000-000000000002", target_countries=["USA"])
    s, w = compute_profile_strength(strong), compute_profile_strength(weak)
    assert s.score >= 90 and w.score <= 15
    assert any("GRE" in t for t in w.tips)

    india = StudentProfile(
        user_id="00000000-0000-0000-0000-000000000003", cgpa=8.0, target_countries=["India"],
        entrance_exam="CAT", entrance_percentile=98, target_level="mba",
    )
    r = compute_profile_strength(india)
    assert next(d for d in r.dimensions if d.key == "tests").score > 20  # percentile counts, no GRE needed
    assert not any("GRE" in t for t in r.tips)


def test_catalog_meta_public(client):
    body = client.get("/catalog/meta").json()
    assert "India" in body["countries"] and body["course_count"] > 100
