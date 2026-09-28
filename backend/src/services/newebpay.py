"""NewebPay (藍新金流) 信用卡定期定額 (Periodic) crypto + payload helpers.

Pure functions only — no I/O, no `Settings` import. Key/IV are always parameters so
this module is trivially unit-testable and never accidentally reads a real secret.

Primitive (NDNP-1.0.8 §2, verified against the official manual — see
`docs/agents/auth-admin.md` § Membership for the summary and the research notes this
was built from): AES-256-CBC, PKCS7 padding, ciphertext lower-case hex. The outer
transport for every Periodic API is just two form fields — `MerchantID_` and
`PostData_` (the AES-hex blob of `urlencode()`'d inner params) — with **no**
TradeSha-equivalent signature anywhere in the Periodic family (that only exists in
NewebPay's separate MPG/幕前支付 flow). Decryptability with the merchant's own
HashKey/HashIV *is* the authenticity check for both requests and Notify callbacks.

PR 3a ships this module and its tests only — nothing here talks to NewebPay over the
network yet. PR 3b adds the checkout/notify/cancel endpoints that call
`build_period_post_data` / `parse_period_result` for real.
"""
from __future__ import annotations

import binascii
import json
import secrets
import time
from urllib.parse import urlencode

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

PERIOD_ENDPOINTS = {
    "sandbox": "https://ccore.newebpay.com/MPG/period",
    "production": "https://core.newebpay.com/MPG/period",
}


class NewebPayError(Exception):
    """Raised for any crypto/parse failure. Deliberately generic — never distinguishes
    bad hex from bad padding from a wrong key, so a probing caller learns nothing."""


def _check_key_iv(key: str, iv: str) -> None:
    """AES-256-CBC needs exactly a 32-char key and a 16-char IV. A truncated key
    would otherwise raise a raw ValueError on encrypt (500) or look like a forged
    payload on decrypt — check up front and fail the same way either time."""
    if len(key) != 32 or len(iv) != 16:
        raise NewebPayError("bad key/iv length")


def encrypt(params: dict, key: str, iv: str) -> str:
    """`urlencode(params)` -> AES-256-CBC (PKCS7) -> lower-case hex, per NDNP §2."""
    _check_key_iv(key, iv)
    plaintext = urlencode(params).encode("utf-8")
    padder = padding.PKCS7(algorithms.AES.block_size).padder()
    padded = padder.update(plaintext) + padder.finalize()
    cipher = Cipher(algorithms.AES(key.encode("utf-8")), modes.CBC(iv.encode("utf-8")))
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(padded) + encryptor.finalize()
    return ciphertext.hex()


def decrypt(hex_str: str, key: str, iv: str) -> str:
    """Inverse of `encrypt`. Raises `NewebPayError` on bad hex / bad padding / wrong
    key — never which, so a caller can't use error type to probe the key."""
    _check_key_iv(key, iv)
    try:
        ciphertext = bytes.fromhex(hex_str)
        cipher = Cipher(algorithms.AES(key.encode("utf-8")), modes.CBC(iv.encode("utf-8")))
        decryptor = cipher.decryptor()
        padded = decryptor.update(ciphertext) + decryptor.finalize()
        unpadder = padding.PKCS7(algorithms.AES.block_size).unpadder()
        plaintext = unpadder.update(padded) + unpadder.finalize()
        return plaintext.decode("utf-8")
    except (ValueError, binascii.Error, UnicodeDecodeError) as e:
        raise NewebPayError("failed to decrypt NewebPay payload") from e


def period_endpoint(env: str) -> str:
    """Create-mandate URL for `env` ("sandbox" | "production"), NDNP §4.3."""
    try:
        return PERIOD_ENDPOINTS[env]
    except KeyError:
        raise ValueError(f"unknown NewebPay env: {env!r}") from None


