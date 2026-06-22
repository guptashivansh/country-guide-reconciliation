import hashlib
import logging
import time

import requests
from bs4 import BeautifulSoup

from app.models.workflow_results import FailureDetail, IngestionResult
from app.utils.config import (
    ingestion_max_content_length,
    ingestion_max_retries,
    ingestion_min_line_length,
    ingestion_strip_tags,
    ingestion_timeout,
)


logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
}


class HtmlIngestionService:
    def __init__(self, timeout=None, max_retries=None, strip_tags=None,
                 min_line_length=None, max_content_length=None):
        self.timeout = timeout if timeout is not None else ingestion_timeout()
        self.max_retries = max_retries if max_retries is not None else ingestion_max_retries()
        self.strip_tags = strip_tags if strip_tags is not None else ingestion_strip_tags()
        self.min_line_length = min_line_length if min_line_length is not None else ingestion_min_line_length()
        self.max_content_length = max_content_length if max_content_length is not None else ingestion_max_content_length()

    def fetch_clean_text(self, url):
        last_exc = None
        for attempt in range(self.max_retries):
            try:
                logger.info(
                    "Fetching source content",
                    extra={"stage": "ingestion_fetch", "source_url": url, "attempt": attempt + 1},
                )
                resp = requests.get(url, headers=_HEADERS, timeout=self.timeout)
                resp.raise_for_status()
                break  # success
            except requests.exceptions.Timeout as exc:
                last_exc = exc
                logger.warning(
                    "Timeout fetching source — will retry",
                    extra={"stage": "ingestion_fetch", "source_url": url, "attempt": attempt + 1},
                )
                time.sleep(2)
            except requests.exceptions.HTTPError as exc:
                if exc.response is not None and exc.response.status_code >= 500 and attempt < self.max_retries - 1:
                    last_exc = exc
                    logger.warning(
                        "5xx from source — will retry",
                        extra={"stage": "ingestion_fetch", "source_url": url,
                               "status_code": exc.response.status_code, "attempt": attempt + 1},
                    )
                    time.sleep(2)
                else:
                    last_exc = exc
                    break  # 4xx or final 5xx — no point retrying
            except Exception as exc:
                last_exc = exc
                break  # non-retryable

        if last_exc is not None:
            failure_type = "network_error" if isinstance(last_exc, requests.RequestException) else "unknown_error"
            logger.error(
                "Failed to fetch or normalize source content",
                extra={"stage": "ingestion", "source_url": url,
                       "failure": str(last_exc), "failure_type": failure_type},
            )
            return IngestionResult(
                status="failed",
                source_url=url,
                failure=FailureDetail(
                    type=failure_type,
                    reason=str(last_exc),
                    metadata={"stage": "ingestion"},
                ),
            )

        try:
            logger.info(
                "Fetched source content",
                extra={"stage": "ingestion_fetch", "source_url": url, "status_code": resp.status_code},
            )

            soup = BeautifulSoup(resp.text, "html.parser")
            for tag in soup(self.strip_tags):
                tag.decompose()

            text = soup.get_text(separator="\n", strip=True)
            text = "\n".join(line for line in text.splitlines() if len(line.strip()) > self.min_line_length)
            if len(text) > self.max_content_length:
                logger.warning("Truncating content from %d to %d chars", len(text), self.max_content_length)
                text = text[:self.max_content_length]

            logger.info(
                "Normalized source content",
                extra={"stage": "ingestion_normalize", "source_url": url, "character_count": len(text)},
            )
            content_hash = hashlib.md5(text.encode()).hexdigest()
            return IngestionResult(
                status="success",
                source_url=url,
                raw_text=text,
                content_hash=content_hash,
                metadata={"character_count": len(text)},
            )
        except Exception as e:
            failure_type = "network_error" if isinstance(e, requests.RequestException) else "unknown_error"
            logger.error(
                "Failed to fetch or normalize source content",
                extra={"stage": "ingestion", "source_url": url, "failure": str(e), "failure_type": failure_type},
            )
            return IngestionResult(
                status="failed",
                source_url=url,
                failure=FailureDetail(
                    type=failure_type,
                    reason=str(e),
                    metadata={"stage": "ingestion"},
                ),
            )
