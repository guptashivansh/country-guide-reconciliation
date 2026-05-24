"""End-to-end test of the PDF intake wizard.

Drives the 5-step wizard at /compliance/intake/pdf via the real UI, submits,
and verifies the resulting ingestion job appears in the API and the pipeline
page renders for it.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from tests.e2e.conftest import TEST_COUNTRY


# 4-byte stub PDF. The backend only reads form fields (jurisdiction, publisher,
# doc_title, authority, effective_date, file_hash) — it never opens the file.
# The browser still computes SHA-256 over these bytes via SubtleCrypto.
_STUB_PDF_BYTES = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj<</Type/Catalog>>endobj\ntrailer<<>>\n%%EOF\n"


@pytest.fixture
def stub_pdf(tmp_path: Path) -> Path:
    p = tmp_path / "stub_regulation.pdf"
    p.write_bytes(_STUB_PDF_BYTES)
    return p


@pytest.mark.smoke
def test_pdf_intake_wizard_creates_job_and_pipeline_renders(
    browser_context, seeded_app, stub_pdf
):
    base_url = seeded_app["base_url"]
    page = browser_context.new_page()

    page_errors: list[str] = []
    page.on("pageerror", lambda exc: page_errors.append(str(exc)))

    # Surface alert() from JS as a test failure rather than a hang.
    page.on("dialog", lambda d: pytest.fail(f"Unexpected dialog: {d.message}"))

    resp = page.goto(f"{base_url}/compliance/intake/pdf", wait_until="domcontentloaded")
    assert resp and resp.status == 200

    # ── Step 1: upload PDF ────────────────────────────────────────────────
    page.set_input_files("#fileInput", str(stub_pdf))

    # handleFile() reveals #filePreview and kicks off SubtleCrypto SHA-256.
    # Wait until the hash text appears AND the Continue button is enabled.
    page.wait_for_selector("#fileHash:not(:empty)", timeout=5000)
    page.wait_for_function(
        "() => !document.getElementById('step1Next').disabled", timeout=5000
    )
    assert "SHA-256" in page.locator("#fileHash").inner_text()
    page.click("#step1Next")

    # ── Step 2: publisher + document title ────────────────────────────────
    page.wait_for_selector("#step2:not([style*='display:none'])")
    page.fill("#publisher", "Federal Ministry of Labour")
    page.fill("#docTitle", "Test Gazette Notification 2026")
    page.click("#step2Next")

    # ── Step 3: jurisdiction chip + at least one section ──────────────────
    page.wait_for_selector("#step3:not([style*='display:none'])")
    page.click(f".jurisdiction-chip[data-country='{TEST_COUNTRY}']")
    page.locator(".section-check input[type='checkbox']").first.check()
    page.click("#step3Next")

    # ── Step 4: authority + dates ─────────────────────────────────────────
    page.wait_for_selector("#step4:not([style*='display:none'])")
    page.click(".authority-option[data-value='primary_statute']")
    page.fill("#effectiveDate", "2026-01-01")
    page.fill("#publishedDate", "2025-12-15")
    page.click("#step4Next")

    # ── Step 5: confirm + submit ──────────────────────────────────────────
    page.wait_for_selector("#step5:not([style*='display:none'])")
    confirm_text = page.locator("#confirmGrid").inner_text()
    assert "Federal Ministry of Labour" in confirm_text
    assert TEST_COUNTRY in confirm_text
    page.click("#submitBtn")

    # ── Post-submit: stepDone visible, job_id captured ────────────────────
    page.wait_for_selector("#stepDone:not([style*='display:none'])", timeout=10_000)
    done_text = page.locator("#doneJobId").inner_text()
    m = re.search(r"Job #(\d+)", done_text)
    assert m, f"Expected 'Job #<n>' in done message, got: {done_text!r}"
    job_id = int(m.group(1))

    pipeline_href = page.locator("#donePipelineLink").get_attribute("href")
    assert pipeline_href == f"/compliance/pipeline/{job_id}"

    # ── Verify backend state: job appears in /api/ingestion-jobs ──────────
    jobs_resp = page.request.get(f"{base_url}/api/ingestion-jobs")
    assert jobs_resp.status == 200
    jobs = jobs_resp.json()
    matching = [j for j in jobs if j.get("id") == job_id]
    assert matching, (
        f"Job {job_id} not found in /api/ingestion-jobs. "
        f"Returned {len(jobs)} job(s): {json.dumps(jobs)[:500]}"
    )
    job = matching[0]
    assert job.get("country") == TEST_COUNTRY, (
        f"Job {job_id} country={job.get('country')!r}, expected {TEST_COUNTRY!r}"
    )
    assert (job.get("source_url") or "").startswith("pdf://"), (
        f"Job source_url should start with 'pdf://', got {job.get('source_url')!r}"
    )

    # ── Verify pipeline page renders for the new job ──────────────────────
    pipeline_resp = page.goto(
        f"{base_url}/compliance/pipeline/{job_id}", wait_until="domcontentloaded"
    )
    assert pipeline_resp and pipeline_resp.status == 200
    assert page.title()

    assert not page_errors, f"JS errors during intake flow: {page_errors}"


@pytest.mark.smoke
def test_pdf_intake_api_rejects_no_op_call_creates_job(seeded_app, browser_context):
    """Direct POST to /api/intake/pdf with minimal fields should still create a job.

    Documents the backend boundary contract: jurisdiction is the only field
    that ends up on the row, but the endpoint never refuses a submission.
    """
    base_url = seeded_app["base_url"]
    page = browser_context.new_page()

    resp = page.request.post(
        f"{base_url}/api/intake/pdf",
        multipart={
            "jurisdiction": TEST_COUNTRY,
            "publisher": "Direct API caller",
            "doc_title": "Minimal direct submission",
            "authority": "regulation",
            "effective_date": "2026-02-01",
            "file_hash": "deadbeef" * 8,
        },
    )
    assert resp.status == 200, f"POST failed: {resp.status} {resp.text()}"
    body = resp.json()
    assert body.get("success") is True
    assert isinstance(body.get("job_id"), int)
