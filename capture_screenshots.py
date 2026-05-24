"""
Automated screenshot capture for documentation.

Starts the Flask app, navigates to each key page, and saves screenshots
to docs/assets/screenshots/. Run after any UI changes:

    python docs/capture_screenshots.py
"""

import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:8080"
SCREENSHOT_DIR = Path(__file__).parent / "assets" / "screenshots"

PAGES = [
    {"name": "home", "path": "/", "wait": None},
    {"name": "ops_dashboard", "path": "/ops", "wait": None},
    {"name": "guide_list", "path": "/guide", "wait": None},
    {"name": "guide_country", "path": "/guide/India", "wait": None},
]


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

            for entry in PAGES:
                url = f"{BASE_URL}{entry['path']}"
                print(f"  {entry['name']:20s} → {url}")
                page.goto(url, wait_until="networkidle")

                if entry.get("wait"):
                    page.wait_for_selector(entry["wait"])

                page.screenshot(
                    path=str(SCREENSHOT_DIR / f"{entry['name']}.png"),
                    full_page=True,
                )

            # Capture review queue by scrolling to it on the ops dashboard
            page.goto(f"{BASE_URL}/ops", wait_until="networkidle")
            review_section = page.query_selector("[class*='review'], [id*='review'], table, .queue")
            if review_section:
                review_section.scroll_into_view_if_needed()
                time.sleep(0.3)
            page.screenshot(
                path=str(SCREENSHOT_DIR / "review_queue.png"),
                full_page=False,
            )

            browser.close()

        print(f"\nDone — {len(PAGES) + 1} screenshots saved to {SCREENSHOT_DIR}")

    finally:
        server_process.terminate()
        server_process.wait()


if __name__ == "__main__":
    capture_screenshots()
