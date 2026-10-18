import json

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import Certificate, Payment, User
from app.schemas import CertificateOut
from app.services import certification, payments

router = APIRouter(tags=["payments"])


def _raise(exc: payments.PaymentError):
    raise HTTPException(exc.status_code, str(exc)) from exc


@router.post("/api/certificates/{cert_id}/pay")
def pay_for_certificate(
    cert_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    client=Depends(payments.get_paystack),
):
    """Start a Paystack checkout to claim an earned certificate. Returns the checkout URL."""
    cert = db.get(Certificate, cert_id)
    if cert is None or cert.user_id != user.id:
        raise HTTPException(404, "Certificate not found")
    try:
        return {"authorization_url": payments.start(db, client, user, cert)}
    except payments.PaymentError as exc:
        _raise(exc)


@router.post("/api/payments/{reference}/verify", response_model=CertificateOut)
def verify_payment(
    reference: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    client=Depends(payments.get_paystack),
):
    """Called when Paystack sends the user back: confirms the payment with Paystack."""
    payment = db.scalar(select(Payment).where(Payment.reference == reference, Payment.user_id == user.id))
    if payment is None:
        raise HTTPException(404, "Payment not found")
    if client is None:
        raise HTTPException(503, "Payments are not set up yet.")
    try:
        payments.apply(db, client.verify(reference))
    except payments.PaymentError as exc:
        _raise(exc)
    cert = db.get(Certificate, payment.certificate_id)
    return CertificateOut(**certification.certificate_out(cert))


@router.post("/api/payments/paystack/webhook", include_in_schema=False)
async def paystack_webhook(request: Request, db: Session = Depends(get_db)):
    """Paystack's server-to-server notification. Only correctly signed events are accepted."""
    body = await request.body()
    if not payments.valid_webhook_signature(body, request.headers.get("x-paystack-signature")):
        raise HTTPException(401, "Invalid signature")
    event = json.loads(body)
    if event.get("event") == "charge.success":
        data = event.get("data", {})
        payments.apply(
            db,
            payments.VerifiedTransaction(
                reference=data.get("reference", ""),
                status=data.get("status", ""),
                amount_kobo=int(data.get("amount", 0)),
                currency=data.get("currency", "NGN"),
                channel=data.get("channel"),
            ),
        )
    return {"received": True}
