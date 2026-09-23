"""Public prelaunch prices have no payment/auth side effects."""
from contextlib import contextmanager

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from src.config import settings
from src.routers import billing


@pytest.fixture
def plans(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'plans.db'}", connect_args={"check_same_thread": False})
    factory = sessionmaker(bind=engine)
    @contextmanager
    def scope():
        with factory() as db:
            yield db
    monkeypatch.setattr(billing, "session_scope", scope)
    monkeypatch.setattr(settings, "membership_list_price", 199)
    monkeypatch.setattr(settings, "membership_founding_price", 99)
    monkeypatch.setattr(settings, "membership_founding_limit", 100)
    monkeypatch.setattr(settings, "environment", "production")
    app = FastAPI()
    app.include_router(billing.router)
    return TestClient(app), engine


def test_prelaunch_prices_without_billing_table(plans):
    client, _ = plans
    response = client.get("/api/billing/plans")
    assert response.status_code == 200
    assert response.json() == dict(list_price=199, founding_price=99, founding_limit=100,
                                  founding_remaining=100, founding_open=True,
                                  checkout_open=False, gateway_env="production")
    assert "s-maxage=60" in response.headers["cache-control"]


@pytest.mark.parametrize("environment,expected", [("production", 95), ("development", 99), ("staging", 99)])
def test_counts_only_current_gateway_reservations(plans, monkeypatch, environment, expected):
    client, engine = plans
    with engine.begin() as db:
        db.execute(text("CREATE TABLE subscriptions (is_founding BOOLEAN, gateway_env TEXT, status TEXT)"))
        rows = [{"founding": True, "env": "production", "status": status}
                for status in ("pending", "active", "cancelling", "cancelled", "ended", "failed")]
        rows += [{"founding": False, "env": "production", "status": "active"},
                 {"founding": True, "env": "sandbox", "status": "active"}]
        db.execute(text("INSERT INTO subscriptions VALUES (:founding, :env, :status)"), rows)
    monkeypatch.setattr(settings, "environment", environment)
    response = client.get("/api/billing/plans").json()
    assert response["founding_remaining"] == expected
    assert response["checkout_open"] is False
    with engine.connect() as db:
        assert db.execute(text("SELECT COUNT(*) FROM subscriptions")).scalar_one() == len(rows)


def test_sold_out_clamps_and_backend_settings_are_used(plans, monkeypatch):
    client, _ = plans
    monkeypatch.setattr(billing, "_founding_taken", lambda _: 101)
    monkeypatch.setattr(settings, "membership_list_price", 299)
    response = client.get("/api/billing/plans").json()
    assert response["list_price"] == 299
    assert response["founding_remaining"] == 0 and response["founding_open"] is False


@pytest.mark.parametrize("route", ["checkout", "notify", "return", "cancel", "subscription"])
def test_payment_routes_are_not_exposed(plans, route):
    client, _ = plans
    assert client.post(f"/api/billing/{route}", json={}).status_code == 404
