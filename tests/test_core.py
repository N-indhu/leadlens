import os
import tempfile

os.environ["LEADLENS_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")

from fastapi.testclient import TestClient  # noqa: E402

from app.db import DEFAULT_ICP  # noqa: E402
from app.enrich import dedupe_key, map_row, normalize_domain, validate_email  # noqa: E402
from app.main import app  # noqa: E402
from app.scoring import score_lead  # noqa: E402

client = TestClient(app)


def test_email_validation():
    assert validate_email("ceo@acme.io") == "valid"
    assert validate_email("info@acme.io") == "risky"
    assert validate_email("bob@mailinator.com") == "invalid"
    assert validate_email("nope") == "invalid"
    assert validate_email("") == "missing"


def test_domain_normalization():
    assert normalize_domain("https://www.Acme.io/about") == "acme.io"
    assert normalize_domain("", "x@acme.io") == "acme.io"
    assert normalize_domain("", "x@gmail.com") == ""


def test_dedupe_key_case_insensitive():
    a = {"email": "A@x.io"}
    b = {"email": " a@x.io "}
    assert dedupe_key(a) == dedupe_key(b)


def test_perfect_icp_lead_scores_high():
    lead = map_row({"Name": "A", "Title": "CEO", "Company": "X", "Industry": "SaaS",
                    "Employees": "50", "Country": "United States", "Email": "a@x.io",
                    "LinkedIn": "li", "Phone": "1"})
    s, reasons = score_lead(lead, DEFAULT_ICP)
    assert s == 100 and reasons


def test_bad_fit_scores_low():
    lead = map_row({"Name": "B", "Title": "Intern", "Industry": "Food", "Employees": "20000", "Email": ""})
    s, _ = score_lead(lead, DEFAULT_ICP)
    assert s < 20


def test_upload_dedupes_and_sorts():
    with open(os.path.join(os.path.dirname(__file__), "..", "static", "sample_leads.csv"), "rb") as f:
        r = client.post("/api/upload", files={"file": ("s.csv", f, "text/csv")})
    assert r.status_code == 200
    body = r.json()
    assert body["added"] == 9 and body["duplicates_merged"] == 1
    leads = client.get("/api/leads").json()
    scores = [x["score"] for x in leads]
    assert scores == sorted(scores, reverse=True)
    assert leads[0]["name"] == "Priya Raman"


def test_icp_weights_must_sum_100():
    icp = client.get("/api/icp").json()
    icp["weights"]["industry"] = 99
    assert client.put("/api/icp", json=icp).status_code == 400


def test_status_update_and_export():
    lid = client.get("/api/leads").json()[0]["id"]
    assert client.patch(f"/api/leads/{lid}", json={"status": "qualified"}).status_code == 200
    assert client.patch(f"/api/leads/{lid}", json={"status": "bogus"}).status_code == 400
    assert "score,tier,name" in client.get("/api/export.csv").text
