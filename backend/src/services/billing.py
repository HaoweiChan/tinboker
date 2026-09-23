"""Transactional NewebPay subscriptions; sandbox never changes production grants."""
from calendar import monthrange
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo
import uuid
import re

import httpx
from fastapi import HTTPException
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from src.config import settings
from src.database.models import PaymentEvent, Subscription, User
from src.database.postgres import session_scope
from src.database.user_db import set_member_until
from src.services import newebpay

TAIPEI = ZoneInfo("Asia/Taipei")
OPEN_STATUSES = ("pending", "active", "cancelling")


def billing_urls() -> tuple[str, str]:
    """Never send sandbox callbacks to the production host (settings default there)."""
    hosts = {
        "development": ("https://dev.tinboker.com", "https://dev-api.tinboker.com"),
        "staging": ("https://staging.tinboker.com", "https://staging-api.tinboker.com"),
        "production": ("https://tinboker.com", "https://api.tinboker.com"),
    }
    if settings.environment not in hosts:
        raise HTTPException(503, "Billing environment is not configured")
    return hosts[settings.environment]


def _lock(db: Session) -> None:
    # One transaction lock per gateway serializes seat allocation + callback state
    # across API workers. SQLite's write lock provides the local/test equivalent.
    if db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": f"billing:{settings.newebpay_env}"})
    else:
        db.execute(text("BEGIN IMMEDIATE"))


def _aware(value: datetime | None) -> datetime | None:
    return value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value


def _view(sub: Subscription | None) -> dict:
    return {"subscription": None if sub is None else {
        "id": sub.id, "mer_order_no": sub.mer_order_no, "status": sub.status,
        "amount": sub.amount, "is_founding": sub.is_founding,
        "gateway_env": sub.gateway_env, "paid_until": _aware(sub.paid_until),
        "next_auth_date": sub.next_auth_date,
    }}


def _latest(db: Session, user_id: str) -> Subscription | None:
    return db.query(Subscription).filter_by(user_id=user_id, gateway_env=settings.newebpay_env).order_by(Subscription.created_at.desc()).first()


def subscription_status(user_id: str) -> dict:
    with session_scope() as db:
        return _view(_latest(db, user_id))


def sandbox_member_until(user_id: str) -> datetime | None:
    with session_scope() as db:
        value = db.query(func.max(Subscription.paid_until)).filter_by(user_id=user_id, gateway_env="sandbox").scalar()
        return _aware(value)


def checkout(user_id: str, email: str) -> dict:
    if not settings.newebpay_checkout_enabled or not settings.newebpay_configured:
        raise HTTPException(503, "Membership checkout is not open yet")
    _, api = billing_urls()
    merchant, key, iv = settings.newebpay_credentials
    with session_scope() as db:
        _lock(db)
        user = db.query(User).filter_by(id=user_id).first()
        if not user:
            raise HTTPException(404, "User not found")
        sub = db.query(Subscription).filter_by(user_id=user_id, gateway_env=settings.newebpay_env).filter(Subscription.status.in_(OPEN_STATUSES)).first()
        if sub and sub.status != "pending":
            raise HTTPException(409, "An existing subscription must be cancelled first")
        if sub is None:
            taken = db.query(func.count(Subscription.id)).filter(
                Subscription.gateway_env == settings.newebpay_env,
                Subscription.is_founding.is_(True),
                Subscription.status.in_(("pending", "active", "cancelling", "cancelled", "ended")),
            ).scalar()
            founding = taken < settings.membership_founding_limit
            sub = Subscription(id=str(uuid.uuid4()), user_id=user_id, mer_order_no=newebpay.new_mer_order_no(),
                               amount=settings.membership_founding_price if founding else settings.membership_list_price,
                               is_founding=founding, gateway_env=settings.newebpay_env, status="pending")
            db.add(sub)
            db.flush()
        fields = newebpay.build_period_post_data(
            mer_order_no=sub.mer_order_no, prod_desc="TinBoker Membership", period_amt=sub.amount,
            period_point=datetime.now(TAIPEI).day, payer_email=email,
            merchant_id=merchant, key=key, iv=iv, return_url=f"{api}/api/billing/return",
            notify_url=f"{api}/api/billing/notify",
        )
        return {"action": newebpay.period_endpoint(settings.newebpay_env), "fields": fields,
                "mer_order_no": sub.mer_order_no, "gateway_env": settings.newebpay_env}


def _month_after(day: date) -> date:
    year, month = (day.year + 1, 1) if day.month == 12 else (day.year, day.month + 1)
    return date(year, month, min(day.day, monthrange(year, month)[1]))


def _parse_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y%m%d%H%M%S").date() if isinstance(value, str) and len(value) == 14 and value.isdigit() else date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        raise HTTPException(400, "Invalid payment date") from None


