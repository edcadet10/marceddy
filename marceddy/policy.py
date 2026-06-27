"""The versioned matching policy and the self-improvement loop.

The policy holds the fit threshold, feature weights, and learned emphasis
keywords. ``learn`` takes recorded outcomes (interview/offer/rejected/ghosted),
nudges the policy, increments ``version``, and records an improvement log
mapping each outcome group to the adjustment it produced.
"""
import copy
import json

DEFAULT_POLICY = {
    "version": 1,
    "threshold": 0.35,
    "weights": {"skills": 0.40, "title": 0.35, "seniority": 0.15, "remote": 0.10},
    "tailoring_keywords": [],
    "improvement_log": [],
}


def load_policy(config):
    p = config.policy_path
    if p.exists():
        try:
            d = json.loads(p.read_text())
            for k, v in DEFAULT_POLICY.items():
                d.setdefault(k, copy.deepcopy(v))
            return d
        except Exception:
            pass
    return copy.deepcopy(DEFAULT_POLICY)


def save_policy(config, policy):
    config.policy_path.write_text(json.dumps(policy, indent=2))


def _renorm(weights, fixed):
    fixedv = weights[fixed]
    others = [k for k in weights if k != fixed]
    rem = 1.0 - fixedv
    cur = sum(weights[k] for k in others)
    if cur > 0:
        for k in others:
            weights[k] = round(weights[k] * rem / cur, 4)


def learn(policy, outcomes, profile=None):
    """Update policy from outcomes.

    outcomes: list of {company|job_id, status in
              interview/offer/rejected/ghosted, keywords?: [..]}.
    Returns (new_policy, log_entries). Increments version iff a change is made.
    """
    pol = copy.deepcopy(policy)
    log = []
    pos = [o for o in outcomes if o.get("status") in ("interview", "offer")]
    neg = [o for o in outcomes if o.get("status") in ("rejected", "ghosted")]

    # 1) Threshold recalibration from the positive/negative balance.
    old_t = pol["threshold"]
    delta = 0.0
    if pos and len(pos) >= len(neg):
        delta = -0.03   # our targeting is landing interviews -> widen the net
    elif neg and len(neg) > len(pos):
        delta = +0.03   # too many rejections -> be pickier
    if delta:
        pol["threshold"] = round(min(0.9, max(0.1, old_t + delta)), 4)
        log.append({"outcome": "%d interview/offer vs %d rejected/ghosted" % (len(pos), len(neg)),
                    "adjustment": "threshold", "old": old_t, "new": pol["threshold"]})

    # 2) Emphasize what is winning: bump skills weight + add true emphasis keywords.
    pos_kw = []
    for o in pos:
        pos_kw += (o.get("keywords") or [])
    if pos_kw:
        old_w = pol["weights"]["skills"]
        pol["weights"]["skills"] = round(min(0.7, old_w + 0.05), 4)
        _renorm(pol["weights"], "skills")
        log.append({"outcome": "interview/offer share keywords %s" % sorted(set(pos_kw)),
                    "adjustment": "weights.skills", "old": old_w, "new": pol["weights"]["skills"]})

        allowed = {s.lower() for s in profile["skills"]} if profile else None
        added = []
        for k in pos_kw:
            kk = (k or "").strip()
            if not kk:
                continue
            if allowed is not None and kk.lower() not in allowed:
                continue  # never add a keyword that is not a TRUE skill
            if kk not in pol["tailoring_keywords"]:
                pol["tailoring_keywords"].append(kk)
                added.append(kk)
        if added:
            log.append({"outcome": "emphasize winning keywords",
                        "adjustment": "tailoring_keywords += [%s]" % ", ".join(added),
                        "old": [], "new": added})

    if log:
        pol["version"] = policy.get("version", 1) + 1
        for e in log:
            e["policy_version"] = pol["version"]
        pol["improvement_log"] = policy.get("improvement_log", []) + [
            {"version": pol["version"], "changes": log}]
    return pol, log


def outcomes_from_ledger(ledger):
    """Derive learning outcomes from current ledger statuses (status -> signal)."""
    out = []
    for r in ledger.all():
        st = r.get("status")
        if st in ("interview", "offer", "rejected", "ghosted"):
            out.append({"company": r.get("company"), "job_id": r.get("job_id"),
                        "status": st, "keywords": []})
    return out
