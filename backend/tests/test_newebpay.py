"""Tests for the NewebPay crypto/payload module (PR 3a — billing foundation).

No real DB and no network: `_founding_taken` (the only I/O in `routers/billing.py`)
is patched directly, matching the idiom in `tests/test_membership.py`.
"""
import re
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.services.newebpay import (
    NewebPayError,
    build_period_post_data,
    decrypt,
    encrypt,
    new_mer_order_no,
    parse_period_result,
    period_endpoint,
)

KEY = "k" * 32
IV = "i" * 16


# ---------------------------------------------------------------------------
# encrypt / decrypt round trip
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "params",
    [
        {"a": "b", "c": "1"},
        {"ProdDesc": "聽播客會員"},  # non-ASCII
        {"PayerEmail": "a+test@example.com"},  # '+' in email
        {"ProdDesc": "聽播客會員", "PayerEmail": "a+test@example.com", "PeriodAmt": "99"},
    ],
)
def test_encrypt_decrypt_round_trip(params):
    from urllib.parse import urlencode

    ciphertext = encrypt(params, KEY, IV)
    plaintext = decrypt(ciphertext, KEY, IV)
    assert plaintext == urlencode(params)


def test_ciphertext_is_lowercase_hex_and_block_aligned():
    ciphertext = encrypt({"a": "b"}, KEY, IV)
    assert re.fullmatch(r"[0-9a-f]+", ciphertext)
    assert len(ciphertext) % 32 == 0  # hex chars per 16-byte AES block = 32


def test_tampered_ciphertext_raises():
    ciphertext = encrypt({"a": "b"}, KEY, IV)
    flipped_char = "0" if ciphertext[0] != "0" else "1"
    tampered = flipped_char + ciphertext[1:]
    with pytest.raises(NewebPayError):
        decrypt(tampered, KEY, IV)


def test_wrong_key_raises():
    ciphertext = encrypt({"a": "b"}, KEY, IV)
    with pytest.raises(NewebPayError):
        decrypt(ciphertext, "x" * 32, IV)


def test_non_hex_raises():
    with pytest.raises(NewebPayError):
        decrypt("not hex at all!!", KEY, IV)


# ---------------------------------------------------------------------------
# Known-answer vector — NDNP-1.0.8 §4.1 "PHP 範例" (the official manual's own
# worked example: HashKey, HashIV, the built query string, and its AES-256-CBC
# hex ciphertext are all given verbatim). Source copy:
# /private/tmp/claude-501/-Users-willy-Documents-tinboker--claude-worktrees-tinboker-paid-membership-system-17bb81/48ebfd7f-cfdb-4c5c-a271-be87bc3ccd0d/scratchpad/newebpay/NDNP.txt
# lines 367-449.
# ---------------------------------------------------------------------------

