import hashlib
import hmac
import json
import uuid

import pytest

from app.config import get_settings
from app.main import app
from app.services import payments
from tests.test_certification_admin import complete, report, start

SECRET = "sk_test_fake_secret_for_tests"


class FakePaystack:
    """Records checkouts and returns whatever verification result the test sets."""

    def __init__(self):
        self.initialized: list[dict] = []
        self.results: dict[str, payments.VerifiedTransaction] = {}

    def initialize(self, *, email, amount_kobo, reference, callback_url, metadata):
        self.initialized.append(dict(email=email, amount_kobo=amount_kobo, reference=reference,
                                     callback_url=callback_url, metadata=metadata))
        return f"https://checkout.paystack.test/{reference}"

    def verify(self, reference):
        return self.results.get(reference, payments.VerifiedTransaction(reference, "abandoned", 0, "NGN"))

    def pay(self, reference, amount=None, currency="NGN"):
        sent = next(i for i in self.initialized if i["reference"] == reference)
        self.results[reference] = payments.VerifiedTransaction(
            reference, "success", sent["amount_kobo"] if amount is None else amount, currency, "card")


@pytest.fixture
def paystack(monkeypatch):
    monkeypatch.setattr(get_settings(), "paystack_secret_key", SECRET)
    fake = FakePaystack()
    app.dependency_overrides[payments.get_paystack] = lambda: fake
    yield fake
    app.dependency_overrides.pop(payments.get_paystack, None)


def earn(client):
    """Pass a certification attempt and return the resulting certificate."""
    state = complete(client, start(client).json())
    return client.get(f"/api/attempts/{state['id']}/review").json()["certificate"]


def checkout(client, paystack, cert):
    r = client.post(f"/api/certificates/{cert['id']}/pay")
    assert r.status_code == 200, r.text
    return paystack.initialized[-1]["reference"]


def test_without_payment_keys_certificates_are_free(client):
    assert earn(client)["status"] == "issued"


def test_paid_flow_issues_the_certificate_after_verified_payment(client, paystack, anon):
    cert = earn(client)
    assert cert["status"] == "awaiting_payment" and cert["price_kobo"] == 50000
    assert anon.get(f"/api/public/certificates/{cert['code']}").status_code == 404  # not public until paid

    reference = checkout(client, paystack, cert)
    sent = paystack.initialized[-1]
    assert sent["amount_kobo"] == 50000 and sent["email"] == client.email
    assert sent["callback_url"].endswith("/certificates/claimed")

    # Back from Paystack without paying: nothing changes.
    assert client.post(f"/api/payments/{reference}/verify").json()["status"] == "awaiting_payment"

    paystack.pay(reference)
    issued = client.post(f"/api/payments/{reference}/verify").json()
    assert issued["status"] == "issued" and issued["issued_at"]
    assert anon.get(f"/api/public/certificates/{cert['code']}").json()["valid"] is True

    # Verifying again is harmless.
    assert client.post(f"/api/payments/{reference}/verify").json()["status"] == "issued"


def test_underpayment_or_wrong_currency_does_not_issue(client, paystack):
    cert = earn(client)
    ref = checkout(client, paystack, cert)
    paystack.pay(ref, amount=100)
    assert client.post(f"/api/payments/{ref}/verify").json()["status"] == "awaiting_payment"

    ref2 = checkout(client, paystack, cert)
    paystack.pay(ref2, currency="USD")
    assert client.post(f"/api/payments/{ref2}/verify").json()["status"] == "awaiting_payment"


def test_cannot_pay_for_or_verify_someone_elses_certificate(make_client, paystack):
    owner, other = make_client(), make_client()
    cert = earn(owner)
    assert other.post(f"/api/certificates/{cert['id']}/pay").status_code == 404
    ref = checkout(owner, paystack, cert)
    assert other.post(f"/api/payments/{ref}/verify").status_code == 404


def test_issued_certificates_cannot_be_paid_for_again(client, paystack):
    cert = earn(client)
    ref = checkout(client, paystack, cert)
    paystack.pay(ref)
    client.post(f"/api/payments/{ref}/verify")
    r = client.post(f"/api/certificates/{cert['id']}/pay")
    assert r.status_code == 400 and "does not need a payment" in r.json()["detail"]


def _signed(body: dict, secret=SECRET):
    raw = json.dumps(body).encode()
    return raw, hmac.new(secret.encode(), raw, hashlib.sha512).hexdigest()


def test_signed_webhook_issues_the_certificate(client, paystack, anon):
    cert = earn(client)
    ref = checkout(client, paystack, cert)
    raw, sig = _signed({"event": "charge.success", "data": {
        "reference": ref, "status": "success", "amount": 50000, "currency": "NGN", "channel": "bank_transfer"}})
    r = anon.post("/api/payments/paystack/webhook", content=raw, headers={"x-paystack-signature": sig})
    assert r.status_code == 200
    assert client.get("/api/certificates").json()[0]["status"] == "issued"


def test_webhook_with_bad_signature_is_rejected(client, paystack, anon):
    cert = earn(client)
    ref = checkout(client, paystack, cert)
    raw, _ = _signed({"event": "charge.success", "data": {"reference": ref, "status": "success", "amount": 50000}})
    _, wrong = _signed({"event": "charge.success"}, secret="sk_test_someone_else")
    for headers in ({}, {"x-paystack-signature": wrong}):
        assert anon.post("/api/payments/paystack/webhook", content=raw, headers=headers).status_code == 401
    assert client.get("/api/certificates").json()[0]["status"] == "awaiting_payment"


def test_flagged_attempt_is_reviewed_before_payment(make_client, paystack, monkeypatch):
    email = f"boss-{uuid.uuid4().hex[:8]}@example.com"
    monkeypatch.setattr(get_settings(), "admin_emails", [email])
    admin = make_client(email)
    user = make_client()
    state = start(user).json()
    report(user, state["id"], {"kind": "multiple_screens"})
    complete(user, state)
    cert = user.get("/api/certificates").json()[0]
    assert cert["status"] == "under_review"
    assert user.post(f"/api/certificates/{cert['id']}/pay").status_code == 400  # can't pay before review

    approved = admin.post(f"/api/admin/certificates/{cert['id']}/review", json={"action": "approve"}).json()
    assert approved["status"] == "awaiting_payment"
    waived = admin.post(f"/api/admin/certificates/{cert['id']}/review", json={"action": "waive", "note": "Scholarship"}).json()
    assert waived["status"] == "issued"

    ov = admin.get("/api/admin/overview").json()
    assert "revenue_kobo" in ov and "certificates_awaiting_payment" in ov
