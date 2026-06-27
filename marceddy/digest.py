"""Status digest: an ACTIONABLE submit queue (apply links) + a status summary.

The point of the digest is that Ed can act straight from his inbox: each
ready-to-submit job shows its APPLY link, and report --email attaches the
tailored resume + cover letter so the materials travel with the email.
"""
import os
import re
from collections import defaultdict

HOURS_PER_YEAR = 2080.0


def _fit(r):
    try:
        return float(r.get("fit_score") or 0)
    except (TypeError, ValueError):
        return 0.0


def hourly_pay(salary):
    """Best-effort hourly rate from a free-text salary string; None if unknown.
    Uses the UPPER bound of a range (a posting 'pays above $30' if its top does)."""
    s = (salary or "").lower().replace(",", "")
    nums = [float(x) for x in re.findall(r"\$?\s*(\d+(?:\.\d+)?)", s)]
    nums = [n for n in nums if n > 0]
    if not nums:
        return None
    val = max(nums)
    if "hour" in s or "/hr" in s or "hr" in s:
        return val
    if "year" in s or "annual" in s or "/yr" in s or " yr" in s:
        return val / HOURS_PER_YEAR
    if "month" in s or "/mo" in s:
        return val * 12 / HOURS_PER_YEAR
    if "week" in s:
        return val / 40.0
    return val / HOURS_PER_YEAR if val > 1000 else val  # bare big number => annual


def _qualifies(r, min_fit=0.0, min_hourly=0.0):
    """A row passes the digest filter if its fit and pay are strictly ABOVE the
    configured minimums. A job with no parseable salary can't be confirmed to pay
    above the floor, so it's excluded when a pay floor is set."""
    if min_fit and _fit(r) <= min_fit:
        return False
    if min_hourly:
        hp = hourly_pay(r.get("salary"))
        if hp is None or hp <= min_hourly:
            return False
    return True


def _location_line(r):
    """Where the job is: 'Remote' (with home base if the posting names one) or the
    on-site city/state. Ed wants this called out explicitly on every job."""
    loc = (r.get("location") or "").strip()
    is_remote = r.get("remote") in (True, "true", "True", "1", 1)
    if is_remote:
        if loc and loc.lower() not in ("remote", "anywhere", ""):
            return "Remote (%s)" % loc
        return "Remote"
    return loc or "see posting"


def _salary_line(r):
    """Salary shown for every job: the posting's figure when listed, otherwise a
    researched estimate, otherwise an explicit 'researching' note."""
    s = (r.get("salary") or "").strip()
    if not s:
        return "not listed — estimate pending"
    if r.get("salary_estimated"):
        basis = (r.get("salary_basis") or "researched market estimate").strip()
        return "%s  (estimated — %s)" % (s, basis)
    return s


def build_digest(ledger, state=None, new_only=False, min_fit=0.0, min_hourly=0.0):
    rows = ledger.all()
    state = state or {}
    last_ts = state.get("last_report_ts")

    all_ready = sorted([r for r in rows if r.get("status") == "ready_to_submit"],
                       key=_fit, reverse=True)
    ready = all_ready
    if new_only and last_ts:
        ready = [r for r in all_ready if (r.get("ready_ts") or "") > last_ts]
    if min_fit or min_hourly:
        ready = [r for r in ready if _qualifies(r, min_fit, min_hourly)]
    applied = [r for r in rows if r.get("status") == "applied"]

    L = []
    if min_fit or min_hourly:
        crit = []
        if min_fit:
            crit.append("fit > %.2f" % min_fit)
        if min_hourly:
            crit.append("pay > $%g/hr" % min_hourly)
        L.append("(filtered to: %s)" % ", ".join(crit))
    if ready:
        label = "new " if new_only else ""
        L.append("=== MarcEddy — %d %sapplication(s) ready to submit ===" % (len(ready), label))
        L.append("")
        L.append("WHAT TO DO: for each job, click APPLY, then upload the attached")
        L.append("resume and paste the attached cover letter, and hit submit (~1 min each).")
        L.append("")
        for i, r in enumerate(ready, 1):
            L.append("%d. %s — %s   (fit %.2f)" % (i, r.get("company"), r.get("title"), _fit(r)))
            L.append("   location: %s" % _location_line(r))
            L.append("   salary: %s" % _salary_line(r))
            L.append("   APPLY: %s" % (r.get("apply_target") or r.get("url") or "(no link)"))
            rp = os.path.basename(r.get("tailored_resume_path") or "") or "-"
            cp = os.path.basename(r.get("cover_letter_path") or "") or "-"
            L.append("   attached: %s | %s" % (rp, cp))
            L.append("")
    else:
        L.append("=== MarcEddy Status Digest ===")
        L.append("Nothing waiting to submit right now.")
        L.append("")

    L.append("--- summary ---")
    L.append("Tracked: %d | ready to submit: %d | applied: %d"
             % (len(rows), len(all_ready), len(applied)))
    if applied:
        for r in applied:
            L.append("  applied: %s — %s" % (r.get("company"), r.get("title")))

    recent = [r for r in rows
              if r.get("last_update_ts") and (not last_ts or r["last_update_ts"] > last_ts)
              and r.get("status") in ("replied", "interview", "rejected")]
    L.append("New replies since last run: %d" % len(recent))
    for r in recent:
        L.append("  - %s: %s (from %s)" % (r.get("company"), r.get("status"),
                                           r.get("last_email_from") or "?"))

    upcoming = [r for r in rows if r.get("status") == "interview"]
    L.append("Upcoming interviews: %d" % len(upcoming))
    for r in upcoming:
        L.append("  - %s — %s" % (r.get("company"), r.get("title")))

    return "\n".join(L)
