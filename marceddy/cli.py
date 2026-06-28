"""MarcEddy command-line interface.

Subcommands: scan, report, learn (+ search, email-scan, creds, init).
DRY-RUN by default; real submission only with --submit (off by default).
"""
import argparse
import json
import os
import socket
import sys
from pathlib import Path

from . import __version__
from .apply import prepare_applications, submit_applications
from .config import Config
from .creds import ensure_creds, redacted_view
from .digest import build_digest, _qualifies
from .email_track import (count_imap, count_mailbox, fetch_imap_headers,
                          link_and_update, scan_mailbox, send_self_email)
from .ledger import Ledger
from .outreach import prepare_outreach, send_gate
from .policy import learn, load_policy, outcomes_from_ledger, save_policy
from .profile import load_profile
from .pipeline import run_scan
from .sources import (PKG_DIR, get_source, resolve_company,
                      load_company_registry, CompanyRegistrySource)

BANNER = ("MarcEddy - autonomous job-application agent (DRY-RUN by default; "
          "real submit/account-creation only behind --submit, off by default).")


def _instance_label():
    """Short tag identifying which machine sent an email, so digests from two
    instances (e.g. ed-home vs. an Azure box) are distinguishable in one inbox.
    Defaults to the hostname; override with MARCEDDY_INSTANCE."""
    return (os.environ.get("MARCEDDY_INSTANCE") or socket.gethostname() or "marceddy").strip()


def _subject(text):
    """Prefix an email subject with the instance label, e.g. '[ed-home] ...'."""
    return "[%s] %s" % (_instance_label(), text)

FIXTURE_MAILBOX = PKG_DIR / "data" / "mailbox"


def _utcnow():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _report_filters(cfg):
    """Per-home digest thresholds from config.json: only email jobs whose fit and
    hourly pay are above these floors (0 = no filter). Used for Sarah's home."""
    if cfg.config_path.exists():
        try:
            d = json.loads(cfg.config_path.read_text())
            return float(d.get("min_fit") or 0), float(d.get("min_hourly_pay") or 0)
        except Exception:
            pass
    return 0.0, 0.0


