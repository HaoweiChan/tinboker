"""Integrity-constraint tests for the billing tables (PR 3a review follow-up).

Uses a real in-memory-backed SQLite engine with the actual ORM models (same idiom
as `tests/test_picks_window_returns.py`'s `warm_db` fixture) so the constraints
under test are the ones Postgres will actually enforce, not a re-description of them.
"""
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from src.database.models import Base, PaymentEvent, Subscription


@pytest.fixture()
def db_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'billing.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _subscription(**overrides) -> Subscription:
    defaults = dict(
        id=str(uuid.uuid4()),
        user_id="u1",
        mer_order_no=f"tb{uuid.uuid4().hex[:20]}",
        status="pending",
        amount=99,
        is_founding=True,
        gateway_env="sandbox",
    )
    defaults.update(overrides)
    return Subscription(**defaults)


def _payment_event(**overrides) -> PaymentEvent:
    defaults = dict(
        mer_order_no="tborder1",
        already_times=0,
        kind="first_auth",
        success=True,
        gateway_env="sandbox",
        raw={},
    )
    defaults.update(overrides)
    return PaymentEvent(**defaults)


def test_duplicate_first_auth_payment_event_is_rejected(db_session):
    """Two first-auth results for the same order (a re-delivered create-mandate
    response) must collide on the dedup key — this is exactly the case the old
    (period_no, already_times, kind) key missed, since first-auth never carries
    AlreadyTimes and both rows would have NULL there."""
    db_session.add(_payment_event())
    db_session.commit()

    db_session.add(_payment_event())
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_different_kind_same_order_is_allowed(db_session):
    db_session.add(_payment_event(kind="first_auth"))
    db_session.add(_payment_event(kind="period", already_times=1))
    db_session.commit()  # no error


def test_second_active_subscription_for_same_user_is_rejected(db_session):
    db_session.add(_subscription(status="active"))
    db_session.commit()

    db_session.add(_subscription(status="active"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_second_cancelled_subscription_for_same_user_is_allowed(db_session):
    """The partial unique index only covers status='active' — a user may have any
    number of past (cancelled/ended) subscriptions."""
    db_session.add(_subscription(status="cancelled"))
    db_session.add(_subscription(status="cancelled"))
    db_session.commit()  # no error


def test_active_subscription_allowed_for_different_users(db_session):
    db_session.add(_subscription(user_id="u1", status="active"))
    db_session.add(_subscription(user_id="u2", status="active"))
    db_session.commit()  # no error
