"""Explainable ICP-fit scoring (0-100). Every point is traceable to a reason."""

SENIORITY = [  # (keywords, fraction of title weight)
    (("founder", "ceo", "owner", "chief", "president", "cto", "cfo", "cmo", "coo"), 1.0),
    (("vp", "vice president", "head"), 0.8),
    (("director",), 0.6),
    (("manager", "lead"), 0.35),
]


def _contains_any(text: str, needles) -> bool:
    t = (text or "").lower()
    return any(n in t for n in needles)


def score_lead(lead: dict, icp: dict):
    w = icp["weights"]
    score, reasons = 0.0, []

    # Industry fit
    if _contains_any(lead.get("industry"), icp["industries"]):
        score += w["industry"]
        reasons.append(f"+{w['industry']} industry matches ICP")
    elif not lead.get("industry"):
        reasons.append("+0 industry unknown")

    # Company size fit (graceful decay outside the band)
    emp = lead.get("employees")
    lo, hi = icp["min_employees"], icp["max_employees"]
    if emp:
        if lo <= emp <= hi:
            score += w["size"]
            reasons.append(f"+{w['size']} {emp} employees in target band")
        elif emp < lo * 0.5 or emp > hi * 3:
            reasons.append("+0 company size far from target")
        else:
            part = round(w["size"] * 0.4)
            score += part
            reasons.append(f"+{part} company size near target band")

    # Decision-maker seniority
    title = (lead.get("title") or "").lower()
    for words, frac in SENIORITY:
        if _contains_any(title, words):
            pts = round(w["title"] * frac)
            score += pts
            reasons.append(f"+{pts} decision-maker title ({lead['title']})")
            break

    # Geography
    if _contains_any(lead.get("location"), icp["locations"]):
        score += w["location"]
        reasons.append(f"+{w['location']} target location")

    # Contact quality (what makes it actually reachable)
    c = w["contact"]
    status = lead.get("email_status", "missing")
    email_pts = {"valid": round(c * 0.6), "risky": round(c * 0.25)}.get(status, 0)
    score += email_pts
    reasons.append(f"+{email_pts} email {status}")
    if lead.get("linkedin"):
        pts = round(c * 0.2)
        score += pts
        reasons.append(f"+{pts} LinkedIn available")
    if lead.get("phone"):
        pts = round(c * 0.2)
        score += pts
        reasons.append(f"+{pts} phone available")

    return min(100, round(score)), reasons


def tier(score: int) -> str:
    return "hot" if score >= 75 else "warm" if score >= 50 else "cold"
