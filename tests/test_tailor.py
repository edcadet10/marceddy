from marceddy.policy import DEFAULT_POLICY
from marceddy.profile import MASTER_PROFILE
from marceddy.sources import FixtureSource
from marceddy.tailor import (blocks_to_text, matched_skills, render_resume,
                             resume_basename, write_resume)

PROFILE = MASTER_PROFILE
POLICY = DEFAULT_POLICY


def _content(job):
    return blocks_to_text(render_resume(job, PROFILE, POLICY))


def _core_skills_line(content):
    lines = content.splitlines()
    i = lines.index("CORE SKILLS")
    j = i + 1
    while j < len(lines) and not lines[j].strip():
        j += 1
    return [s.strip() for s in lines[j].split(",")]


def test_no_fabricated_skills():
    job = FixtureSource().fetch()[0]
    items = _core_skills_line(_content(job))
    # every listed skill is a TRUE profile skill — nothing invented
    assert all(it in PROFILE["skills"] for it in items)
    assert set(items) == set(PROFILE["skills"])


def test_matched_skill_listed_first():
    job = FixtureSource().fetch()[0]
    items = _core_skills_line(_content(job))
    assert items[0] in matched_skills(job, PROFILE)


def test_objective_targets_job():
    job = FixtureSource().fetch()[0]
    content = _content(job)
    assert job.title in content and job.company in content
    assert PROFILE["name"] in content


def test_writes_docx_and_txt(cfg):
    job = FixtureSource().fetch()[0]
    path = write_resume(job, PROFILE, POLICY, cfg)
    assert path.endswith(".docx")
    base = resume_basename(job)
    assert (cfg.resumes_dir / (base + ".docx")).exists()
    assert (cfg.resumes_dir / (base + ".txt")).exists()