_MANUAL_KEY = "IaWudQJsuOT994cpHRWzv7Ge67yC1cE3"
_MANUAL_IV = "C1dLm3nxZRVlmBSP"
_MANUAL_PARAMS = {
    "RespondType": "JSON",
    "TimeStamp": "1700033460",
    "Version": "1.5",
    "LangType": "zh-Tw",
    "MerOrderNo": "myorder1700033460",
    "ProdDesc": "Test commssion",  # sic — typo in the manual's own example
    "PeriodAmt": "10",
    "PeriodType": "M",
    "PeriodPoint": "05",
    "PeriodStartType": "2",
    "PeriodTimes": "12",
    "PayerEmail": "test@neweb.com.tw",
    "PaymentInfo": "Y",
    "OrderInfo": "N",
    "EmailModify": "1",
    "NotifyURL": "https://webhook.site/b728e917-1bf7-478b-b0f9-73b56aeb44e0",
}
_MANUAL_CIPHERTEXT = (
    "45d5175feaa9ef2ea039f84afba34c6330e8fa21ae01ec40f15ab00073b4e"
    "93584cc1d3a7e2b26feb08216d14074dd4a83a64791e114cd15e200a88ef3"
    "8720e7830d892953a25b84411abc8d0f86ff73719af52e0c303de9586c422"
    "702e806e599ffd739086b0c3f8c3b995b2a6ba92902070f5f8c4c2916f72b"
    "0d9c1027ca050799a6a55e78ff07c663e4b90aa3a84dfde353f1354fc5165"
    "ccc897f5ee0586a2852e2e5e1be1f3fa2f7a618377abdab9b6aa3af39eb00"
    "5e461aaa2c8da4d2fd3af93bed9eb3438b01804a9a1bc39bcb6f7bd3a35bd"
    "275fe53923960bd76c4def1175e8b1f60acb21cd4ebe9c03fe10df2c1a6aa"
    "455e21899c02cba501ce2fb87c72a6cbb2a146ddd4688fd3ce9cf068bdb6f"
    "4f2c4351d78973d32268737e931def628d0f3f3aac038cd551a0f8c85e0d1"
    "94542da74f6ba841c4068bab0f14453dbac0d16dba1de2656368238855dc6"
    "351821380a3455532a2259c2c5caf4cac"
)


def test_known_answer_vector_from_official_manual():
    assert encrypt(_MANUAL_PARAMS, _MANUAL_KEY, _MANUAL_IV) == _MANUAL_CIPHERTEXT


def test_known_answer_vector_decrypts_back():
    from urllib.parse import urlencode

    assert decrypt(_MANUAL_CIPHERTEXT, _MANUAL_KEY, _MANUAL_IV) == urlencode(_MANUAL_PARAMS)


# ---------------------------------------------------------------------------
# build_period_post_data
# ---------------------------------------------------------------------------

def test_build_period_post_data_round_trips_expected_fields():
    post_data = build_period_post_data(
        mer_order_no="tborder1",
        prod_desc="TinBoker Membership",
        period_amt=99,
        period_point=5,
        payer_email="a@b.com",
        merchant_id="MID123",
        key=KEY,
        iv=IV,
        return_url="https://tinboker.com/membership",
        notify_url="https://api.tinboker.com/api/billing/notify",
    )
    assert post_data["MerchantID_"] == "MID123"
    from urllib.parse import parse_qsl

    inner = dict(parse_qsl(decrypt(post_data["PostData_"], KEY, IV)))
    assert inner["PeriodType"] == "M"
    assert inner["PeriodStartType"] == "2"
    assert inner["PeriodTimes"] == "99"
    assert inner["PeriodPoint"] == "05"  # zero-padded
    assert inner["PeriodAmt"] == "99"
    assert inner["Version"] == "1.5"
    assert inner["RespondType"] == "JSON"
    # PaymentInfo/OrderInfo default to Y in the manual; we force N (no PII collection).
    assert inner["PaymentInfo"] == "N"
    assert inner["OrderInfo"] == "N"
    assert inner["EmailModify"] == "0"
    assert inner["NotifyURL"] == "https://api.tinboker.com/api/billing/notify"
    assert inner["ReturnURL"] == "https://tinboker.com/membership"


def test_build_period_post_data_pads_double_digit_day():
    post_data = build_period_post_data(
        mer_order_no="tborder2",
        prod_desc="TinBoker Membership",
        period_amt=199,
        period_point=28,
        payer_email="a@b.com",
        merchant_id="MID123",
        key=KEY,
        iv=IV,
        return_url="https://tinboker.com/membership",
        notify_url="https://api.tinboker.com/api/billing/notify",
    )
    inner = dict(
        pair.split("=", 1) for pair in decrypt(post_data["PostData_"], KEY, IV).split("&")
    )
    assert inner["PeriodPoint"] == "28"


