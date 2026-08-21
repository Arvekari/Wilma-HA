"""Parse the logged-in student list from Wilma's home page."""
from __future__ import annotations

import re
from typing import TypedDict

from bs4 import BeautifulSoup

NAV_KEYWORDS = [
    "messages",
    "viestit",
    "schedule",
    "lukujärjestys",
    "gradebook",
    "assessments",
    "exams",
    "attendance",
    "poissaolot",
    "printouts",
    "news",
]

HREF_RE = re.compile(r"/!(\d+)/")


class StudentInfo(TypedDict):
    student_number: str
    name: str
    href: str


def parse_students_from_home(html: str) -> list[StudentInfo]:
    soup = BeautifulSoup(html, "html.parser")
    students: dict[str, StudentInfo] = {}

    for anchor in soup.select("a[href^='/!']"):
        href = anchor.get("href", "")
        match = HREF_RE.search(href)
        if not match:
            continue
        student_number = match.group(1)

        clone = BeautifulSoup(str(anchor), "html.parser")
        for tag in clone.select("small, span.lem"):
            tag.decompose()
        text = clone.get_text().strip()
        if not text:
            continue

        lower = text.lower()
        if any(kw in lower for kw in NAV_KEYWORDS):
            continue

        if student_number not in students:
            students[student_number] = {
                "student_number": student_number,
                "name": text,
                "href": href,
            }

    return list(students.values())
