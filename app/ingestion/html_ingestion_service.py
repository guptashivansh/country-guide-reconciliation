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
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
}

_ALT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "no-cache",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}


class HtmlIngestionService:
    def __init__(self, timeout=None, max_retries=None,
                 max_content_length=None):
        self.timeout = timeout if timeout is not None else ingestion_timeout()
        self.max_retries = max_retries if max_retries is not None else ingestion_max_retries()
        self.max_content_length = max_content_length if max_content_length is not None else ingestion_max_content_length()
    def fetch_clean_text(self, url, engine=None, js_heavy=False):
        if engine == "requests":
            return self._fetch_requests(url)
        if engine == "crawl4ai" and _HAS_CRAWL4AI:
            result = self._fetch_crawl4ai(url)
            if result.succeeded:
                return result
            logger.info("Crawl4AI failed for %s, falling back to requests", url)
            return self._fetch_requests(url)

        if js_heavy and _HAS_CRAWL4AI:
            result = self._fetch_crawl4ai(url)
            if result.succeeded:
                return result
            logger.info("Crawl4AI failed for JS-heavy %s, falling back to requests", url)
            return self._fetch_requests(url)

        result = self._fetch_requests(url)
        if result.succeeded:
            return result
        if _HAS_CRAWL4AI:
            logger.info("requests failed for %s, falling back to Crawl4AI", url)
            return self._fetch_crawl4ai(url)
        return result

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
        got_403 = False
        for attempt in range(self.max_retries):
            try:
                logger.info(
                    "Fetching source content via requests",
                    extra={"stage": "ingestion_fetch", "source_url": url, "attempt": attempt + 1},
                )
                resp = requests.get(url, headers=_HEADERS, timeout=self.timeout)
                resp.raise_for_status()
                text = self._parse_html(url, resp.text)
                return self._build_success(url, text)
            except requests.exceptions.Timeout as exc:
                last_exc = exc
                logger.warning(
                    "Timeout fetching source — will retry",
                    extra={"stage": "ingestion_fetch", "source_url": url, "attempt": attempt + 1},
                )
                time.sleep(2)
            except requests.exceptions.HTTPError as exc:
                last_exc = exc
                if exc.response is not None and exc.response.status_code == 403:
                    got_403 = True
                    break
                if exc.response is not None and exc.response.status_code >= 500 and attempt < self.max_retries - 1:
                    time.sleep(2)
                else:
                    break
            except Exception as exc:
                last_exc = exc
                break

        if got_403:
            result = self._retry_with_alt_headers(url)
            if result is not None:
                return result

        if got_403:
            failure_type = "http_403"
        elif isinstance(last_exc, requests.exceptions.HTTPError) and last_exc.response is not None:
            failure_type = f"http_{last_exc.response.status_code}"
        elif isinstance(last_exc, requests.RequestException):
            failure_type = "network_error"
        else:
            failure_type = "unknown_error"
        return self._build_failure(url, last_exc, failure_type)

    def _retry_with_alt_headers(self, url):
        try:
            logger.info("Retrying with alternate headers after 403",
                        extra={"stage": "ingestion_fetch", "source_url": url})
            time.sleep(1)
            session = requests.Session()
            resp = session.get(url, headers=_ALT_HEADERS, timeout=self.timeout,
                               allow_redirects=True)
            if resp.status_code == 200:
                text = self._parse_html(url, resp.text)
                return self._build_success(url, text)
        except Exception as exc:
            logger.debug("Alt-header retry also failed for %s: %s", url, exc)
        return None

    @staticmethod
    def _parse_html(url, html_text):
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html_text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        return soup.get_text(separator="\n", strip=True)

    # -- shared helpers --------------------------------------------------------

    def _build_success(self, url, text):
        text = text.replace("\x00", "")
        if len(text) > self.max_content_length:
            text = self._smart_truncate(text, self.max_content_length, url)

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

    @staticmethod
    def _smart_truncate(text, max_length, url):
        import re
        lines = text.split("\n")
        start = 0
        for i, line in enumerate(lines):
            stripped = line.strip().lower()
            if not stripped:
                continue
            if any(kw in stripped for kw in (
                "skip to", "cookie", "accept all", "menu", "navigation",
                "sign in", "log in", "search", "subscribe",
            )):
                start = i + 1
                continue
            if len(stripped) < 15 and not re.search(r"\d", stripped):
                start = i + 1
                continue
            break
        trimmed = "\n".join(lines[start:])
        if len(trimmed) <= max_length:
            return trimmed
        logger.warning("Truncating content from %d to %d chars (skipped %d boilerplate lines)",
                       len(text), max_length, start)
        return trimmed[:max_length]

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
