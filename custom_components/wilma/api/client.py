"""High-level Wilma client: login + typed accessors for each data surface."""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Awaitable, Callable, Optional

import aiohttp

from .dates import parse_wilma_timestamp
from .parsers.attendance import LessonNote, parse_attendance_html
from .parsers.messages import Message, parse_message_detail_html, parse_messages_list
from .parsers.news import (
    NewsItem,
    parse_news_detail_html,
    parse_news_detail_json,
    parse_news_list,
    parse_news_list_html,
)
from .parsers.overview import OverviewData, parse_overview
from .parsers.students import StudentInfo, parse_students_from_home
from .session import MfaRequiredError, WilmaSession

MfaCallback = Callable[[str], Awaitable[str]]

MESSAGE_FOLDER_PATHS = {
    "inbox": "/messages/list",
    "archive": "/messages/list/archive",
    "outbox": "/messages/list/outbox",
    "drafts": "/messages/list/drafts",
    "appointments": "/messages/list/appointments",
}


def _safe_json(text: str) -> dict:
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return {}


class WilmaClient:
    """Thin wrapper matching the shape of the aikarjal/wilmai TS client's public API."""

    def __init__(self, session: WilmaSession) -> None:
        self._session = session

    @classmethod
    async def login(
        cls,
        client_session: aiohttp.ClientSession,
        base_url: str,
        username: str,
        password: str,
        student_number: Optional[str] = None,
        on_mfa_required: Optional[MfaCallback] = None,
    ) -> "WilmaClient":
        session = WilmaSession(client_session, base_url, student_number)
        try:
            await session.login(username, password)
        except MfaRequiredError as err:
            if not on_mfa_required:
                raise
            otp_code = await on_mfa_required(err.formkey)
            await session.submit_mfa_code(err.formkey, otp_code)
        return cls(session)

    @staticmethod
    async def list_students(
        client_session: aiohttp.ClientSession,
        base_url: str,
        username: str,
        password: str,
        on_mfa_required: Optional[MfaCallback] = None,
    ) -> list[StudentInfo]:
        session = WilmaSession(client_session, base_url)
        try:
            await session.login(username, password)
        except MfaRequiredError as err:
            if not on_mfa_required:
                raise
            otp_code = await on_mfa_required(err.formkey)
            await session.submit_mfa_code(err.formkey, otp_code)
        resp = await session.get("/")
        html = await resp.text()
        return parse_students_from_home(html)

    async def get_overview(self) -> OverviewData:
        resp = await self._session.get("/overview")
        text = await resp.text()
        return parse_overview(_safe_json(text))

    async def get_attendance(self, date: Optional[str] = None) -> list[LessonNote]:
        path = "/attendance/view" + (f"?date={date}" if date else "")
        resp = await self._session.get(path)
        text = await resp.text()
        return parse_attendance_html(text, date or "")

    async def list_messages(self, folder: str = "inbox") -> list[Message]:
        path = MESSAGE_FOLDER_PATHS.get(folder, "/messages/list")
        resp = await self._session.get(path)
        text = await resp.text()
        return parse_messages_list(_safe_json(text), folder)

    async def get_message(self, message_id: int) -> Message:
        resp = await self._session.get(f"/messages/{message_id}")
        content_type = (resp.headers.get("content-type") or "").lower()
        text = await resp.text()
        if "application/json" in content_type:
            data = _safe_json(text)
            return {
                "wilma_id": message_id,
                "subject": str(data.get("Subject", data.get("subject", ""))),
                "sent_at": parse_wilma_timestamp(data.get("TimeStamp", data.get("timestamp"))),
                "folder": str(data.get("Folder", "unknown")),
                "sender_name": data.get("Sender", data.get("sender")),
                "content": data.get("Content", data.get("content")),
                "fetched_at": datetime.now(),
            }
        return parse_message_detail_html(text, message_id)

    async def list_news(self) -> list[NewsItem]:
        resp = await self._session.get("/news")
        text = await resp.text()
        data = _safe_json(text)
        if isinstance(data, list):
            return parse_news_list(data)
        return parse_news_list_html(text)

    async def get_news(self, news_id: int) -> NewsItem:
        resp = await self._session.get(f"/news/{news_id}")
        content_type = (resp.headers.get("content-type") or "").lower()
        text = await resp.text()
        if "text/html" not in content_type:
            data = _safe_json(text)
            if data:
                return parse_news_detail_json(news_id, data, str(resp.url))
        return parse_news_detail_html(text, news_id, str(resp.url))

    async def fetch_news_resource(
        self, news_id: int, resource_id: str, item: Optional[NewsItem] = None
    ) -> dict:
        """Download one news attachment. Returns a dict with keys:
        status ("downloaded" | "not_a_file"), content (bytes | None),
        content_type (str | None), and the resolved resource dict.
        """
        item = item or await self.get_news(news_id)
        resource = next((r for r in item.get("resources", []) if r["id"] == resource_id), None)
        if resource is None:
            raise ValueError(f'News resource "{resource_id}" not found')

        if resource["auth_context"] == "wilma":
            from urllib.parse import urlparse

            parsed = urlparse(resource["url"])
            response = await self._session.get(f"{parsed.path}?{parsed.query}" if parsed.query else parsed.path)
            content_type = (response.headers.get("content-type") or "").lower()
            if content_type.startswith("text/html") or content_type.startswith("application/xhtml"):
                await response.read()
                return {"status": "not_a_file", "content": None, "content_type": None, "resource": resource}
            content = await response.read()
            return {"status": "downloaded", "content": content, "content_type": content_type, "resource": resource}

        result = await self._fetch_external_file(resource["url"])
        if result is None:
            return {"status": "not_a_file", "content": None, "content_type": None, "resource": resource}
        content, content_type = result
        return {"status": "downloaded", "content": content, "content_type": content_type, "resource": resource}

    async def _fetch_external_file(self, raw_url: str) -> Optional[tuple[bytes, str | None]]:
        """Fetch an external URL like a signed-out browser — isolated cookies, no Wilma auth."""
        from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

        candidates = [raw_url]
        parsed = urlparse(raw_url)
        params = parse_qs(parsed.query)
        for key in ("download", "dl"):
            if key not in params:
                new_params = {**params, key: ["1"]}
                candidates.append(
                    urlunparse(parsed._replace(query=urlencode(new_params, doseq=True)))
                )

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36"
            ),
            "Accept": "*/*",
        }
        async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar()) as isolated:
            for candidate in candidates:
                resp = await isolated.get(candidate, headers=headers, allow_redirects=True)
                content_type = (resp.headers.get("content-type") or "").lower()
                is_html = content_type.startswith("text/html") or content_type.startswith("application/xhtml")
                body = await resp.read()
                if resp.ok and is_html:
                    continue
                return body, content_type
        return None
