import asyncio
import hashlib
import logging
import time

import requests

from app.models.workflow_results import FailureDetail, IngestionResult
from app.utils.config import (
    ingestion_max_content_length,
    ingestion_max_retries,
    ingestion_timeout,
)

try:
    from crawl4ai import AsyncWebCrawler
    _HAS_CRAWL4AI = True
except Exception:
    _HAS_CRAWL4AI = False


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
    def __init__(self, timeout=None, max_retries=None,
                 max_content_length=None):
        self.timeout = timeout if timeout is not None else ingestion_timeout()
        self.max_retries = max_retries if max_retries is not None else ingestion_max_retries()
        self.max_content_length = max_content_length if max_content_length is not None else ingestion_max_content_length()
    def fetch_clean_text(self, url, engine=None):
        if engine == "requests":
            return self._fetch_requests(url)
        if _HAS_CRAWL4AI and engine != "requests":
            result = self._fetch_crawl4ai(url)
            if result.succeeded:
                return result
            logger.info("Crawl4AI failed for %s, falling back to requests", url)
        return self._fetch_requests(url)

    # -- Crawl4AI (primary) ---------------------------------------------------

    def _fetch_crawl4ai(self, url):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(self._crawl(url))
        finally:
            loop.close()

    async def _crawl(self, url):
        last_exc = None
        for attempt in range(self.max_retries):
            crawler = None
            try:
                logger.info(
                    "Fetching source content via Crawl4AI",
                    extra={"stage": "ingestion_fetch", "source_url": url, "attempt": attempt + 1},
                )
                crawler = AsyncWebCrawler()
                await crawler.__aenter__()
                result = await crawler.arun(url=url)

                if not result.success:
                    raise RuntimeError(result.error_message or "Crawl failed")

                return self._build_success(url, result.markdown or "")
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "Crawl attempt failed — will retry",
                    extra={"stage": "ingestion_fetch", "source_url": url,
                           "attempt": attempt + 1, "error": str(exc)},
                )
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2)
            finally:
                if crawler is not None:
                    try:
                        await crawler.__aexit__(None, None, None)
                    except Exception:
                        pass

        return self._build_failure(url, last_exc, "crawl_error")

    # -- requests fallback -----------------------------------------------------

    def _fetch_requests(self, url):
        last_exc = None
        for attempt in range(self.max_retries):
            try:
                logger.info(
                    "Fetching source content via requests",
                    extra={"stage": "ingestion_fetch", "source_url": url, "attempt": attempt + 1},
                )
                resp = requests.get(url, headers=_HEADERS, timeout=self.timeout)
                resp.raise_for_status()

                from bs4 import BeautifulSoup
                soup = BeautifulSoup(resp.text, "html.parser")
                for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                    tag.decompose()
                text = soup.get_text(separator="\n", strip=True)

                return self._build_success(url, text)
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
                    time.sleep(2)
                else:
                    last_exc = exc
                    break
            except Exception as exc:
                last_exc = exc
                break

        failure_type = "network_error" if isinstance(last_exc, requests.RequestException) else "unknown_error"
        return self._build_failure(url, last_exc, failure_type)

    # -- shared helpers --------------------------------------------------------

    def _build_success(self, url, text):
        text = text.replace("\x00", "")
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
            metadata={"character_count": len(text), "engine": "crawl4ai" if _HAS_CRAWL4AI else "requests"},
        )

    def _build_failure(self, url, exc, failure_type):
        logger.error(
            "Failed to fetch or normalize source content",
            extra={"stage": "ingestion", "source_url": url,
                   "failure": str(exc), "failure_type": failure_type},
        )
        return IngestionResult(
            status="failed",
            source_url=url,
            failure=FailureDetail(
                type=failure_type,
                reason=str(exc),
                metadata={"stage": "ingestion"},
            ),
        )
