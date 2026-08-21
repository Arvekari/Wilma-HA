"""Sensor entities: one set of Wilma data sensors per configured student."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import WilmaCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    coordinator: WilmaCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[SensorEntity] = []
    for student in coordinator.students:
        student_number = student["student_number"]
        entities.extend(
            [
                WilmaScheduleSensor(coordinator, entry, student_number),
                WilmaHomeworkSensor(coordinator, entry, student_number),
                WilmaExamsSensor(coordinator, entry, student_number),
                WilmaGradesSensor(coordinator, entry, student_number),
                WilmaAttendanceSensor(coordinator, entry, student_number),
                WilmaMessagesSensor(coordinator, entry, student_number),
                WilmaNewsSensor(coordinator, entry, student_number),
                WilmaTriageSensor(coordinator, entry, student_number),
            ]
        )
    async_add_entities(entities)


class WilmaStudentSensorBase(CoordinatorEntity[WilmaCoordinator], SensorEntity):
    """Shared device grouping (one HA device per student) and availability."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: WilmaCoordinator, entry: ConfigEntry, student_number: str, key: str) -> None:
        super().__init__(coordinator)
        self._student_number = student_number
        self._attr_unique_id = f"{entry.entry_id}_{student_number}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}_{student_number}")},
            name=self._student_data.get("name", student_number) if coordinator.data else student_number,
            manufacturer="Wilma (aikarjal/wilmai)",
            model="Student",
        )

    @property
    def _student_data(self) -> dict[str, Any]:
        return (self.coordinator.data or {}).get(self._student_number, {})

    @property
    def available(self) -> bool:
        return super().available and self._student_number in (self.coordinator.data or {})


def _truncate(text: str, limit: int = 250) -> str:
    # HA sensor states are capped at 255 chars; leave headroom.
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


FI_WEEKDAYS = ["Maanantai", "Tiistai", "Keskiviikko", "Torstai", "Perjantai", "Lauantai", "Sunnuntai"]


def _weekday_name(date_str: str | None) -> str | None:
    if not date_str:
        return None
    try:
        parsed = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return None
    return FI_WEEKDAYS[parsed.weekday()]


def _expected_next_school_date(today: datetime) -> datetime:
    """Calendar-only guess at the next school day, ignoring holidays: Mon-Thu -> +1,
    Fri -> next Mon (+3), Sat -> next Mon (+2), Sun -> next Mon (+1)."""
    weekday = today.weekday()  # 0=Mon ... 6=Sun
    if weekday == 4:
        return today + timedelta(days=3)
    if weekday == 5:
        return today + timedelta(days=2)
    if weekday == 6:
        return today + timedelta(days=1)
    return today + timedelta(days=1)


class WilmaScheduleSensor(WilmaStudentSensorBase):
    """State = the current/next lesson today as text; full school-week awareness in attributes.

    "Next school day" is derived from Wilma's own schedule data (the next date
    that actually has lessons), not a naive calendar +1 day — so Friday
    correctly points at Monday, and a public holiday correctly makes Tuesday
    point at Thursday instead of Wednesday.
    """

    _attr_translation_key = "schedule"
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, coordinator, entry, student_number) -> None:
        super().__init__(coordinator, entry, student_number, "schedule")

    def _lessons_on(self, date_str: str) -> list[dict[str, Any]]:
        lessons = self._student_data.get("overview", {}).get("schedule", [])
        on_date = [lesson for lesson in lessons if lesson["date"] == date_str]
        return sorted(on_date, key=lambda lesson: lesson.get("start", ""))

    def _todays_lessons(self) -> list[dict[str, Any]]:
        return self._lessons_on(datetime.now().strftime("%Y-%m-%d"))

    def _next_school_day(self) -> str | None:
        """The next date (after today) that Wilma's schedule actually has lessons on."""
        today = datetime.now().strftime("%Y-%m-%d")
        lessons = self._student_data.get("overview", {}).get("schedule", [])
        future_dates = sorted({lesson["date"] for lesson in lessons if lesson["date"] > today})
        return future_dates[0] if future_dates else None

    @property
    def native_value(self) -> Any:
        now_hm = datetime.now().strftime("%H:%M")
        todays = self._todays_lessons()
        weekday = _weekday_name(datetime.now().strftime("%Y-%m-%d"))
        if not todays:
            return _truncate(f"{weekday}: ei tunteja tänään")
        # Current or next lesson: first one that hasn't ended yet, else the last one.
        upcoming = [l for l in todays if l.get("end", "") >= now_hm]
        lesson = upcoming[0] if upcoming else todays[-1]
        return _truncate(
            f"{weekday} {lesson.get('start', '')}–{lesson.get('end', '')} {lesson.get('subject', '')}"
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        today_dt = datetime.now()
        next_day = self._next_school_day()
        expected_next = _expected_next_school_date(today_dt).strftime("%Y-%m-%d")
        return {
            "weekday_today": _weekday_name(today_dt.strftime("%Y-%m-%d")),
            "lessons_today": self._todays_lessons(),
            "next_school_day": next_day,
            "weekday_next_school_day": _weekday_name(next_day),
            "lessons_next_school_day": self._lessons_on(next_day) if next_day else [],
            # True when a holiday (or other closure) pushed the next school day
            # later than a plain Mon-Fri calendar would suggest — e.g. Tuesday
            # jumping to Thursday because Wednesday is a public holiday.
            "next_school_day_skips_a_weekday": bool(next_day) and next_day > expected_next,
            "lessons": self._student_data.get("overview", {}).get("schedule", []),
        }


class WilmaHomeworkSensor(WilmaStudentSensorBase):
    """State = the most recent homework entry as text; full list in `items`."""

    _attr_translation_key = "homework"
    _attr_icon = "mdi:notebook-edit-outline"

    def __init__(self, coordinator, entry, student_number) -> None:
        super().__init__(coordinator, entry, student_number, "homework")

    @property
    def native_value(self) -> Any:
        items = self._student_data.get("overview", {}).get("homework", [])
        if not items:
            return "Ei läksyjä"
        hw = items[0]  # overview.homework is sorted newest-date-first
        return _truncate(f"{hw.get('subject', '')}: {hw.get('homework', '')}")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        items = self._student_data.get("overview", {}).get("homework", [])
        return {"count": len(items), "items": items}


class WilmaExamsSensor(WilmaStudentSensorBase):
    """State = the next upcoming exam as text; full list in `upcoming_exams`."""

    _attr_translation_key = "exams"
    _attr_icon = "mdi:file-document-edit-outline"

    def __init__(self, coordinator, entry, student_number) -> None:
        super().__init__(coordinator, entry, student_number, "exams")

    @property
    def native_value(self) -> Any:
        exams = self._student_data.get("overview", {}).get("upcoming_exams", [])
        if not exams:
            return "Ei tulevia kokeita"
        exam = exams[0]
        return _truncate(f"{exam.get('date', '')} {exam.get('subject', '')}: {exam.get('name', '')}")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        exams = self._student_data.get("overview", {}).get("upcoming_exams", [])
        return {"count": len(exams), "upcoming_exams": exams}


class WilmaGradesSensor(WilmaStudentSensorBase):
    _attr_translation_key = "grades"
    _attr_icon = "mdi:school-outline"

    def __init__(self, coordinator, entry, student_number) -> None:
        super().__init__(coordinator, entry, student_number, "grades")

    @property
    def native_value(self) -> Any:
        grades = self._student_data.get("overview", {}).get("grades", [])
        return grades[0]["grade"] if grades else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"recent_grades": self._student_data.get("overview", {}).get("grades", [])[:10]}


