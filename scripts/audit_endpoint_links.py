#!/usr/bin/env python3
"""Audit source endpoint URLs and resolve landing pages to content-specific sub-pages.

For each endpoint in official-sources.json:
1. Crawl the page (single shared Crawl4AI browser session) and extract links
2. Use LLM to classify: content page vs landing/index page
3. For landing pages, map extracted links to sections
4. Output an updated JSON with resolved endpoints

Usage:
    python3 scripts/audit_endpoint_links.py                         # all countries
    python3 scripts/audit_endpoint_links.py --country Singapore     # single country
    python3 scripts/audit_endpoint_links.py --dry-run               # classify only, don't update
"""
import argparse
import asyncio
import json
import logging
import os
import sys
import time
from urllib.parse import urljoin

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.utils.config import load_env_file

load_env_file()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("crawl4ai").setLevel(logging.WARNING)

try:
    from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
    HAS_CRAWL4AI = True
except ImportError:
    HAS_CRAWL4AI = False

from openai import AzureOpenAI, RateLimitError

SOURCES_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "official-sources.json")
RESULTS_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "audit-results.json")

CLASSIFY_PROMPT = """You are analyzing a government website page to determine if it contains specific employment law content or is just a landing/navigation page.

Page URL: {url}
Sections this endpoint is supposed to cover: {sections}

Page content (first 2000 chars):
{content}

Links found on this page:
{links}

Analyze and respond in JSON:
{{
  "page_type": "content" or "landing",
  "has_extractable_rules": true/false,
  "reasoning": "brief explanation",
  "sub_pages": [
    {{
      "url": "full URL of the sub-page",
      "sections": ["section1", "section2"],
      "description": "what content this sub-page likely has"
    }}
  ]
}}

Rules:
- "content" = page has actual employment law rules/values (e.g., "16 weeks maternity leave", "minimum wage is $X")
- "landing" = page is an index/navigation page with links to content but no rules itself
- For "content" pages, sub_pages should be empty
- For "landing" pages, map the links to the most relevant sections from the allowed list
- Only include links that are likely to have employment law content
- Sections must come from this allowed list: {all_sections}
- Prefer direct/specific links over broad category pages
"""


def load_sources():
    with open(SOURCES_PATH) as f:
        return json.load(f)


def build_country_map(data):
    auth_map = {a["id"]: a for a in data["authorities"]}
    country_map = {c["id"]: c["name"] for c in data["countries"]}
    ep_country = {}
    for ep in data["source_endpoints"]:
        auth = auth_map.get(ep.get("authority_id", ""))
        if auth:
            ep_country[ep["id"]] = country_map.get(auth.get("country_id", ""), "Unknown")
    return ep_country


def get_all_sections(data):
    sections = set()
    for ep in data["source_endpoints"]:
        for s in ep.get("sections_covered", []):
            sections.add(s)
    return sorted(sections)


