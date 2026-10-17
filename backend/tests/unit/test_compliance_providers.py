"""The real compliance providers: OFAC SDN screening and Stripe Identity."""

from __future__ import annotations

import os
import time
from pathlib import Path

import httpx

from misthos.domain.compliance import IdentityStatus, ScreeningOutcome
from misthos.services.compliance.ofac import OfacSdnScreening
from misthos.services.compliance.stripe_identity import StripeIdentity

NAMESPACED_SDN = """<?xml version="1.0" standalone="yes"?>
<sdnList xmlns="https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/XML">
  <sdnEntry>
    <firstName>Bad</firstName>
    <lastName>Actor</lastName>
    <idList>
      <id>
        <idType>Digital Currency Address - XBT</idType>
        <idNumber>1BadAddress</idNumber>
      </id>
    </idList>
  </sdnEntry>
</sdnList>
"""

SDN = """<?xml version="1.0"?>
<sdnList>
  <sdnEntry>
    <firstName>Bad</firstName>
    <lastName>Actor</lastName>
    <idList>
      <id>
        <idType>Digital Currency Address - XBT</idType>
        <idNumber>1BadAddress</idNumber>
      </id>
    </idList>
  </sdnEntry>
</sdnList>
"""


def cached(tmp_path: Path) -> Path:
    path = tmp_path / "sdn.xml"
    path.write_text(SDN)
    return path


def test_a_listed_address_is_a_hit(tmp_path: Path) -> None:
    provider = OfacSdnScreening("https://example.test/sdn.xml", 3600, cached(tmp_path))
    outcome, list_name = provider.screen("1badaddress")
    assert outcome is ScreeningOutcome.HIT
    assert list_name and "Bad Actor" in list_name


def test_a_clean_address_is_clear(tmp_path: Path) -> None:
    provider = OfacSdnScreening("https://example.test/sdn.xml", 3600, cached(tmp_path))
    assert provider.screen("0xclean")[0] is ScreeningOutcome.CLEAR


def test_a_redirect_to_the_list_is_followed(tmp_path: Path) -> None:
    """The treasury serves the list behind a redirect, so stopping at 302 blocks."""
    provider = OfacSdnScreening(
        "https://example.test/sdn.xml",
        3600,
        tmp_path / "sdn.xml",
        transport=httpx.MockTransport(
            lambda request: (
                httpx.Response(
                    status_code=302,
                    headers={"Location": "https://example.test/signed/sdn.xml"},
                )
                if request.url.path == "/sdn.xml"
                else httpx.Response(200, text=SDN)
            )
        ),
    )

    outcome, _ = provider.screen("1badaddress")

    assert outcome is ScreeningOutcome.HIT


def test_the_lists_default_namespace_does_not_hide_every_entry(tmp_path: Path) -> None:
    """The published document is namespaced; matching bare tags parses it to nothing,
    which would clear every wallet."""
    path = tmp_path / "sdn.xml"
    path.write_text(NAMESPACED_SDN)
    provider = OfacSdnScreening("https://example.test/sdn.xml", 3600, path)

    outcome, list_name = provider.screen("1badaddress")

    assert outcome is ScreeningOutcome.HIT
    assert list_name and "Bad Actor" in list_name


def test_a_stale_list_that_cannot_be_refreshed_blocks(tmp_path: Path) -> None:
    path = cached(tmp_path)
    old = time.time() - 3600 * 2
    os.utime(path, (old, old))
    provider = OfacSdnScreening(
        "https://example.test/sdn.xml",
        3600,
        path,
        transport=httpx.MockTransport(lambda _: httpx.Response(500)),
    )
    assert provider.screen("1badaddress")[0] is ScreeningOutcome.UNAVAILABLE


class StubStripe:
    def __init__(self, payload: dict, status: int = 200) -> None:
        self.payload = payload
        self.status = status
        self.requests: list[tuple[str, str]] = []

    def request(self, method: str, url: str, **_kwargs):
        self.requests.append((method, url))
        return httpx.Response(self.status, json=self.payload)


def test_start_returns_the_session_id() -> None:
    client = StubStripe({"id": "vs_123"})
    provider = StripeIdentity("sk_test", client=client)
    assert provider.start("CON-1") == "vs_123"
    assert client.requests[0][0] == "POST"


def test_status_maps_stripes_vocabulary() -> None:
    for stripe, ours in [
        ("verified", IdentityStatus.VERIFIED),
        ("processing", IdentityStatus.PENDING),
        ("requires_input", IdentityStatus.PENDING),
        ("canceled", IdentityStatus.FAILED),
        ("something_new", IdentityStatus.UNVERIFIED),
    ]:
        provider = StripeIdentity("sk_test", client=StubStripe({"status": stripe}))
        assert provider.status("vs_1") is ours, stripe


def test_every_screening_outcome_fits_its_column() -> None:
    """`unavailable` is eleven characters; the column was eight, which turned every
    failed screening into a 500 on the funding path."""
    from misthos.domain.compliance import ScreeningOutcome
    from misthos.models import tables as t

    width = t.screenings.c.outcome.type.length
    assert max(len(outcome.value) for outcome in ScreeningOutcome) <= width
