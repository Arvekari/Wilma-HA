"""DataUpdateCoordinator that logs into Wilma once and refreshes all students."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import AuthenticationError, MfaRequiredError, WilmaApiError, WilmaClient
from .api.totp import generate_totp
from .const import (
    CONF_BASE_URL,
    CONF_SCAN_INTERVAL_MINUTES,
    CONF_STUDENTS,
    CONF_TOTP_SECRET,
    DEFAULT_SCAN_INTERVAL_MINUTES,
)
from .triage import build_triage_summary

_LOGGER = logging.getLogger(__name__)


class WilmaCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """One coordinator per config entry; one isolated login/session per student."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        self.base_url: str = entry.data[CONF_BASE_URL]
        self.username: str = entry.data["username"]
        self.password: str = entry.data["password"]
        self.totp_secret: str | None = entry.data.get(CONF_TOTP_SECRET)
        self.students: list[dict[str, str]] = entry.options.get(
            CONF_STUDENTS, entry.data.get(CONF_STUDENTS, [])
        )
        minutes = entry.options.get(CONF_SCAN_INTERVAL_MINUTES, DEFAULT_SCAN_INTERVAL_MINUTES)

        # One aiohttp session PER STUDENT, each with its own cookie jar.
        #
        # Wilma's session cookie is account-wide: once one student's login
        # sets it, a second login attempt on that same cookie jar hits Wilma
        # already-authenticated and gets an unexpected response (no login
        # form fields to parse, odd /token behaviour) — this is exactly what
        # broke accounts with multiple children on one Wilma login (e.g. two
        # kids on the same inschool.fi tenant). Isolating the cookie jar per
        # student, like the upstream Node client does per session instance,
        # keeps every login fully independent even though they share one
        # account.
        self._client_sessions: dict[str, aiohttp.ClientSession] = {}
        self._clients: dict[str, WilmaClient] = {}

        super().__init__(
            hass,
            _LOGGER,
            name="wilma",
            update_interval=timedelta(minutes=minutes),
        )

    async def _mfa_callback(self, _formkey: str) -> str:
        if not self.totp_secret:
            raise AuthenticationError("MFA required but no TOTP secret is configured")
        return generate_totp(self.totp_secret)

    async def _get_client(self, student_number: str) -> WilmaClient:
        client = self._clients.get(student_number)
        if client is not None:
            return client

        client_session = aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar())
        try:
            client = await WilmaClient.login(
                client_session,
                self.base_url,
                self.username,
                self.password,
                student_number=student_number,
                on_mfa_required=self._mfa_callback if self.totp_secret else None,
            )
        except Exception:
            await client_session.close()
            raise
        self._client_sessions[student_number] = client_session
        self._clients[student_number] = client
        return client

    async def _drop_client(self, student_number: str) -> None:
        self._clients.pop(student_number, None)
        session = self._client_sessions.pop(student_number, None)
        if session is not None:
            await session.close()

    async def _async_update_data(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for student in self.students:
            student_number = student["student_number"]
            try:
                client = await self._get_client(student_number)
                overview = await client.get_overview()
                attendance = await client.get_attendance()
                messages = await client.list_messages("inbox")
                news = await client.list_news()
            except (AuthenticationError, MfaRequiredError, WilmaApiError, aiohttp.ClientError) as err:
                # Drop the cached client/session so the next refresh re-authenticates from scratch.
                await self._drop_client(student_number)
                raise UpdateFailed(f"Wilma update failed for {student['name']}: {err}") from err

            student_data = {
                "name": student["name"],
                "student_number": student_number,
                "overview": overview,
                "attendance": attendance,
                "messages": messages[:20],
                "news": news[:20],
            }
            student_data["triage"] = build_triage_summary(student_data)
            result[student_number] = student_data

        return result

    async def async_close(self) -> None:
        for session in self._client_sessions.values():
            await session.close()
        self._client_sessions.clear()
        self._clients.clear()
