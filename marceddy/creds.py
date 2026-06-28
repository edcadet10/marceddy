"""Local credentials store.

The file is created with 0600 permissions and holds ONLY structure/placeholders
by default (no real secrets). Any value under a secret-looking key is redacted
when displayed. MarcEddy never prints a real secret.
"""
import json
import os

SECRET_KEY_HINTS = ("password", "passwd", "secret", "token", "api_key",
                    "apikey", "app_password", "key", "credential")


def is_secret_key(k):
    kl = (k or "").lower()
    return any(h in kl for h in SECRET_KEY_HINTS)


def default_creds(config):
    return {
        "version": 1,
        "note": "Local secrets for MarcEddy. Placeholders only; fill via a secret "
                "manager or env. Never commit. File is chmod 600.",
        "accounts": {
            "primary": {
                "address": config.account_email,
                "imap_host": "imap.gmail.com",
                "imap_port": 993,
                "app_password": "",
            }
        },
        "job_sources": {
            "arbeitnow": {"api_key": ""},
            "remotive": {"api_key": ""},
            "usajobs": {"email": config.account_email, "api_key": "",
                        "note": "Free API key at developer.usajobs.gov/apirequest "
                                "(email is sent as the required User-Agent)."},
            "careeronestop": {"token": "", "user_id": "",
                              "note": "Free token + userId at careeronestop.org/"
                                      "Developers/WebAPI (US Dept. of Labor job postings)."},
            "jsearch": {"api_key": "",
                        "note": "RapidAPI key for JSearch (Google for Jobs: "
                                "Indeed + LinkedIn). Free tier at rapidapi.com."},
        },
        "smtp": {"host": "smtp.gmail.com", "port": 587,
                 "username": config.account_email, "password": ""},
        "submit": {"enabled": False,
                   "note": "Real submission requires --submit AND enabled:true"},
        "outreach": {"enabled": False,
                     "note": "Recruiter outreach send requires --send AND enabled:true; "
                             "even then this build only test-sends to your own address"},
    }


def ensure_creds(config):
    p = config.creds_path
    if not p.exists():
        p.write_text(json.dumps(default_creds(config), indent=2))
    os.chmod(p, 0o600)
    return p


def load_creds(config):
    if config.creds_path.exists():
        try:
            return json.loads(config.creds_path.read_text())
        except Exception:
            return {}
    return {}


def redact(obj):
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if is_secret_key(k):
                out[k] = "***REDACTED***" if v not in (None, "", [], {}) else "<empty>"
            else:
                out[k] = redact(v)
        return out
    if isinstance(obj, list):
        return [redact(x) for x in obj]
    return obj


def redacted_view(config):
    return redact(load_creds(config))