def build_parser():
    p = argparse.ArgumentParser(
        prog="marceddy", description=BANNER,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="MarcEddy never submits applications or creates accounts unless "
               "--submit is passed (off by default) AND credentials enable it. "
               "Status digests are emailed only to your own address.")
    p.add_argument("--version", action="version", version="MarcEddy %s" % __version__)
    p.add_argument("--home", default=None, help="data home (default ~/.marceddy)")
    sub = p.add_subparsers(dest="command", metavar="{scan,report,learn,apply,autofill,search,email-scan,creds,init}")

    sp = sub.add_parser("scan", help="search sources, score fit, tailor resumes (dry-run)")
    sp.add_argument("--source", default="fixture",
                    help="us|muse|greenhouse|remoteok|jobicy|jsearch|remotive|arbeitnow|fixture")
    sp.add_argument("--query", default="")
    sp.add_argument("--limit", type=int, default=25)
    sp.add_argument("--no-tailor", action="store_true")
    sp.add_argument("--submit", action="store_true",
                    help="DANGER: enable real submission (off by default; also needs creds submit.enabled)")

    rp = sub.add_parser("report", help="print status digest (by status, new replies, upcoming interviews)")
    rp.add_argument("--email", action="store_true",
                    help="email the digest to your own address only (dry-run prints the intent)")
    rp.add_argument("--heartbeat", action="store_true",
                    help="with --email, also send a short 'no new matches this scan' note when nothing new is found")

    lp = sub.add_parser("learn", help="update the versioned policy from recorded outcomes")
    lp.add_argument("--outcomes", default=None, help="path to outcomes JSON (else derive from ledger)")

    scp = sub.add_parser("search", help="live source smoke test: print real jobs")
    scp.add_argument("--source", default="arbeitnow")
    scp.add_argument("--query", default="")
    scp.add_argument("--limit", type=int, default=5)

    ep = sub.add_parser("email-scan", help="link inbox messages to applications and update status")
    ep.add_argument("--mailbox", default=None, help="dir of .eml files (default: bundled fixture)")
    ep.add_argument("--live", action="store_true",
                    help="read your real Gmail inbox over IMAP (headers only) and link to applications")
    ep.add_argument("--limit", type=int, default=200,
                    help="max recent messages to fetch in --live mode")
    ep.add_argument("--real", action="store_true",
                    help="real-mailbox mode: print ONLY a scanned-message count")

    app = sub.add_parser("apply", help="prepare a full application for every fit job; real submit gated")
    app.add_argument("--submit", action="store_true",
                     help="DANGER: actually transmit applications (needs creds submit.enabled; email channel only)")
    app.add_argument("--limit", type=int, default=None)

    afp = sub.add_parser("autofill", help="fill an application form in a browser (demo target; submit gated behind --confirm)")
    afp.add_argument("--demo", action="store_true", help="use the local sandbox demo form (safe)")
    afp.add_argument("--job", default=None, help="ledger job_id (default: first ready_to_submit)")
    afp.add_argument("--url", default=None, help="override target URL (real ATS targets discouraged from this datacenter IP)")
    afp.add_argument("--confirm", action="store_true", help="click submit (demo form only; real employers need your own machine + review)")

    smp = sub.add_parser("salary-missing",
                         help="print JSON of ready jobs that have no salary yet (for research)")
    smp.add_argument("--status", default="ready_to_submit",
                     help="ledger status to scan (default ready_to_submit)")
    smp.add_argument("--limit", type=int, default=0,
                     help="cap how many to return (0 = all); bounds per-run research cost")

    sap = sub.add_parser("salary-apply",
                         help="merge researched salary estimates (JSON job_id->{salary,basis}) into the ledger")
    sap.add_argument("file", help="path to the estimates JSON file")

    op = sub.add_parser("outreach",
                        help="find a hiring contact per ready job + prepare a short tailored email (gated send)")
    op.add_argument("--limit", type=int, default=5)
    op.add_argument("--dry-run", action="store_true", help="prepare only; never transmit (default behavior)")
    op.add_argument("--send", action="store_true",
                    help="DANGER: attempt real send (needs creds outreach.enabled; recruiter delivery still gated to a no-op)")

    ocp = sub.add_parser("outreach-companies",
                         help="print JSON of distinct companies for the top-N ready jobs (feeds the Apollo discovery bridge)")
    ocp.add_argument("--limit", type=int, default=5)

    rcp = sub.add_parser("resolve-company",
                         help="detect a company's ATS backend+slug (light ATS only; Workday needs manual triple)")
    rcp.add_argument("name", help="company display name, e.g. 'Datadog'")
    rcp.add_argument("--slug", help="override the slug guessed from the name")
    rcp.add_argument("--add", action="store_true",
                     help="append the resolved entry to <home>/companies.json")

    cmp = sub.add_parser("companies", help="list the company registry and live job counts")
    cmp.add_argument("--check", action="store_true", help="actually hit each backend and count jobs")

    sub.add_parser("creds", help="show credentials store structure (secrets redacted)")
    sub.add_parser("init", help="initialize home, policy, and creds store")
    return p


def _cfg(args):
    return Config(home=args.home)


def cmd_scan(args, cfg):
    ensure_creds(cfg)
    run_scan(cfg, source_name=args.source, query=args.query, limit=args.limit,
             tailor=not args.no_tailor, submit=args.submit)
    return 0


