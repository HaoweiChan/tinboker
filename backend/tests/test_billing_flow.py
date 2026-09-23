"""Transaction/API tests using isolated SQLite and a mocked gateway."""
import json
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from urllib.parse import parse_qs
from unittest.mock import Mock

import httpx
import pytest
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.config import settings
from src.database import user_db
from src.database.models import Base, PaymentEvent, Subscription, User
from src.routers import auth, billing as router
from src.services import billing, newebpay
from src.utils.auth import create_jwt_token, create_refresh_token
from src.utils.dependencies import get_current_user, require_member

KEY, IV, MERCHANT = "k" * 32, "i" * 16, "TEST_MERCHANT"


def encrypted(payload):
    pad = padding.PKCS7(128).padder()
    data = pad.update(json.dumps(payload).encode()) + pad.finalize()
    enc = Cipher(algorithms.AES(KEY.encode()), modes.CBC(IV.encode())).encryptor()
    return (enc.update(data) + enc.finalize()).hex()


@pytest.fixture
def flow(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'billing.db'}", connect_args={"check_same_thread": False, "timeout": 20})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    @contextmanager
    def scope():
        with factory() as db:
            try:
                yield db
                db.commit()
            except Exception:
                db.rollback()
                raise
    monkeypatch.setattr(billing, "session_scope", scope)
    monkeypatch.setattr(user_db, "session_scope", scope)
    monkeypatch.setattr(settings, "environment", "development")
    monkeypatch.setattr(settings, "admin_emails", ["a@example.com", "b@example.com"])
    monkeypatch.setattr(settings, "jwt_secret_key", "billing-test-jwt")
    monkeypatch.setattr(settings, "newebpay_checkout_enabled", True)
    monkeypatch.setattr(settings, "membership_founding_limit", 1)
    for prefix in ("newebpay", "newebpay_sandbox"):
        for suffix, value in (("merchant_id", MERCHANT), ("hash_key", KEY), ("hash_iv", IV)):
            monkeypatch.setattr(settings, f"{prefix}_{suffix}", value)
    with scope() as db:
        for name in ("a", "b", "viewer"):
            db.add(User(id=name, google_id=name, email=f"{name}@example.com", name=name, created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc)))
    app = FastAPI()
    app.include_router(router.router)
    app.include_router(auth.router)
    return TestClient(app), scope


def headers(user="a", preview=False):
    extra = {"membership_preview_session": True, "membership_preview": "paid"} if preview else None
    return {"Authorization": "Bearer " + create_jwt_token(user, f"{user}@example.com", extra)}


def checkout(client, user="a"):
    response = client.post("/api/billing/checkout", headers=headers(user), json={})
    assert response.status_code == 200, response.text
    return response.json()


def first(order, **updates):
    result = {"MerchantID": MERCHANT, "MerchantOrderNo": order, "PeriodNo": "P_test",
              "PeriodAmt": settings.membership_founding_price, "AuthTimes": 12,
              "RespondCode": "00", "AuthTime": "20270131120000",
              "DateArray": "2027-01-31,2027-02-28,2027-03-31"}
    result.update(updates)
    return {"Status": "SUCCESS", "Result": result}


def recurring(order, **updates):
    result = {"MerchantID": MERCHANT, "MerchantOrderNo": order, "PeriodNo": "P_test",
              "AuthAmt": settings.membership_founding_price, "AlreadyTimes": 2, "TotalTimes": 12,
              "RespondCode": "00", "AuthDate": "2027-02-28 12:00:00", "NextAuthDate": "2027-03-31",
              "OrderNo": f"{order}_2"}
    result.update(updates)
    return {"Status": "SUCCESS", "Result": result}


def notify(client, payload, multipart=False, path="/api/billing/notify"):
    kwargs = {"files": {"Period": (None, encrypted(payload))}} if multipart else {"data": {"Period": encrypted(payload)}}
    return client.post(path, **kwargs, follow_redirects=False)


def test_checkout_price_owner_status_sandbox_isolation_and_refresh(flow):
    client, scope = flow
    started = checkout(client)
    params = parse_qs(newebpay.decrypt(started["fields"]["PostData_"], KEY, IV))
    assert params["PeriodAmt"] == [str(settings.membership_founding_price)]
    assert params["NotifyURL"] == ["https://dev-api.tinboker.com/api/billing/notify"]
    assert started["action"].startswith("https://ccore.")
    assert checkout(client)["mer_order_no"] == started["mer_order_no"]
    response = notify(client, first(started["mer_order_no"]))
    assert response.status_code == 200, response.text
    with scope() as db:
        assert db.get(User, "a").member_until is None
        assert db.query(Subscription).one().paid_until is not None
    status = client.get("/api/billing/subscription", headers=headers())
    assert "no-store" in status.headers["cache-control"]
    assert status.json()["subscription"]["status"] == "active"
    assert client.get("/api/billing/subscription", headers=headers("b")).json()["subscription"] is None
    assert require_member(get_current_user(headers()["Authorization"]))
    refresh = client.post("/api/auth/refresh", json={"refresh_token": create_refresh_token("a", "a@example.com")})
    assert refresh.json()["user"]["is_member"] is True


