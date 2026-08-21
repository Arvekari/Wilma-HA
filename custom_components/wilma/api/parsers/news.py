"""Parse Wilma news list/detail responses (JSON and HTML variants)."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, TypedDict
from urllib.parse import unquote, urljoin, urlparse

from bs4 import BeautifulSoup

from ..dates import parse_wilma_timestamp

FILE_EXTENSION_RE = re.compile(
    r"\.(?:pdf|docx?|xlsx?|pptx?|odt|ods|odp|rtf|txt|csv|zip|7z|png|jpe?g|gif|webp)$", re.IGNORECASE
)


class NewsResource(TypedDict):
    id: str
    label: str
    url: str
    auth_context: str  # "wilma" | "external"
    file_name: str | None


class NewsItem(TypedDict):
    wilma_id: int
    title: str
    subtitle: str | None
    author: str | None
    published: datetime | None
    content: str | None
    resources: list[NewsResource]
    fetched_at: datetime


def parse_news_list(data: Any) -> list[NewsItem]:
    if not isinstance(data, list):
        return []
    now = datetime.now()
    items: list[NewsItem] = []
    for item in data:
        try:
            items.append(
                {
                    "wilma_id": int(item.get("id", item.get("Id"))),
                    "title": str(item.get("Title", item.get("title", ""))),
                    "subtitle": None,
                    "author": None,
                    "published": parse_wilma_timestamp(item.get("Published", item.get("published"))),
                    "content": None,
                    "resources": [],
                    "fetched_at": now,
                }
            )
        except (TypeError, ValueError):
            continue
    return items


def _decode(value: str) -> str:
    try:
        return unquote(value)
    except Exception:  # noqa: BLE001 - defensive, mirrors decodeURIComponentSafely
        return value


def _resolve_safe_http_url(raw_href: str, base_url: str | None) -> str | None:
    raw_href = (raw_href or "").strip()
    if not raw_href or raw_href.startswith("#"):
        return None
    try:
        url = urljoin(base_url, raw_href) if base_url else raw_href
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return None
        return url
    except Exception:  # noqa: BLE001
        return None


def _extract_news_resources(content_html: str, base_url: str | None) -> list[NewsResource]:
    resources: list[NewsResource] = []
    seen: set[str] = set()
    soup = BeautifulSoup(content_html, "html.parser")
    base_origin = urlparse(base_url).netloc if base_url else None

    for anchor in soup.select("a[href]"):
        url = _resolve_safe_http_url(anchor.get("href", ""), base_url)
        if not url or url in seen:
            continue
        seen.add(url)

        origin = urlparse(url).netloc
        auth_context = "wilma" if base_origin and origin == base_origin else "external"

        path = urlparse(url).path
        file_name = None
        if FILE_EXTENSION_RE.search(_decode(path)):
            last_segment = [p for p in path.split("/") if p]
            file_name = _decode(last_segment[-1]) if last_segment else None

        label = anchor.get_text().strip() or file_name or urlparse(url).netloc
        resources.append(
            {
                "id": f"resource-{len(resources) + 1}",
                "label": label,
                "url": url,
                "auth_context": auth_context,
                "file_name": file_name,
            }
        )
    return resources


def parse_news_detail_json(news_id: int, data: dict[str, Any], base_url: str | None = None) -> NewsItem:
    content = data.get("content", data.get("Content"))
    resources: list[NewsResource] = []
    if content and "<a" in content:
        resources = _extract_news_resources(content, base_url)
    return {
        "wilma_id": news_id,
        "title": str(data.get("title", data.get("Title", ""))),
        "subtitle": data.get("subtitle", data.get("Subtitle")),
        "author": data.get("author", data.get("Author")),
        "published": parse_wilma_timestamp(data.get("Published", data.get("published"))),
        "content": content,
        "resources": resources,
        "fetched_at": datetime.now(),
    }


def parse_news_detail_html(html: str, news_id: int, base_url: str | None = None) -> NewsItem:
    soup = BeautifulSoup(html, "html.parser")

    title = (soup.title.get_text().strip() if soup.title else "") or ""
    if title.endswith(" - Wilma"):
        title = title[:-8].strip()
    if not title:
        title_elem = soup.select_one("#page-content-area h1, #main-content h1, h1")
        title = title_elem.get_text().strip() if title_elem else ""

    subtitle_elem = soup.select_one("p.sub-text, .subtitle")
    subtitle = subtitle_elem.get_text().strip() if subtitle_elem else None

    content = None
    resources: list[NewsResource] = []
    content_elem = soup.select_one("#news-content") or soup.select_one(
        ".news-content, .content, .ckeditor, article, .panel-body"
    )
    if content_elem is not None:
        resources = _extract_news_resources(str(content_elem), base_url)

        clean = BeautifulSoup(str(content_elem), "html.parser")
        for tag in clean.select("script, style"):
            tag.decompose()
        text = clean.get_text().strip()

        prose_only = BeautifulSoup(str(content_elem), "html.parser")
        for tag in prose_only.select("a[href]"):
            tag.decompose()
        content = text if prose_only.get_text().strip() else None

    return {
        "wilma_id": news_id,
        "title": title,
        "subtitle": subtitle,
        "author": None,
        "published": None,
        "content": content,
        "resources": resources,
        "fetched_at": datetime.now(),
    }


def parse_news_list_html(html: str) -> list[NewsItem]:
    soup = BeautifulSoup(html, "html.parser")
    now = datetime.now()
    items: list[NewsItem] = []
    seen_ids: set[int] = set()

    headers = soup.select("div.left h2.no-border, h2.no-border")
    for header in headers:
        published = parse_wilma_timestamp(header.get_text().strip())

        sib = header.find_next_sibling()
        while sib is not None:
            if sib.name == "h2" and "no-border" in (sib.get("class") or []):
                break
            classes = sib.get("class") or []
            if sib.name == "div" and ("well" in classes or "margin-bottom" in classes):
                link_tag = sib.select_one("a[href*='/news/']")
                href = link_tag.get("href", "") if link_tag else ""
                match = re.search(r"/news/(\d+)", href)
                news_id = int(match.group(1)) if match else None
                if not news_id or news_id in seen_ids:
                    sib = sib.find_next_sibling()
                    continue
                seen_ids.add(news_id)

                title_elem = sib.select_one("h1, h2, h3, h4")
                title = (
                    (title_elem.get_text().strip() if title_elem else "")
                    or (link_tag.get_text().strip() if link_tag else "")
                    or "Untitled News"
                )

                subtitle_elem = sib.select_one("p.sub-text")
                subtitle = subtitle_elem.get_text().strip() if subtitle_elem else None

                author = None
                meta_p = sib.select_one("p.small")
                if meta_p is not None:
                    author_link = meta_p.select_one("a.profile-link")
                    if author_link is not None:
                        author = author_link.get("title") or author_link.get_text().strip()
                    else:
                        tooltip = meta_p.select_one("span.tooltip")
                        if tooltip is not None:
                            author = tooltip.get("title") or tooltip.get_text().strip()
                        else:
                            meta_span = meta_p.select_one("span.horizontal-link-container.small")
                            if meta_span is not None:
                                meta_text = meta_span.get_text().strip()
                                link_text = link_tag.get_text().strip() if link_tag else ""
                                if "ylläpidon tiedote" in meta_text.lower():
                                    author = "Ylläpito"
                                elif len(meta_text.split()) < 5 and meta_text != link_text:
                                    author = meta_text

                items.append(
                    {
                        "wilma_id": news_id,
                        "title": title,
                        "subtitle": subtitle,
                        "author": author,
                        "published": published,
                        "content": None,
                        "resources": [],
                        "fetched_at": now,
                    }
                )

            sib = sib.find_next_sibling()

    return items
