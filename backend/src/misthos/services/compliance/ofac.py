"""Sanctions screening against the official OFAC SDN list.

The list is the published SDN XML, parsed for digital-currency addresses. It is
downloaded once and cached; a cache older than the refresh window is replaced from
the source. When the list cannot be read or downloaded, screening answers
`UNAVAILABLE`, which blocks funding and payouts rather than clearing a wallet against
a stale list.
"""

from __future__ import annotations

import logging
import tempfile
import threading
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import httpx

from misthos.domain.compliance import ScreeningOutcome

log = logging.getLogger("misthos.compliance.ofac")

DIGITAL_CURRENCY = "Digital Currency Address"


class OfacSdnError(RuntimeError):
    """The SDN list could not be read, parsed, or downloaded."""


class OfacSdnScreening:
    name = "ofac-sdn"

    def __init__(
        self,
        url: str,
        refresh_seconds: int,
        cache_path: str | Path | None = None,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._url = url
        self._refresh = refresh_seconds
        self._cache = (
            Path(cache_path) if cache_path else Path(tempfile.gettempdir()) / "misthos-ofac-sdn.xml"
        )
        self._transport = transport
        self._lock = threading.Lock()
        self._loaded_at = 0.0
        self._listed: dict[str, str] = {}
        self._last_error: str | None = None

    def screen(self, wallet_address: str) -> tuple[ScreeningOutcome, str | None]:
        try:
            self._ensure_loaded()
        except Exception as exc:  # noqa: BLE001 - any failure must block, not clear
            self._last_error = str(exc)
            log.error("OFAC SDN screening unavailable: %s", exc, extra={"alert": "compliance"})
            return ScreeningOutcome.UNAVAILABLE, "OFAC SDN unavailable"

        entry = self._listed.get(wallet_address.strip().lower())
        if entry is not None:
            return ScreeningOutcome.HIT, f"OFAC SDN: {entry}"
        return ScreeningOutcome.CLEAR, None

    def _ensure_loaded(self) -> None:
        with self._lock:
            now = time.time()
            if self._loaded_at and now - self._loaded_at < self._refresh:
                return

            fresh = self._cache.exists() and now - self._cache.stat().st_mtime < self._refresh
            if not fresh:
                self._download()
            self._listed = _parse(self._cache)
            self._loaded_at = now
            self._last_error = None

    def _download(self) -> None:
        self._cache.parent.mkdir(parents=True, exist_ok=True)
        # The treasury answers with a redirect to a signed object rather than the
        # list itself, so a client that stops at 302 never reads the list.
        with httpx.Client(transport=self._transport, timeout=60.0, follow_redirects=True) as client:
            response = client.get(self._url)
            response.raise_for_status()
            body = response.content
        if not body.strip():
            raise OfacSdnError(f"{self._url} returned an empty list")
        # Replace atomically: a reader never sees a half-written list.
        temporary = self._cache.with_suffix(".tmp")
        temporary.write_bytes(body)
        temporary.replace(self._cache)


def _local(tag: str) -> str:
    """An element's name without the namespace the treasury wraps the list in."""
    return tag.rsplit("}", 1)[-1]


def _parse(path: Path) -> dict[str, str]:
    """Every digital-currency address in the list, mapped to the entry's name.

    The document carries a default namespace, so a tag never compares equal to the
    bare name. Matching on the local name is what keeps the list from parsing to
    nothing, which would clear every wallet.
    """
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as exc:
        raise OfacSdnError(f"could not parse {path}: {exc}") from exc

    listed: dict[str, str] = {}
    for entry in root.iter():
        if _local(entry.tag) != "sdnEntry":
            continue
        parts: dict[str, str] = {}
        for child in entry:
            name = _local(child.tag)
            if name in ("firstName", "lastName"):
                parts[name] = (child.text or "").strip()
        display = (
            " ".join(part for part in (parts.get("firstName"), parts.get("lastName")) if part)
            or "unnamed entry"
        )
        for node in entry.iter():
            if _local(node.tag) != "id":
                continue
            kind = ""
            number = ""
            for child in node:
                name = _local(child.tag)
                if name == "idType":
                    kind = (child.text or "").strip()
                elif name == "idNumber":
                    number = (child.text or "").strip()
            if kind.startswith(DIGITAL_CURRENCY) and number:
                listed[number.lower()] = display
    return listed