def new_mer_order_no() -> str:
    """A `MerOrderNo` (<=30 chars, alnum + underscore, NDNP §1): `tb` + UTC epoch
    seconds + 8 hex chars of randomness — collision-resistant without a DB round trip."""
    return f"tb{int(time.time())}_{secrets.token_hex(4)}"


def build_period_post_data(
    *,
    mer_order_no: str,
    prod_desc: str,
    period_amt: int,
    period_point: int,
    payer_email: str,
    merchant_id: str,
    key: str,
    iv: str,
    return_url: str,
    notify_url: str,
    period_times: int = 99,
) -> dict:
    """Build `{"MerchantID_": ..., "PostData_": ...}` for a monthly (`PeriodType=M`)
    mandate, per NDNP §1 create-mandate (`NPA-B05`) inner params.

    `period_point` is the day-of-month (1-31) the mandate authorizes on; NewebPay
    wants it zero-padded to 2 digits. `PeriodStartType=2` (immediate first-period-
    amount auth) matches the plan: joining charges the real price immediately, not a
    NT$10 verification hold. `PaymentInfo`/`OrderInfo` default to `Y` in the manual —
    both explicitly `N` here: `OrderInfo=Y` makes NewebPay demand a recipient
    name/phone/address, which is friction and PII we have no reason to collect for a
    digital subscription. `return_url`/`notify_url` are required: an empty
    NotifyURL means NewebPay never tells us about a renewal charge, so cards get
    billed monthly while membership never extends.
    """
    if not (1 <= period_point <= 31):
        raise ValueError(f"period_point must be 1-31, got {period_point}")
    if period_amt <= 0:
        raise ValueError(f"period_amt must be > 0, got {period_amt}")
    inner = {
        "RespondType": "JSON",
        "TimeStamp": str(int(time.time())),
        "Version": "1.5",
        "MerOrderNo": mer_order_no,
        "ProdDesc": prod_desc,
        "PeriodAmt": period_amt,
        "PeriodType": "M",
        "PeriodPoint": f"{period_point:02d}",
        "PeriodStartType": 2,
        "PeriodTimes": str(period_times),
        "ReturnURL": return_url,
        "NotifyURL": notify_url,
        "PayerEmail": payer_email,
        "PaymentInfo": "N",
        "OrderInfo": "N",
        "EmailModify": 0,
    }
    return {
        "MerchantID_": merchant_id,
        "PostData_": encrypt(inner, key, iv),
    }


def parse_period_result(hex_str: str, key: str, iv: str) -> dict:
    """Decrypt a `Period` field (create-mandate response or per-period Notify) into
    its JSON dict. Raises `NewebPayError` if it isn't valid JSON or lacks `Status`."""
    plaintext = decrypt(hex_str, key, iv)
    try:
        data = json.loads(plaintext)
    except json.JSONDecodeError as e:
        raise NewebPayError("NewebPay payload was not valid JSON") from e
    if not isinstance(data, dict) or "Status" not in data:
        raise NewebPayError("NewebPay payload missing Status")
    return data


if __name__ == "__main__":
    # ponytail: smoke check, not a substitute for tests/test_newebpay.py
    _key = "k" * 32
    _iv = "i" * 16
    _plain = {"hello": "world", "zh": "聽播客"}
    _enc = encrypt(_plain, _key, _iv)
    assert all(c in "0123456789abcdef" for c in _enc)
    assert decrypt(_enc, _key, _iv) == urlencode(_plain)
    _post = build_period_post_data(
        mer_order_no=new_mer_order_no(),
        prod_desc="TinBoker Membership",
        period_amt=99,
        period_point=15,
        payer_email="a@b.com",
        merchant_id="MID",
        key=_key,
        iv=_iv,
        return_url="https://tinboker.com/membership",
        notify_url="https://api.tinboker.com/api/billing/notify",
    )
    _inner = dict(x.split("=", 1) for x in decrypt(_post["PostData_"], _key, _iv).split("&"))
    assert _inner["PeriodPoint"] == "15"
    print("newebpay.py self-check OK")
