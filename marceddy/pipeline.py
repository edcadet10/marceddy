"""The scan pipeline: search -> dedup -> fit -> tailor -> ledger.

Submission is gated: even with submit=True nothing is sent unless the creds
store has submit.enabled=true, and account creation is never performed.
"""
import re
from datetime import datetime, timezone

from .creds import load_creds
from .dedup import SeenStore
from .fit import score_job
from .ledger import Ledger
from .policy import load_policy
from .profile import load_profile
from .sources import get_source
from .tailor import matched_skills, role_type, write_resume


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fmt(t):
    return ("%g" % t)


IT_TITLE_RE = re.compile(
    r"(it support|help ?desk|service desk|desktop|technician|sys ?admin|"
    r"system[s]? admin|network|infrastructure|endpoint|deskside|field service|"
    r"\bnoc\b|support|security|devops|information technology|\bit\b|cloud)", re.I)


def is_relevant(job, profile):
    """Keep on-target roles, drop clearly-unrelated ones. Title is the primary
    signal; fall back to strong skill overlap. The title pattern is per-profile:
    a profile may set ``relevant_title_pattern`` (e.g. a beauty pattern for Sarah);
    otherwise the IT default applies (Ed)."""
    pat = (profile or {}).get("relevant_title_pattern")
    try:
        rx = re.compile(pat, re.I) if pat else IT_TITLE_RE
    except re.error:
        rx = IT_TITLE_RE
    if rx.search(job.title or ""):
        return True
    return len(matched_skills(job, profile)) >= 5


def _refuse_or_noop_submit(passed, config):
    """Submission is intentionally inert. It refuses unless explicitly enabled,
    and even when enabled it is a no-op in this build (no real applications are
    sent, no accounts are created)."""
    creds = load_creds(config)
    if not creds.get("submit", {}).get("enabled"):
        print("[--submit] refused: credentials submit.enabled is false. "
              "0 applications submitted, 0 accounts created.")
        return 0
    print("[--submit] enabled flag set, but real submission is a deliberate no-op "
          "in this build (safety). 0 submitted.")
    return 0


def run_scan(config, source_name="fixture", query="", limit=25, tailor=True,
             submit=False, fixture_path=None, verbose=True):
    config.ensure_dirs()
    profile = load_profile(config)
    policy = load_policy(config)
    source = get_source(source_name, config, fixture_path=fixture_path)

    jobs = source.fetch(query, limit)
    seen = SeenStore.load(config)
    new_jobs = [j for j in jobs if not seen.contains(j.job_id)]

    ledger = Ledger.load(config)
    passed = []
    for j in new_jobs:
        sc = score_job(j, profile, policy)
        if sc >= policy["threshold"] and is_relevant(j, profile):
            passed.append((j, sc))

    now = _now()
    tailored = 0
    for j, sc in passed:
        path = write_resume(j, profile, policy, config) if tailor else ""
        if ledger.get(j.job_id):
            ledger.upsert({"job_id": j.job_id, "fit_score": sc,
                           "tailored_resume_path": path})
        else:
            ledger.upsert({
                "job_id": j.job_id, "source": j.source, "company": j.company,
                "title": j.title, "url": j.url, "fit_score": sc,
                "tailored_resume_path": path,
                "status": "tailored" if tailor else "matched",
                "first_seen_ts": now, "account_email": config.account_email,
                "last_update_ts": now, "last_email_from": "",
                "notes": source.attribution,
                "match_keywords": ", ".join(matched_skills(j, profile)[:8]),
                "role_type": role_type(j),
                "salary": getattr(j, "salary", "") or "",
                "salary_estimated": bool(getattr(j, "salary_estimated", False)),
                "salary_basis": getattr(j, "salary_basis", "") or "",
                "location": getattr(j, "location", "") or "",
                "remote": bool(getattr(j, "remote", False)),
            })
        if tailor:
            tailored += 1

    submitted = 0
    if submit:
        submitted = _refuse_or_noop_submit(passed, config)

    # Mark every new job as seen so re-runs are idempotent (NEW: 0 next time),
    # regardless of whether it passed the fit gate.
    for j in new_jobs:
        seen.add(j.job_id)
    seen.save()
    ledger.save()

    result = {"found": len(jobs), "new": len(new_jobs), "fit": len(passed),
              "tailored": tailored, "submitted": submitted,
              "threshold": policy["threshold"]}
    if verbose:
        print("FOUND: %d | NEW: %d | FIT>=%s: %d | TAILORED: %d"
              % (result["found"], result["new"], _fmt(policy["threshold"]),
                 result["fit"], result["tailored"]))
    return result
