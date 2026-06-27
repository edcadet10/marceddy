"""MarcEddy — a fully autonomous job-application agent.

DRY-RUN by default. MarcEddy searches real job sources, scores each opening
against the user's true resume, tailors a resume per role, dedups what it has
already seen, keeps a ledger, tracks application status from email, produces a
status digest, and improves its own matching policy from recorded outcomes.

Real application submission and account creation are gated behind an explicit
``--submit`` flag that is OFF by default and is never auto-triggered.
"""

__version__ = "0.1.0"
__agent_name__ = "MarcEddy"
