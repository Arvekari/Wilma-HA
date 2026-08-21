"""Parse Wilma's /overview JSON payload into schedule/exams/grades/homework."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, TypedDict

FINNISH_DATE_RE = re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$")
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class ScheduleLesson(TypedDict):
    date: str
    day_of_week: int
    start: str
    end: str
    subject: str
    subject_code: str
    teacher: str
    teacher_code: str
    group_id: int


class UpcomingExam(TypedDict):
    exam_id: int
    date: str
    name: str
    subject: str
    subject_code: str
    topic: str | None
    teacher: str
    teacher_code: str


class ExamGrade(TypedDict):
    exam_id: int
    date: str
    name: str
    subject: str
    subject_code: str
    grade: str
    verbal_grade: str | None
    info: str | None
    teacher: str
    teacher_code: str


class HomeworkItem(TypedDict):
    date: str
    subject: str
    subject_code: str
    homework: str
    teacher: str
    teacher_code: str


class OverviewData(TypedDict):
    schedule: list[ScheduleLesson]
    upcoming_exams: list[UpcomingExam]
    grades: list[ExamGrade]
    homework: list[HomeworkItem]
    fetched_at: datetime


def _parse_finnish_date(raw: str) -> str:
    trimmed = (raw or "").strip()
    if ISO_DATE_RE.match(trimmed):
        return trimmed
    m = FINNISH_DATE_RE.match(trimmed)
    if m:
        d, mo, y = m.groups()
        return f"{y}-{mo.zfill(2)}-{d.zfill(2)}"
    return trimmed


def _first_teacher(teachers: list[dict[str, Any]] | None) -> tuple[str, str]:
    t = (teachers or [{}])[0] if teachers else {}
    return t.get("TeacherName") or "", t.get("TeacherCode") or ""


def _first_schedule_teacher(teachers: list[dict[str, Any]] | None) -> tuple[str, str]:
    t = (teachers or [{}])[0] if teachers else {}
    return t.get("LongCaption") or "", t.get("Caption") or ""


def parse_overview(raw: Any) -> OverviewData:
    data = raw if isinstance(raw, dict) else {}
    now = datetime.now()
    return {
        "schedule": _parse_schedule(data.get("Schedule") or []),
        "upcoming_exams": _parse_upcoming_exams(data.get("Groups") or [], now.strftime("%Y-%m-%d")),
        "grades": _parse_top_level_grades(data.get("Exams") or []),
        "homework": _parse_homework(data.get("Groups") or []),
        "fetched_at": now,
    }


def _parse_schedule(entries: list[dict[str, Any]]) -> list[ScheduleLesson]:
    lessons: list[ScheduleLesson] = []
    for entry in entries:
        dates = entry.get("DateArray") or []
        groups = entry.get("Groups") or []
        day = entry.get("Day") or 0
        start = entry.get("Start") or ""
        end = entry.get("End") or ""
        for date in dates:
            for group in groups:
                teacher_name, teacher_code = _first_schedule_teacher(group.get("Teachers"))
                lessons.append(
                    {
                        "date": date,
                        "day_of_week": day,
                        "start": start,
                        "end": end,
                        "subject": group.get("FullCaption") or group.get("Caption") or "",
                        "subject_code": group.get("ShortCaption") or "",
                        "teacher": teacher_name,
                        "teacher_code": teacher_code,
                        "group_id": group.get("Id") or 0,
                    }
                )
    lessons.sort(key=lambda x: (x["date"], x["start"]))
    return lessons


def _parse_upcoming_exams(groups: list[dict[str, Any]], today: str) -> list[UpcomingExam]:
    upcoming: list[UpcomingExam] = []
    for group in groups:
        teacher_name, teacher_code = _first_teacher(group.get("Teachers"))
        subject = group.get("CourseName") or ""
        subject_code = group.get("CourseCode") or ""
        for exam in group.get("Exams") or []:
            grade = exam.get("Grade")
            if grade is not None and str(grade).strip() != "":
                continue
            date = _parse_finnish_date(exam.get("Date") or "")
            if date < today:
                continue
            upcoming.append(
                {
                    "exam_id": exam.get("Id") or 0,
                    "date": date,
                    "name": exam.get("Caption") or exam.get("Name") or "",
                    "subject": subject,
                    "subject_code": subject_code,
                    "topic": (exam.get("Topic") or "").strip() or None,
                    "teacher": teacher_name,
                    "teacher_code": teacher_code,
                }
            )
    upcoming.sort(key=lambda x: x["date"])
    return upcoming


def _parse_top_level_grades(exams: list[dict[str, Any]]) -> list[ExamGrade]:
    grades: list[ExamGrade] = []
    for exam in exams:
        grade = str(exam.get("Grade") or "").strip()
        if not grade:
            continue
        date = _parse_finnish_date(exam.get("Date") or "")
        teachers = exam.get("Teachers") or []
        teacher = teachers[0] if teachers else {}
        grades.append(
            {
                "exam_id": exam.get("ExamId") or exam.get("Id") or 0,
                "date": date,
                "name": exam.get("Name") or "",
                "subject": exam.get("CourseTitle") or "",
                "subject_code": (exam.get("Course") or "").split(" ")[0],
                "grade": grade,
                "verbal_grade": None,
                "info": (exam.get("Info") or "").strip() or None,
                "teacher": teacher.get("TeacherName") or "",
                "teacher_code": teacher.get("TeacherCode") or "",
            }
        )
    grades.sort(key=lambda x: x["date"], reverse=True)
    return grades


def _parse_homework(groups: list[dict[str, Any]]) -> list[HomeworkItem]:
    items: list[HomeworkItem] = []
    for group in groups:
        teacher_name, teacher_code = _first_teacher(group.get("Teachers"))
        subject = group.get("CourseName") or ""
        subject_code = group.get("CourseCode") or ""
        for hw in group.get("Homework") or []:
            text = (hw.get("Homework") or "").replace("\r\n", "\n").strip()
            if not text:
                continue
            items.append(
                {
                    "date": hw.get("Date") or "",
                    "subject": subject,
                    "subject_code": subject_code,
                    "homework": text,
                    "teacher": teacher_name,
                    "teacher_code": teacher_code,
                }
            )
    items.sort(key=lambda x: x["date"], reverse=True)
    return items
