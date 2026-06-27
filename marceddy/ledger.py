"""The application ledger: one row per job, persisted as JSON + CSV.

Every row carries the fields the goal requires: source, company, title, url,
fit_score, tailored_resume_path, status, first_seen_ts, account_email (plus a
few operational fields for status tracking).
"""
import csv
import io
import json

LEDGER_FIELDS = [
    "job_id", "source", "company", "title", "url", "fit_score",
    "tailored_resume_path", "status", "first_seen_ts", "account_email",
    "last_update_ts", "last_email_from", "notes",
    "salary", "salary_estimated", "salary_basis", "location", "remote",
]


class Ledger:
    def __init__(self, config, rows=None):
        self.config = config
        self.rows = rows or []
        self._index = {r["job_id"]: r for r in self.rows}

    @classmethod
    def load(cls, config):
        p = config.ledger_json
        rows = []
        if p.exists():
            try:
                rows = json.loads(p.read_text())
            except Exception:
                rows = []
        return cls(config, rows)

    def get(self, jid):
        return self._index.get(jid)

    def upsert(self, row):
        jid = row["job_id"]
        if jid in self._index:
            self._index[jid].update({k: v for k, v in row.items() if v is not None})
        else:
            self.rows.append(row)
            self._index[jid] = row
        return self._index[jid]

    def update_status(self, jid, status, ts=None, **extra):
        r = self._index.get(jid)
        if not r:
            return None
        old = r.get("status")
        r["status"] = status
        if ts:
            r["last_update_ts"] = ts
        for k, v in extra.items():
            r[k] = v
        return old

    def all(self):
        return list(self.rows)

    def to_csv(self):
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=LEDGER_FIELDS)
        w.writeheader()
        for r in self.rows:
            w.writerow({k: r.get(k, "") for k in LEDGER_FIELDS})
        return buf.getvalue()

    def save(self):
        self.config.ledger_json.write_text(json.dumps(self.rows, indent=2))
        self.config.ledger_csv.write_text(self.to_csv())
