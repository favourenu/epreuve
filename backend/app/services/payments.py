"""Paystack payments for claiming certificates.

Flow: the user starts a payment, we create a pending Payment with our own
reference and ask Paystack for a checkout URL. After paying, Paystack sends the
user back with the reference, and (separately) calls our webhook. Either path
re-checks the transaction with Paystack, or a signed webhook, and only then
issues the certificate. Amounts always come from the server, never the browser.
"""

import hashlib
import hmac
import logging
import secrets
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Certificate, CertificateStatus, Payment, PaymentStatus, User, utcnow

log = logging.getLogger(__name__)


class PaymentError(Exception):
    status_code = 400


class PaymentUnavailable(PaymentError):
    status_code = 503


@dataclass
class VerifiedTransaction:
    reference: str
    status: str  # "success", "failed", "abandoned", ...
    amount_kobo: int
    currency: str
    channel: str | None = None


class PaystackClient(Protocol):
    def initialize(self, *, email: str, amount_kobo: int, reference: str, callback_url: str, metadata: dict) -> str: ...

    def verify(self, reference: str) -> VerifiedTransaction: ...


@dataclass
class HttpPaystack:
    secret_key: str
    base_url: str
    timeout: float = 20.0

    def _call(self, method: str, path: str, **kwargs) -> dict:
        try:
            resp = httpx.request(
                method,
                f"{self.base_url}{path}",
                timeout=self.timeout,
                headers={"Authorization": f"Bearer {self.secret_key}"},
                **kwargs,
            )
        except httpx.HTTPError as exc:
            raise PaymentUnavailable("Could not reach the payment provider. Please try again.") from exc
        try:
            data = resp.json()
        except ValueError:
            data = {}
        if resp.status_code >= 400 or not data.get("status"):
            log.warning("Paystack %s %s failed: %s %s", method, path, resp.status_code, resp.text[:300])
            raise PaymentUnavailable("The payment provider returned an error. Please try again.")
        return data["data"]

    def initialize(self, *, email, amount_kobo, reference, callback_url, metadata) -> str:
        data = self._call(
            "POST",
            "/transaction/initialize",
            json={
                "email": email,
                "amount": amount_kobo,
                "currency": "NGN",
                "reference": reference,
                "callback_url": callback_url,
                "metadata": metadata,
            },
        )
        return data["authorization_url"]

    def verify(self, reference: str) -> VerifiedTransaction:
        data = self._call("GET", f"/transaction/verify/{reference}")
        return VerifiedTransaction(
            reference=data["reference"],
            status=data["status"],
            amount_kobo=int(data["amount"]),
            currency=data.get("currency", "NGN"),
            channel=data.get("channel"),
        )


@lru_cache
def get_paystack() -> PaystackClient | None:
    s = get_settings()
    return HttpPaystack(s.paystack_secret_key, s.paystack_base_url) if s.paystack_secret_key else None


def payment_required() -> bool:
    s = get_settings()
    return s.certificate_price_kobo > 0 and bool(s.paystack_secret_key)


def has_paid(db: Session, cert: Certificate) -> bool:
    return bool(
        db.scalar(select(Payment.id).where(Payment.certificate_id == cert.id, Payment.status == PaymentStatus.SUCCESS))
    )


def status_after_approval(db: Session, cert: Certificate) -> str:
    """What an earned certificate becomes once cleared: issued, or waiting for the fee."""
    if payment_required() and not has_paid(db, cert):
        return CertificateStatus.AWAITING_PAYMENT
    return CertificateStatus.ISSUED


def start(db: Session, client: PaystackClient | None, user: User, cert: Certificate) -> str:
    """Create a pending payment and return Paystack's checkout URL."""
    if cert.user_id != user.id:
        raise PaymentError("Certificate not found")
    if cert.status != CertificateStatus.AWAITING_PAYMENT:
        raise PaymentError("This certificate does not need a payment.")
    if client is None or not payment_required():
        raise PaymentUnavailable("Payments are not set up yet.")
    s = get_settings()
    payment = Payment(
        reference=f"EPR-{secrets.token_hex(10)}",
        user_id=user.id,
        certificate_id=cert.id,
        amount_kobo=s.certificate_price_kobo,
        currency="NGN",
    )
    db.add(payment)
    db.commit()
    return client.initialize(
        email=user.email,
        amount_kobo=payment.amount_kobo,
        reference=payment.reference,
        callback_url=f"{s.app_base_url.rstrip('/')}/certificates/claimed",
        metadata={"certificate_code": cert.code, "purpose": "certificate"},
    )


def apply(db: Session, tx: VerifiedTransaction) -> Payment | None:
    """Record a verified transaction. Issues the certificate on success. Idempotent."""
    payment = db.scalar(select(Payment).where(Payment.reference == tx.reference))
    if payment is None:
        log.warning("Paystack transaction for unknown reference %s", tx.reference)
        return None
    if payment.status == PaymentStatus.SUCCESS:
        return payment
    if tx.status != "success":
        if tx.status in ("failed", "reversed"):
            payment.status = PaymentStatus.FAILED
            db.commit()
        return payment
    if tx.amount_kobo < payment.amount_kobo or tx.currency != payment.currency:
        log.error("Paystack amount mismatch for %s: got %s %s", tx.reference, tx.amount_kobo, tx.currency)
        payment.status = PaymentStatus.FAILED
        db.commit()
        return payment
    payment.status = PaymentStatus.SUCCESS
    payment.channel = tx.channel
    payment.paid_at = utcnow()
    cert = db.get(Certificate, payment.certificate_id)
    if cert and cert.status == CertificateStatus.AWAITING_PAYMENT:
        cert.status = CertificateStatus.ISSUED
        cert.issued_at = utcnow()
    db.commit()
    return payment


def valid_webhook_signature(body: bytes, signature: str | None) -> bool:
    key = get_settings().paystack_secret_key
    if not key or not signature:
        return False
    expected = hmac.new(key.encode(), body, hashlib.sha512).hexdigest()
    return hmac.compare_digest(expected, signature)


def revenue(db: Session) -> dict:
    total, count = db.execute(
        select(func.coalesce(func.sum(Payment.amount_kobo), 0), func.count(Payment.id)).where(
            Payment.status == PaymentStatus.SUCCESS
        )
    ).one()
    return {"revenue_kobo": int(total), "payments": int(count)}