def cmd_report(args, cfg):
    ledger = Ledger.load(cfg)
    state = cfg.load_state()
    last_ts = state.get("last_report_ts")
    mf, mh = _report_filters(cfg)
    if not args.email:
        print(build_digest(ledger, state, new_only=False, min_fit=mf, min_hourly=mh))
        return 0
    # --email: only notify about NEW ready jobs / replies since the last email,
    # so the hourly digest never re-sends the same jobs. Per-home thresholds
    # (mf/mh) further restrict what gets emailed (e.g. Sarah: fit>0.6, pay>$30/hr).
    ready = [r for r in ledger.all() if r.get("status") == "ready_to_submit"]
    new_ready = [r for r in ready if (r.get("ready_ts") or "") > (last_ts or "")
                 and _qualifies(r, mf, mh)]
    new_replies = [r for r in ledger.all()
                   if r.get("last_update_ts") and (not last_ts or r["last_update_ts"] > last_ts)
                   and r.get("status") in ("replied", "interview", "rejected")]
    if not new_ready and not new_replies:
        base = "[report --email] Nothing new since last digest — %d still queued." % len(ready)
        if not getattr(args, "heartbeat", False):
            print(base + " No email sent.")
            return 0
        # Heartbeat: confirm the scan ran even when nothing matched, so Ed isn't
        # left wondering whether MarcEddy is alive on a quiet hour.
        to = cfg.account_email
        smtp = (json.loads(Path(cfg.creds_path).read_text()).get("smtp", {})
                if Path(cfg.creds_path).exists() else {})
        subject = _subject("MarcEddy — no new matches this scan (%d in queue)" % len(ready))
        body = ("MarcEddy just ran its scan and found no new roles matching your filters this time.\n\n"
                "Ready-to-submit queue: %d job(s) still waiting for you.\n"
                "Last new matches were sent %s.\n\n"
                "I'll keep scanning every hour and email the moment something new fits."
                % (len(ready), last_ts or "earlier"))
        if not smtp.get("password"):
            print(base + " [heartbeat] no smtp password configured; printed only.")
            return 0
        try:
            send_self_email(smtp.get("host", "smtp.gmail.com"), int(smtp.get("port", 587)),
                            smtp.get("username", to), smtp["password"], to, subject, body,
                            attachments=[])
            print(base + " [heartbeat] sent 'no new matches' note to %s." % to)
        except Exception as e:
            print(base + " [heartbeat] send FAILED: %s." % type(e).__name__)
        return 0
    digest = build_digest(ledger, state, new_only=True, min_fit=mf, min_hourly=mh)
    print(digest)
    to = cfg.account_email
    smtp = (json.loads(Path(cfg.creds_path).read_text()).get("smtp", {})
            if Path(cfg.creds_path).exists() else {})
    if not smtp.get("password"):
        print("\n[report --email] No smtp password configured; printed only.")
        return 0
    attach = []
    for r in new_ready:
        for p in (r.get("cover_letter_path"), r.get("tailored_resume_path")):
            if p and Path(p).exists():
                attach.append(p)
    subject = _subject(("MarcEddy — %d new job(s) ready to submit" % len(new_ready)) if new_ready
                       else ("MarcEddy — %d new update(s)" % len(new_replies)))
    try:
        send_self_email(smtp.get("host", "smtp.gmail.com"), int(smtp.get("port", 587)),
                        smtp.get("username", to), smtp["password"], to, subject, digest,
                        attachments=attach)
        print("\n[report --email] Sent %d new job(s) + %d attachment(s) to %s (your own address only)."
              % (len(new_ready), len(attach), to))
        state["last_report_ts"] = __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        cfg.save_state(state)
    except Exception as e:
        print("\n[report --email] send FAILED: %s." % type(e).__name__)
    return 0


def cmd_learn(args, cfg):
    profile = load_profile(cfg)
    if args.outcomes:
        outcomes = json.loads(Path(args.outcomes).read_text())
    else:
        outcomes = outcomes_from_ledger(Ledger.load(cfg))
    policy = load_policy(cfg)
    old_v = policy.get("version", 1)
    new_policy, log = learn(policy, outcomes, profile=profile)
    save_policy(cfg, new_policy)
    print("=== MarcEddy self-improvement ===")
    print("outcomes fed: %d" % len(outcomes))
    if not log:
        print("no actionable signal; policy unchanged (version %d)" % old_v)
        return 0
    for e in log:
        print("  outcome[%s] -> %s: %s -> %s"
              % (e["outcome"], e["adjustment"], e["old"], e["new"]))
    print("policy_version: %d -> %d" % (old_v, new_policy["version"]))
    print("threshold: %s | weights: %s" % (new_policy["threshold"], new_policy["weights"]))
    if new_policy["tailoring_keywords"]:
        print("tailoring_keywords: %s" % ", ".join(new_policy["tailoring_keywords"]))
    return 0


