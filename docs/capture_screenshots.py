"""
Automated screenshot capture for documentation.

Starts the Flask app, navigates to each key page, and saves targeted
screenshots showcasing 12 platform capabilities. Run after any UI changes:

    python docs/capture_screenshots.py
"""

import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:8080"
SCREENSHOT_DIR = Path(__file__).parent / "assets" / "screenshots"


def wait_for_server(url, timeout=15):
    import urllib.request
    import urllib.error

    start = time.time()
    while time.time() - start < timeout:
        try:
            urllib.request.urlopen(url, timeout=2)
            return True
        except (urllib.error.URLError, ConnectionError, OSError):
            time.sleep(0.5)
    return False


def shot(page, name, full_page=True):
    path = SCREENSHOT_DIR / f"{name}.png"
    page.screenshot(path=str(path), full_page=full_page)
    print(f"  ✓ {name}")


def js_scroll_to(page, selector):
    """Scroll to an element using JS — bypasses Playwright visibility checks."""
    page.evaluate(f"""() => {{
        const el = document.querySelector('{selector}');
        if (el) el.scrollIntoView({{ behavior: 'instant', block: 'center' }});
    }}""")
    time.sleep(0.3)


def switch_tab(page, index):
    """Switch to a tab by index (0-based) using JS."""
    page.evaluate(f"""() => {{
        const tabs = document.querySelectorAll('button.tab');
        const panels = document.querySelectorAll('.tabpanel');
        tabs.forEach((t, i) => {{
            t.setAttribute('aria-current', i === {index} ? 'true' : 'false');
        }});
        panels.forEach((p, i) => {{
            if (i === {index}) p.classList.add('active');
            else p.classList.remove('active');
        }});
    }}""")
    time.sleep(0.4)


def expand_card(page, index=0):
    """Expand a review card by index using JS."""
    page.evaluate(f"""() => {{
        const cards = document.querySelectorAll('.rcard');
        if (cards[{index}]) {{
            const grid = cards[{index}].querySelector('.rcard-grid');
            if (grid) grid.style.display = 'grid';
            const btn = cards[{index}].querySelector('[class*="expand"]');
            if (btn) btn.textContent = '▲';
        }}
    }}""")
    time.sleep(0.3)


