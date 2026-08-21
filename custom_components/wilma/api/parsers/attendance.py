"""Parse Wilma's /attendance/view lesson-notes ("merkinnät") grid.

The attendance table is a fine-grained grid: <thead> declares hour-group
headers like <th colspan="3">9</th>, and <tbody> rows mix filler/event <td>s
with varying colspans. To map an event cell to its hour, walk cumulative grid
columns (sum of colspans) within the row and look up the column's hour group
from the thead — counting <td> indices alone drifts once a filler cell with
colspan > 1 appears.
"""
from __future__ import annotations

import re
from typing import TypedDict

from bs4 import BeautifulSoup

TP_CLASS_RE = re.compile(r"\bat-tp\d+\b")


class LessonNote(TypedDict):
    date: str
    start: str | None
    end: str | None
    subject: str
    type_label: str
    type_class: str
    teacher: str


def _pad(n: int) -> str:
    return str(n).zfill(2)


def _date_to_finnish(date: str) -> str:
    if not date:
        return ""
    parts = date.split("-")
    if len(parts) != 3:
        return date
    year, month, day = parts
    return f"{int(day)}.{int(month)}.{year}"


def parse_attendance_html(html: str, date: str) -> list[LessonNote]:
    soup = BeautifulSoup(html, "html.parser")
    notes: list[LessonNote] = []
    target_finnish = _date_to_finnish(date)

    for table in soup.select("table"):
        hour_map: list[int] = []
        for th in table.select("thead th"):
            text = th.get_text().strip()
            try:
                hour = int(text)
            except ValueError:
                continue
            if 0 <= hour <= 23:
                colspan = int(th.get("colspan", "1") or "1")
                hour_map.extend([hour] * colspan)
        if not hour_map:
            continue  # not the attendance table (e.g. legend)

        for row in table.select("tbody tr"):
            cells = row.find_all("td")
            if len(cells) < 3:
                continue

            row_date = cells[1].get_text().strip()
            if not row_date or row_date != target_finnish:
                continue

            grid_col = 0
            for cell in cells[2:]:
                colspan = int(cell.get("colspan", "1") or "1")
                classes = cell.get("class") or []
                tp_class = next((c for c in classes if TP_CLASS_RE.match(c)), None)

                if tp_class:
                    title = (cell.get("title") or "").strip()
                    cell_text = cell.get_text().strip()

                    subject = ""
                    type_label = ""
                    teacher = cell_text

                    if title:
                        rest = title
                        semi_idx = rest.find(";")
                        if semi_idx > 0:
                            subject = rest[:semi_idx].strip()
                            rest = rest[semi_idx + 1 :].strip()
                        slash_idx = rest.rfind(" /")
                        if slash_idx > 0:
                            after_slash = rest[slash_idx + 2 :]
                            space_after = 1 if after_slash.startswith(" ") else 0
                            type_label = rest[:slash_idx].strip()
                            teacher = rest[slash_idx + 2 + space_after :].strip()

                    start_hour = hour_map[grid_col] if grid_col < len(hour_map) else None
                    end_index = grid_col + colspan - 1
                    end_hour = hour_map[end_index] if end_index < len(hour_map) else None
                    start = end = None
                    if start_hour is not None and end_hour is not None:
                        start = f"{_pad(start_hour)}:00"
                        end = f"{_pad(end_hour)}:45"

                    notes.append(
                        {
                            "date": date,
                            "start": start,
                            "end": end,
                            "subject": subject,
                            "type_label": type_label or tp_class.replace("at-tp", "Type "),
                            "type_class": tp_class,
                            "teacher": teacher,
                        }
                    )
                grid_col += colspan

    return notes
