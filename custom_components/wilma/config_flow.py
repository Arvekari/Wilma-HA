"""Config flow: base URL + credentials -> optional MFA -> pick students."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .api import AuthenticationError, MfaRequiredError, WilmaApiError, WilmaClient
from .const import (
    CONF_BASE_URL,
    CONF_SCAN_INTERVAL_MINUTES,
    CONF_STUDENTS,
    CONF_TOTP_SECRET,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_BASE_URL): str,
        vol.Required("username"): str,
        vol.Required("password"): str,
    }
)

STEP_MFA_SCHEMA = vol.Schema(
    {
        vol.Optional("otp_code"): str,
        vol.Optional(CONF_TOTP_SECRET): str,
    }
)


class WilmaConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._base_url: str | None = None
        self._username: str | None = None
        self._password: str | None = None
        self._totp_secret: str | None = None
        self._mfa_formkey: str | None = None
        self._students: list[dict[str, str]] = []

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> config_entries.FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._base_url = user_input[CONF_BASE_URL].rstrip("/")
            self._username = user_input["username"]
            self._password = user_input["password"]

            session = aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar())
            try:
                students = await WilmaClient.list_students(
                    session, self._base_url, self._username, self._password
                )
            except MfaRequiredError as err:
                self._mfa_formkey = err.formkey
                await session.close()
                return await self.async_step_mfa()
            except AuthenticationError:
                errors["base"] = "invalid_auth"
            except (WilmaApiError, aiohttp.ClientError):
                errors["base"] = "cannot_connect"
            else:
                self._students = [
                    {"student_number": s["student_number"], "name": s["name"]} for s in students
                ]
                await session.close()
                if not self._students:
                    errors["base"] = "no_students"
                else:
                    return await self.async_step_students()
            finally:
                if not session.closed:
                    await session.close()

        return self.async_show_form(step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors)

    async def async_step_mfa(self, user_input: dict[str, Any] | None = None) -> config_entries.FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            from .api.totp import generate_totp

            otp_code = user_input.get("otp_code")
            totp_secret = user_input.get(CONF_TOTP_SECRET)
            if not otp_code and not totp_secret:
                errors["base"] = "mfa_code_required"
            else:
                session = aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar())
                try:
                    code = otp_code or generate_totp(totp_secret)
                    students = await WilmaClient.list_students(
                        session,
                        self._base_url,
                        self._username,
                        self._password,
                        on_mfa_required=lambda _formkey: _return_code(code),
                    )
                except AuthenticationError:
                    errors["base"] = "invalid_mfa"
                except (WilmaApiError, aiohttp.ClientError):
                    errors["base"] = "cannot_connect"
                else:
                    self._totp_secret = totp_secret
                    self._students = [
                        {"student_number": s["student_number"], "name": s["name"]} for s in students
                    ]
                    if not self._students:
                        errors["base"] = "no_students"
                    else:
                        await session.close()
                        return await self.async_step_students()
                finally:
                    if not session.closed:
                        await session.close()

        return self.async_show_form(step_id="mfa", data_schema=STEP_MFA_SCHEMA, errors=errors)

    async def async_step_students(self, user_input: dict[str, Any] | None = None) -> config_entries.FlowResult:
        if user_input is not None:
            selected = set(user_input[CONF_STUDENTS])
            chosen = [s for s in self._students if s["student_number"] in selected]

            await self.async_set_unique_id(f"{self._base_url}:{self._username}")
            self._abort_if_unique_id_configured()

            title = self._base_url.replace("https://", "").replace("http://", "")
            return self.async_create_entry(
                title=f"Wilma ({title})",
                data={
                    CONF_BASE_URL: self._base_url,
                    "username": self._username,
                    "password": self._password,
                    CONF_TOTP_SECRET: self._totp_secret,
                    CONF_STUDENTS: chosen,
                },
            )

        options = {s["student_number"]: s["name"] for s in self._students}
        schema = vol.Schema(
            {
                vol.Required(CONF_STUDENTS, default=list(options.keys())): SelectSelector(
                    SelectSelectorConfig(
                        options=[{"value": k, "label": v} for k, v in options.items()],
                        multiple=True,
                        mode=SelectSelectorMode.LIST,
                    )
                )
            }
        )
        return self.async_show_form(step_id="students", data_schema=schema)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> "WilmaOptionsFlow":
        return WilmaOptionsFlow(config_entry)


async def _return_code(code: str) -> str:
    return code


class WilmaOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> config_entries.FlowResult:
        all_students = self.config_entry.data.get(CONF_STUDENTS, [])
        current_selection = self.config_entry.options.get(
            CONF_STUDENTS, all_students
        )
        current_numbers = [s["student_number"] for s in current_selection]

        if user_input is not None:
            selected = set(user_input[CONF_STUDENTS])
            chosen = [s for s in all_students if s["student_number"] in selected]
            return self.async_create_entry(
                title="",
                data={
                    CONF_STUDENTS: chosen,
                    CONF_SCAN_INTERVAL_MINUTES: user_input[CONF_SCAN_INTERVAL_MINUTES],
                },
            )

        options_map = {s["student_number"]: s["name"] for s in all_students}
        schema = vol.Schema(
            {
                vol.Required(CONF_STUDENTS, default=current_numbers): SelectSelector(
                    SelectSelectorConfig(
                        options=[{"value": k, "label": v} for k, v in options_map.items()],
                        multiple=True,
                        mode=SelectSelectorMode.LIST,
                    )
                ),
                vol.Required(
                    CONF_SCAN_INTERVAL_MINUTES,
                    default=self.config_entry.options.get(
                        CONF_SCAN_INTERVAL_MINUTES, DEFAULT_SCAN_INTERVAL_MINUTES
                    ),
                ): vol.All(int, vol.Range(min=5, max=240)),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