def capture_screenshots():
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

    server_process = subprocess.Popen(
        [sys.executable, "app.py"],
        cwd=Path(__file__).parent.parent,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    try:
        print("Waiting for Flask server...")
        if not wait_for_server(BASE_URL):
            print("ERROR: Server did not start within 15 seconds.")
            server_process.terminate()
            sys.exit(1)

        print("Server is up. Capturing screenshots...\n")

        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1440, "height": 900})

            # ── FULL PAGE CAPTURES ────────────────────────────────────
            page.goto(f"{BASE_URL}/", wait_until="networkidle")
            shot(page, "home")

            page.goto(f"{BASE_URL}/ops", wait_until="networkidle")
            shot(page, "ops_dashboard")

            page.goto(f"{BASE_URL}/guide", wait_until="networkidle")
            shot(page, "guide_list")

            page.goto(f"{BASE_URL}/guide/India", wait_until="networkidle")
            shot(page, "guide_country")

            # ── OPS DASHBOARD — Review tab ────────────────────────────
            page.goto(f"{BASE_URL}/ops", wait_until="networkidle")
            switch_tab(page, 0)

            # ── FEATURE 1: REGULATORY RISK SCORING ────────────────────
            # Metrics cards + country severity pills at the top
            js_scroll_to(page, ".mgr")
            shot(page, "regulatory_risk_scoring", full_page=False)

            # ── FEATURE 2: MATERIALITY CLASSIFICATION ─────────────────
            # Review list showing severity badges and materiality chips
            js_scroll_to(page, ".review-list")
            shot(page, "materiality_classification", full_page=False)

            # ── FEATURE 3: GOVERNANCE REVIEW QUEUE ────────────────────
            # Expand first two review cards for richer view
            expand_card(page, 0)
            expand_card(page, 1)
            js_scroll_to(page, ".rcard")
            shot(page, "governance_review_queue", full_page=False)

            # ── FEATURE 4: SEMANTIC DIFF ENGINE ───────────────────────
            # Scroll to the diff panel inside the first expanded card
            js_scroll_to(page, ".diff")
            shot(page, "semantic_diff_engine", full_page=False)

            # ── FEATURE 5: AI RECOMMENDATION LAYER ────────────────────
            # Scroll to the AI reasoning sidebar (confidence + classification)
            js_scroll_to(page, ".rai")
            shot(page, "ai_recommendation_layer", full_page=False)

            # ── FEATURE 6: MANUAL OVERRIDE CONTROLS ───────────────────
            # Approve / Reject / Escalate buttons
            js_scroll_to(page, ".rcard-actions")
            shot(page, "manual_override_controls", full_page=False)

            # ── FEATURE 7: REVIEW RATIONALE CAPTURE ───────────────────
            # The audit-mini section within a card showing the approval chain
            js_scroll_to(page, ".audit-mini")
            shot(page, "review_rationale_capture", full_page=False)

            # ── FEATURE 8: DRIFT MONITORING DASHBOARD ─────────────────
            switch_tab(page, 1)
            # Expand drift table rows
            page.evaluate("""() => {
                document.querySelectorAll('.drift-table .parent').forEach(row => {
                    const detail = row.nextElementSibling;
                    if (detail && detail.classList.contains('detail-row')) {
                        detail.style.display = 'table-row';
                    }
                });
            }""")
            time.sleep(0.3)
            shot(page, "drift_monitoring_dashboard", full_page=False)

            # ── FEATURE 9: CMS SYNCHRONIZATION ───────────────────────
            # Open the sync modal
            page.evaluate("""() => {
                const scrim = document.querySelector('.modal-scrim');
                if (scrim) scrim.classList.add('open');
            }""")
            time.sleep(0.4)
            shot(page, "cms_synchronization", full_page=False)
            # Close modal
            page.evaluate("""() => {
                const scrim = document.querySelector('.modal-scrim');
                if (scrim) scrim.classList.remove('open');
            }""")
            time.sleep(0.2)

            # ── FEATURE 10: MULTI-SOURCE INGESTION (Pipeline tab) ─────
            switch_tab(page, 3)
            # Expand first pipeline job row
            page.evaluate("""() => {
                const rows = document.querySelectorAll('.pipe-table tbody tr.parent, .pipe-table tbody tr');
                if (rows[0]) {
                    const detail = rows[0].nextElementSibling;
                    if (detail) detail.style.display = 'table-row';
                }
            }""")
            time.sleep(0.3)
            shot(page, "multi_source_ingestion", full_page=False)

            # ── FEATURE 11: PROVENANCE TRACKING (Audit tab) ───────────
            switch_tab(page, 2)
            shot(page, "provenance_audit_trail", full_page=False)

            # ── FEATURE 12: PDF COMPLIANCE PARSING ────────────────────
            page.goto(f"{BASE_URL}/compliance/intake", wait_until="networkidle")
            shot(page, "pdf_compliance_parsing")

            # ── COMPLIANCE PIPELINE (bonus) ───────────────────────────
            try:
                page.goto(f"{BASE_URL}/compliance/pipeline", wait_until="networkidle", timeout=5000)
                shot(page, "compliance_pipeline")
            except Exception:
                pass

            # ── PROVENANCE CARDS (client overview, bonus) ─────────────
            try:
                page.goto(f"{BASE_URL}/client", wait_until="networkidle", timeout=5000)
                prov = page.query_selector(".prov-grid")
                if prov:
                    js_scroll_to(page, ".prov-grid")
                    shot(page, "provenance_tracking", full_page=False)
            except Exception:
                pass

            browser.close()

        files = list(SCREENSHOT_DIR.glob("*.png"))
        print(f"\nDone — {len(files)} screenshots saved to {SCREENSHOT_DIR}")

    finally:
        server_process.terminate()
        server_process.wait()


if __name__ == "__main__":
    capture_screenshots()