def test_build_period_post_data_requires_notify_url():
    with pytest.raises(TypeError):
        build_period_post_data(
            mer_order_no="tborder3",
            prod_desc="TinBoker Membership",
            period_amt=99,
            period_point=5,
            payer_email="a@b.com",
            merchant_id="MID123",
            key=KEY,
            iv=IV,
            return_url="https://tinboker.com/membership",
            # notify_url omitted on purpose
        )


@pytest.mark.parametrize("bad_point", [0, 32])
def test_build_period_post_data_rejects_bad_period_point(bad_point):
    with pytest.raises(ValueError):
        build_period_post_data(
            mer_order_no="tborder4",
            prod_desc="TinBoker Membership",
            period_amt=99,
            period_point=bad_point,
            payer_email="a@b.com",
            merchant_id="MID123",
            key=KEY,
            iv=IV,
            return_url="https://tinboker.com/membership",
            notify_url="https://api.tinboker.com/api/billing/notify",
        )


def test_build_period_post_data_rejects_non_positive_amount():
    with pytest.raises(ValueError):
        build_period_post_data(
            mer_order_no="tborder5",
            prod_desc="TinBoker Membership",
            period_amt=0,
            period_point=5,
            payer_email="a@b.com",
            merchant_id="MID123",
            key=KEY,
            iv=IV,
            return_url="https://tinboker.com/membership",
            notify_url="https://api.tinboker.com/api/billing/notify",
        )


# ---------------------------------------------------------------------------
# key/IV length validation
# ---------------------------------------------------------------------------

def test_encrypt_rejects_short_key():
    with pytest.raises(NewebPayError):
        encrypt({"a": "b"}, "k" * 31, IV)


def test_decrypt_rejects_short_key():
    ciphertext = encrypt({"a": "b"}, KEY, IV)
    with pytest.raises(NewebPayError):
        decrypt(ciphertext, "k" * 31, IV)


# ---------------------------------------------------------------------------
# new_mer_order_no
# ---------------------------------------------------------------------------

def test_new_mer_order_no_matches_newebpay_charset():
    for _ in range(20):
        assert re.fullmatch(r"[A-Za-z0-9_]{1,30}", new_mer_order_no())


def test_new_mer_order_no_is_collision_resistant():
    values = {new_mer_order_no() for _ in range(1000)}
    assert len(values) == 1000


# ---------------------------------------------------------------------------
# parse_period_result
# ---------------------------------------------------------------------------

def _encrypt_raw_bytes(plaintext: bytes, key: str, iv: str) -> str:
    """Encrypt raw bytes (not urlencoded params) — the real `Period` field is a JSON
    blob, not a form-encoded query string, so this bypasses `encrypt()`'s urlencode."""
    from cryptography.hazmat.primitives import padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    padder = padding.PKCS7(algorithms.AES.block_size).padder()
    padded = padder.update(plaintext) + padder.finalize()
    cipher = Cipher(algorithms.AES(key.encode()), modes.CBC(iv.encode()))
    encryptor = cipher.encryptor()
    return (encryptor.update(padded) + encryptor.finalize()).hex()


def test_parse_period_result_decrypts_json():
    import json as _json

    payload = {"Status": "SUCCESS", "Result": {"PeriodNo": "P123", "MerOrderNo": "tborder1"}}
    ciphertext = _encrypt_raw_bytes(
        _json.dumps(payload, ensure_ascii=False).encode("utf-8"), KEY, IV
    )

    result = parse_period_result(ciphertext, KEY, IV)
    assert result["Status"] == "SUCCESS"
    assert result["Result"]["PeriodNo"] == "P123"


def test_parse_period_result_rejects_non_json():
    ciphertext = encrypt({"not": "json"}, KEY, IV)  # decrypts to a query string, not JSON
    with pytest.raises(NewebPayError):
        parse_period_result(ciphertext, KEY, IV)


def test_parse_period_result_rejects_missing_status():
    import json as _json

    ciphertext = _encrypt_raw_bytes(_json.dumps({"Result": {}}).encode("utf-8"), KEY, IV)
    with pytest.raises(NewebPayError):
        parse_period_result(ciphertext, KEY, IV)


