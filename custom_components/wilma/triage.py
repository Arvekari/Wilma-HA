"""Rule-based triage, ported from the wilma-triage skill's deterministic rules.

Note on scope: the original wilma-triage skill leaned on an LLM to read full
message/bulletin prose and pull out buried logistics ("school starts at 9:30
tomorrow, bring outdoor clothes"). That step is language understanding, not a
fixed rule, and doesn't translate into deterministic Python. What *is*
deterministic — and is ported here — is the structural classification: which
lesson-note types are always reported, which message senders/folders are
high-signal, which upcoming items are actionable by date proximity, and so
on. Pair this sensor's `items` attribute with an automation (e.g. calling a
conversation agent on the raw `content` fields) to recover the prose-reading
behaviour if you need it.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from .const import TRIAGE_ALWAYS, TRIAGE_BRIEF, TRIAGE_SKIP

# Lesson-note (merkinnät) typeLabel keyword -> bucket.
ALWAYS_NOTE_KEYWORDS = (
    "selvittämätön poissaolo",  # unexplained absence
    "häiritsi",  # disrupted class
    "puuttui opiskeluvälineitä",  # missing study materials
)
BRIEF_NOTE_KEYWORDS = (
    "terveydellinen syy",  # medical
    "muu selvitetty poissaolo",  # other explained absence
)

WEEKLY_LETTER_KEYWORDS = ("viikkoviesti", "weekly letter")
MONTHLY_NEWSLETTER_KEYWORDS = ("kuukausitiedote", "monthly newsletter")
LOW_SIGNAL_SENDER_KEYWORDS = ("vanhempainyhdistys", "parent union", "kaupunki", "municipality")

ACTIONABLE_DEADLINE_WINDOW_DAYS = 3


def _within_days(date_str: str, days: int) -> bool:
    try:
        date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return False
    today = datetime.now().date()
    return today <= date <= today + timedelta(days=days)


def _classify_lesson_note(note: dict[str, Any]) -> tuple[str, str]:
    label = (note.get("type_label") or "").lower()
    if any(kw in label for kw in ALWAYS_NOTE_KEYWORDS):
        return TRIAGE_ALWAYS, f"{note.get('subject', '')}: {note.get('type_label', '')}".strip(": ")
    if any(kw in label for kw in BRIEF_NOTE_KEYWORDS):
        return TRIAGE_BRIEF, f"{note.get('subject', '')}: {note.get('type_label', '')}".strip(": ")
    return TRIAGE_SKIP, f"{note.get('subject', '')}: {note.get('type_label', '')}".strip(": ")


def _classify_message(message: dict[str, Any]) -> tuple[str, str]:
    sender = (message.get("sender_name") or "").lower()
    subject = message.get("subject") or ""
    lower_subject = subject.lower()

    if any(kw in lower_subject for kw in WEEKLY_LETTER_KEYWORDS):
        return TRIAGE_ALWAYS, f"Viikkoviesti: {subject}"
    if any(kw in lower_subject for kw in MONTHLY_NEWSLETTER_KEYWORDS):
        return TRIAGE_BRIEF, f"Kuukausitiedote: {subject}"
    if any(kw in sender for kw in LOW_SIGNAL_SENDER_KEYWORDS):
        return TRIAGE_SKIP, subject
    # Default: teacher/office messages are worth a brief mention; the actual
    # "always read the full body" judgement call is left to an automation
    # that can pass message.content to a conversation agent.
    return TRIAGE_BRIEF, subject


def build_triage_summary(student_data: dict[str, Any]) -> dict[str, Any]:
    """Classify this refresh's data into always/brief/skip buckets.

    Returns a dict with `items` (flat list, most-actionable first) and
    `counts` per bucket, meant to back a single "actionable summary" sensor.
    """
    items: list[dict[str, str]] = []

    overview = student_data.get("overview", {})

    for exam in overview.get("upcoming_exams", []):
        if _within_days(exam.get("date", ""), ACTIONABLE_DEADLINE_WINDOW_DAYS):
            items.append(
                {
                    "bucket": TRIAGE_ALWAYS,
                    "category": "exam",
                    "text": f"{exam.get('date')} {exam.get('subject')}: {exam.get('name')}",
                }
            )

    for hw in overview.get("homework", [])[:10]:
        if _within_days(hw.get("date", ""), ACTIONABLE_DEADLINE_WINDOW_DAYS):
            items.append(
                {
                    "bucket": TRIAGE_BRIEF,
                    "category": "homework",
                    "text": f"{hw.get('date')} {hw.get('subject')}: {hw.get('homework')}",
                }
            )

    for note in student_data.get("attendance", []):
        bucket, text = _classify_lesson_note(note)
        if bucket != TRIAGE_SKIP:
            items.append({"bucket": bucket, "category": "lesson_note", "text": text})

    for message in student_data.get("messages", [])[:10]:
        bucket, text = _classify_message(message)
        if bucket != TRIAGE_SKIP:
            items.append({"bucket": bucket, "category": "message", "text": text})

    bucket_order = {TRIAGE_ALWAYS: 0, TRIAGE_BRIEF: 1, TRIAGE_SKIP: 2}
    items.sort(key=lambda i: bucket_order.get(i["bucket"], 3))

    counts = {
        TRIAGE_ALWAYS: sum(1 for i in items if i["bucket"] == TRIAGE_ALWAYS),
        TRIAGE_BRIEF: sum(1 for i in items if i["bucket"] == TRIAGE_BRIEF),
    }

    return {"items": items, "counts": counts}