class WilmaAttendanceSensor(WilmaStudentSensorBase):
    """State = the most recent lesson note as text; full list in `lesson_notes`."""

    _attr_translation_key = "attendance"
    _attr_icon = "mdi:account-alert-outline"

    def __init__(self, coordinator, entry, student_number) -> None:
        super().__init__(coordinator, entry, student_number, "attendance")

    @property
    def native_value(self) -> Any:
        notes = self._student_data.get("attendance", [])
        if not notes:
            return "Ei merkintöjä"
        note = notes[0]
        return _truncate(f"{note.get('subject', '')}: {note.get('type_label', '')}".strip(": "))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        notes = self._student_data.get("attendance", [])
        return {"count": len(notes), "lesson_notes": notes}


class WilmaMessagesSensor(WilmaStudentSensorBase):
    """State = the most recent message's subject as text; full list in `recent_messages`."""

    _attr_translation_key = "messages"
    _attr_icon = "mdi:email-outline"

    def __init__(self, coordinator, entry, student_number) -> None:
        super().__init__(coordinator, entry, student_number, "messages")

    @property
    def native_value(self) -> Any:
        messages = self._student_data.get("messages", [])
        if not messages:
            return "Ei viestejä"
        return _truncate(messages[0].get("subject", ""))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        messages = self._student_data.get("messages", [])
        return {"count": len(messages), "recent_messages": messages}


class WilmaNewsSensor(WilmaStudentSensorBase):
    """State = the most recent news title as text; full list in `recent_news`."""

    _attr_translation_key = "news"
    _attr_icon = "mdi:newspaper-variant-outline"

    def __init__(self, coordinator, entry, student_number) -> None:
        super().__init__(coordinator, entry, student_number, "news")

    @property
    def native_value(self) -> Any:
        news = self._student_data.get("news", [])
        if not news:
            return "Ei tiedotteita"
        return _truncate(news[0].get("title", ""))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        news = self._student_data.get("news", [])
        return {"count": len(news), "recent_news": news}


class WilmaTriageSensor(WilmaStudentSensorBase):
    """Opt-in-by-nature summary sensor: always present, but only meaningful
    once the user wires an automation/notification on top of it — see
    triage.py module docstring for what this can and can't classify on its own.
    """

    _attr_translation_key = "actionable_summary"
    _attr_icon = "mdi:clipboard-alert-outline"

    def __init__(self, coordinator, entry, student_number) -> None:
        super().__init__(coordinator, entry, student_number, "triage")

    @property
    def native_value(self) -> Any:
        counts = self._student_data.get("triage", {}).get("counts", {})
        return counts.get("always_report", 0) + counts.get("report_briefly", 0)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self._student_data.get("triage", {"items": [], "counts": {}})
