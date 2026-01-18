from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from ..services.mcp_registry import mcp_tool


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._texts: list[str] = []
        self._links: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style", "noscript"):
            self._skip += 1
        if tag == "a":
            for k, v in attrs:
                if k == "href" and v:
                    self._links.append(v)

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "noscript") and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        s = data.strip()
        if not s:
            return
        self._texts.append(s)

    def finish(self) -> tuple[str, list[str]]:
        text = "\n".join(self._texts)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text, self._links


def _normalize_url(u: str) -> str:
    u = (u or "").strip()
    if not u:
        return u
    return u


@mcp_tool(
    name="web.search",
    description="通过 SearxNG JSON API 搜索网页（需要提供 searxng_base_url）",
    parameters={
        "type": "object",
        "properties": {
            "searxng_base_url": {"type": "string"},
            "query": {"type": "string"},
            "max_results": {"type": "integer", "minimum": 1, "maximum": 10},
        },
        "required": ["searxng_base_url", "query"],
        "additionalProperties": False,
    },
    read_only=True,
    dangerous=False,
    timeout_seconds=15.0,
    max_output_chars=12000,
)
def web_search(args: dict[str, Any]) -> dict:
    base = str(args.get("searxng_base_url") or "").rstrip("/")
    q = str(args.get("query") or "").strip()
    max_results = int(args.get("max_results") or 5)
    max_results = min(max(1, max_results), 10)
    url = f"{base}/search"
    params = {"q": q, "format": "json"}
    with httpx.Client(timeout=15.0, follow_redirects=True, headers={"User-Agent": "FASS-Hub/0.1"}) as client:
        r = client.get(url, params=params)
        r.raise_for_status()
        data = r.json() or {}
    results = []
    for it in (data.get("results") or [])[:max_results]:
        if not isinstance(it, dict):
            continue
        href = it.get("url")
        if isinstance(href, str) and href:
            results.append(
                {
                    "url": href,
                    "title": it.get("title"),
                    "content": it.get("content"),
                }
            )
    return {"query": q, "results": results}


@mcp_tool(
    name="web.fetch",
    description="抓取单个 URL 并提取正文文本（强制截断）",
    parameters={
        "type": "object",
        "properties": {"url": {"type": "string"}, "max_chars": {"type": "integer", "minimum": 200, "maximum": 20000}},
        "required": ["url"],
        "additionalProperties": False,
    },
    read_only=True,
    dangerous=False,
    timeout_seconds=20.0,
    max_output_chars=12000,
)
def web_fetch(args: dict[str, Any]) -> dict:
    url = _normalize_url(str(args.get("url") or ""))
    max_chars = int(args.get("max_chars") or 6000)
    max_chars = min(max(200, max_chars), 20000)
    with httpx.Client(timeout=20.0, follow_redirects=True, headers={"User-Agent": "FASS-Hub/0.1"}) as client:
        r = client.get(url)
        r.raise_for_status()
        ct = (r.headers.get("content-type") or "").lower()
        text = r.text or ""

    if "text/html" in ct or "<html" in text.lower():
        parser = _TextExtractor()
        parser.feed(text)
        body, links = parser.finish()
        abs_links = []
        for ln in links:
            try:
                abs_links.append(urljoin(url, ln))
            except Exception:
                continue
        out = body[:max_chars]
        return {"url": url, "content": out, "links": abs_links[:50]}

    return {"url": url, "content": text[:max_chars], "links": []}


@mcp_tool(
    name="web.extract_links",
    description="从 URL 列表中过滤出同域名链接（用于爬虫下一跳）",
    parameters={
        "type": "object",
        "properties": {"seed_url": {"type": "string"}, "links": {"type": "array", "items": {"type": "string"}}, "max_links": {"type": "integer", "minimum": 1, "maximum": 50}},
        "required": ["seed_url", "links"],
        "additionalProperties": False,
    },
    read_only=True,
    dangerous=False,
    timeout_seconds=5.0,
    max_output_chars=8000,
)
def extract_links(args: dict[str, Any]) -> dict:
    seed_url = str(args.get("seed_url") or "")
    links = args.get("links") or []
    max_links = int(args.get("max_links") or 20)
    max_links = min(max(1, max_links), 50)
    if not isinstance(links, list):
        return {"links": []}
    host = urlparse(seed_url).netloc
    out = []
    for u in links:
        if not isinstance(u, str):
            continue
        pu = urlparse(u)
        if pu.scheme in ("http", "https") and pu.netloc == host:
            out.append(u)
        if len(out) >= max_links:
            break
    return {"links": out}

