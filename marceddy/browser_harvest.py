"""Headless-browser job harvester for ATSs that won't serve a clean no-auth JSON
board (Taleo, Phenom, SuccessFactors): load the careers page, let its own JS
fetch + render the listings, then read the rendered DOM.

This is the FALLBACK path, deliberately separate from the pure-JSON sources:
 - Slower and heavier (a real Chromium per site) -> run at low cadence, not hourly.
 - From a datacenter IP some ATSs (notably iCIMS) hard-block with a human-
   verification wall; those simply return [] here and need a residential IP
   (e.g. running MarcEddy on Ed's laptop).

No Playwright import at module load, so importing marceddy never requires it; the
dependency is only touched when harvest() actually runs.
"""
from .models import Job

# JS run in the page: collect plausible job rows generically across ATS DOMs.
_EXTRACT_JS = r"""
() => {
  const out = [];
  const seen = new Set();
  const anchors = Array.from(document.querySelectorAll(
    "a[href*='/job/'], a[href*='jobid'], a[href*='requisition'], a[data-ph-at-id='job-link'], a[href*='ftl']"));
  for (const a of anchors) {
    const title = (a.innerText || a.textContent || "").trim();
    const href = a.href || "";
    if (!title || title.length < 3 || title.length > 160) continue;
    if (seen.has(href)) continue;
    seen.add(href);
    // best-effort nearby location text
    let loc = "";
    const row = a.closest("li, tr, article, div[class*='job'], div[class*='result']");
    if (row) {
      const m = (row.innerText || "").match(/[A-Za-z .'-]+,\s*[A-Z]{2}(?:,\s*United States)?/);
      if (m) loc = m[0];
    }
    out.push({title, href, loc});
  }
  return out;
}
"""


def harvest(url, company, source="company", wait_ms=6000, timeout_ms=35000):
    """Return a list[Job] scraped from a rendered careers page. [] on block/error."""
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return []
    jobs = []
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(headless=True, args=[
                "--no-sandbox", "--disable-blink-features=AutomationControlled"])
            ctx = b.new_context(
                user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                            "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"),
                viewport={"width": 1366, "height": 900}, locale="en-US")
            # Light anti-headless-fingerprint shims. The dominant block signal is
            # datacenter-IP reputation (cleared by a residential IP); these reduce
            # the secondary headless tells so a home-server run has the best shot.
            ctx.add_init_script(
                "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
                "Object.defineProperty(navigator,'plugins',{get:()=>[1,2,3,4,5]});"
                "Object.defineProperty(navigator,'languages',{get:()=>['en-US','en']});"
                "window.chrome={runtime:{}};")
            pg = ctx.new_page()
            try:
                pg.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                pg.wait_for_timeout(wait_ms)
                html = (pg.content() or "").lower()
                title = (pg.title() or "").lower()
                if "human verification" in title or "are you a human" in html or "access denied" in title:
                    return []  # IP/bot wall -> caller treats as no coverage
                rows = pg.evaluate(_EXTRACT_JS) or []
            finally:
                b.close()
        for r in rows:
            t = (r.get("title") or "").strip()
            if not t:
                continue
            jobs.append(Job(source=source, company=company, title=t,
                            url=r.get("href", ""), location=r.get("loc", ""),
                            remote=("remote" in (r.get("loc", "") or "").lower())))
    except Exception:
        return []
    return jobs
