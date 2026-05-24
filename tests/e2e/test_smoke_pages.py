"""Smoke tests: every user-facing HTML route loads cleanly.

Each parametrized case opens a route in a real Chromium page, asserts the
response status, that the page has a title, and that no uncaught JS errors
or console errors fire. App/templates run against the seeded test DB.
"""
from __future__ import annotations

import pytest

from tests.e2e.conftest import TEST_COUNTRY


# (path, expected_status, id)
ROUTES = [
    # Seed-dependent (need at least one country row)
    ("/",                                              200, "home"),
    ("/guide",                                         200, "guide_list"),
    (f"/guide/{TEST_COUNTRY}",                         200, "guide_country"),
    (f"/employee/{TEST_COUNTRY}",                      200, "employee_country"),
    (f"/guide/employee/{TEST_COUNTRY}",                200, "guide_view_employee"),
    (f"/guide/client/{TEST_COUNTRY}",                  200, "guide_view_client"),
    (f"/guide/ops/{TEST_COUNTRY}",                     200, "guide_view_ops"),

    # Seed-independent
    ("/ops",                                           200, "ops_dashboard"),
    ("/ops-legacy",                                    200, "ops_legacy"),
    ("/client",                                        200, "client_overview"),
    ("/compliance/intake",                             200, "compliance_intake_select"),
    (f"/intake/{TEST_COUNTRY}",                        200, "compliance_intake_country"),
    ("/compliance/intake/pdf",                         200, "compliance_intake_pdf"),
    ("/compliance/pipeline",                           200, "compliance_pipeline"),
    ("/compliance/pipeline/9999",                      200, "compliance_pipeline_job"),
    ("/compliance/dashboard",                          200, "compliance_dashboard"),
    ("/compliance/review",                             200, "compliance_review"),
    ("/compliance/audit",                              200, "compliance_audit"),
    ("/compliance/settings",                           200, "compliance_settings"),
]


def _ignorable_console_error(text: str) -> bool:
    """Filter out errors that aren't app-code regressions."""
    lowered = text.lower()
    return (
        "favicon" in lowered
        or "/favicon" in lowered
        or "net::err_aborted" in lowered  # navigations cancelled by SPA boot
    )


@pytest.mark.smoke
@pytest.mark.parametrize(
    "path,expected_status",
    [(p, s) for p, s, _ in ROUTES],
    ids=[i for _, _, i in ROUTES],
)
def test_page_smoke(browser_context, seeded_app, path, expected_status):
    page = browser_context.new_page()
    page_errors: list[str] = []
    console_errors: list[str] = []
    page.on("pageerror", lambda exc: page_errors.append(str(exc)))
    page.on(
        "console",
        lambda msg: console_errors.append(msg.text)
        if msg.type == "error" and not _ignorable_console_error(msg.text)
        else None,
    )

    resp = page.goto(f"{seeded_app['base_url']}{path}", wait_until="domcontentloaded")
    assert resp is not None, f"No response object for {path}"
    assert resp.status == expected_status, (
        f"{path} returned {resp.status}, expected {expected_status}"
    )
    assert page.title(), f"{path} rendered with empty <title>"
    assert not page_errors, f"{path} threw uncaught JS errors: {page_errors}"
    assert not console_errors, f"{path} logged console errors: {console_errors}"


@pytest.mark.smoke
def test_compliance_root_redirects(seeded_app, browser_context):
    """/compliance should 302 to /compliance/intake."""
    page = browser_context.new_page()
    resp = page.request.get(
        f"{seeded_app['base_url']}/compliance",
        max_redirects=0,
    )
    assert resp.status == 302, f"/compliance returned {resp.status}, expected 302"
    location = resp.headers.get("location", "")
    assert location.endswith("/compliance/intake"), (
        f"/compliance redirected to {location!r}, expected …/compliance/intake"
    )
