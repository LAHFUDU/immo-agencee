from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CommissionRule


def find_rule(db: Session, transaction_type, property_type: str | None, price: Decimal | None) -> CommissionRule | None:
    rules = db.scalars(
        select(CommissionRule)
        .where(CommissionRule.is_active.is_(True), CommissionRule.transaction_type == transaction_type)
        .order_by(CommissionRule.priority.desc(), CommissionRule.created_at)
    ).all()

    def applies(r: CommissionRule) -> bool:
        if r.property_type and r.property_type != property_type:
            return False
        if price is not None:
            if r.min_price is not None and price < r.min_price:
                return False
            if r.max_price is not None and price > r.max_price:
                return False
        return True

    candidates = [r for r in rules if applies(r)]
    # Highest priority first; among equals prefer the one specific to the property type.
    candidates.sort(key=lambda r: (-r.priority, r.property_type is None))
    return candidates[0] if candidates else None


def compute(rule: CommissionRule | None, price: Decimal | None) -> tuple[Decimal | None, Decimal | None]:
    """Returns (rate_percent, amount). Amount = price * rate% + fixed amount."""
    if rule is None or price is None:
        return (rule.rate_percent if rule else None), None
    amount = (Decimal(price) * rule.rate_percent / Decimal(100) + rule.fixed_amount).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    return rule.rate_percent, amount
