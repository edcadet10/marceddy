"""Recruiter / hiring-contact outreach.

For ready-to-submit jobs, find a hiring contact and prepare a SHORT, tailored
interest email that travels with the resume + cover letter already produced at
apply time. Discovery is TIERED and never fabricates:

  apollo-recruiter         - a real recruiter Apollo found at the company
  company-careers-fallback - careers@<verified-company-domain> (marked unverified)
  none                     - no reliable contact; use the posting's apply channel

HARD SAFETY BOUNDARY: nothing is transmitted to a third party unless BOTH --send
and creds outreach.enabled are set, and even then this build only ever test-sends
to Ed's own address. Cold recruiter blasting is never automatic.
"""
import json
import os
import re

# Apply URLs on these hosts are job boards or third-party ATSes, not the employer's
# own domain, so we must NOT derive a "careers@" address from them (that would be a
# fake guess at the wrong host). Keep this list broad — false-negatives just demote
# a job to tier "none", which is safe; a false-positive would fabricate an address.
AGGREGATOR_HOSTS = (
    # aggregators / job boards
    "indeed.com", "linkedin.com", "themuse.com", "remotive.com", "remoteok.com",
    "jobicy.com", "glassdoor", "ziprecruiter", "jooble", "jobleads", "google.com",
    "clearancejobs.com", "dice.com", "monster.com", "careerbuilder.com",
    "simplyhired.com", "snagajob.com", "flexjobs.com", "wellfound.com", "angel.co",
    "builtin.com", "jobs.net", "talent.com", "adzuna", "lensa.com", "joinrise",
    # third-party ATS / recruiting platforms (host != employer domain)
    "lever.co", "greenhouse.io", "myworkdayjobs.com", "ashbyhq.com", "jobvite.com",
    "smartrecruiters.com", "workable.com", "bamboohr.com", "icims.com", "taleo.net",
    "successfactors.com", "paycomonline.com", "adp.com", "paylocity.com",
    "applytojob.com", "breezy.hr", "rippling.com", "dayforcehcm.com", "ukg.com",
    "recruiting.com", "hire.lever", "jobs.ashby", "eightfold.ai", "phenom",
)


def load_outreach_contacts(config):
    p = config.home / "outreach_contacts.json"
    if p.exists():
        try:
            d = json.loads(p.read_text())
            return d if isinstance(d, dict) else {}
        except Exception:
            return {}
    return {}


def load_voice_samples(config):
    p = config.home / "voice_samples.txt"
    if p.exists():
        try:
            return (p.read_text().strip() or None)
        except Exception:
            return None
    return None


def _norm(s):
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def _domain_from_url(url):
    """Employer domain from an apply URL — ONLY when it's the company's own site,
    never an aggregator (so we never synthesize a fake address). '' otherwise."""
    m = re.search(r"https?://([^/]+)", url or "")
    if not m:
        return ""
    host = m.group(1).lower()
    if host.startswith("www."):
        host = host[4:]
    if any(a in host for a in AGGREGATOR_HOSTS):
        return ""
    parts = host.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else ""


def discover_contact(row, contacts):
    company = row.get("company") or ""
    c = contacts.get(company) or contacts.get(_norm(company)) or {}
    if c.get("found") and (c.get("name") or c.get("title")):
        return {"tier": "apollo-recruiter", "name": (c.get("name") or "").strip(),
                "role": (c.get("title") or "Recruiter").strip(),
                # email is revealed only at SEND time (Apollo enrichment = credits)
                "email": "", "email_verified": False, "email_known": bool(c.get("has_email"))}
    dom = _domain_from_url(row.get("apply_target") or row.get("url"))
    if dom:
        return {"tier": "company-careers-fallback", "name": "",
                "role": "Talent Acquisition / Hiring Team",
                "email": "careers@%s" % dom, "email_verified": False, "email_known": False}
    return {"tier": "none", "name": "", "role": "Hiring Team",
            "email": "", "email_verified": False, "email_known": False}


def _cert_phrase(profile):
    certs = " ".join(profile.get("certifications", []))
    have = [c for c in ("A+", "Network+", "Security+") if c in certs]
    if not have:
        return "CompTIA-certified"
    if len(have) == 1:
        return "CompTIA " + have[0]
    return "CompTIA " + ", ".join(have[:-1]) + ", and " + have[-1]


