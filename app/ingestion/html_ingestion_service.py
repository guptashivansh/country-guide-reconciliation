import hashlib
import logging

import requests
from bs4 import BeautifulSoup

from app.models.workflow_results import FailureDetail, IngestionResult


logger = logging.getLogger(__name__)


class HtmlIngestionService:
    def fetch_clean_text(self, url):
        try:
            logger.info(
                "Fetching source content",
                extra={"stage": "ingestion_fetch", "source_url": url},
            )
            headers = {"User-Agent": "Mozilla/5.0 (compatible; CountryGuideBot/1.0)"}
            resp = requests.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
            logger.info(
                "Fetched source content",
                extra={"stage": "ingestion_fetch", "source_url": url, "status_code": resp.status_code},
            )

            soup = BeautifulSoup(resp.text, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                tag.decompose()

            text = soup.get_text(separator="\n", strip=True)
            text = "\n".join(line for line in text.splitlines() if len(line.strip()) > 30)
            text = text[:6000]

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
