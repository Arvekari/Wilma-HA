"""Look up known Wilma school instances by municipality (bundled directory)."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import TypedDict

TENANT_LIST_PATH = Path(__file__).parent / "tenant_list.json"


class Municipality(TypedDict):
    name_fi: str
    name_sv: str


class TenantInfo(TypedDict):
    url: str
    name: str
    municipalities: list[Municipality]


@lru_cache(maxsize=1)
def _load_tenants() -> list[TenantInfo]:
    try:
        with TENANT_LIST_PATH.open(encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return []
    return data.get("wilmat", [])


def list_tenants() -> list[TenantInfo]:
    return _load_tenants()


def search_tenants_by_municipality(municipality: str, limit: int = 50) -> list[TenantInfo]:
    needle = (municipality or "").lower()
    if not needle:
        return []
    results = []
    for tenant in _load_tenants():
        municipalities = tenant.get("municipalities") or []
        if any(
            needle in (m.get("name_fi") or "").lower() or needle in (m.get("name_sv") or "").lower()
            for m in municipalities
        ):
            results.append(tenant)
    return results[:limit]
