"""Application preparation + gated submission.

prepare_applications(): for EVERY fit/tailored job not yet handled, generate a
truthful cover letter, assemble a packet, and move the ledger row to
'ready_to_submit'. Fully reversible and ToS-clean — this is "apply to every fit
job" up to the irreversible step.

submit_applications(): gated behind --submit AND creds submit.enabled. Only the
'email' method is legitimately auto-transmittable (a tailored email to a real
application address listed in the posting). Portal/ATS postings (Muse,
Greenhouse, most company career pages) have NO public auto-submit API and
prohibit bot submission, so they stay queued with a link for one-click human
submission. Idempotent: never re-applies to a job already 'applied'. Account
creation is never performed.
"""
import re
from datetime import datetime, timezone

from .creds import load_creds
from .email_track import send_self_email
from .ledger import Ledger

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PREPARABLE = {"tailored", "matched"}
DONE = {"ready_to_submit", "applied"}


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


ROLE_LINE = {
    "helpdesk": "Tier 1–2 service-desk experience supporting 15,000+ users in ServiceNow at 95% CSAT",
    "desktop": "desktop and endpoint experience imaging and troubleshooting Dell, HP, Apple, and Lenovo hardware",
    "sysadmin": "hands-on Active Directory / Microsoft Entra ID, Windows Server, and infrastructure administration",
    "network": "networking experience across DNS, DHCP, TCP/IP, VPN, and switch/router troubleshooting",
    "cloud": "cloud experience operating Docker, GCP/Azure, and CI/CD pipelines in production",
    "developer": "Python/FastAPI experience building and operating a production SaaS end to end",
}


def make_cover_letter(row, profile):
    """Per-job cover letter: role-type-aware opening + the posting's own matched
    keywords. Varies by job; never invents experience."""
    company = row.get("company", "the company")
    title = row.get("title", "the role")
    name = profile["name"]
    kws = (row.get("match_keywords") or "").strip()
    rt = row.get("role_type") or "helpdesk"
    roleline = ROLE_LINE.get(rt, ROLE_LINE["helpdesk"])
    second = ("This role calls for %s — areas I work in directly." % kws) if kws \
        else "My background maps directly to what this role calls for."
    lines = [
        name,
        " | ".join(x for x in [profile.get("location", ""), profile.get("email", ""),
                               profile.get("phone", "")] if x),
        "",
        "Dear %s Hiring Team," % company,
        "",
        ("I'm applying for the %s role at %s. As a CompTIA A+, Network+, and Security+ "
         "certified IT professional, I'd bring %s.") % (title, company, roleline),
        "",
        second,
        "",
        profile.get("summary", ""),
        "",
        "I'd welcome the chance to discuss how I can support your team. My resume is attached.",
        "",
        "Sincerely,",
        name,
    ]
    return "\n".join(lines) + "\n"


def _write_cover_docx(text, path):
    from docx import Document
    doc = Document()
    for para in text.split("\n"):
        doc.add_paragraph(para)
    doc.save(path)


def apply_method(row):
    """Return (method, target). 'email' only if the posting exposes a real,
    non-noreply application address; otherwise 'portal' with the listing URL."""
    blob = " ".join([row.get("notes") or "", row.get("url") or ""])
    m = EMAIL_RE.search(blob)
    if m and "noreply" not in m.group(0).lower() and "no-reply" not in m.group(0).lower():
        return ("email", m.group(0))
    return ("portal", row.get("url", ""))


def prepare_applications(config, profile, limit=None):
    config.ensure_dirs()
    ledger = Ledger.load(config)
    outbox = config.home / "outbox"
    outbox.mkdir(parents=True, exist_ok=True)
    prepared, now = [], _now()
    for r in ledger.all():
        if r.get("status") in DONE or r.get("status") not in PREPARABLE:
            continue
        method, target = apply_method(r)
        text = make_cover_letter(r, profile)
        cl_txt = outbox / ("%s_cover.txt" % r["job_id"])
        cl_docx = outbox / ("%s_cover.docx" % r["job_id"])
        cl_txt.write_text(text)
        cover_path = str(cl_txt)
        try:
            _write_cover_docx(text, str(cl_docx))
            cover_path = str(cl_docx)
        except Exception:
            pass
        ledger.update_status(r["job_id"], "ready_to_submit", ts=now,
                             apply_method=method, apply_target=target,
                             cover_letter_path=cover_path, cover_letter_txt=str(cl_txt),
                             ready_ts=now)
        prepared.append({"job_id": r["job_id"], "company": r.get("company"),
                         "title": r.get("title"), "method": method, "target": target})
        if limit and len(prepared) >= limit:
            break
    ledger.save()
    return prepared


def submit_applications(config, profile, do_submit=False):
    """Transmit queued applications. Double-gated; email channel only."""
    ledger = Ledger.load(config)
    creds = load_creds(config)
    enabled = bool(creds.get("submit", {}).get("enabled"))
    ready = [r for r in ledger.all() if r.get("status") == "ready_to_submit"]
    if not (do_submit and enabled):
        why = "submit.enabled is false" if do_submit else "no --submit flag"
        print("[apply --submit] refused: %s. 0 applications submitted, 0 accounts created." % why)
        print("  %d application(s) queued (status ready_to_submit) for your review." % len(ready))
        return {"submitted": 0, "queued": len(ready), "accounts_created": 0}
    smtp = creds.get("smtp", {})
    submitted = portal = 0
    now = _now()
    for r in ready:
        if r.get("apply_method") != "email" or not smtp.get("password"):
            portal += 1
            continue
        body = ""
        clt = r.get("cover_letter_txt") or r.get("cover_letter_path")
        if clt:
            try:
                body += open(clt).read()
            except Exception:
                pass
        rp = r.get("tailored_resume_path") or ""
        rtxt = rp[:-5] + ".txt" if rp.endswith(".docx") else rp
        if rtxt:
            try:
                body += "\n\n--- RESUME ---\n" + open(rtxt).read()
            except Exception:
                pass
        try:
            send_self_email(smtp.get("host", "smtp.gmail.com"), int(smtp.get("port", 587)),
                            smtp.get("username"), smtp["password"], r["apply_target"],
                            "Application: %s — %s" % (r.get("title"), profile["name"]), body)
            ledger.update_status(r["job_id"], "applied", ts=now)
            submitted += 1
        except Exception as e:
            print("  submit failed for %s: %s" % (r.get("company"), type(e).__name__))
    ledger.save()
    print("[apply --submit] submitted=%d (email channel) | portal/manual queued=%d | accounts_created=0"
          % (submitted, portal))
    return {"submitted": submitted, "queued": portal, "accounts_created": 0}
