"""Live end-to-end + isolation check against the deployed API with 3 throwaway accounts (created and deleted here)."""
import io
import os
import sys
import time
import uuid

import httpx
from PIL import Image

sys.path.insert(0, os.getcwd())
from app.config import get_settings  # noqa: E402

s = get_settings()
API = "https://pathpilot-api-n4ox.onrender.com"
SB = s.supabase_url.rstrip("/")
ANON, SVC = s.supabase_anon_key, s.supabase_service_role_key
tag = uuid.uuid4().hex[:6]
PW = "Pp-e2e-" + uuid.uuid4().hex[:10]
results = []


def check(name, ok, extra=""):
    results.append(ok)
    print(("PASS " if ok else "FAIL ") + name + (f"  [{extra}]" if extra else ""))


QUIZ = {"full_name": "E2E Tester", "current_status": "ug_final_year", "degree": "B.Tech", "field_of_study": "Computer Science",
        "graduation_year": 2027, "cgpa": 8.4, "college_tier": 2, "work_exp_months": 0, "gre": 318, "ielts": 7.5,
        "target_level": "masters", "target_field": "computer_science", "target_countries": ["USA", "Canada"],
        "target_intake": "Fall 2027", "budget_lakhs": 10, "co_applicant_income_lpa": 12, "has_collateral": False,
        "consent_data_processing": True}

http = httpx.Client(timeout=90)


def make_user(i):
    email = f"pp-e2e-{tag}-{i}@example.com"
    r = http.post(f"{SB}/auth/v1/admin/users", headers={"apikey": SVC, "Authorization": f"Bearer {SVC}"},
                  json={"email": email, "password": PW, "email_confirm": True, "user_metadata": {"full_name": f"E2E {i}"}})
    assert r.status_code in (200, 201), r.text[:200]
    t = http.post(f"{SB}/auth/v1/token?grant_type=password", headers={"apikey": ANON}, json={"email": email, "password": PW})
    assert t.status_code == 200, t.text[:200]
    return {"Authorization": "Bearer " + t.json()["access_token"]}, r.json()["id"]


def call(h, method, path, **kw):
    return http.request(method, API + path, headers=h, **kw)


print("waking API...")
for _ in range(12):
    try:
        if http.get(API + "/health", timeout=40).status_code == 200:
            break
    except httpx.HTTPError:
        time.sleep(5)

users = [make_user(i) for i in range(3)]
A, B, Cc = users[0][0], users[1][0], users[2][0]
try:
    for h, _ in users:
        r = call(h, "PUT", "/me/profile", json=QUIZ)
        assert r.status_code == 200, r.text[:200]
    check("3 accounts sign up and finish the quiz", True)

    nav = call(A, "POST", "/navigator/run")
    check("navigator run", nav.status_code == 200, f"ai={nav.json().get('ai') if nav.status_code == 200 else nav.text[:80]}")
    cid = nav.json()["matches"][0]["course_id"]
    call(A, "POST", f"/navigator/shortlist/{cid}")
    tl = call(A, "POST", "/timeline/generate")
    check("timeline generated", tl.status_code == 200, f"{len(tl.json()['tasks'])} tasks")
    task_id = tl.json()["tasks"][0]["id"]
    sop = call(A, "POST", "/sop/review", json={"text": "I built a recommender for my college canteen that cut waiting time by 30 percent. " * 6})
    check("SOP review", sop.status_code == 200, f"ai={sop.json().get('ai')}")
    sop_id = sop.json()["id"]
    iv = call(A, "POST", "/visa/start", json={"country": "USA"})
    iv_id = iv.json()["id"]
    offers = call(A, "POST", "/loan/offers", json={"course_id": cid, "amount_lakhs": 30}).json()
    pid = next(o["product_id"] for o in offers["offers"] if o["eligible"])
    app = call(A, "POST", "/loan/applications", json={"product_id": pid, "course_id": cid}).json()
    app_id = app["id"]
    buf = io.BytesIO()
    Image.new("RGB", (300, 200), "white").save(buf, format="PNG")
    up = call({"Authorization": A["Authorization"]}, "POST", f"/loan/applications/{app_id}/documents", data={"doc_type": "pan"},
              files={"file": ("pan.png", buf.getvalue(), "image/png")})
    check("document upload to private storage", up.status_code == 200, f"{up.status_code} {str(up.json().get('notice') or '')[:60]}")
    doc_id = up.json().get("document", {}).get("id") if up.status_code == 200 else None
    nid = call(A, "GET", "/growth").json()["nudges"][0]["id"]

    for name, h in (("B", B), ("C", Cc)):
        probes = [
            ("loan application", call(h, "GET", f"/loan/applications/{app_id}")),
            ("loan patch", call(h, "PATCH", f"/loan/applications/{app_id}", json={"applicant": {"pan": "ZZZZZ9999Z"}})),
            ("SOP review", call(h, "GET", f"/sop/reviews/{sop_id}")),
            ("visa interview", call(h, "GET", f"/visa/{iv_id}")),
            ("timeline task", call(h, "PATCH", f"/timeline/tasks/{task_id}", json={"done": True})),
            ("nudge", call(h, "POST", f"/growth/nudges/{nid}", json={"action": "dismiss"})),
        ]
        if doc_id:
            probes.append(("document link", call(h, "GET", f"/loan/applications/{app_id}/documents/{doc_id}/url")))
        for what, r in probes:
            check(f"{name} cannot reach A's {what}", r.status_code == 404, str(r.status_code))
        lists = [call(h, "GET", "/loan/applications").json()["applications"], call(h, "GET", "/sop").json()["reviews"],
                 call(h, "GET", "/navigator/shortlist").json()["shortlist"], call(h, "GET", "/mentor/history").json()["messages"]]
        check(f"{name} sees empty lists", all(x == [] for x in lists))
        check(f"{name} blocked from admin", call(h, "GET", "/admin/overview").status_code == 403)
    check("A still sees own application", call(A, "GET", f"/loan/applications/{app_id}").status_code == 200)

    a = call(A, "GET", "/me/export")
    check("export works", a.status_code == 200 and "loanapplication" in a.json()["data"])
    fb = call(A, "POST", "/feedback", json={"message": "e2e check, please ignore", "category": "other"})
    check("feedback accepted", fb.status_code == 200)
    pub = http.get(API + "/content")
    check("public guides list", pub.status_code == 200 and len(pub.json()) > 0, f"{len(pub.json())} guides")
    if pub.json():
        slug = pub.json()[0]["slug"]
        check("public guide page", http.get(API + f"/content/{slug}").status_code == 200)
    check("signed-in discover feed", call(A, "GET", "/content/feed").status_code == 200)
finally:
    for h, uid in users:
        r = call(h, "DELETE", "/me", json={"confirm": "DELETE"})
        ok = r.status_code == 200 and r.json().get("deleted")
        print("cleanup", uid[:8], r.status_code, "login_removed=", r.json().get("login_removed") if r.status_code == 200 else r.text[:80])
        if not (ok and r.json().get("login_removed")):  # fall back to deleting the auth user directly
            http.delete(f"{SB}/auth/v1/admin/users/{uid}", headers={"apikey": SVC, "Authorization": f"Bearer {SVC}"})

print(f"\n{sum(results)}/{len(results)} checks passed")
sys.exit(0 if all(results) else 1)
