"""Async Wilma session handling: login, cookies, MFA, and prefixed requests.

Ported from the wilma-client TypeScript package (session.ts) at
https://github.com/aikarjal/wilmai (MIT licensed).
"""
from __future__ import annotations

import logging
import re
from typing import Any, Optional

import aiohttp

_LOGGER = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36"
)
LOGIN_FAIL_RE = re.compile(r"loginFailed", re.IGNORECASE)
MFA_FORMKEY_RE = re.compile(r'id="mfa-formkey"\s+value="([^"]+)"')
INPUT_TAG_RE = re.compile(r"<input[^>]+>", re.IGNORECASE)
NAME_RE = re.compile(r"""name=['"]([^'"]+)['"]""", re.IGNORECASE)
VALUE_RE = re.compile(r"""value=['"]([^'"]*)['"]""", re.IGNORECASE)
TYPE_RE = re.compile(r"""type=['"]([^'"]+)['"]""", re.IGNORECASE)
WILMA2LOGINID_RE = re.compile(r'"Wilma2LoginID"\s*:\s*"([^"\s]+)"')


class AuthenticationError(Exception):
    """Raised when a Wilma login attempt fails."""


class MfaRequiredError(Exception):
    """Raised when Wilma challenges the login with an MFA/TOTP code."""

    def __init__(self, formkey: str) -> None:
        super().__init__("MFA verification required")
        self.formkey = formkey


class WilmaApiError(Exception):
    """Raised for non-2xx Wilma API responses."""

    def __init__(self, message: str, status: int) -> None:
        super().__init__(message)
        self.status = status


class WilmaSession:
    """Holds one authenticated Wilma cookie session, optionally scoped to a student."""

    def __init__(
        self,
        client_session: aiohttp.ClientSession,
        base_url: str,
        student_number: Optional[str] = None,
    ) -> None:
        self._session = client_session
        self.base_url = base_url.rstrip("/")
        self.student_number = student_number
        self.logged_in = False
        self._username: Optional[str] = None
        self._password: Optional[str] = None

    @property
    def url_prefix(self) -> Optional[str]:
        return f"!{self.student_number}" if self.student_number else None

    def _prefixed_path(self, path: str) -> str:
        prefix = self.url_prefix
        if prefix and not path.startswith("/!"):
            if path.startswith("/"):
                return f"/{prefix}{path}"
            return f"/{prefix}/{path}"
        return path

    async def login(self, username: str, password: str) -> None:
        if self.logged_in:
            return

        login_fields = await self._get_login_form_fields()
        session_id = login_fields.get("SESSIONID")
        if not session_id:
            session_id = await self._get_login_token()

        form = {**login_fields, "Login": username, "Password": password, "SESSIONID": session_id}

        resp = await self._raw_request(
            "/login",
            method="POST",
            data=form,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            allow_redirects=False,
        )

        # aiohttp's filter_cookies() returns a SimpleCookie (a dict of Morsel) for the URL.
        has_session_cookie = "Wilma2SID" in self._session.cookie_jar.filter_cookies(self.base_url)

        text = await resp.text()

        if 300 <= resp.status < 400 and has_session_cookie:
            location = resp.headers.get("location")
            if location:
                redirect_resp = await self._raw_request(location, method="GET")
                redirect_text = await redirect_resp.text()
                match = MFA_FORMKEY_RE.search(redirect_text)
                if match:
                    _LOGGER.debug("Wilma MFA challenge detected")
                    self._username = username
                    self._password = password
                    raise MfaRequiredError(match.group(1))

        if has_session_cookie or _is_login_ok(text):
            self.logged_in = True
            self._username = username
            self._password = password
            return

        raise AuthenticationError("Wilma login failed")

    async def submit_mfa_code(self, formkey: str, otp_code: str) -> None:
        """POST the TOTP/OTP code to Wilma's account-level MFA endpoint."""
        import json

        path = "/api/v1/accounts/me/mfa/otp/check"
        payload = json.dumps({"otp": otp_code, "action": "login"})
        resp = await self._raw_request(
            path,
            method="POST",
            data={"formkey": formkey, "payload": payload},
            headers={"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
        )
        text = await resp.text()
        try:
            data = json.loads(text)
        except ValueError as err:
            raise AuthenticationError("MFA verification failed: unexpected response") from err

        success = (data.get("payload") or {}).get("success", data.get("success", False))
        if not success:
            raise AuthenticationError("MFA verification failed: invalid OTP code")

        self.logged_in = True

    async def _get_login_form_fields(self) -> dict[str, str]:
        resp = await self._raw_request("/login", method="GET")
        if resp.status >= 400:
            return {}
        html = await resp.text()
        return _parse_login_form_fields(html)

    async def request(self, path: str, method: str = "GET", **kwargs: Any) -> aiohttp.ClientResponse:
        if not self.logged_in:
            raise AuthenticationError("WilmaSession not logged in - call login() first")

        prefixed = self._prefixed_path(path)
        resp = await self._raw_request(prefixed, method=method, **kwargs)

        if resp.status == 401 and self._username and self._password:
            self.logged_in = False
            await self.login(self._username, self._password)
            resp = await self._raw_request(prefixed, method=method, **kwargs)

        if resp.status >= 400:
            raise WilmaApiError(f"Wilma HTTP {resp.status} at {prefixed}", resp.status)

        return resp

    async def get(self, path: str, **kwargs: Any) -> aiohttp.ClientResponse:
        return await self.request(path, method="GET", **kwargs)

    async def post(self, path: str, **kwargs: Any) -> aiohttp.ClientResponse:
        return await self.request(path, method="POST", **kwargs)

    async def _get_login_token(self) -> str:
        resp = await self._raw_request("/token", method="GET")
        if resp.status != 200:
            raise AuthenticationError("/token fetch failed")
        text = await resp.text()
        try:
            import json

            data = json.loads(text)
            token = data.get("Wilma2LoginID")
            if token:
                return token
        except ValueError:
            pass
        match = WILMA2LOGINID_RE.search(text)
        if not match:
            raise AuthenticationError("Wilma2LoginID not found in /token response")
        return match.group(1)

    async def _raw_request(self, path: str, method: str = "GET", **kwargs: Any) -> aiohttp.ClientResponse:
        url = path if path.startswith("http") else f"{self.base_url}{path if path.startswith('/') else '/' + path}"
        headers = dict(kwargs.pop("headers", None) or {})
        headers.setdefault("User-Agent", USER_AGENT)
        headers.setdefault("Referer", f"{self.base_url}/")
        return await self._session.request(method, url, headers=headers, **kwargs)


def _is_login_ok(text: str) -> bool:
    return not LOGIN_FAIL_RE.search(text)


def _parse_login_form_fields(html: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for tag in INPUT_TAG_RE.findall(html):
        name_match = NAME_RE.search(tag)
        if not name_match:
            continue
        name = name_match.group(1)
        if name in ("Login", "Password"):
            continue
        type_match = TYPE_RE.search(tag)
        field_type = (type_match.group(1).lower() if type_match else "text")
        if field_type in ("hidden", "submit"):
            value_match = VALUE_RE.search(tag)
            fields[name] = value_match.group(1) if value_match else ""
    return fields