def test_free_preview_overrides_sandbox(flow):
    client, _ = flow
    order = checkout(client)["mer_order_no"]
    assert notify(client, first(order)).status_code == 200
    token = create_jwt_token("a", "a@example.com", {"membership_preview_session": True, "membership_preview": "free"})
    user = get_current_user("Bearer " + token)
    assert not user.is_member
    with pytest.raises(HTTPException) as exc:
        require_member(user)
    assert exc.value.status_code == 402


def test_production_grant_and_crossenv_rejection(flow, monkeypatch):
    client, scope = flow
    order = checkout(client)["mer_order_no"]
    assert notify(client, first(order)).status_code == 200
    monkeypatch.setattr(settings, "environment", "production")
    assert not get_current_user(headers()["Authorization"]).is_member
    assert notify(client, first(order)).status_code == 400
    order = checkout(client)["mer_order_no"]
    assert notify(client, first(order)).status_code == 200
    with scope() as db:
        assert db.get(User, "a").member_until is not None


def test_idempotent_form_callbacks_final_and_out_of_order(flow):
    client, scope = flow
    order = checkout(client)["mer_order_no"]
    assert notify(client, first(order), multipart=True, path="/api/billing/return").status_code == 303
    assert notify(client, first(order)).status_code == 200
    assert notify(client, recurring(order)).status_code == 200
    final = recurring(order, AlreadyTimes=12, OrderNo=f"{order}_12", AuthDate="2027-12-31 12:00:00", NextAuthDate="2027-12-31")
    assert notify(client, final).status_code == 200
    assert notify(client, first(order)).status_code == 200
    with scope() as db:
        sub = db.query(Subscription).one()
        assert sub.status == "ended"
        assert sub.paid_until.month == 1 and sub.paid_until.year == 2028
        assert db.query(PaymentEvent).count() == 3


@pytest.mark.parametrize("change", [{"MerchantID": "wrong"}, {"PeriodAmt": 1}, {"MerchantOrderNo": "foreign"}, {"AuthTime": "bad"}, {"RespondCode": "05"}])
def test_wrong_callback_never_grants(flow, change):
    client, scope = flow
    order = checkout(client)["mer_order_no"]
    notify(client, first(order, **change))
    with scope() as db:
        assert db.get(User, "a").member_until is None
        assert db.query(Subscription).one().paid_until is None


def test_terminal_failure_allows_new_order_conflicting_success_rejected(flow):
    client, scope = flow
    order = checkout(client)["mer_order_no"]
    declined = first(order, RespondCode="05")
    declined["Status"] = "PER10034"
    assert notify(client, declined).status_code == 200
    next_order = checkout(client)["mer_order_no"]
    assert next_order != order
    assert notify(client, first(order)).status_code == 409
    assert notify(client, first(next_order)).status_code == 200
    assert notify(client, recurring(next_order, RespondCode="05")).status_code == 200
    with scope() as db:
        assert db.query(Subscription).filter_by(mer_order_no=next_order).one().status == "active"


def test_concurrent_checkout_one_founder_and_same_order(flow):
    _, scope = flow
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda name: billing.checkout(name, f"{name}@example.com"), ["a", "b", "a", "b"]))
    assert len({r["mer_order_no"] for r in results}) == 2
    with scope() as db:
        assert db.query(Subscription).count() == 2
        assert db.query(Subscription).filter_by(is_founding=True).count() == 1


def test_auth_preview_and_disabled_gate(flow, monkeypatch):
    client, _ = flow
    assert client.post("/api/billing/checkout").status_code == 401
    assert client.post("/api/billing/checkout", headers=headers("viewer")).status_code == 403
    for path in ("checkout", "cancel"):
        assert client.post(f"/api/billing/{path}", headers=headers(preview=True)).status_code == 403
    assert client.get("/api/billing/subscription", headers=headers(preview=True)).status_code == 200
    monkeypatch.setattr(settings, "newebpay_checkout_enabled", False)
    assert client.post("/api/billing/checkout", headers=headers()).status_code == 503


def test_cancel_preserves_paid_term_with_checkout_disabled(flow, monkeypatch):
    client, scope = flow
    order = checkout(client)["mer_order_no"]
    notify(client, first(order))
    monkeypatch.setattr(settings, "newebpay_checkout_enabled", False)
    result = {"Status": "SUCCESS", "Result": {"MerOrderNo": order, "PeriodNo": "P_test", "AlterType": "terminate"}}
    mocked = Mock(return_value=Mock(raise_for_status=Mock(), json=lambda: {"period": encrypted(result)}))
    monkeypatch.setattr(billing.httpx, "post", mocked)
    response = client.post("/api/billing/cancel", headers=headers())
    assert response.status_code == 200, response.text
    assert response.json()["subscription"]["status"] == "cancelled"
    assert response.json()["subscription"]["paid_until"] is not None
    assert client.post("/api/billing/cancel", headers=headers()).status_code == 200
    assert mocked.call_count == 1
    with scope() as db:
        assert db.get(User, "a").member_until is None


