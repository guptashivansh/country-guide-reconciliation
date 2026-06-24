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


def _make_stub_pdf_bytes():
    """Build a minimal valid PDF with text content that pdfplumber can parse."""
    stream = b"BT /F1 12 Tf 72 720 Td (Stub regulation content for e2e testing.) Tj ET"
    objects = []
    offsets = []

    def _obj(num, data):
        offsets.append(len(b"".join(objects)))
        objects.append(f"{num} 0 obj\n".encode() + data + b"\nendobj\n")

    _obj(1, b"<< /Type /Catalog /Pages 2 0 R >>")
    _obj(2, b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>")
    _obj(3, b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>")
    _obj(4, f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream")
    _obj(5, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    header = b"%PDF-1.4\n"
    body = b"".join(objects)
    xref_offset = len(header) + len(body)
    xref = f"xref\n0 {len(offsets) + 1}\n0000000000 65535 f \n"
    for off in offsets:
        xref += f"{off + len(header):010d} 00000 n \n"
    trailer = (f"trailer\n<< /Size {len(offsets) + 1} /Root 1 0 R >>\n"
               f"startxref\n{xref_offset}\n%%EOF\n")
    return header + body + xref.encode() + trailer.encode()


@pytest.fixture
def stub_pdf(tmp_path: Path) -> Path:
    p = tmp_path / "stub_regulation.pdf"
    p.write_bytes(_make_stub_pdf_bytes())
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
def test_pdf_intake_api_rejects_missing_file(seeded_app, browser_context):
    """POST to /api/intake/pdf without a file attachment returns 400."""
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
    assert resp.status == 400
    body = resp.json()
    assert body.get("success") is False
