"""Sensor entities: one set of Wilma data sensors per configured student."""
from __future__ import annotations

from datetime import datetime
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


class WilmaScheduleSensor(WilmaStudentSensorBase):
    _attr_translation_key = "schedule"
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, coordinator, entry, student_number) -> None:
        super().__init__(coordinator, entry, student_number, "schedule")

    @property
    def native_value(self) -> Any:
        today = datetime.now().strftime("%Y-%m-%d")
        lessons = self._student_data.get("overview", {}).get("schedule", [])
        todays = [lesson for lesson in lessons if lesson["date"] == today]
        return len(todays)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"lessons": self._student_data.get("overview", {}).get("schedule", [])}


class WilmaHomeworkSensor(WilmaStudentSensorBase):
    _attr_translation_key = "homework"
    _attr_icon = "mdi:notebook-edit-outline"

    def __init__(self, coordinator, entry, student_number) -> None:
        super().__init__(coordinator, entry, student_number, "homework")

    @property
    def native_value(self) -> Any:
        return len(self._student_data.get("overview", {}).get("homework", []))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"items": self._student_data.get("overview", {}).get("homework", [])}


class WilmaExamsSensor(WilmaStudentSensorBase):
    _attr_translation_key = "exams"
    _attr_icon = "mdi:file-document-edit-outline"

    def __init__(self, coordinator, entry, student_number) -> None:
        super().__init__(coordinator, entry, student_number, "exams")

    @property
    def native_value(self) -> Any:
        exams = self._student_data.get("overview", {}).get("upcoming_exams", [])
        return exams[0]["date"] if exams else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"upcoming_exams": self._student_data.get("overview", {}).get("upcoming_exams", [])}


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
    _attr_translation_key = "attendance"
    _attr_icon = "mdi:account-alert-outline"

    def __init__(self, coordinator, entry, student_number) -> None:
        super().__init__(coordinator, entry, student_number, "attendance")

    @property
    def native_value(self) -> Any:
        return len(self._student_data.get("attendance", []))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"lesson_notes": self._student_data.get("attendance", [])}


class WilmaMessagesSensor(WilmaStudentSensorBase):
    _attr_translation_key = "messages"
    _attr_icon = "mdi:email-outline"

    def __init__(self, coordinator, entry, student_number) -> None:
        super().__init__(coordinator, entry, student_number, "messages")

    @property
    def native_value(self) -> Any:
        return len(self._student_data.get("messages", []))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"recent_messages": self._student_data.get("messages", [])}


class WilmaNewsSensor(WilmaStudentSensorBase):
    _attr_translation_key = "news"
    _attr_icon = "mdi:newspaper-variant-outline"

    def __init__(self, coordinator, entry, student_number) -> None:
        super().__init__(coordinator, entry, student_number, "news")

    @property
    def native_value(self) -> Any:
        return len(self._student_data.get("news", []))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"recent_news": self._student_data.get("news", [])}


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