def test_cancel_timeout_query_reconciliation(flow, monkeypatch):
    client, _ = flow
    order = checkout(client)["mer_order_no"]
    notify(client, first(order))
    result = {"status": "SUCCESS", "result": {"MerchantID": MERCHANT, "MerchantOrderNo": order,
        "PeriodNo": "P_test", "PeriodAmt": settings.membership_founding_price, "Status": 3}}
    mocked = Mock(side_effect=[httpx.TimeoutException("timeout"), Mock(raise_for_status=Mock(), json=lambda: {"Period": encrypted(result)})])
    monkeypatch.setattr(billing.httpx, "post", mocked)
    assert client.post("/api/billing/cancel", headers=headers()).json()["subscription"]["status"] == "cancelled"


def test_production_grant_failure_rolls_back_payment_and_subscription(flow, monkeypatch):
    client, scope = flow
    monkeypatch.setattr(settings, "environment", "production")
    order = checkout(client)["mer_order_no"]
    monkeypatch.setattr(billing, "set_member_until", Mock(side_effect=RuntimeError("write failed")))
    with pytest.raises(RuntimeError):
        billing.process_notification(encrypted(first(order)))
    with scope() as db:
        assert db.query(PaymentEvent).count() == 0
        assert db.query(Subscription).one().paid_until is None
        assert db.query(Subscription).one().status == "pending"


def test_parallel_callback_delivery_has_one_event(flow):
    client, scope = flow
    payload = encrypted(first(checkout(client)["mer_order_no"]))
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert list(pool.map(billing.process_notification, [payload] * 4)) == [{"status": "ok"}] * 4
    with scope() as db:
        assert db.query(PaymentEvent).count() == 1


def test_bad_ciphertext_and_return_query_do_not_activate(flow):
    client, scope = flow
    checkout(client)
    assert client.post("/api/billing/notify", data={"Period": "tampered"}).status_code == 400
    assert client.post("/api/billing/return?status=SUCCESS", data={}).status_code == 400
    with scope() as db:
        assert db.query(Subscription).one().paid_until is None


def test_unconfirmed_or_wrong_order_cancellation_does_not_change_status(flow, monkeypatch):
    client, _ = flow
    order = checkout(client)["mer_order_no"]
    notify(client, first(order))
    bad = {"Status": "SUCCESS", "Result": {"MerOrderNo": "wrong", "PeriodNo": "P_test", "AlterType": "terminate"}}
    monkeypatch.setattr(billing.httpx, "post", Mock(return_value=Mock(raise_for_status=Mock(), json=lambda: {"period": encrypted(bad)})))
    assert client.post("/api/billing/cancel", headers=headers()).status_code == 502
    assert client.get("/api/billing/subscription", headers=headers()).json()["subscription"]["status"] == "active"


def test_staging_admin_and_revoked_admin_entitlement(flow, monkeypatch):
    client, _ = flow
    order = checkout(client)["mer_order_no"]
    notify(client, first(order))
    monkeypatch.setattr(settings, "environment", "staging")
    assert get_current_user(headers()["Authorization"]).is_member
    assert client.post("/api/billing/checkout", headers=headers("viewer")).status_code == 403
    monkeypatch.setattr(settings, "admin_emails", [])
    assert not get_current_user(headers()["Authorization"]).is_member


@pytest.mark.parametrize("changes", [{"MerchantOrderNo": []}, {"PeriodNo": {"bad": "value"}}])
def test_malformed_identifiers_rejected_before_database(flow, changes):
    client, _ = flow
    order = checkout(client)["mer_order_no"]
    assert notify(client, first(order, **changes)).status_code == 400


def test_duplicate_provider_error_retains_pending_order(flow):
    client, _ = flow
    order = checkout(client)["mer_order_no"]
    payload = first(order)
    payload["Status"] = "PER10032"
    assert notify(client, payload).status_code == 400
    assert checkout(client)["mer_order_no"] == order


def test_terminal_failure_without_optional_success_fields_allows_retry(flow):
    client, _ = flow
    order = checkout(client)["mer_order_no"]
    payload = {"Status": "PER10034", "Result": {"MerchantID": MERCHANT, "MerchantOrderNo": order}}
    assert notify(client, payload).status_code == 200
    assert checkout(client)["mer_order_no"] != order


def test_existing_billing_table_upgrade_is_idempotent(tmp_path, monkeypatch):
    from sqlalchemy import inspect, text
    from src.database import postgres
    engine = create_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text("DROP INDEX uq_one_open_sub_per_user_env"))
        conn.execute(text("ALTER TABLE subscriptions DROP COLUMN paid_until"))
        conn.execute(text("CREATE UNIQUE INDEX uq_one_active_sub_per_user ON subscriptions(user_id) WHERE status = 'active'"))
    monkeypatch.setattr(postgres, "engine", engine)
    postgres.create_all_tables()
    postgres.create_all_tables()
    assert "paid_until" in {column["name"] for column in inspect(engine).get_columns("subscriptions")}
    indexes = {index["name"] for index in inspect(engine).get_indexes("subscriptions")}
    assert "uq_one_open_sub_per_user_env" in indexes
    assert "uq_one_active_sub_per_user" not in indexes
