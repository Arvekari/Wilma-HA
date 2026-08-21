"""TOTP helpers for Wilma's account-level MFA (RFC 6238, HMAC-SHA1, 6 digits, 30s)."""
from __future__ import annotations

from urllib.parse import urlparse, parse_qs

import pyotp


def parse_totp_secret(raw: str) -> str:
    """Accept either a bare base32 key or an otpauth:// URI."""
    if raw.startswith("otpauth://"):
        parsed = urlparse(raw)
        secret = parse_qs(parsed.query).get("secret", [None])[0]
        if not secret:
            raise ValueError("No 'secret' parameter found in otpauth:// URI.")
        return secret
    return raw.replace(" ", "").replace("-", "")


def generate_totp(secret: str) -> str:
    clean_secret = secret.replace(" ", "").replace("-", "").replace("=", "").upper()
    return pyotp.TOTP(clean_secret).now()
