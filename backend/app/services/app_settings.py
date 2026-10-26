"""Business configuration stored in the app_settings table, with documented defaults.

Assumptions about ambiguous business rules live here so administrators can change them
from the Settings page without a redeploy.
"""

from copy import deepcopy
from typing import Any

from sqlalchemy.orm import Session

from app.models import AppSetting

DEFAULTS: dict[str, Any] = {
    "agency": {
        "name": "Mon Agence Immobilière",
        "phone": "",
        "email": "",
        "address": "",
        "default_currency": "MAD",
    },
    "matching": {
        # Statuses a property must have to be proposed as a match.
        "eligible_statuses": ["available"],
        # If true, a property in another neighbourhood of the same city is NOT a match at all.
        # If false (default) it is shown as a partial match with the unmet preference explained.
        "neighborhood_mandatory": False,
        # Over-budget tolerance in %. 0 = any property above budget_max fails the mandatory budget
        # rule. When > 0, slightly over-budget properties are kept but never better than "partial".
        "budget_tolerance_percent": 0,
        # Surface tolerance in % below surface_min (same principle).
        "surface_tolerance_percent": 0,
        "bedrooms_mandatory": True,
        # Minimum category that triggers an agent notification: exact | strong | partial.
        "notify_min_category": "strong",
        "strong_threshold": 75,
        # Score weights (sum of optional criteria = 50; mandatory criteria satisfied = 50).
        "weights": {"neighborhood": 20, "price_fit": 10, "surface_fit": 5, "bathrooms": 5, "preferred_features": 10},
    },
    "deals": {
        # Put an available property "under negotiation" when a deal is opened on it.
        "mark_under_negotiation": True,
        # Close competing open deals as lost when a deal on the same property is won.
        "close_competing_deals": True,
    },
    "reminders": {
        "visit_reminder_hours": 24,
        "overdue_follow_up_enabled": True,
    },
    "public_site": {
        "enabled": True,
        "show_price": True,
    },
}


def get_setting(db: Session, key: str) -> Any:
    row = db.get(AppSetting, key)
    default = deepcopy(DEFAULTS.get(key))
    if row is None:
        return default
    if isinstance(default, dict) and isinstance(row.value, dict):
        merged = default
        for k, v in row.value.items():
            if isinstance(v, dict) and isinstance(merged.get(k), dict):
                merged[k] = {**merged[k], **v}
            else:
                merged[k] = v
        return merged
    return row.value


def set_setting(db: Session, key: str, value: Any, user_id=None) -> None:
    row = db.get(AppSetting, key)
    if row is None:
        db.add(AppSetting(key=key, value=value, updated_by_id=user_id))
    else:
        row.value = value
        row.updated_by_id = user_id
