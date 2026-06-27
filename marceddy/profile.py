"""The master resume profile — the single source of TRUE content.

Tailoring only ever selects, reorders, or emphasizes items already present
here. Nothing in a tailored resume is invented; every skill, certification,
and bullet below is factual for the user. An on-disk ``profile.json`` in the
home dir may override this (e.g. to use a fuller real resume).
"""
import json

MASTER_PROFILE = {
    "name": "Ed Cadet",
    "email": "you@example.com",
    "phone": "",
    "location": "Columbus, OH",
    "summary": (
        "CompTIA A+ and Network+ certified IT support professional with hands-on "
        "experience troubleshooting Windows, networking, and cloud infrastructure, "
        "plus Python automation and full-stack SaaS engineering from building and "
        "operating production systems end to end."
    ),
    "certifications": [
        "CompTIA A+ (certified Dec 2025)",
        "CompTIA Network+ N10-009 (certified May 2026)",
        "CompTIA CIOS stackable credential (A+ and Network+)",
    ],
    "skills": [
        "Windows 11", "Active Directory", "Networking", "TCP/IP", "DNS", "DHCP",
        "Subnetting", "Help Desk", "Ticketing", "Troubleshooting", "Hardware",
        "Python", "FastAPI", "PostgreSQL", "Docker", "Linux", "Bash", "Git",
        "Azure", "GCP", "REST APIs", "Automation",
    ],
    "experience": [
        {
            "title": "Founder / Full-Stack Builder",
            "org": "TradeProof (Cadet Group LLC)",
            "dates": "2025-present",
            "bullets": [
                "Built and operate a FastAPI + PostgreSQL SaaS with Stripe billing and 50-state data pipelines.",
                "Run Docker blue/green zero-downtime deploys across GCP and Azure Linux VMs.",
                "Automated data ingestion and monitoring with Python, Bash, and cron/systemd timers.",
                "Hardened the stack: JWT auth, dependency pinning, IAP-only SSH, and audit logging.",
            ],
        },
        {
            "title": "IT / Infrastructure (self-directed)",
            "org": "Home lab & cloud",
            "dates": "2024-present",
            "bullets": [
                "Configured and troubleshot Windows 11, networking (DNS/DHCP/subnetting), and Linux servers.",
                "Managed Git workflows, SSH, and remote administration of cloud instances.",
            ],
        },
    ],
    "education": [
        "CompTIA certification track (A+, Network+) - completed 2025-2026",
    ],
}


def load_profile(config):
    p = config.home / "profile.json"
    if p.exists():
        try:
            d = json.loads(p.read_text())
            if d.get("skills") and d.get("name"):
                return d
        except Exception:
            pass
    return MASTER_PROFILE
