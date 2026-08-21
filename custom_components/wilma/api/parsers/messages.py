"""Parse Wilma message list/detail responses."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, TypedDict

from bs4 import BeautifulSoup

from ..dates import parse_wilma_timestamp

TIME_FIELD_KEYS = (
    "Time", "time", "TimeStamp", "Timestamp", "timestamp",
    "SentAt", "sentAt", "Sent", "sent", "Date", "date",
    "Created", "created", "CreatedAt", "createdAt",
)


class Message(TypedDict):
    wilma_id: int
    subject: str
    sent_at: datetime
    folder: str
    sender_name: str | None
    content: str | None
    fetched_at: datetime


def _compact(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _normalize_list(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        lst = data.get("messages", data.get("Messages"))
        if isinstance(lst, list):
            return lst
    return []


def parse_messages_list(data: Any, folder: str) -> list[Message]:
    now = datetime.now()
    messages: list[Message] = []
    for item in _normalize_list(data):
        try:
            wilma_id = int(item.get("id", item.get("Id")))
        except (TypeError, ValueError):
            continue
        subject = _compact(str(item.get("Subject", item.get("subject", ""))))
        time_value = next((item[k] for k in TIME_FIELD_KEYS if k in item), None)
        messages.append(
            {
                "wilma_id": wilma_id,
                "subject": subject,
                "sent_at": parse_wilma_timestamp(time_value),
                "folder": folder,
                "sender_name": None,
                "content": None,
                "fetched_at": now,
            }
        )
    return messages


def _extract_reply_sender_name(header_text: str) -> str | None:
    match = re.match(r"^(.+?)\s+(?:vastasi|svarade|replied)\b", _compact(header_text), re.IGNORECASE)
    if match:
        sender = match.group(1).strip()
        return sender or None
    return None


def _extract_reply_timestamp_text(header_text: str) -> str:
    match = re.search(r"(\d{1,2}\.\d{1,2}\.\d{4}\s+\d{1,2}:\d{2})", header_text)
    return match.group(1) if match else header_text


def parse_message_detail_html(html: str, message_id: int) -> Message:
    soup = BeautifulSoup(html, "html.parser")

    panel_body = soup.select_one("div#page-content-area.panel-body")
    if panel_body is not None:
        subj_elem = panel_body.find("h1", recursive=False)
    else:
        subj_elem = soup.select_one("h1, h2, .panel-title, .msg-subject")
    subject = subj_elem.get_text().strip() if subj_elem else ""

    sender_name: str | None = None
    sent_at = datetime.now()

    prop_table = soup.select_one("table.proptable")
    if prop_table is not None:
        for row in prop_table.select("tr"):
            th = row.find("th")
            td = row.find("td")
            if th is None or td is None:
                continue
            header = th.get_text().strip().lower()
            if "lähettäjä" in header or "sender" in header:
                sender_link = td.select_one("a.profile-link")
                sender_name = sender_link.get_text().strip() if sender_link else td.get_text().strip()
            elif "lähetetty" in header or "sent" in header:
                sent_at = parse_wilma_timestamp(td.get_text().strip())

    content: str | None = None

    reply_boxes = soup.select("div.m-replybox.hidden")
    if reply_boxes:
        other_replies = [box for box in reply_boxes if "m-replybox-me" not in (box.get("class") or [])]
        if other_replies:
            latest = other_replies[-1]
            inner = latest.select_one("div.inner.hidden")
            if inner is not None:
                content = inner.get_text().strip()
                reply_header = latest.find("h2")
                reply_header_text = reply_header.get_text().strip() if reply_header else ""
                reply_sender = latest.select_one("a.profile-link")

                if reply_sender is not None:
                    sender_name = reply_sender.get_text().strip()
                else:
                    replied = _extract_reply_sender_name(reply_header_text)
                    if replied:
                        sender_name = replied

                if reply_header_text:
                    sent_at = parse_wilma_timestamp(_extract_reply_timestamp_text(reply_header_text))

    if not content:
        hidden = soup.select_one("div.ckeditor.hidden")
        if hidden is not None:
            content = hidden.get_text().strip()

    if not content and panel_body is not None:
        clone = BeautifulSoup(str(panel_body), "html.parser")
        for sel in ("table.proptable", "h1", "iframe", "script", "style"):
            for tag in clone.select(sel):
                tag.decompose()
        text = clone.get_text().strip()
        if text:
            content = text

    if not content:
        fallback = soup.select_one(".message-body, .msg-content")
        if fallback is not None:
            for tag in fallback.select("script, style"):
                tag.decompose()
            content = fallback.get_text().strip()

    if not content or not content.strip():
        content = "(Could not extract content body)"

    return {
        "wilma_id": message_id,
        "subject": subject,
        "sent_at": sent_at,
        "folder": "unknown",
        "sender_name": sender_name,
        "content": content,
        "fetched_at": datetime.now(),
    }