def cmd_search(args, cfg):
    source = get_source(args.source, cfg)
    jobs = source.fetch(args.query, args.limit)
    print("LIVE SEARCH source=%s query=%r -> %d job(s)" % (source.name, args.query, len(jobs)))
    print("attribution: %s" % source.attribution)
    for j in jobs:
        print("  - %s | %s | %s" % (j.title, j.company, j.url))
    return 0 if jobs else 1


def cmd_email_scan(args, cfg):
    if args.live:
        # Live Gmail over IMAP. Headers only (FROM/SUBJECT/DATE), read-only.
        ensure_creds(cfg)
        acct = json.loads(Path(cfg.creds_path).read_text()).get(
            "accounts", {}).get("primary", {})
        if not acct.get("app_password"):
            print("EMAIL-SCAN live: no app_password in credentials.json "
                  "(accounts.primary.app_password). Add a Gmail App Password first.")
            return 1
        host = acct.get("imap_host", "imap.gmail.com")
        port = int(acct.get("imap_port", 993))
        user = acct.get("address", cfg.account_email)
        if args.real:
            n = count_imap(host, user, acct["app_password"], "INBOX", port)
            print("SCANNED_MESSAGES: %d" % n)
            print("(live real-mailbox mode prints only a count; no headers or bodies shown.)")
            return 0
        ledger = Ledger.load(cfg)
        msgs = fetch_imap_headers(host, user, acct["app_password"], "INBOX", port,
                                  limit=args.limit)
        ts = __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        changes = link_and_update(msgs, ledger, ts=ts)
        ledger.save()
        print("EMAIL-SCAN source=imap:%s/INBOX scanned=%d linked=%d"
              % (host, len(msgs), len(changes)))
        for c in changes:
            print("  %s | from %s | %s -> %s"
                  % (c["company"], c["sender"], c["old_status"], c["new_status"]))
        return 0
    if args.real:
        # Real-mailbox smoke test: count ONLY. Never reads bodies.
        target = args.mailbox or str(cfg.maildir)
        n = count_mailbox(target)
        print("SCANNED_MESSAGES: %d" % n)
        print("(real-mailbox mode prints only a count; no headers or bodies shown. "
              "IMAP supported when credentials are configured.)")
        return 0
    mailbox = args.mailbox or str(FIXTURE_MAILBOX)
    ledger = Ledger.load(cfg)
    msgs = scan_mailbox(mailbox)
    ts = __import__("datetime").datetime.now(
        __import__("datetime").timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    changes = link_and_update(msgs, ledger, ts=ts)
    ledger.save()
    print("EMAIL-SCAN mailbox=%s scanned=%d linked=%d" % (mailbox, len(msgs), len(changes)))
    for c in changes:
        print("  %s | from %s | %s -> %s"
              % (c["company"], c["sender"], c["old_status"], c["new_status"]))
    return 0


def cmd_apply(args, cfg):
    profile = load_profile(cfg)
    prepared = prepare_applications(cfg, profile, limit=args.limit)
    print("PREPARED applications for %d fit job(s) (status: ready_to_submit)" % len(prepared))
    for p in prepared[:60]:
        print("  - %s | %s | apply via %s: %s"
              % (p["company"], p["title"], p["method"], p["target"]))
    submit_applications(cfg, profile, do_submit=args.submit)
    return 0


def cmd_autofill(args, cfg):
    from .autofill import ensure_demo_form, fill_application, mark_applied
    profile = load_profile(cfg)
    ledger = Ledger.load(cfg)
    ready = [r for r in ledger.all() if r.get("status") == "ready_to_submit"]
    row = ledger.get(args.job) if args.job else (ready[0] if ready else None)
    if not row:
        print("autofill: no ready_to_submit application found (run `marceddy apply` first).")
        return 1
    real = not args.demo
    if args.demo:
        target = "file://" + str(ensure_demo_form(cfg))
    else:
        target = args.url or row.get("apply_target") or row.get("url")
        print("autofill: WARNING real target. Most ATS forms use reCAPTCHA and recruiters' "
              "bot-detection flags datacenter IPs like this box; run on your own machine for real applies.")
    res = fill_application(cfg, profile, row, target, confirm=args.confirm)
    print("AUTOFILL job=%s | company=%s | target=%s"
          % (res["job_id"], row.get("company"), "demo-form" if args.demo else target))
    print("  fields entered:")
    for k, v in res["entered"].items():
        print("    %-12s = %s" % (k, v))
    print("  screenshot:    %s" % res["screenshot"])
    print("  html artifact: %s" % res["html"])
    if args.confirm and args.demo and res["submitted"]:
        mark_applied(cfg, row["job_id"])
        print("  SUBMITTED (demo form) -> ledger status: applied")
    elif args.confirm and real:
        print("  real-target auto-submit is intentionally NOT performed (ToS + datacenter-IP risk); "
              "review the filled form and submit it yourself.")
        print("AWAITING HUMAN CONFIRM — 0 applications submitted")
    else:
        print("AWAITING HUMAN CONFIRM — 0 applications submitted")
    return 0


def cmd_salary_missing(args, cfg):
    ledger = Ledger.load(cfg)
    out = []
    for r in ledger.all():
        if r.get("status") == args.status and not (r.get("salary") or "").strip():
            out.append({
                "job_id": r.get("job_id"), "title": r.get("title"),
                "company": r.get("company"), "location": r.get("location") or "",
                "url": r.get("apply_target") or r.get("url") or "",
            })
    if getattr(args, "limit", 0) and args.limit > 0:
        out = out[:args.limit]
    print(json.dumps(out, indent=2))
    return 0


def cmd_salary_apply(args, cfg):
    path = Path(args.file)
    if not path.exists():
        print("salary-apply: file not found: %s" % path)
        return 1
    try:
        data = json.loads(path.read_text())
    except Exception as e:
        print("salary-apply: bad JSON (%s)" % type(e).__name__)
        return 1
    ledger = Ledger.load(cfg)
    ts = _utcnow()
    n = 0
    items = data.items() if isinstance(data, dict) else []
    for jid, info in items:
        row = ledger.get(jid)
        if not row or not isinstance(info, dict):
            continue
        sal = (info.get("salary") or "").strip()
        if not sal:
            continue
        row["salary"] = sal
        row["salary_estimated"] = True
        row["salary_basis"] = (info.get("basis") or "researched estimate").strip()
        row["last_update_ts"] = ts
        n += 1
    ledger.save()
    print("salary-apply: updated %d job(s) with researched estimates" % n)
    return 0


def cmd_outreach(args, cfg):
    profile = load_profile(cfg)
    results = prepare_outreach(cfg, profile, limit=args.limit)
    for x in results:
        print("- %s | %s | tier=%s | contact=%s (%s) | email=%s | resume=%s | cover=%s | %dw"
              % (x["company"], x["title"], x["tier"],
                 x["contact_name"] or "(role only)", x["contact_role"],
                 os.path.basename(x["email_path"]),
                 os.path.basename(x["resume_path"]) or "-",
                 os.path.basename(x["cover_letter_path"]) or "-",
                 x["word_count"]))
    found = sum(1 for x in results if x["tier"] != "none")
    print("OUTREACH summary: processed=%d | contacts_found=%d | drafts_queued=%d"
          % (len(results), found, len(results)))
    if results:
        first = results[0]
        print("\n--- sample outreach email (%s — %s, %d words) ---"
              % (first["company"], first["title"], first["word_count"]))
        print(Path(first["email_path"]).read_text())
    send_gate(args, cfg, results)
    return 0


def cmd_outreach_companies(args, cfg):
    ledger = Ledger.load(cfg)
    ready = [r for r in ledger.all() if r.get("status") == "ready_to_submit"]
    ready.sort(key=lambda r: float(r.get("fit_score") or 0), reverse=True)
    seen, out = set(), []
    for r in ready:
        c = (r.get("company") or "").strip()
        if c and c not in seen:
            seen.add(c)
            out.append({"company": c, "location": r.get("location") or ""})
        if len(out) >= args.limit:
            break
    print(json.dumps(out, indent=2))
    return 0


def cmd_creds(args, cfg):
    path = ensure_creds(cfg)
    print("credentials store: %s (perms 600, secrets redacted)" % path)
    print(json.dumps(redacted_view(cfg), indent=2))
    return 0


def cmd_init(args, cfg):
    cfg.ensure_dirs()
    ensure_creds(cfg)
    save_policy(cfg, load_policy(cfg))
    # seed a real on-disk Maildir for the real-mailbox count smoke test
    (cfg.maildir / "new").mkdir(parents=True, exist_ok=True)
    (cfg.maildir / "cur").mkdir(parents=True, exist_ok=True)
    print("initialized MarcEddy home at %s" % cfg.home)
    print("  policy: %s" % cfg.policy_path)
    print("  creds:  %s" % cfg.creds_path)
    print("  maildir:%s" % cfg.maildir)
    return 0


def cmd_resolve_company(args, cfg):
    backend, slug, n = resolve_company(args.name, slug=args.slug)
    if not backend:
        print("UNRESOLVED  %s -- no light ATS hit. If it's an enterprise it is "
              "likely Workday: open its careers page, read the "
              "{tenant}.{dc}.myworkdayjobs.com/{site} URL, and add a workday entry "
              "to companies.json by hand." % args.name)
        return 1
    entry = {"name": args.name, "backend": backend, "slug": slug}
    print("RESOLVED  %s -> %s (%s)  %d jobs live" % (args.name, backend, slug, n))
    print(json.dumps(entry))
    if args.add:
        path = Path(cfg.home) / "companies.json"
        try:
            data = json.loads(path.read_text()) if path.exists() else {"companies": []}
        except Exception:
            data = {"companies": []}
        data.setdefault("companies", [])
        if not any(c.get("name") == args.name for c in data["companies"]):
            data["companies"].append(entry)
            path.write_text(json.dumps(data, indent=2))
            print("added to %s" % path)
        else:
            print("already in %s" % path)
    return 0


def cmd_companies(args, cfg):
    reg = load_company_registry()
    print("company registry: %d employers" % len(reg))
    for c in reg:
        if c.get("backend") == "oracle":
            ident = "%s/%s" % (c.get("host", "?"), c.get("site", "CX_1"))
        else:
            ident = c.get("slug") or "%s/%s/%s" % (c.get("tenant"), c.get("dc"), c.get("site"))
        tag = " [%s]" % c["local"] if c.get("local") else ""
        line = "  %-22s %-15s %s%s" % (c.get("name", "?"), c.get("backend", "?"), ident, tag)
        if args.check:
            try:
                if (c.get("backend") or "").lower() == "browser":
                    from .sources import BrowserRegistrySource
                    jobs = BrowserRegistrySource(registry=[c]).fetch(limit=999)
                else:
                    jobs = CompanyRegistrySource(registry=[c]).fetch(limit=999)
                line += "  -> %d US/remote jobs" % len(jobs)
            except Exception as e:
                line += "  -> ERROR %s" % str(e)[:40]
        print(line)
    return 0


COMMANDS = {
    "scan": cmd_scan, "report": cmd_report, "learn": cmd_learn,
    "apply": cmd_apply, "autofill": cmd_autofill, "search": cmd_search,
    "email-scan": cmd_email_scan, "creds": cmd_creds, "init": cmd_init,
    "salary-missing": cmd_salary_missing, "salary-apply": cmd_salary_apply,
    "outreach": cmd_outreach, "outreach-companies": cmd_outreach_companies,
    "resolve-company": cmd_resolve_company, "companies": cmd_companies,
}


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0
    cfg = _cfg(args)
    return COMMANDS[args.command](args, cfg)


if __name__ == "__main__":
    sys.exit(main())
