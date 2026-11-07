"""Match an M-Pesa short code to the business that owns it.

A paybill or till is only a number. The case this check is for: the shop
presents one name, and the short code is registered to a different company.
Typing the digits is not proof.

Recheck legal details runs this when both Daraja keys are set:

1. OAuth. The consumer key and secret go to Safaricom as HTTP Basic on
   /oauth/v1/generate?grant_type=client_credentials. The reply is a bearer
   token. Sandbox uses sandbox.safaricom.co.ke. Production uses
   api.safaricom.co.ke.
2. Name lookup. That token authorizes POST /mpesa/orginfo/v1/query
   (Query Organization Info) with {"ShortCode": "<paybill>"}. Safaricom
   returns the business name on that short code as OrganizationName or
   MerchantName. DARAJA_NAME_LOOKUP_URL can replace the path when an app
   is enabled for a different route on the same host.
3. Compare. Both names are reduced to words. Case, punctuation, and a
   trailing Ltd or Limited are ignored. The remaining words must be the
   same list, in the same order.
4. Badge. M-Pesa Verified turns on only when those names agree and the
   KRA/BRS record is active or registered. A mismatch is stored and the
   badge turns off. The trust score does not move. The +25 is still only
   the legal-record bonus.

Empty consumer key and secret skip the call, and the seeded badge stays.
"""

from __future__ import annotations

import base64
import json
import os
import re
from urllib.error import URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen


class DarajaError(Exception):
    """A Daraja lookup could not be completed safely."""

    status_code = 502


class DarajaConfigurationError(DarajaError):
    status_code = 503


def _merchant_name(payload: dict) -> str:
    """Read the short-code name from either response shape Daraja sends."""
    for field in ("MerchantName", "merchantName", "OrganizationName", "organizationName"):
        value = payload.get(field)
        if isinstance(value, str) and value.strip():
            return " ".join(value.split())
    return ""


def daraja_credentials_configured() -> bool:
    return bool(
        os.getenv("DARAJA_CONSUMER_KEY", "").strip()
        or os.getenv("DARAJA_CONSUMER_SECRET", "").strip()
    )


def registered_names_match(left: str, right: str) -> bool:
    """True when two business names are the same entity, ignoring legal suffixes.

    "Nairobi Tech Hub Electronics Ltd." matches "nairobi tech hub electronics limited".
    An extra word, such as Kenya, does not match.
    """

    def key(value: str) -> tuple[str, ...]:
        words = re.findall(r"[a-z0-9]+", value.casefold())
        while words and words[-1] in {
            "co",
            "company",
            "inc",
            "incorporated",
            "limited",
            "llc",
            "llp",
            "ltd",
            "plc",
        }:
            words.pop()
        return tuple(words)

    left_key = key(left)
    return bool(left_key and left_key == key(right))


class DarajaClient:
    def __init__(self) -> None:
        self.consumer_key = os.getenv("DARAJA_CONSUMER_KEY", "").strip()
        self.consumer_secret = os.getenv("DARAJA_CONSUMER_SECRET", "").strip()
        self.environment = os.getenv("DARAJA_ENVIRONMENT", "sandbox").strip().lower()
        self.name_lookup_url = os.getenv("DARAJA_NAME_LOOKUP_URL", "").strip()

    def lookup_paybill_name(self, paybill: str) -> str:
        if not self.consumer_key or not self.consumer_secret:
            raise DarajaConfigurationError("Set both DARAJA_CONSUMER_KEY and DARAJA_CONSUMER_SECRET.")
        # Query Organization Info is the Daraja product that returns the name on a short code.
        if not self.name_lookup_url:
            self.name_lookup_url = "/mpesa/orginfo/v1/query"
        if self.environment == "sandbox":
            base_url = "https://sandbox.safaricom.co.ke"
        elif self.environment == "production":
            base_url = "https://api.safaricom.co.ke"
        else:
            raise DarajaConfigurationError("DARAJA_ENVIRONMENT must be sandbox or production.")
        if not re.fullmatch(r"\d{5,7}", paybill):
            raise DarajaConfigurationError("A valid 5-to-7 digit paybill is required for Daraja verification.")

        endpoint = self._endpoint(base_url)
        token = self._access_token(base_url)
        payload = self._request_json(
            Request(
                endpoint,
                data=json.dumps({"ShortCode": paybill}).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                method="POST",
            )
        )
        name = _merchant_name(payload)
        if not name:
            raise DarajaError("Daraja name-inquiry response did not contain a merchant name.")
        return name

    def _endpoint(self, base_url: str) -> str:
        parsed = urlparse(self.name_lookup_url)
        if parsed.scheme or parsed.netloc:
            expected_host = urlparse(base_url).hostname
            if parsed.scheme != "https" or parsed.hostname != expected_host:
                raise DarajaConfigurationError(
                    "DARAJA_NAME_LOOKUP_URL must use the configured Safaricom environment host."
                )
            return self.name_lookup_url
        if not self.name_lookup_url.startswith("/"):
            raise DarajaConfigurationError("DARAJA_NAME_LOOKUP_URL must be an absolute URL or begin with '/'.")
        return urljoin(base_url, self.name_lookup_url)

    def _access_token(self, base_url: str) -> str:
        credentials = base64.b64encode(
            f"{self.consumer_key}:{self.consumer_secret}".encode("utf-8")
        ).decode("ascii")
        request = Request(
            f"{base_url}/oauth/v1/generate?grant_type=client_credentials",
            headers={"Authorization": f"Basic {credentials}", "Accept": "application/json"},
        )
        payload = self._request_json(request)
        token = payload.get("access_token")
        if not isinstance(token, str) or not token:
            raise DarajaError("Daraja OAuth response did not contain an access token.")
        return token

    @staticmethod
    def _request_json(request: Request) -> dict:
        try:
            with urlopen(request, timeout=10) as response:
                payload = json.loads(response.read())
        except (URLError, TimeoutError, OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise DarajaError("Daraja request failed; check the credentials, endpoint, and network.") from exc
        if not isinstance(payload, dict):
            raise DarajaError("Daraja returned an invalid response.")
        return payload
