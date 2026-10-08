# LeadLens — ICP-fit lead triage on top of a lead-gen list

**Built for the Caprae Capital AI-Readiness Pre-Screening Challenge (≈5 hours of scope).**

## Why this feature
SaaSquatch finds leads. The bottleneck after that is *deciding who to call first*.
Reps waste hours on duplicates, dead emails, and companies that were never a fit.
LeadLens is the **quality-first** option from the handbook: one focused layer that turns a raw
lead export into a ranked, explainable, outreach-ready list.

| Step | What it does | Why it matters |
|---|---|---|
| Import | CSV with flexible header mapping ("Company Name", "Organization", …) | Works with SaaSquatch / Apollo / any export |
| Clean | Email validation (syntax, disposable, role-based, free-mail), domain normalization | Fewer bounces, protects sender reputation |
| Dedupe + merge | Email-first key, then name+domain; blanks are enriched, good data never overwritten | One record per person |
| Score | 0-100 against an editable ICP; **every point has a written reason** | Reps trust it; managers can tune it |
| Triage | Hot / Warm / Cold tiers, filters, status tracking | Highest-impact leads first |
| Act | Personalized outreach draft, CSV export | Plugs into any CRM / sequencer |

## Run it
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
# open http://localhost:8000  ->  "Load sample data"
pytest -q
```

## Architecture
- **Backend:** Python 3.11+, FastAPI + Pydantic validation
- **Storage:** SQLite (file DB, zero ops) with a UNIQUE `dedupe_key` and an index on `score`
- **Frontend:** single static page, vanilla JS, no build step; all user data rendered via `textContent` (XSS-safe)
- **Performance:** scoring is O(1) per lead and runs at import time, so reads are a single indexed query; filters are debounced client-side; uploads capped at 5MB
- **Hosting (recommended):** one container on Google Cloud Run (serverless, scales to zero) serving API + static files. For multi-user production, swap SQLite for Postgres (Cloud SQL) — only `db.py` changes.
- **Deploy:** `gcloud run deploy leadlens --source .` (add a Dockerfile with `uvicorn app.main:app --host 0.0.0.0 --port $PORT`)

## API
`POST /api/upload` · `GET /api/leads` · `PATCH /api/leads/{id}` · `GET/PUT /api/icp` ·
`GET /api/stats` · `GET /api/leads/{id}/outreach` · `GET /api/export.csv`

## Honest limitations / next steps
- Email checks are syntactic; add MX/SMTP verification and a provider (e.g. enrichment API) next.
- It scores leads you already have; the next step is wiring it directly behind the scraper.
- Outreach drafts are templates; an LLM call could personalize further.
- Scraping must respect robots.txt, site ToS and privacy law (GDPR/CCPA) — kept out of scope here on purpose.

## 2-minute video script
1. **0:00** Problem: lead lists are noisy; reps don't know who to call first.
2. **0:20** Demo: load sample data → note duplicate merged, invalid emails flagged.
3. **0:50** Click "Why?" on the top lead — show the explainable score.
4. **1:10** Tune ICP (change industry/weights) → scores re-rank instantly.
5. **1:30** Draft outreach, export CSV. Close with architecture + next steps.
