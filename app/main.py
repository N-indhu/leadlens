"""LeadLens API: import -> clean -> dedupe -> score -> triage -> export."""
import csv
import io
import json
import os
from typing import Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .db import get_db, init_db, load_icp, save_icp
from .enrich import dedupe_key, map_row
from .scoring import score_lead, tier

app = FastAPI(title="LeadLens", version="1.0")
init_db()

MAX_UPLOAD = 5 * 1024 * 1024  # 5MB guard
STATUSES = {"new", "contacted", "qualified", "rejected"}
MERGE_FIELDS = ["name", "title", "company", "domain", "industry", "employees",
                "location", "email", "linkedin", "phone", "email_status"]


class ICP(BaseModel):
    industries: list[str]
    min_employees: int
    max_employees: int
    target_titles: list[str]
    locations: list[str]
    weights: dict[str, int]


class StatusUpdate(BaseModel):
    status: str


def _row_to_dict(r):
    d = dict(r)
    d["reasons"] = json.loads(d["reasons"] or "[]")
    d["tier"] = tier(d["score"])
    return d


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    raw = await file.read()
    if len(raw) > MAX_UPLOAD:
        raise HTTPException(413, "File too large (max 5MB)")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(400, "CSV must be UTF-8 encoded")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(400, "CSV has no header row")

    added = merged = skipped = 0
    with get_db() as c:
        icp = load_icp(c)
        for row in reader:
            lead = map_row(row)
            if not (lead["name"] or lead["email"] or lead["company"]):
                skipped += 1
                continue
            key = dedupe_key(lead)
            existing = c.execute("SELECT * FROM leads WHERE dedupe_key=?", (key,)).fetchone()
            if existing:
                # enrichment-merge: fill blanks only, never overwrite good data
                upd = {f: lead[f] for f in MERGE_FIELDS if lead[f] and not existing[f]}
                if upd:
                    merged_lead = {**dict(existing), **upd}
                    s, reasons = score_lead(merged_lead, icp)
                    sets = ", ".join(f"{k}=?" for k in upd) + ", score=?, reasons=?"
                    c.execute(f"UPDATE leads SET {sets} WHERE id=?",
                              (*upd.values(), s, json.dumps(reasons), existing["id"]))
                merged += 1
                continue
            s, reasons = score_lead(lead, icp)
            c.execute(
                """INSERT INTO leads (dedupe_key,name,title,company,domain,industry,employees,
                   location,email,linkedin,phone,email_status,score,reasons)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (key, lead["name"], lead["title"], lead["company"], lead["domain"], lead["industry"],
                 lead["employees"], lead["location"], lead["email"], lead["linkedin"], lead["phone"],
                 lead["email_status"], s, json.dumps(reasons)),
            )
            added += 1
    return {"added": added, "duplicates_merged": merged, "skipped": skipped}


@app.get("/api/leads")
def list_leads(q: Optional[str] = None, min_score: int = 0, tier_: Optional[str] = None,
               status: Optional[str] = None, email_status: Optional[str] = None,
               limit: int = 500):
    sql, args = "SELECT * FROM leads WHERE score >= ?", [min_score]
    if q:
        sql += " AND (name LIKE ? OR company LIKE ? OR title LIKE ? OR industry LIKE ?)"
        args += [f"%{q}%"] * 4
    if status:
        sql += " AND status=?"
        args.append(status)
    if email_status:
        sql += " AND email_status=?"
        args.append(email_status)
    sql += " ORDER BY score DESC, id ASC LIMIT ?"
    args.append(min(limit, 2000))
    with get_db() as c:
        rows = [_row_to_dict(r) for r in c.execute(sql, args)]
    if tier_:
        rows = [r for r in rows if r["tier"] == tier_]
    return rows


@app.patch("/api/leads/{lead_id}")
def update_status(lead_id: int, body: StatusUpdate):
    if body.status not in STATUSES:
        raise HTTPException(400, f"status must be one of {sorted(STATUSES)}")
    with get_db() as c:
        cur = c.execute("UPDATE leads SET status=? WHERE id=?", (body.status, lead_id))
        if cur.rowcount == 0:
            raise HTTPException(404, "Lead not found")
    return {"ok": True}


@app.delete("/api/leads")
def clear_leads():
    with get_db() as c:
        c.execute("DELETE FROM leads")
    return {"ok": True}


@app.get("/api/icp")
def get_icp():
    with get_db() as c:
        return load_icp(c)


@app.put("/api/icp")
def put_icp(icp: ICP):
    if sum(icp.weights.values()) != 100:
        raise HTTPException(400, "Weights must sum to 100")
    with get_db() as c:
        save_icp(c, icp.model_dump())
        # instant re-score so the user sees the effect of tuning their ICP
        for r in c.execute("SELECT * FROM leads").fetchall():
            s, reasons = score_lead(dict(r), icp.model_dump())
            c.execute("UPDATE leads SET score=?, reasons=? WHERE id=?", (s, json.dumps(reasons), r["id"]))
    return {"ok": True}


@app.get("/api/stats")
def stats():
    with get_db() as c:
        total = c.execute("SELECT COUNT(*) n FROM leads").fetchone()["n"]
        scores = [r["score"] for r in c.execute("SELECT score FROM leads")]
        valid = c.execute("SELECT COUNT(*) n FROM leads WHERE email_status='valid'").fetchone()["n"]
    return {
        "total": total,
        "hot": sum(1 for s in scores if s >= 75),
        "warm": sum(1 for s in scores if 50 <= s < 75),
        "cold": sum(1 for s in scores if s < 50),
        "valid_emails": valid,
        "avg_score": round(sum(scores) / total) if total else 0,
    }


@app.get("/api/leads/{lead_id}/outreach")
def outreach(lead_id: int):
    """Personalized first-touch draft built from the lead's own data."""
    with get_db() as c:
        r = c.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
    if not r:
        raise HTTPException(404, "Lead not found")
    first = (r["name"] or "there").split()[0]
    company = r["company"] or "your team"
    hook = f"teams in {r['industry']}" if r["industry"] else "growing teams"
    return {
        "subject": f"Quick idea for {company}",
        "body": (
            f"Hi {first},\n\nI came across {company} and noticed you're {r['title'] or 'leading the team'}. "
            f"We help {hook} cut the time spent finding and qualifying leads, so reps only talk "
            f"to accounts that match their ideal customer profile.\n\n"
            f"Worth a 15-minute chat this week?\n\nBest,\n[Your name]"
        ),
    }


@app.get("/api/export.csv", response_class=PlainTextResponse)
def export_csv(min_score: int = 0):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["score", "tier", "name", "title", "company", "domain", "industry", "employees",
                "location", "email", "email_status", "linkedin", "phone", "status"])
    with get_db() as c:
        for r in c.execute("SELECT * FROM leads WHERE score>=? ORDER BY score DESC", (min_score,)):
            w.writerow([r["score"], tier(r["score"]), r["name"], r["title"], r["company"], r["domain"],
                        r["industry"], r["employees"], r["location"], r["email"], r["email_status"],
                        r["linkedin"], r["phone"], r["status"]])
    return PlainTextResponse(buf.getvalue(), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=leadlens_export.csv"})


static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