async def crawl_with_shared_browser(crawler, url):
    """Crawl a URL using the shared Crawl4AI browser session."""
    try:
        config = CrawlerRunConfig(page_timeout=20000, verbose=False)
        result = await crawler.arun(url=url, config=config)
        if not result.success:
            return {"success": False, "error": result.error_message or "crawl failed"}

        links = []
        seen = set()
        if result.links:
            for group in [result.links.get("internal", []), result.links.get("external", [])]:
                for link in group:
                    href = link.get("href", "")
                    text = link.get("text", "").strip()
                    if href and text and len(text) < 200 and href not in seen and not href.startswith("javascript:"):
                        seen.add(href)
                        links.append({"url": href, "text": text})
        return {"success": True, "content": result.markdown or "", "links": links}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def crawl_with_requests(url):
    """Crawl with requests+BS4."""
    import requests as req
    from bs4 import BeautifulSoup
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    try:
        resp = req.get(url, headers=headers, timeout=15, allow_redirects=True)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        links, seen = [], set()
        for a in soup.find_all("a", href=True):
            href = urljoin(url, a["href"])
            if href in seen or href.startswith("javascript:"):
                continue
            seen.add(href)
            link_text = a.get_text(strip=True)
            if link_text and len(link_text) < 200:
                links.append({"url": href, "text": link_text})
        return {"success": True, "content": text, "links": links}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def crawl_with_playwright(url, browser):
    """Crawl with Playwright headless browser — handles JS-heavy and bot-blocking sites."""
    from bs4 import BeautifulSoup
    try:
        page = await browser.new_page(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        )
        try:
            await page.goto(url, timeout=25000, wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)
            html = await page.content()
        finally:
            await page.close()

        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        links, seen = [], set()
        for a in soup.find_all("a", href=True):
            href = urljoin(url, a["href"])
            if href in seen or href.startswith("javascript:"):
                continue
            seen.add(href)
            link_text = a.get_text(strip=True)
            if link_text and len(link_text) < 200:
                links.append({"url": href, "text": link_text})
        if not text or len(text.strip()) < 50:
            return {"success": False, "error": "Page returned empty or near-empty content"}
        return {"success": True, "content": text, "links": links}
    except Exception as e:
        return {"success": False, "error": str(e)}


def classify_page(client, model, url, sections, content, links, all_sections):
    content_preview = content[:2000] if content else "(empty page)"
    links_text = "\n".join(
        f"- {l['text']}: {l['url']}" for l in links[:50]
    ) or "(no links found)"

    prompt = CLASSIFY_PROMPT.format(
        url=url,
        sections=", ".join(sections) if sections else "(none assigned)",
        content=content_preview,
        links=links_text,
        all_sections=", ".join(all_sections),
    )

    for attempt in range(5):
        try:
            kwargs = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "response_format": {"type": "json_object"},
            }
            if model.startswith("o"):
                kwargs["max_completion_tokens"] = 4000
            else:
                kwargs["temperature"] = 0.1
            response = client.chat.completions.create(**kwargs)
            raw = response.choices[0].message.content.strip()
            return json.loads(raw)
        except RateLimitError as e:
            retry_after = getattr(e, 'retry_after', None)
            if not retry_after and hasattr(e, 'response') and e.response:
                retry_after = e.response.headers.get('retry-after')
            wait = int(retry_after) if retry_after else min(60 * (2 ** attempt), 300)
            logger.warning("Rate limited (attempt %d/5), waiting %ds. Error: %s", attempt + 1, wait, str(e)[:200])
            time.sleep(wait)
    raise RuntimeError("LLM classification failed after 5 retries")


def _save_results(results, path=RESULTS_PATH):
    with open(path, "w") as f:
        json.dump(results, f, indent=2)


