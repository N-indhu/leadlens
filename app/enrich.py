"""Cleaning, validation and dedupe helpers."""
import re
from urllib.parse import urlparse

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@([A-Za-z0-9\-]+\.)+[A-Za-z]{2,}$")
ROLE_LOCALS = {"info", "admin", "support", "sales", "contact", "hello", "office", "team", "noreply", "no-reply"}
DISPOSABLE = {"mailinator.com", "10minutemail.com", "guerrillamail.com", "tempmail.com", "yopmail.com"}
FREE_MAIL = {"gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "icloud.com"}


def normalize_domain(website: str = "", email: str = "") -> str:
    if website:
        w = website.strip().lower()
        if "//" not in w:
            w = "//" + w
        host = urlparse(w).netloc.split(":")[0]
        if host.startswith("www."):
            host = host[4:]
        if host:
            return host
    if email and "@" in email:
        d = email.split("@")[-1].strip().lower()
        if d not in FREE_MAIL:
            return d
    return ""


def validate_email(email: str):
    """Returns status: valid | risky | invalid | missing."""
    e = (email or "").strip().lower()
    if not e:
        return "missing"
    if not EMAIL_RE.match(e):
        return "invalid"
    local, domain = e.split("@")
    if domain in DISPOSABLE:
        return "invalid"
    if local in ROLE_LOCALS or domain in FREE_MAIL:
        return "risky"
    return "valid"


def dedupe_key(lead: dict) -> str:
    """Email wins; otherwise name+domain/company. Case/whitespace-insensitive."""
    email = (lead.get("email") or "").strip().lower()
    if email:
        return "e:" + email
    name = re.sub(r"\W+", "", (lead.get("name") or "").lower())
    org = lead.get("domain") or re.sub(r"\W+", "", (lead.get("company") or "").lower())
    return f"n:{name}|{org}"


def to_int(v):
    if v is None:
        return None
    s = re.sub(r"[^\d\-]", "", str(v).split("-")[0].replace(",", ""))
    return int(s) if s.isdigit() else None


ALIASES = {
    "name": ["name", "full name", "contact", "contact name"],
    "title": ["title", "job title", "position", "role"],
    "company": ["company", "company name", "organization", "account"],
    "website": ["website", "domain", "url", "company website"],
    "industry": ["industry", "sector", "vertical"],
    "employees": ["employees", "company size", "headcount", "size", "# employees"],
    "location": ["location", "country", "city", "region", "hq"],
    "email": ["email", "email address", "work email"],
    "linkedin": ["linkedin", "linkedin url", "linkedin profile"],
    "phone": ["phone", "phone number", "mobile"],
}


def map_row(row: dict) -> dict:
    low = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
    out = {}
    for field, names in ALIASES.items():
        out[field] = next((low[n] for n in names if low.get(n)), "")
    out["employees"] = to_int(out["employees"])
    out["domain"] = normalize_domain(out.pop("website"), out["email"])
    out["email"] = out["email"].lower()
    out["email_status"] = validate_email(out["email"])
    return out
