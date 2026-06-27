#!/usr/bin/env python3
"""Run this ON THE HOME SERVER (residential IP) to test whether the ATSs that
hard-block the Azure datacenter IP (iCIMS, SuccessFactors) are reachable there.

Usage:
    pip install playwright && playwright install chromium
    python3 probe_blocked_ats.py

It loads each site with a stealthier, non-headless-looking config and reports
http status, whether a human-verification wall appeared, and how many job rows
rendered. If iCIMS shows blocked=False with jobrows>0, the IP move worked and
we can wire those employers as browser entries.
"""
from playwright.sync_api import sync_playwright

TARGETS = {
    "iCIMS  (Hyland)":         "https://careers-hyland.icims.com/jobs/search?ss=1",
    "iCIMS  (Sarnova)":        "https://careers-sarnova.icims.com/jobs/search?ss=1",
    "SuccessFactors (Hexion)": "https://careers.hexion.com/",
    "SuccessFactors (NetJets)":"https://careers.netjets.com/",
    "Phenom (Battelle)":       "https://jobs.battelle.org/us/en/search-results",
}

STEALTH = """
Object.defineProperty(navigator,'webdriver',{get:()=>undefined});
Object.defineProperty(navigator,'plugins',{get:()=>[1,2,3,4,5]});
Object.defineProperty(navigator,'languages',{get:()=>['en-US','en']});
window.chrome = {runtime:{}};
"""

def run(name, url):
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True, args=[
            "--no-sandbox", "--disable-blink-features=AutomationControlled"])
        ctx = b.new_context(
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"),
            viewport={"width": 1366, "height": 900}, locale="en-US")
        ctx.add_init_script(STEALTH)
        pg = ctx.new_page()
        try:
            resp = pg.goto(url, wait_until="domcontentloaded", timeout=40000)
            pg.wait_for_timeout(7000)
            html = (pg.content() or "").lower()
            title = (pg.title() or "")
            blocked = any(s in (title.lower() + html) for s in
                          ("human verification", "are you a human", "access denied",
                           "just a moment", "verify you are", "unusual traffic"))
            rows = len(pg.query_selector_all(
                "a[href*='job'], li[class*='job'], div[class*='job'], [data-ph-at-id*='job']"))
            print(f"{name:26s} http={resp.status if resp else '?':>3} "
                  f"blocked={str(blocked):5s} jobrows~{rows:<4d} title='{title[:45]}'")
        except Exception as e:
            print(f"{name:26s} ERROR {str(e)[:60]}")
        finally:
            b.close()

if __name__ == "__main__":
    print("Probing from THIS machine's IP...\n")
    for n, u in TARGETS.items():
        run(n, u)
    print("\nIf iCIMS rows>0 & blocked=False, the residential IP cleared it — tell Claude to wire them.")
