"""PayFast custom-payment signatures and ITN verification helpers."""

import hashlib
import hmac
import socket
from decimal import Decimal, InvalidOperation
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

from flask import current_app

PAYFAST_FORM_FIELD_ORDER = (
    "merchant_id",
    "merchant_key",
    "return_url",
    "cancel_url",
    "notify_url",
    "notify_method",
    "name_first",
    "name_last",
    "email_address",
    "cell_number",
    "m_payment_id",
    "amount",
    "item_name",
    "item_description",
    "custom_int1",
    "custom_int2",
    "custom_int3",
    "custom_int4",
    "custom_int5",
    "custom_str1",
    "custom_str2",
    "custom_str3",
    "custom_str4",
    "custom_str5",
    "email_confirmation",
    "confirmation_address",
    "currency",
    "payment_method",
)

ITN_SOURCE_HOSTS = (
    "www.payfast.co.za",
    "sandbox.payfast.co.za",
    "w1w.payfast.co.za",
    "w2w.payfast.co.za",
)


def _urlencode(value: str) -> str:
    # PayFast uses PHP urlencode (RFC 1738): spaces become '+', and '*'/'~'
    # are percent escaped. urllib leaves those characters unescaped by default.
    return quote_plus(value.strip(), safe="").replace("~", "%7E").replace("*", "%2A")


def _parameter_string(pairs: list[tuple[str, str]]) -> str:
    return "&".join(f"{key}={_urlencode(value)}" for key, value in pairs)


def generate_form_signature(fields: dict[str, str], passphrase: str | None) -> str:
    """Sign custom checkout fields in PayFast's documented field order."""
    ordered = [(key, fields[key]) for key in PAYFAST_FORM_FIELD_ORDER if fields.get(key, "") != ""]
    parameters = _parameter_string(ordered)
    if passphrase:
        parameters += f"&passphrase={_urlencode(passphrase)}" if parameters else (
            f"passphrase={_urlencode(passphrase)}"
        )
    return hashlib.md5(parameters.encode("utf-8")).hexdigest()


def verify_itn_signature(pairs: list[tuple[str, str]], passphrase: str | None) -> bool:
    signatures = [index for index, (key, _) in enumerate(pairs) if key == "signature"]
    if len(signatures) != 1 or signatures[0] != len(pairs) - 1:
        return False
    supplied = pairs[-1][1]
    signed_parameters = _parameter_string(pairs[:-1])
    if passphrase:
        signed_parameters += f"&passphrase={_urlencode(passphrase)}"
    expected = hashlib.md5(signed_parameters.encode("utf-8")).hexdigest()
    return hmac.compare_digest(supplied, expected)


def format_cents(amount_cents: int) -> str:
    if amount_cents < 0:
        raise ValueError("amount_cents cannot be negative")
    return f"{amount_cents // 100}.{amount_cents % 100:02d}"


def parse_amount_cents(amount: str) -> int | None:
    try:
        parsed = Decimal(amount)
    except (InvalidOperation, ValueError):
        return None
    if not parsed.is_finite():
        return None
    cents = parsed * 100
    if cents != cents.to_integral_value():
        return None
    return int(cents)


def resolve_payfast_ips(hostname: str) -> set[str]:
    """Resolve PayFast's published hostnames on each ITN request."""
    try:
        return {
            result[4][0]
            for result in socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
        }
    except OSError:
        current_app.logger.warning("PayFast hostname resolution failed for %s", hostname)
        return set()


def validate_itn_with_payfast(
    pairs: list[tuple[str, str]], endpoint: str, timeout_seconds: int
) -> str:
    body = _parameter_string(pairs).encode("ascii")
    request = Request(
        endpoint,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urlopen(request, timeout=timeout_seconds) as response:
        return response.read().decode("ascii").strip()
