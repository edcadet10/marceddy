"""Email-based status tracking.

PRIVACY: we read only message *headers* (From / Subject / Date). Message bodies
are never parsed, returned, logged, or printed. Status is inferred from the
subject line alone, which is enough to detect replies, interviews, and
rejections without ever touching private content.
"""
import email
import re
from email import policy as email_policy
from pathlib import Path

INTERVIEW_RE = re.compile(
    r"\b(interview|schedule a call|phone screen|technical screen|meet with|"
    r"availability|next steps|move forward to)\b", re.I)
REJECT_RE = re.compile(
    r"\b(unfortunately|not moving forward|other candidates|won'?t be moving|"
    r"decided (?:to )?(?:not|to go)|regret to inform|position has been filled|"
    r"no longer (?:being )?consider)", re.I)
REPLY_RE = re.compile(r"^\s*re:", re.I)


def parse_headers(path):
    """Return ONLY safe header metadata. Body is intentionally never read."""
    msg = email.message_from_bytes(Path(path).read_bytes(), policy=email_policy.default)
    return {
        "from": str(msg.get("From", "")),
        "subject": str(msg.get("Subject", "")),
        "date": str(msg.get("Date", "")),
        "path": str(path),
    }


def scan_mailbox(mailbox_dir):
    d = Path(mailbox_dir)
    msgs = []
    if not d.exists():
        return msgs
    for p in sorted(d.glob("*.eml")):
        msgs.append(parse_headers(p))
    return msgs


def classify(subject, from_addr=""):
    s = subject or ""
    if INTERVIEW_RE.search(s):
        return "interview"
    if REJECT_RE.search(s):
        return "rejected"
    if REPLY_RE.search(s):
        return "replied"
    return None


def _domain(addr):
    m = re.search(r"@([\w.-]+)", addr or "")
    return m.group(1).lower() if m else ""


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def match_row(msg, rows):
    frm, subj = msg.get("from", ""), msg.get("subject", "")
    dom = _domain(frm)
    dom_flat = dom.replace(".", "")
    frm_n, subj_n = _norm(frm), _norm(subj)
    fallback = None
    for r in rows:
        comp = _norm(r.get("company"))
        if not comp:
            continue
        if comp in frm_n or comp in subj_n:
            return r
        if comp in dom_flat or dom_flat.startswith(comp[:6]):
            fallback = fallback or r
        url_dom = _domain(r.get("url", ""))
        if url_dom and dom and url_dom.split(".")[0] == dom.split(".")[0]:
            fallback = fallback or r
    return fallback


def _sender_field(frm):
    # The From header (display name + address). A header field, never body text.
    return (frm or "").strip()


def link_and_update(messages, ledger, ts=None):
    """Match inbox messages to ledger rows and update their status.

    Returns a list of change dicts: {company, sender, old_status, new_status, job_id}.
    No message body is ever included.
    """
    changes = []
    for m in messages:
        new = classify(m.get("subject", ""), m.get("from", ""))
        if not new:
            continue
        row = match_row(m, ledger.all())
        if not row:
            continue
        old = row.get("status")
        ledger.update_status(row["job_id"], new, ts=ts,
                             last_email_from=_sender_field(m.get("from", "")))
        changes.append({
            "company": row.get("company"),
            "sender": _sender_field(m.get("from", "")),
            "old_status": old,
            "new_status": new,
            "job_id": row["job_id"],
        })
    return changes


def count_mailbox(path):
    """Count messages in a real on-disk mailbox (Maildir or a dir of .eml).

    Returns ONLY an integer count. Never reads message content.
    """
    p = Path(path)
    if not p.exists():
        return 0
    if (p / "cur").exists() or (p / "new").exists():
        n = 0
        for sub in ("cur", "new"):
            d = p / sub
            if d.exists():
                n += sum(1 for f in d.iterdir() if f.is_file())
        return n
    return sum(1 for _ in p.glob("*.eml"))


def count_imap(host, user, password, mailbox="INBOX", port=993):
    """Count messages in a real IMAP folder. Returns only an integer.

    Used by the real-mailbox smoke test when IMAP credentials are configured.
    Opens the folder read-only and never fetches message bodies.
    """
    import imaplib
    M = imaplib.IMAP4_SSL(host, port)
    try:
        M.login(user, password)
        M.select(mailbox, readonly=True)
        typ, data = M.search(None, "ALL")
        return len(data[0].split()) if data and data[0] else 0
    finally:
        try:
            M.logout()
        except Exception:
            pass


def send_self_email(host, port, username, password, to_addr, subject, body, attachments=None):
    """Send an email, optionally with file attachments. Caller guarantees
    to_addr is the user's own address (digests are never sent externally)."""
    import smtplib, os, mimetypes
    from email.message import EmailMessage
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = username
    msg["To"] = to_addr
    msg.set_content(body)
    for path in (attachments or []):
        try:
            with open(path, "rb") as f:
                data = f.read()
            ctype, _ = mimetypes.guess_type(path)
            maintype, subtype = (ctype or "application/octet-stream").split("/", 1)
            msg.add_attachment(data, maintype=maintype, subtype=subtype,
                               filename=os.path.basename(path))
        except Exception:
            pass
    s = smtplib.SMTP(host, port, timeout=30)
    try:
        s.ehlo()
        s.starttls()
        s.login(username, password)
        s.send_message(msg)
    finally:
        try:
            s.quit()
        except Exception:
            pass


def fetch_imap_headers(host, user, password, mailbox="INBOX", port=993, limit=200):
    """Fetch recent message HEADERS from a live IMAP folder (e.g. Gmail).

    PRIVACY: uses BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)] over a read-only
    folder, so message bodies are never fetched and messages are never marked
    read. Returns the same header dicts scan_mailbox() produces, so the existing
    classify / match / link logic is reused unchanged.
    """
    import imaplib
    msgs = []
    M = imaplib.IMAP4_SSL(host, port)
    try:
        M.login(user, password)
        M.select(mailbox, readonly=True)
        typ, data = M.search(None, "ALL")
        ids = data[0].split() if data and data[0] else []
        if limit and len(ids) > limit:
            ids = ids[-limit:]
        if not ids:
            return msgs
        typ, resp = M.fetch(b",".join(ids),
                            "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
        for part in resp or []:
            if not (isinstance(part, tuple) and len(part) >= 2):
                continue
            hdr = email.message_from_bytes(part[1], policy=email_policy.default)
            msgs.append({
                "from": str(hdr.get("From", "")),
                "subject": str(hdr.get("Subject", "")),
                "date": str(hdr.get("Date", "")),
                "path": "imap:%s" % mailbox,
            })
    finally:
        try:
            M.logout()
        except Exception:
            pass
    return msgs
