from __future__ import annotations

from typing import Optional, List
from uuid import UUID

from sqlalchemy import select, func, or_
from sqlalchemy.orm import Session

from app.models import Rule
from app.models.rule import RuleAction


def list_rules(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    search: Optional[str] = None,
    enabled: Optional[bool] = None,
    action: Optional[str] = None,
    sort_by: str = "priority",
    sort_order: str = "asc",
) -> dict:
    # Validate bounds already via API, but ensure deterministic
    if page < 1:
        page = 1
    if page_size < 1 or page_size > 100:
        page_size = 20

    base = select(Rule)
    count_q = select(func.count(Rule.id))

    if search:
        like = f"%{search}%"
        cond = or_(Rule.name.ilike(like), Rule.dsl_expression.ilike(like))
        base = base.where(cond)
        count_q = count_q.where(cond)
    if enabled is not None:
        base = base.where(Rule.enabled == enabled)
        count_q = count_q.where(Rule.enabled == enabled)
    if action:
        # action filter case-insensitive, values allow/review/block
        try:
            act_enum = RuleAction(action.lower())
            base = base.where(Rule.action == act_enum)
            count_q = count_q.where(Rule.action == act_enum)
        except ValueError:
            # invalid action will be handled by API validation, but if reaches here, return empty
            pass

    total = db.execute(count_q).scalar() or 0
    total_pages = (total + page_size - 1) // page_size if total else 0

    # Sorting deterministic: priority asc, then created_at, then id
    # Allowed sort_by: priority, created_at, name, action
    sort_map = {
        "priority": Rule.priority,
        "created_at": Rule.created_at,
        "name": Rule.name,
        "action": Rule.action,
    }
    col = sort_map.get(sort_by, Rule.priority)
    order = col.desc() if sort_order == "desc" else col.asc()
    # secondary deterministic order by id
    base = base.order_by(order, Rule.id.asc()).offset((page - 1) * page_size).limit(page_size)

    rows = db.execute(base).scalars().all()

    items = []
    for r in rows:
        # description: if not in model, derive from name or use None; we use name as fallback description
        # Do not invent
        items.append({
            "id": r.id,
            "name": r.name,
            "description": None,  # existing schema has no description column; expose None transparently
            "enabled": r.enabled,
            "priority": r.priority,
            "action": r.action.value if hasattr(r.action, "value") else str(r.action),
            "condition": r.dsl_expression,
            "dsl_expression": r.dsl_expression,
            "created_at": r.created_at,
            "updated_at": None,  # no updated_at column; expose None
            "version": r.version,
        })

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


def get_rule(db: Session, rule_id: UUID) -> Optional[dict]:
    r = db.execute(select(Rule).where(Rule.id == rule_id)).scalar_one_or_none()
    if not r:
        return None
    return {
        "id": r.id,
        "name": r.name,
        "description": None,
        "enabled": r.enabled,
        "priority": r.priority,
        "action": r.action.value if hasattr(r.action, "value") else str(r.action),
        "condition": r.dsl_expression,
        "dsl_expression": r.dsl_expression,
        "created_at": r.created_at,
        "updated_at": None,
        "version": r.version,
    }
