---
name: e2e-test
description: Run Playwright end-to-end tests that verify cross-persona data synchronization across the compliance pipeline. Tests that rule changes propagate simultaneously to all personas (Compliance Reviewer, Ops Admin, Guide Publisher, Employee Consumer).
---

# Playwright E2E Testing Skill

## When to use
Use when the user asks to: run e2e tests, test cross-persona sync, verify data propagation, check that changes appear for all roles, run playwright tests, run integration tests with a browser, or test the UI end-to-end.

## Prerequisites
- Python packages: `playwright`, `pytest`, `pytest-playwright`
- Playwright browsers installed: `python3 -m playwright install chromium`
- No external services required — tests spin up an isolated Flask app with in-memory SQLite

## How to run

### Install dependencies (first time only)
```bash
pip3 install pytest-playwright
python3 -m playwright install chromium
```

### Run all E2E tests
```bash
python3 -m pytest tests/e2e/ -v --headed   # visible browser
python3 -m pytest tests/e2e/ -v             # headless (CI)
```

### Run specific test scenarios
```bash
# Cross-persona sync tests only
python3 -m pytest tests/e2e/test_cross_persona_sync.py -v

# Single test
python3 -m pytest tests/e2e/test_cross_persona_sync.py::TestCrossPersonaSync::test_manual_edit_propagates_to_all_personas -v
```

### Test markers
```bash
python3 -m pytest tests/e2e/ -m "sync"       # sync propagation tests
python3 -m pytest tests/e2e/ -m "review"      # review workflow tests
python3 -m pytest tests/e2e/ -m "smoke"       # quick smoke tests
```

## Architecture

### Personas tested
1. **Compliance Reviewer** — `/compliance/review`, `/api/queue`, `/api/approve/<id>`
2. **Ops Admin** — `/ops`, `/compliance/pipeline`, `/api/metrics`
3. **Guide Publisher** — `/guide/<country>`, `/api/guide/<country>/<section>`
4. **Employee Consumer** — `/employee/<country>`, `/api/employee/guide/<country>`

### What the sync tests verify
- A rule change made by one persona is immediately visible to ALL other personas
- Approval of a review item publishes the rule to the live guide and employee view
- Manual edits by the publisher appear in the employee view and audit trail
- Metrics (pending count, critical count) update consistently across dashboards
- Version history records appear for all state transitions

### Fixtures (conftest.py)
- `live_app` — spins up a Flask test server on a random port with in-memory SQLite
- `seeded_app` — same as `live_app` but pre-loaded with test country data and review items
- `browser_context` — fresh Playwright browser context per test
- `reviewer_page` / `admin_page` / `publisher_page` / `employee_page` — persona-specific browser pages

## Troubleshooting
- If `playwright install` fails, run: `python3 -m playwright install --with-deps chromium`
- Tests use `--timeout=30000` by default; increase for slow machines
- The test server binds to `127.0.0.1` on a random port — no port conflicts
