import hashlib
import logging
import os
import tempfile

import pdfplumber

from app.models.workflow_results import FailureDetail, IngestionResult

logger = logging.getLogger(__name__)

UPLOAD_DIR = os.environ.get("PDF_UPLOAD_DIR", os.path.join(tempfile.gettempdir(), "regulift_pdfs"))


class PdfIngestionService:
    def __init__(self, upload_dir=None, max_content_length=None):
        self.upload_dir = upload_dir or UPLOAD_DIR
        os.makedirs(self.upload_dir, exist_ok=True)
        from app.utils.config import ingestion_max_content_length
        self.max_content_length = max_content_length if max_content_length is not None else ingestion_max_content_length()

    def save_upload(self, file_storage, filename=None):
        safe_name = filename or file_storage.filename or "upload.pdf"
        safe_name = os.path.basename(safe_name).replace(" ", "_")
        dest = os.path.join(self.upload_dir, safe_name)

        counter = 1
        base, ext = os.path.splitext(dest)
        while os.path.exists(dest):
            dest = f"{base}_{counter}{ext}"
            counter += 1

        file_storage.save(dest)
        logger.info("PDF saved", extra={"stage": "pdf_upload", "path": dest})
        return dest

    def extract_text(self, pdf_path):
        try:
            pages_text = []
            with pdfplumber.open(pdf_path) as pdf:
                page_count = len(pdf.pages)
                for i, page in enumerate(pdf.pages):
                    text = page.extract_text() or ""
                    tables = page.extract_tables() or []
                    for table in tables:
                        for row in table:
                            cells = [c or "" for c in row]
                            text += "\n" + " | ".join(cells)
                    if text.strip():
                        pages_text.append(text)
                    logger.debug("Extracted page %d/%d", i + 1, page_count)

            full_text = "\n\n".join(pages_text).replace("\x00", "")
            if not full_text.strip():
                return IngestionResult(
                    status="failed",
                    source_url=f"file://{pdf_path}",
                    failure=FailureDetail(
                        type="pdf_error",
                        reason="PDF contains no extractable text (may be scanned/image-only)",
                        metadata={"path": pdf_path, "page_count": page_count},
                    ),
                )

            if len(full_text) > self.max_content_length:
                logger.warning("Truncating PDF text from %d to %d chars", len(full_text), self.max_content_length)
                full_text = full_text[:self.max_content_length]

            content_hash = hashlib.md5(full_text.encode()).hexdigest()
            logger.info(
                "PDF text extracted",
                extra={"stage": "pdf_extract", "path": pdf_path,
                       "page_count": page_count, "character_count": len(full_text)},
            )
            return IngestionResult(
                status="success",
                source_url=f"file://{pdf_path}",
                raw_text=full_text,
                content_hash=content_hash,
                metadata={"page_count": page_count, "character_count": len(full_text), "engine": "pdfplumber"},
            )
        except Exception as e:
            logger.error("PDF extraction failed", extra={"stage": "pdf_extract", "path": pdf_path, "error": str(e)})
            return IngestionResult(
                status="failed",
                source_url=f"file://{pdf_path}",
                failure=FailureDetail(
                    type="pdf_error",
                    reason=str(e),
                    metadata={"path": pdf_path},
                ),
            )