def process_notification(encrypted: str) -> dict:
    if not settings.newebpay_configured:
        raise HTTPException(503, "Payment gateway unavailable")
    merchant, key, iv = settings.newebpay_credentials
    try:
        payload = newebpay.parse_period_result(encrypted, key, iv)
        result = payload.get("Result")
        if not isinstance(result, dict):
            raise ValueError()
        order = result["MerchantOrderNo"]
        if not isinstance(order, str) or not re.fullmatch(r"[A-Za-z0-9_]{1,30}", order):
            raise ValueError()
        period_no = result.get("PeriodNo")
        if period_no is not None and (not isinstance(period_no, str) or not re.fullmatch(r"[A-Za-z0-9_]{1,40}", period_no)):
            raise ValueError()
        if result.get("MerchantID") != merchant:
            raise ValueError()
        kind = "period" if "AlreadyTimes" in result else "first_auth"
        success = payload["Status"] == "SUCCESS" and result.get("RespondCode") == "00"
        terminal_failure = kind == "first_auth" and payload["Status"] == "PER10034" and result.get("RespondCode") != "00"
        bank_failure = kind == "period" and isinstance(result.get("RespondCode"), str) and bool(re.fullmatch(r"[0-9]{2}", result["RespondCode"])) and result["RespondCode"] != "00"
        if not (success or terminal_failure or bank_failure):
            # Duplicate submissions and unknown provider errors do not prove that
            # the outstanding mandate failed. Retain the reservation for recovery.
            raise ValueError()
        amount_value = result.get("AuthAmt" if kind == "period" else "PeriodAmt")
        amount = int(amount_value) if amount_value is not None else None
        if amount is None and not terminal_failure:
            raise ValueError()
        cycle = int(result.get("AlreadyTimes", 0))
        total_value = result.get("TotalTimes" if kind == "period" else "AuthTimes")
        total = int(total_value) if total_value is not None else 0
        if cycle < 0 or (not terminal_failure and (total <= 0 or cycle > total)):
            raise ValueError()
    except (newebpay.NewebPayError, ValueError, TypeError, KeyError):
        raise HTTPException(400, "Invalid payment notification") from None
    event_kind = kind if success else ("first_failed" if kind == "first_auth" else "period_failed")
    with session_scope() as db:
        _lock(db)
        sub = db.query(Subscription).filter_by(mer_order_no=order, gateway_env=settings.newebpay_env).first()
        if not sub or (amount is not None and sub.amount != amount):
            raise HTTPException(400, "Payment order or amount mismatch")
        if success and sub.status == "failed":
            # A contradictory success after a verified terminal failure requires
            # provider reconciliation; never create a second live mandate/grant.
            raise HTTPException(409, "Conflicting payment outcome requires reconciliation")
        period_no = result.get("PeriodNo")
        if sub.period_no and period_no != sub.period_no:
            raise HTTPException(400, "Payment mandate mismatch")
        if db.query(PaymentEvent.id).filter_by(mer_order_no=order, already_times=cycle, kind=event_kind).first():
            return {"status": "ok"}
        if success and not period_no:
            raise HTTPException(400, "Missing payment mandate")
        if success:
            paid_on = _parse_date(result.get("AuthDate") or result.get("AuthTime"))
            if kind == "first_auth":
                scheduled = [_parse_date(value) for value in str(result.get("DateArray", "")).split(",")]
                next_date = min((value for value in scheduled if value > paid_on), default=_month_after(paid_on))
            else:
                if result.get("OrderNo") != f"{order}_{cycle}":
                    raise HTTPException(400, "Payment cycle mismatch")
                next_date = _parse_date(result["NextAuthDate"])
                if cycle == total and next_date == paid_on:
                    next_date = _month_after(paid_on)
            following = _month_after(paid_on)
            latest_next = following.replace(day=monthrange(following.year, following.month)[1])
            if next_date <= paid_on or next_date > latest_next:
                raise HTTPException(400, "Invalid next payment date")
            until = datetime.combine(next_date, time.min, tzinfo=TAIPEI).astimezone(timezone.utc)
            sub.period_no = period_no
            sub.paid_until = max(filter(None, [_aware(sub.paid_until), until]))
            if sub.next_auth_date is None or next_date > sub.next_auth_date:
                sub.next_auth_date = next_date
            sub.total_times = total
            if sub.status not in ("cancelled", "cancelling", "ended"):
                sub.status = "ended" if (kind == "period" and cycle == total) or total == 1 else "active"
            if settings.newebpay_env == "production":
                user = db.query(User).filter_by(id=sub.user_id).with_for_update().first()
                if not user:
                    raise HTTPException(400, "Payment user not found")
                set_member_until(user.email, max(filter(None, [_aware(user.member_until), _aware(sub.paid_until)])), session=db)
        elif sub.status == "pending" and kind == "first_auth":
            sub.status = "failed"
        elif kind == "period" and cycle == total and sub.status == "active":
            sub.status = "ended"
        if sub.status in ("ended", "cancelled"):
            sub.next_auth_date = None
        # Retain only reconciliation fields. Never persist arbitrary gateway PII.
        raw = {k: result[k] for k in ("MerchantID", "MerchantOrderNo", "PeriodNo", "PeriodAmt", "AuthAmt", "TradeNo", "RespondCode", "AlreadyTimes", "AuthDate", "AuthTime", "NextAuthDate", "AuthTimes", "TotalTimes") if k in result}
        db.add(PaymentEvent(subscription_id=sub.id, mer_order_no=order, period_no=period_no,
                            already_times=cycle, kind=event_kind, success=success, amount=amount,
                            gateway_env=settings.newebpay_env, raw={"Status": payload["Status"], "Result": raw}))
        return {"status": "ok"}