async def run_audit(countries_filter=None, dry_run=False, model_override=None, output_path=None, retry_failed=False):
    data = load_sources()
    ep_country_map = build_country_map(data)
    all_sections = get_all_sections(data)

    from app.utils.config import azure_openai_api_keys
    api_keys = azure_openai_api_keys()
    api_key = api_keys[0] if api_keys else ""
    model = model_override or "o4-mini"

    if not api_key:
        logger.error("OPENAI_AZURE_API_KEY not set")
        return

    client = AzureOpenAI(
        azure_endpoint="https://eastus.api.cognitive.microsoft.com/",
        api_key=api_key,
        api_version="2024-12-01-preview",
        max_retries=0,
    )
    min_interval = 60.0 / 5
    last_llm_call = 0.0
    results_path = output_path or RESULTS_PATH

    endpoints = data["source_endpoints"]
    if countries_filter:
        filter_set = set(countries_filter)
        endpoints = [ep for ep in endpoints if ep_country_map.get(ep["id"]) in filter_set]

    # Load existing results
    results = []
    if os.path.exists(results_path):
        try:
            with open(results_path) as f:
                results = json.load(f)
        except Exception:
            pass

    # Retry-failed mode: filter to crawl_failed endpoints, use Playwright
    pw_browser = None
    if retry_failed:
        failed_ids = {r["endpoint_id"] for r in results if r.get("status") == "crawl_failed"}
        remaining = [ep for ep in endpoints if ep["id"] in failed_ids]

        from playwright.async_api import async_playwright
        pw = await async_playwright().start()
        pw_browser = await pw.chromium.launch(headless=True)

        print(f"\n{'='*60}")
        print(f"  RETRY with Playwright: {len(remaining)} crawl-failed endpoints")
        print(f"{'='*60}\n")
    else:
        # Normal mode — resume support
        done_ids = set()
        for rp in set([RESULTS_PATH, results_path]):
            if os.path.exists(rp):
                try:
                    with open(rp) as f:
                        for r in json.load(f):
                            done_ids.add(r["endpoint_id"])
                except Exception:
                    pass
        remaining = [ep for ep in endpoints if ep["id"] not in done_ids]

        print(f"\n{'='*60}")
        print(f"  AUDIT: {len(remaining)} remaining of {len(endpoints)} total ({len(done_ids)} already done)")
        print(f"{'='*60}\n")

    landing_pages = sum(1 for r in results if r.get("page_type") == "landing")
    content_pages = sum(1 for r in results if r.get("page_type") == "content")
    failures = sum(1 for r in results if r.get("status") != "ok")

    for i, ep in enumerate(remaining, 1):
        country = ep_country_map.get(ep["id"], "Unknown")
        url = ep["url"]
        sections = ep.get("sections_covered", [])
        ep_id = ep["id"]

        print(f"[{i}/{len(remaining)}] {country} — {url[:70]}", end="", flush=True)

        if pw_browser:
            crawl_result = await crawl_with_playwright(url, pw_browser)
        else:
            crawl_result = await crawl_with_requests(url)

        if not crawl_result["success"]:
            result = {
                "endpoint_id": ep_id, "country": country, "url": url,
                "sections": sections, "status": "crawl_failed",
                "error": crawl_result.get("error", "unknown"),
            }
            if retry_failed:
                results = [r for r in results if r["endpoint_id"] != ep_id]
            results.append(result)
            failures += 1
            print(f" ✗ crawl failed")
            _save_results(results, results_path)
            continue

        # Rate limit
        elapsed = time.time() - last_llm_call
        if elapsed < min_interval:
            await asyncio.sleep(min_interval - elapsed)
        last_llm_call = time.time()

        # Classify
        try:
            classification = classify_page(
                client, model, url, sections,
                crawl_result["content"], crawl_result["links"], all_sections,
            )
        except Exception as e:
            result = {
                "endpoint_id": ep_id, "country": country, "url": url,
                "sections": sections, "status": "classify_failed",
                "error": str(e),
            }
            if retry_failed:
                results = [r for r in results if r["endpoint_id"] != ep_id]
            results.append(result)
            failures += 1
            print(f" ✗ classify failed")
            _save_results(results, results_path)
            continue

        page_type = classification.get("page_type", "unknown")
        sub_pages = classification.get("sub_pages", [])

        result = {
            "endpoint_id": ep_id, "country": country, "url": url,
            "sections": sections, "status": "ok", "page_type": page_type,
            "has_extractable_rules": classification.get("has_extractable_rules", False),
            "reasoning": classification.get("reasoning", ""),
            "sub_pages": sub_pages,
        }
        if retry_failed:
            results = [r for r in results if r["endpoint_id"] != ep_id]
        results.append(result)

        if page_type == "landing":
            landing_pages += 1
            print(f" → LANDING ({len(sub_pages)} sub-pages)")
        else:
            content_pages += 1
            print(f" → CONTENT")

        _save_results(results, results_path)

    if pw_browser:
        await pw_browser.close()

    print(f"\n{'='*60}")
    print(f"  AUDIT COMPLETE")
    print(f"  Content pages: {content_pages}")
    print(f"  Landing pages: {landing_pages}")
    print(f"  Failures: {failures}")
    print(f"  Total: {len(results)}")
    print(f"{'='*60}")

    if not dry_run:
        updated = generate_updated_sources(data, results, ep_country_map)
        updated_path = os.path.join(os.path.dirname(SOURCES_PATH), "official-sources-updated.json")
        with open(updated_path, "w") as f:
            json.dump(updated, f, indent=2)
        new_count = len(updated["source_endpoints"])
        old_count = len(data["source_endpoints"])
        print(f"\nUpdated sources written to: {updated_path}")
        print(f"Endpoints: {old_count} -> {new_count} ({new_count - old_count:+d})")