def test_period_endpoint():
    assert period_endpoint("sandbox") == "https://ccore.newebpay.com/MPG/period"
    assert period_endpoint("production") == "https://core.newebpay.com/MPG/period"
    with pytest.raises(ValueError):
        period_endpoint("bogus")


# ---------------------------------------------------------------------------
# GET /api/billing/plans
# ---------------------------------------------------------------------------

def test_plans_founding_open_when_no_seats_taken():
    with patch("src.routers.billing._founding_taken", return_value=0):
        client = TestClient(app)
        resp = client.get("/api/billing/plans")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["founding_open"] is True
    assert body["founding_remaining"] > 0
    assert body["checkout_open"] is False  # CHECKOUT_IMPLEMENTED is False in PR 3a


def test_plans_founding_closed_at_limit():
    from src.config import settings

    with patch("src.routers.billing._founding_taken", return_value=settings.membership_founding_limit):
        client = TestClient(app)
        resp = client.get("/api/billing/plans")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["founding_open"] is False
    assert body["founding_remaining"] == 0


def test_plans_checkout_never_open_in_pr_3a():
    """Even with credentials configured, checkout_open must stay False — PR 3a ships
    no checkout endpoint, so CHECKOUT_IMPLEMENTED gates it off regardless.

    Test settings run with `environment=development`, so `newebpay_env` resolves to
    "sandbox" and `newebpay_configured` reads the sandbox credential fields."""
    from src.config import settings

    with patch("src.routers.billing._founding_taken", return_value=0), patch.object(
        settings, "newebpay_sandbox_merchant_id", "MID"
    ), patch.object(settings, "newebpay_sandbox_hash_key", "k" * 32), patch.object(
        settings, "newebpay_sandbox_hash_iv", "i" * 16
    ):
        assert settings.newebpay_env == "sandbox"
        assert settings.newebpay_configured is True
        client = TestClient(app)
        resp = client.get("/api/billing/plans")
    assert resp.json()["checkout_open"] is False


# ---------------------------------------------------------------------------
# Settings — env-derived NewebPay credential selection
# ---------------------------------------------------------------------------

def test_settings_pick_sandbox_credentials_when_not_production():
    from src.config import Settings

    s = Settings(
        environment="development",
        newebpay_merchant_id="PROD_MID",
        newebpay_hash_key="p" * 32,
        newebpay_hash_iv="p" * 16,
        newebpay_sandbox_merchant_id="SANDBOX_MID",
        newebpay_sandbox_hash_key="s" * 32,
        newebpay_sandbox_hash_iv="s" * 16,
    )
    assert s.newebpay_env == "sandbox"
    assert s.newebpay_credentials == ("SANDBOX_MID", "s" * 32, "s" * 16)
    assert s.newebpay_configured is True


def test_settings_pick_production_credentials_when_production():
    from src.config import Settings

    s = Settings(
        environment="production",
        newebpay_merchant_id="PROD_MID",
        newebpay_hash_key="p" * 32,
        newebpay_hash_iv="p" * 16,
        newebpay_sandbox_merchant_id="SANDBOX_MID",
        newebpay_sandbox_hash_key="s" * 32,
        newebpay_sandbox_hash_iv="s" * 16,
    )
    assert s.newebpay_env == "production"
    assert s.newebpay_credentials == ("PROD_MID", "p" * 32, "p" * 16)
    assert s.newebpay_configured is True


def test_settings_newebpay_configured_false_when_this_envs_creds_missing():
    from src.config import Settings

    s = Settings(
        environment="production",
        newebpay_sandbox_merchant_id="SANDBOX_MID",
        newebpay_sandbox_hash_key="s" * 32,
        newebpay_sandbox_hash_iv="s" * 16,
        # production fields left at their empty default
    )
    assert s.newebpay_env == "production"
    assert s.newebpay_configured is False