def cancel_subscription(user_id: str) -> dict:
    """Stop future charges; never shorten the last paid entitlement."""
    if not settings.newebpay_configured:
        raise HTTPException(503, "Payment gateway unavailable")
    merchant, key, iv = settings.newebpay_credentials
    with session_scope() as db:
        _lock(db)
        sub = _latest(db, user_id)
        if not sub:
            raise HTTPException(404, "Subscription not found")
        if sub.status in ("cancelled", "ended"):
            return _view(sub)
        if not sub.period_no:
            raise HTTPException(409, "Payment confirmation is still pending")
        # No blind retry after timeout: the provider may already have cancelled.
        # Keep the mandate visible and let the owner retry its idempotent termination.
        try:
            response = httpx.post(
                newebpay.period_endpoint(settings.newebpay_env) + "/AlterStatus",
                data={"MerchantID_": merchant, "PostData_": newebpay.encrypt({
                    "RespondType": "JSON", "Version": "1.0", "TimeStamp": str(int(datetime.now(timezone.utc).timestamp())),
                    "MerOrderNo": sub.mer_order_no, "PeriodNo": sub.period_no, "AlterType": "terminate",
                }, key, iv)}, timeout=15.0,
            )
            response.raise_for_status()
            data = response.json()
            result = newebpay.parse_period_result(data["period"], key, iv)
            expected = result.get("Result", {})
            if (not isinstance(expected, dict) or result.get("Status") != "SUCCESS" or expected.get("MerOrderNo") != sub.mer_order_no
                    or expected.get("PeriodNo") != sub.period_no or expected.get("AlterType") != "terminate"):
                raise ValueError()
        except (httpx.HTTPError, ValueError, TypeError, KeyError, newebpay.NewebPayError):
            if not _confirmed_terminated(sub, merchant, key, iv):
                raise HTTPException(502, "Cancellation could not be confirmed; please retry") from None
        sub.status = "cancelled"
        sub.next_auth_date = None
        sub.cancelled_at = datetime.now(timezone.utc)
        return _view(sub)


def _confirmed_terminated(sub: Subscription, merchant: str, key: str, iv: str) -> bool:
    """Recover an uncertain termination. Mandate queries never prove a charge."""
    import json
    try:
        response = httpx.post(newebpay.period_endpoint(settings.newebpay_env) + "/query", data={
            "MerchantID_": merchant,
            "PostData_": newebpay.encrypt({"RespondType": "JSON", "Version": "1.0",
                "TimeStamp": str(int(datetime.now(timezone.utc).timestamp())),
                "MerOrderNo": sub.mer_order_no, "PeriodNo": sub.period_no}, key, iv),
        }, timeout=15.0)
        response.raise_for_status()
        payload = json.loads(newebpay.decrypt(response.json()["Period"], key, iv))
        # The official query example uses lowercase root keys, unlike its table.
        if any(k in payload and k.lower() in payload and payload[k] != payload[k.lower()] for k in ("Status", "Result")):
            return False
        result = payload.get("Result", payload.get("result", {}))
        orders = [result[k] for k in ("MerOrderNo", "MerchantOrderNo") if k in result]
        return (payload.get("Status", payload.get("status")) == "SUCCESS"
                and bool(orders) and all(order == sub.mer_order_no for order in orders)
                and result.get("MerchantID") == merchant and result.get("PeriodNo") == sub.period_no
                and int(result.get("PeriodAmt", -1)) == sub.amount and str(result.get("Status")) == "3")
    except (httpx.HTTPError, ValueError, TypeError, KeyError, AttributeError, newebpay.NewebPayError):
        return False