def generate_updated_sources(data, audit_results, ep_country_map):
    all_sections = get_all_sections(data)
    updated = json.loads(json.dumps(data))
    results_by_id = {r["endpoint_id"]: r for r in audit_results}

    new_endpoints = []
    for ep in updated["source_endpoints"]:
        result = results_by_id.get(ep["id"])

        if not result or result["status"] != "ok" or result["page_type"] != "landing":
            new_endpoints.append(ep)
            continue

        sub_pages = result.get("sub_pages", [])
        valid_subs = []
        for sp in sub_pages:
            sp_sections = [s for s in sp.get("sections", []) if s in all_sections]
            if sp_sections and sp.get("url"):
                valid_subs.append({"url": sp["url"], "sections": sp_sections, "description": sp.get("description", "")})

        if not valid_subs:
            new_endpoints.append(ep)
            continue

        ep["notes"] = f"Landing page — {len(valid_subs)} sub-pages resolved by audit"
        ep["status"] = "landing_page"
        new_endpoints.append(ep)

        for j, sp in enumerate(valid_subs):
            country = ep_country_map.get(ep["id"], "Unknown")
            new_endpoints.append({
                "id": f"{ep['id']}_sub{j+1}",
                "authority_id": ep["authority_id"],
                "name": f"{ep.get('name', '')} — {sp['description'][:60]}" if sp.get("description") else f"{ep.get('name', '')} — sub-page {j+1}",
                "url": sp["url"],
                "source_type": ep.get("source_type", "html"),
                "content_language": ep.get("content_language", "en"),
                "sections_covered": sp["sections"],
                "authority_category": ep.get("authority_category", ""),
                "extraction_strategy": ep.get("extraction_strategy", "html_readability"),
                "parser_key": ep.get("parser_key", "html_readability_v1"),
                "crawl_frequency": ep.get("crawl_frequency", "monthly"),
                "change_detection_strategy": ep.get("change_detection_strategy", "semantic"),
                "requires_authentication": ep.get("requires_authentication", False),
                "is_javascript_heavy": ep.get("is_javascript_heavy", False),
                "supports_incremental_diffs": True,
                "is_human_curated": False,
                "status": "active",
                "last_crawled_at": None,
                "last_successful_crawl_at": None,
                "last_change_detected_at": None,
                "owner_team": ep.get("owner_team", ""),
                "owner_user_id": None,
                "reviewer_group": None,
                "escalation_required": False,
                "supports_replay": True,
                "parent_endpoint_id": ep["id"],
                "created_at": "2026-07-02T00:00:00Z",
                "updated_at": "2026-07-02T00:00:00Z",
            })

    updated["source_endpoints"] = new_endpoints
    return updated


def main():
    parser = argparse.ArgumentParser(description="Audit source endpoint URLs")
    parser.add_argument("--country", type=str, nargs="+", help="Filter to specific countries")
    parser.add_argument("--dry-run", action="store_true", help="Classify only, don't generate updated JSON")
    parser.add_argument("--model", type=str, default="o4-mini", help="Model to use (e.g. gpt-4o, o4-mini)")
    parser.add_argument("--output", type=str, default=None, help="Output results file path")
    parser.add_argument("--retry-failed", action="store_true", help="Retry crawl_failed endpoints using Playwright")
    args = parser.parse_args()

    asyncio.run(run_audit(countries_filter=args.country, dry_run=args.dry_run, model_override=args.model, output_path=args.output, retry_failed=args.retry_failed))


if __name__ == "__main__":
    main()
