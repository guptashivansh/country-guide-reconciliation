import logging
import re
import time

logger = logging.getLogger(__name__)

_GUIDE_TITLE_RE = re.compile(r"^(.+?)\s*[-–]\s*Employment Guide", re.IGNORECASE)


class NotionIngestionService:
    """
    Imports country guide text from Notion using the official API.

    Requires a Notion integration token (NOTION_API_KEY) with access to the
    Skuad Country Product Guides page tree.
    """

    def __init__(self, page_id: str, api_key: str = "", country_names: list = None):
        self.root_id = page_id.replace("-", "")
        self._api_key = api_key
        self._countries = {c.lower(): c for c in (country_names or [])}
        self._client = None

    def _get_client(self):
        if self._client is not None:
            return self._client
        if not self._api_key:
            logger.warning("NOTION_API_KEY not set — Notion ingestion will return empty results")
            return None
        from notion_client import Client
        self._client = Client(auth=self._api_key)
        return self._client

    def fetch_country_texts(self) -> dict:
        """Return {canonical_country_name: plain_text} for whitelisted countries."""
        client = self._get_client()
        if not client:
            return {}

        pages = self._discover_guide_pages(client)
        results = {}
        for page_id, (title, url) in pages.items():
            for lower, canonical in self._countries.items():
                if lower in title.lower() and canonical not in results:
                    text = self._extract_page_text(client, page_id)
                    results[canonical] = text
                    logger.info("Fetched country page", extra={"country": canonical, "char_count": len(text)})
                    break
            if len(results) >= len(self._countries):
                break
        return results

    def fetch_all_employment_guides(self) -> dict:
        """
        Auto-discover all pages matching '<Country> - Employment Guide' and
        return {country_name: plain_text}.
        """
        client = self._get_client()
        if not client:
            return {}

        pages = self._discover_guide_pages(client)
        results = {}
        for page_id, (title, url) in pages.items():
            match = _GUIDE_TITLE_RE.match(title.strip())
            if not match:
                continue
            country = match.group(1).strip()
            if country in results:
                continue
            text = self._extract_page_text(client, page_id)
            results[country] = text
            logger.info("Discovered country guide", extra={"country": country, "char_count": len(text)})

        if not results:
            logger.warning("Auto-discovery found no employment guides")
        return results

    def fetch_page_urls(self) -> dict:
        """Return {country_name: notion_url} for all discovered guide pages."""
        client = self._get_client()
        if not client:
            return {}
        pages = self._discover_guide_pages(client)
        urls = {}
        for page_id, (title, url) in pages.items():
            match = _GUIDE_TITLE_RE.match(title.strip())
            if match:
                country = match.group(1).strip()
                if country not in urls:
                    urls[country] = url
        return urls

    def _discover_guide_pages(self, client) -> dict:
        """Search for all Employment Guide pages accessible to the integration.
        Returns {page_id: (title, url)}."""
        pages = {}
        try:
            has_more = True
            start_cursor = None
            while has_more:
                time.sleep(0.4)
                resp = client.search(
                    query="Employment Guide",
                    filter={"property": "object", "value": "page"},
                    start_cursor=start_cursor,
                    page_size=100,
                )
                for result in resp.get("results", []):
                    page_id = result["id"]
                    title_parts = result.get("properties", {}).get("title", {}).get("title", [])
                    title = "".join(t.get("plain_text", "") for t in title_parts)
                    url = result.get("url", "")
                    if _GUIDE_TITLE_RE.match(title.strip()):
                        pages[page_id] = (title, url)
                has_more = resp.get("has_more", False)
                start_cursor = resp.get("next_cursor")
        except Exception as exc:
            logger.error("Notion search failed: %s", exc)
        return pages

    def _extract_page_text(self, client, page_id: str) -> str:
        """Recursively read all blocks from a page and convert to plain text."""
        blocks = self._fetch_all_blocks(client, page_id)
        lines = []
        for block in blocks:
            self._append_block(client, block, lines, depth=0)
        return "\n".join(lines)

    def _fetch_all_blocks(self, client, block_id: str) -> list:
        """Fetch all direct children of a block, handling pagination."""
        blocks = []
        has_more = True
        start_cursor = None
        while has_more:
            time.sleep(0.4)
            resp = client.blocks.children.list(
                block_id=block_id,
                start_cursor=start_cursor,
                page_size=100,
            )
            blocks.extend(resp.get("results", []))
            has_more = resp.get("has_more", False)
            start_cursor = resp.get("next_cursor")
        return blocks

    def _append_block(self, client, block: dict, lines: list, depth: int):
        block_type = block.get("type", "")
        text = self._rich_text_to_plain(block.get(block_type, {}).get("rich_text", []))
        prefix = "  " * depth

        if block_type == "heading_1":
            lines.append(f"\n## {text}")
        elif block_type == "heading_2":
            lines.append(f"\n### {text}")
        elif block_type == "heading_3":
            lines.append(f"\n#### {text}")
        elif block_type in ("bulleted_list_item", "numbered_list_item", "to_do"):
            lines.append(f"{prefix}- {text}")
        elif block_type == "toggle":
            lines.append(f"{prefix}{text}:")
        elif block_type == "quote":
            lines.append(f"> {text}")
        elif block_type == "callout":
            lines.append(f"Note: {text}")
        elif block_type == "table":
            self._append_table(client, block, lines, prefix)
            return
        elif block_type == "table_row":
            cells = block.get("table_row", {}).get("cells", [])
            cell_texts = [self._rich_text_to_plain(cell) for cell in cells]
            lines.append(prefix + " | ".join(c for c in cell_texts if c))
        elif block_type == "paragraph" and text:
            lines.append(f"{prefix}{text}")
        elif block_type == "divider":
            pass
        elif text:
            lines.append(f"{prefix}{text}")

        if block.get("has_children") and block_type not in ("table",):
            child_depth = depth + 1 if block_type == "toggle" else depth
            children = self._fetch_all_blocks(client, block["id"])
            for child in children:
                self._append_block(client, child, lines, child_depth)

    def _append_table(self, client, block: dict, lines: list, prefix: str):
        """Fetch table rows and render as pipe-delimited text."""
        rows = self._fetch_all_blocks(client, block["id"])
        for row in rows:
            cells = row.get("table_row", {}).get("cells", [])
            cell_texts = [self._rich_text_to_plain(cell) for cell in cells]
            lines.append(prefix + " | ".join(c for c in cell_texts if c))

    @staticmethod
    def _rich_text_to_plain(rich_text_array) -> str:
        if not rich_text_array:
            return ""
        return "".join(item.get("plain_text", "") for item in rich_text_array if isinstance(item, dict))
