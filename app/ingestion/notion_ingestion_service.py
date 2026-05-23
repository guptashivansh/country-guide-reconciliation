import json
import logging
import time
import urllib.request
import urllib.error

logger = logging.getLogger(__name__)

_NOTION_API = "https://www.notion.so/api/v3"
_PAGE_MENTION = "‣"  # ‣ inline page reference character


def _to_uuid(raw_id: str) -> str:
    s = raw_id.replace("-", "")
    return f"{s[0:8]}-{s[8:12]}-{s[12:16]}-{s[16:20]}-{s[20:32]}"


def _plain_text(rich_text) -> str:
    if not rich_text:
        return ""
    return "".join(
        str(seg[0]) for seg in rich_text
        if isinstance(seg, list) and seg and seg[0] != _PAGE_MENTION
    )


def _extract_page_mentions(rich_text) -> list:
    """Return page IDs referenced via ‣ inline mentions in a Notion rich-text array."""
    ids = []
    for seg in (rich_text or []):
        if isinstance(seg, list) and seg and seg[0] == _PAGE_MENTION:
            for ann in (seg[1] if len(seg) > 1 else []):
                if isinstance(ann, list) and len(ann) > 1 and ann[0] == "p":
                    ids.append(ann[1])
    return ids


class NotionIngestionService:
    """
    Imports country guide text from a public Notion page using the unofficial API.

    Traversal path inside the Skuad Country Guides page:
      Root → "Quick Country Guides" header
           → column_list (one per region pair: APAC+Europe, MEA+Americas)
           → column → sub_sub_header (e.g. "APAC", "MEA")
           → text blocks with ‣ inline page links → country pages

    Key efficiency note: loadPageChunk(sub_sub_header_id) returns the sub_sub_header
    AND its direct children (the ‣ text blocks) in one call — so we never need a
    separate API call per text block.
    """

    def __init__(self, page_id: str, country_names: list):
        self.root_id = _to_uuid(page_id)
        self._countries = {c.lower(): c for c in country_names}

    # ------------------------------------------------------------------ public

    def fetch_country_texts(self) -> dict:
        """Return {canonical_country_name: plain_text} for each matched country page."""
        logger.info("Loading root Notion page", extra={"page_id": self.root_id})
        root_blocks = self._load_blocks(self.root_id)

        qcg_id = self._find_country_guides_header(root_blocks)
        if not qcg_id:
            logger.error("Could not find 'Quick Country Guides' header on root page")
            return {}

        qcg_header = root_blocks.get(qcg_id, {})

        # Collect ‣ page mention IDs from all region column_lists
        candidate_ids: set = set()
        for col_list_id in qcg_header.get("content", []):
            candidate_ids.update(self._collect_mentions_from_column_list(col_list_id))

        logger.info("Collected page mention candidates", extra={"count": len(candidate_ids)})

        # Load each candidate page and match against known country names
        results: dict = {}
        for page_id in candidate_ids:
            if len(results) >= len(self._countries):
                break
            try:
                time.sleep(1.5)
                page_uuid = _to_uuid(page_id)
                page_blocks = self._load_blocks(page_uuid)
                root_block = page_blocks.get(page_uuid, {})
                title = _plain_text(root_block.get("properties", {}).get("title", []))
                for lower, canonical in self._countries.items():
                    if lower in title.lower() and canonical not in results:
                        text = self._blocks_to_text(page_blocks, page_uuid)
                        results[canonical] = text
                        logger.info(
                            "Fetched country page",
                            extra={"country": canonical, "char_count": len(text)},
                        )
                        break
            except Exception as exc:
                logger.debug("Skipping candidate page %s: %s", page_id, exc)

        if not results:
            logger.warning("No country pages found — Notion page structure may have changed")
        return results

    # ----------------------------------------------------------------- helpers

    def _find_country_guides_header(self, blocks: dict):
        root = blocks.get(self.root_id, {})
        for cid in root.get("content", []):
            block = blocks.get(cid, {})
            title = _plain_text(block.get("properties", {}).get("title", []))
            if "country" in title.lower() and block.get("type") == "header":
                return cid
        return None

    def _collect_mentions_from_column_list(self, col_list_id: str) -> set:
        """
        Walk one column_list three levels:
          column_list → column → sub_sub_header
        Then load each sub_sub_header — its direct children (‣ text blocks) are
        returned in the same loadPageChunk response, so we scan all returned blocks
        for ‣ mentions rather than making one call per text block.
        """
        mentions: set = set()
        try:
            col_list_blocks = self._load_blocks(col_list_id)
            col_list = col_list_blocks.get(col_list_id, {})

            for col_id in col_list.get("content", []):
                col = col_list_blocks.get(col_id, {})
                for header_id in col.get("content", []):
                    try:
                        # loadPageChunk(sub_sub_header) includes its text children
                        time.sleep(1.5)
                        header_blocks = self._load_blocks(header_id)
                        for block in header_blocks.values():
                            for pid in _extract_page_mentions(
                                block.get("properties", {}).get("title", [])
                            ):
                                mentions.add(pid)
                    except Exception as exc:
                        logger.debug("Cannot load region header %s: %s", header_id, exc)
        except Exception as exc:
            logger.debug("Cannot load column_list %s: %s", col_list_id, exc)
        return mentions

    def _load_blocks(self, page_uuid: str) -> dict:
        """
        Fetch blocks for a page/block via the unofficial Notion API.
        Retries on 429 with exponential backoff.
        """
        blocks = {}
        cursor = {"stack": []}
        while True:
            payload = json.dumps({
                "page": {"id": page_uuid},
                "limit": 100,
                "cursor": cursor,
                "chunkNumber": 0,
                "verticalColumns": False,
            }).encode()
            req = urllib.request.Request(
                f"{_NOTION_API}/loadPageChunk",
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            data = self._request_with_backoff(req)
            if data is None:
                break

            for bid, bdata in data.get("recordMap", {}).get("block", {}).items():
                val = bdata.get("value", {})
                if isinstance(val, dict) and "value" in val:
                    val = val["value"]
                if val:
                    blocks[bid] = val

            cursor = data.get("cursor", {"stack": []})
            if not cursor.get("stack"):
                break
        return blocks

    def _request_with_backoff(self, req, max_retries: int = 5):
        delay = 5.0
        for attempt in range(max_retries):
            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    return json.loads(resp.read())
            except urllib.error.HTTPError as exc:
                if exc.code == 429 and attempt < max_retries - 1:
                    logger.debug("Rate limited, waiting %.1fs before retry %d", delay, attempt + 1)
                    time.sleep(delay)
                    delay *= 2
                else:
                    raise
        return None

    def _blocks_to_text(self, blocks: dict, root_uuid: str) -> str:
        root = blocks.get(root_uuid, {})
        lines: list = []
        for bid in root.get("content", []):
            block = blocks.get(bid) or blocks.get(_to_uuid(bid))
            if block:
                self._append_block(block, blocks, lines, depth=0)
        return "\n".join(lines)

    def _append_block(self, block: dict, all_blocks: dict, lines: list, depth: int):
        t = block.get("type", "")
        props = block.get("properties", {})
        text = _plain_text(props.get("title", []))
        prefix = "  " * depth

        if t == "header":
            lines.append(f"\n## {text}")
        elif t == "sub_header":
            lines.append(f"\n### {text}")
        elif t == "sub_sub_header":
            lines.append(f"\n#### {text}")
        elif t in ("bulleted_list", "numbered_list", "to_do"):
            lines.append(f"{prefix}- {text}")
        elif t == "toggle":
            lines.append(f"{prefix}{text}:")
        elif t == "quote":
            lines.append(f"> {text}")
        elif t == "callout":
            lines.append(f"Note: {text}")
        elif t == "table_row":
            cells = [_plain_text(v) for v in props.values()]
            lines.append(prefix + " | ".join(c for c in cells if c))
        elif t == "text" and text:
            lines.append(f"{prefix}{text}")

        child_depth = depth + 1 if t == "toggle" else depth
        for cid in block.get("content", []):
            child = all_blocks.get(cid) or all_blocks.get(_to_uuid(cid))
            if child:
                self._append_block(child, all_blocks, lines, child_depth)
