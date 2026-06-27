"""Fit scoring: how well a job matches the user's true profile.

Score is a weighted blend in [0,1] of four interpretable features. The weights
and threshold live in the policy and are tuned by the self-improvement loop.
"""

# Tokens that signal an on-target role for an entry-level IT / support / junior dev.
TARGET_ROLE_TOKENS = [
    "support", "help desk", "helpdesk", "service desk", "desktop", "technician",
    "systems administrator", "sysadmin", "system administrator", "it ",
    "information technology", "network", "noc", "junior", "associate", "entry",
    "python", "developer", "engineer", "analyst",
]

# Tokens that signal a role above the user's current level (down-weighted).
SENIOR_TOKENS = [
    "senior", "sr.", "sr ", "staff", "principal", "lead ", " lead", "director",
    "head of", "manager", "vp ", "vice president", "architect",
]


def features(job, profile):
    text = job.text_blob()
    title = (job.title or "").lower()
    skills = profile.get("skills", [])
    matched = [s for s in skills if s.lower() in text]
    skill_ratio = min(1.0, len(matched) / 5.0)
    # Title/seniority token lists are per-profile so the scorer fits the field:
    # IT defaults for Ed, a beauty set for Sarah (else "Beauty Advisor" never
    # matches an IT token and is wrongly scored 0.4).
    target_tokens = profile.get("target_role_tokens") or TARGET_ROLE_TOKENS
    senior_tokens = profile.get("senior_tokens") or SENIOR_TOKENS
    title_score = 1.0 if any(t in title for t in target_tokens) else 0.4
    seniority = 0.2 if any(t in title for t in senior_tokens) else 1.0
    # onsite_ok profiles (e.g. retail) aren't penalized for on-site roles.
    if profile.get("onsite_ok"):
        remote = 1.0
    else:
        remote = 1.0 if job.remote else 0.6
    return {
        "skills": skill_ratio,
        "title": title_score,
        "seniority": seniority,
        "remote": remote,
        "matched_skills": matched,
    }


def score_job(job, profile, policy):
    f = features(job, profile)
    w = policy["weights"]
    s = (w["skills"] * f["skills"] + w["title"] * f["title"]
         + w["seniority"] * f["seniority"] + w["remote"] * f["remote"])
    return round(min(1.0, max(0.0, s)), 4)


def meets(job, profile, policy):
    return score_job(job, profile, policy) >= policy["threshold"]