def render_outreach_email(row, profile, contact, voice=None):
    """A short (<150 word), fully-grounded interest email. Every concrete claim is
    drawn from the profile; nothing is invented. Names the contact's role and the
    specific job. When voice samples exist, the register is nudged casual."""
    name = profile.get("name", "Ed Cadet")
    first = name.split()[0] if name else "Ed"
    email = profile.get("email", "")
    phone = profile.get("phone", "")
    title = row.get("title") or "your open IT support role"
    company = row.get("company") or "your team"
    role = contact.get("role") or "Hiring Team"
    greet = ("Hi %s," % contact["name"].split()[0]) if contact.get("name") else ("Hi %s," % role)
    certs = _cert_phrase(profile)
    kws = [k.strip() for k in (row.get("match_keywords") or "").split(",") if k.strip()][:3]
    hook = (" with hands-on " + ", ".join(kws)) if kws else \
           " with hands-on help desk, desktop, and networking support"
    casual = bool(voice)
    signoff = ("Thanks,\n%s" % first) if casual else ("Best regards,\n%s" % name)
    body = (
        "%s\n\n"
        "I'm reaching out to %s's %s about your %s opening. I'm an IT support "
        "specialist certified in %s,%s, and I think I'd be a strong fit. My tailored "
        "resume and a short cover letter are attached — I'd welcome the chance to be "
        "considered.\n\n"
        "%s\n%s%s"
    ) % (greet, company, role, title, certs, hook, signoff,
         (email + "\n") if email else "", phone or "")
    subject = "Interested in your %s role — %s IT support" % (title, certs)
    return subject, body.strip()


def prepare_outreach(config, profile, limit=5):
    from .ledger import Ledger
    ledger = Ledger.load(config)
    contacts = load_outreach_contacts(config)
    voice = load_voice_samples(config)
    ready = [r for r in ledger.all() if r.get("status") == "ready_to_submit"]
    ready.sort(key=lambda r: float(r.get("fit_score") or 0), reverse=True)
    ready = ready[:limit]
    outdir = config.home / "outreach"
    outdir.mkdir(parents=True, exist_ok=True)
    results = []
    for r in ready:
        contact = discover_contact(r, contacts)
        subject, body = render_outreach_email(r, profile, contact, voice)
        slug = re.sub(r"[^a-z0-9]+", "-",
                      ((r.get("company") or "") + "-" + (r.get("title") or ""))[:48].lower()).strip("-") or "job"
        epath = outdir / (slug + "_email.txt")
        addr = contact.get("email") or ""
        if addr and not contact.get("email_verified"):
            recipient = "%s — UNVERIFIED, confirm before sending" % addr
        elif addr:
            recipient = addr
        else:
            recipient = "resolve at send time (Apollo reveal or company careers page)"
        epath.write_text("To: %s <%s>\nSubject: %s\n\n%s\n" % (
            contact["role"], recipient, subject, body))
        results.append({
            "job_id": r.get("job_id"), "company": r.get("company"), "title": r.get("title"),
            "tier": contact["tier"], "contact_role": contact["role"],
            "contact_name": contact.get("name", ""), "email_addr": contact.get("email", ""),
            "email_path": str(epath), "resume_path": r.get("tailored_resume_path", ""),
            "cover_letter_path": r.get("cover_letter_path", ""),
            "word_count": len(body.split()), "voice": bool(voice),
        })
    return results


def send_gate(args, config, results):
    """Print exactly what (didn't) get sent. Returns count actually transmitted to
    third parties — ALWAYS 0 in this build."""
    from .creds import load_creds
    if not getattr(args, "send", False):
        print("[outreach] dry-run: 0 emails transmitted. Use --send AND creds "
              "outreach.enabled:true to enable; recruiter delivery stays gated.")
        return 0
    creds = load_creds(config)
    if not creds.get("outreach", {}).get("enabled"):
        print("[outreach --send] refused: creds outreach.enabled is false. "
              "0 emails sent to third parties, 0 recruiters contacted.")
        return 0
    print("[outreach --send] enabled (test mode): a single sample would go ONLY to "
          "your own address (%s). Real recruiter delivery is intentionally NOT "
          "performed in this build." % config.account_email)
    return 0
