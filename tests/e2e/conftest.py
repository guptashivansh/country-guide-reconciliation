import os
import socket
import tempfile
import threading
import time
from datetime import datetime, timezone

import pytest
from playwright.sync_api import sync_playwright


def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


TEST_COUNTRY = "Germany"
TEST_RULES = {
    "annual_leave": "20 working days minimum",
    "sick_leave": "6 weeks full pay, then statutory sick pay",
    "working_hours": "8 hours/day, 48 hours/week maximum",
    "minimum_wage": "EUR 12.82 per hour (2025)",
    "termination_notice": "4 weeks to the 15th or end of a calendar month",
    "maternity_leave": "14 weeks (6 before, 8 after birth)",
    "public_holidays": "9-13 public holidays depending on state",
}


def _seed_data(services):
    repo = services["country_guide_repository"]
    now = datetime.now(timezone.utc).isoformat()

    for section, value in TEST_RULES.items():
        repo.upsert_guide_entry(
            country=TEST_COUNTRY,
            section=section,
            value=value,
            source_url="seed://e2e-test",
            source_hash="e2e_seed",
            effective_date=now[:10],
            approval_reference="e2e_seed",
        )

    repo.enqueue_review_item(
        country=TEST_COUNTRY,
        section="annual_leave",
        old_value="20 working days minimum",
        new_value="24 working days minimum (updated 2026)",
        severity="major",
        confidence=0.92,
        source_url="seed://e2e-test",
        source_paragraph="Annual leave entitlement increased to 24 working days.",
        source_hash="e2e_change_1",
        source_snapshot_id=None,
    )

    repo.enqueue_review_item(
        country=TEST_COUNTRY,
        section="minimum_wage",
        old_value="EUR 12.82 per hour (2025)",
        new_value="EUR 13.50 per hour (2026)",
        severity="critical",
        confidence=0.95,
        source_url="seed://e2e-test",
        source_paragraph="Minimum wage raised to EUR 13.50 effective January 2026.",
        source_hash="e2e_change_2",
        source_snapshot_id=None,
    )


@pytest.fixture(scope="session")
def playwright_instance():
    with sync_playwright() as p:
        yield p


@pytest.fixture(scope="session")
def browser(playwright_instance):
    b = playwright_instance.chromium.launch(headless=True)
    yield b
    b.close()


@pytest.fixture(scope="function")
def live_app():
    saved_env = {}
    for key in ("DATABASE_URL", "SYNC_CRON_SCHEDULE", "SLACK_WEBHOOK_URL"):
        saved_env[key] = os.environ.get(key)
        os.environ[key] = ""

    try:
        from app import create_app

        port = _free_port()
        tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp_db_path = tmp_db.name
        tmp_db.close()
        app = create_app(db_path=tmp_db_path)
        services = app.config["services"]

        server_thread = threading.Thread(
            target=lambda: app.run(host="127.0.0.1", port=port, use_reloader=False),
            daemon=True,
        )
        server_thread.start()

        base_url = f"http://127.0.0.1:{port}"
        deadline = time.time() + 10
        while time.time() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=1):
                    break
            except OSError:
                time.sleep(0.1)
        else:
            raise RuntimeError(f"Flask server did not start on port {port}")

        yield {"app": app, "services": services, "base_url": base_url, "port": port}
    finally:
        for key, val in saved_env.items():
            if val is not None:
                os.environ[key] = val
            else:
                os.environ.pop(key, None)
        try:
            os.unlink(tmp_db_path)
        except OSError:
            pass


@pytest.fixture(scope="function")
def seeded_app(live_app):
    _seed_data(live_app["services"])
    return live_app


@pytest.fixture(scope="function")
def browser_context(browser):
    ctx = browser.new_context()
    yield ctx
    ctx.close()


@pytest.fixture(scope="function")
def reviewer_page(browser_context, seeded_app):
    page = browser_context.new_page()
    page.goto(f"{seeded_app['base_url']}/compliance/review")
    page.wait_for_load_state("networkidle")
    return page


@pytest.fixture(scope="function")
def admin_page(browser_context, seeded_app):
    page = browser_context.new_page()
    page.goto(f"{seeded_app['base_url']}/ops")
    page.wait_for_load_state("networkidle")
    return page


@pytest.fixture(scope="function")
def publisher_page(browser_context, seeded_app):
    page = browser_context.new_page()
    page.goto(f"{seeded_app['base_url']}/guide/{TEST_COUNTRY}")
    page.wait_for_load_state("networkidle")
    return page


@pytest.fixture(scope="function")
def employee_page(browser_context, seeded_app):
    page = browser_context.new_page()
    page.goto(f"{seeded_app['base_url']}/employee/{TEST_COUNTRY}")
    page.wait_for_load_state("networkidle")
    return page
