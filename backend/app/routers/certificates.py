from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import Certificate, User
from app.schemas import CertificateOut
from app.services import certification

router = APIRouter(tags=["certificates"])


@router.get("/api/certificates", response_model=list[CertificateOut])
def my_certificates(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    certs = db.scalars(select(Certificate).where(Certificate.user_id == user.id).order_by(Certificate.created_at.desc()))
    return [CertificateOut(**certification.certificate_out(c)) for c in certs]


@router.get("/api/public/certificates/{code}")
def verify_certificate(code: str, db: Session = Depends(get_db)):
    """Anyone can check a certificate by its code (e.g. an employer)."""
    view = certification.public_view(db, code)
    if view is None:
        raise HTTPException(404, "No certificate with this code exists.")
    return view
