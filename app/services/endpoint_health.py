"""Lightweight endpoint health checks — HEAD requests in parallel."""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
}

_OK_CODES = {200, 301, 302, 303, 304}
_WORKERS = 20
_TIMEOUT = 10


def _check_one(ep):
    url = ep.url
    try:
        resp = requests.head(url, headers=_HEADERS, timeout=_TIMEOUT,
                             allow_redirects=True)
        code = resp.status_code
        if code in _OK_CODES:
            return {"endpoint_id": ep.endpoint_id, "country": ep.country,
                    "url": url, "ok": True, "status": code}
        if code == 405:
            resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT,
                                allow_redirects=True, stream=True)
            resp.close()
            code = resp.status_code
            if code in _OK_CODES:
                return {"endpoint_id": ep.endpoint_id, "country": ep.country,
                        "url": url, "ok": True, "status": code}
        return {"endpoint_id": ep.endpoint_id, "country": ep.country,
                "url": url, "ok": False, "status": code, "error": f"HTTP {code}"}
    except requests.exceptions.Timeout:
        return {"endpoint_id": ep.endpoint_id, "country": ep.country,
                "url": url, "ok": False, "status": 0, "error": "timeout"}
    except Exception as exc:
        return {"endpoint_id": ep.endpoint_id, "country": ep.country,
                "url": url, "ok": False, "status": 0, "error": str(exc)[:120]}


def check_endpoints(endpoints, workers=_WORKERS):
    results = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_check_one, ep): ep for ep in endpoints}
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception as exc:
                ep = futures[future]
                results.append({
                    "endpoint_id": ep.endpoint_id, "country": ep.country,
                    "url": ep.url, "ok": False, "status": 0,
                    "error": str(exc)[:120],
                })
    results.sort(key=lambda r: (r["ok"], r["country"], r["url"]))
    logger.info("Endpoint health check complete: %d checked, %d broken",
                len(results), sum(1 for r in results if not r["ok"]))
    return results
