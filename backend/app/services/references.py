from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.models.crm import customer_ref_seq, request_ref_seq
from app.models.deals import deal_ref_seq
from app.models.property import property_ref_seq

_SEQS = {"CLI": customer_ref_seq, "DEM": request_ref_seq, "BIEN": property_ref_seq, "TRX": deal_ref_seq}


def next_reference(db: Session, prefix: str) -> str:
    """Human-friendly unique reference, e.g. DEM-2026-00042 (backed by a PostgreSQL sequence)."""
    n = db.execute(_SEQS[prefix].next_value()).scalar_one()
    return f"{prefix}-{utcnow().year}-{n:05d}"
