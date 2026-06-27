"""Browser auto-FILL for job applications (Playwright engine).

Fills an application form in a real (headless) browser from a queued ledger
application, screenshots it, saves the filled HTML, and STOPS before submitting
unless confirm=True.

Real submission to live employers is gated on purpose: it is irreversible, most
ATS/job platforms prohibit automated submission in their ToS, Greenhouse/Workday
gate forms with reCAPTCHA, and recruiters' bot-detection flags datacenter IPs
(this box). So by default MarcEddy only FILLS; a human reviews and submits.
"""
from datetime import datetime, timezone
from pathlib import Path

DEMO_FORM = """<!doctype html><html><head><meta charset="utf-8"><title>Demo Application</title></head>
<body><h3>Demo Application Form (sandbox)</h3>
<form id="appform" onsubmit="document.body.setAttribute('data-submitted','1');return false;">
  <label>Full name <input id="full_name" name="full_name"></label><br>
  <label>Email <input id="email" name="email" type="email"></label><br>
  <label>Phone <input id="phone" name="phone" type="tel"></label><br>
  <label>Resume <textarea id="resume" name="resume"></textarea></label><br>
  <label>Cover letter <textarea id="cover_letter" name="cover_letter"></textarea></label><br>
  <button id="submit_btn" type="submit">Submit Application</button>
</form></body></html>"""

SELECTORS = {
    "full_name": ["#full_name", "input[name='full_name']", "input[name='name']",
                  "input[autocomplete='name']"],
    "email": ["#email", "input[type='email']", "input[name='email']"],
    "phone": ["#phone", "input[type='tel']", "input[name='phone']"],
    "resume": ["#resume", "textarea[name='resume']", "textarea[name='summary']"],
    "cover_letter": ["#cover_letter", "textarea[name='cover_letter']",
                     "textarea[name='comments']", "textarea[name='message']"],
}


def ensure_demo_form(config):
    p = config.home / "demo_form.html"
    p.write_text(DEMO_FORM)
    return p


def _first(page, selectors):
    for s in selectors:
        try:
            if page.query_selector(s):
                return s
        except Exception:
            continue
    return None


def fill_application(config, profile, job_row, target_url, confirm=False):
    """Fill the form at target_url from the ledger row + profile. Returns a dict
    of what was entered, artifact paths, and whether a submit occurred."""
    from playwright.sync_api import sync_playwright
    outbox = config.home / "outbox"
    outbox.mkdir(parents=True, exist_ok=True)
    jid = job_row["job_id"]

    def _text_of(path):
        if not path:
            return ""
        if path.endswith(".docx"):
            sib = path[:-5] + ".txt"
            if Path(sib).exists():
                return Path(sib).read_text()
            try:
                import docx
                return "\n".join(p.text for p in docx.Document(path).paragraphs)
            except Exception:
                return ""
        return Path(path).read_text() if Path(path).exists() else ""

    resume_text = _text_of(job_row.get("tailored_resume_path"))
    cover_text = _text_of(job_row.get("cover_letter_txt") or job_row.get("cover_letter_path"))

    values = {
        "full_name": profile.get("name", ""),
        "email": profile.get("email", ""),
        "phone": profile.get("phone", ""),
        "resume": resume_text,
        "cover_letter": cover_text,
    }
    shot = str(outbox / ("%s_filled.png" % jid))
    htmlp = str(outbox / ("%s_filled.html" % jid))
    entered, submitted = {}, False

    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        pg = b.new_page()
        pg.goto(target_url)
        for key, val in values.items():
            if not val:
                continue
            sel = _first(pg, SELECTORS[key])
            if not sel:
                continue
            try:
                pg.fill(sel, val[:4000])
                entered[key] = pg.input_value(sel)[:80]
            except Exception:
                pass
        try:
            pg.screenshot(path=shot, full_page=True)
        except Exception:
            pass
        try:
            Path(htmlp).write_text(pg.content())
        except Exception:
            pass
        if confirm:
            sb = _first(pg, ["#submit_btn", "button[type='submit']", "input[type='submit']"])
            if sb:
                try:
                    pg.click(sb)
                    pg.wait_for_timeout(300)
                except Exception:
                    pass
            submitted = pg.query_selector("body[data-submitted='1']") is not None
        b.close()

    return {"job_id": jid, "entered": entered, "screenshot": shot,
            "html": htmlp, "submitted": submitted, "confirm": confirm}


def mark_applied(config, job_id):
    from .ledger import Ledger
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    led = Ledger.load(config)
    led.update_status(job_id, "applied", ts=ts)
    led.save()
