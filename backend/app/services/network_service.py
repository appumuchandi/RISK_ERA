from __future__ import annotations

from collections import defaultdict, Counter
from decimal import Decimal
from typing import Dict, List, Optional, Set, Tuple
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Customer, Merchant, Device, Transaction, Case, Rule
from app.models.transaction import TransactionStatus
from app.schemas.transaction import TransactionAction
from app.services.rule_engine import RuleEngine, Rule as RuleEngineRule


def _get_enabled_rules(db: Session) -> list[RuleEngineRule]:
    from app.models import Rule
    rows = db.execute(select(Rule).where(Rule.enabled).order_by(Rule.priority)).scalars().all()
    return [
        RuleEngineRule(
            id=r.id,
            name=r.name,
            dsl_expression=r.dsl_expression,
            action=TransactionAction(r.action.value),
            priority=r.priority,
            enabled=r.enabled,
            version=r.version,
        )
        for r in rows
    ]


def _risk_level_from_score(score: float) -> str:
    if score >= 85:
        return "critical"
    if score >= 60:
        return "high"
    if score >= 25:
        return "medium"
    return "low"


def _compute_txn_risk(txn: Transaction, engine: RuleEngine) -> Tuple[float, str]:
    customer = txn.customer
    merchant = txn.merchant
    device = txn.device
    data = {
        "amount": txn.amount,
        "currency": txn.currency,
        "customer_risk_tier": customer.risk_tier if customer else "standard",
        "customer_kyc_status": customer.kyc_status if customer else "pending",
        "device_risk_score": float(device.risk_score) if device and device.risk_score is not None else None,
        "merchant_category_code": merchant.category_code if merchant else "",
        "merchant_risk_level": merchant.risk_level if merchant else "standard",
    }
    result = engine.evaluate(data)
    score = float(result.risk_score) if result.risk_score is not None else 0.0
    level = _risk_level_from_score(score)
    return score, level


class NetworkService:
    ALLOWED_TYPES = {"customer", "merchant", "device", "transaction", "case"}
    MAX_HOPS = 3

    def __init__(self, db: Session):
        self.db = db
        self._engine: Optional[RuleEngine] = None

    def _get_engine(self) -> RuleEngine:
        if self._engine is None:
            self._engine = RuleEngine(_get_enabled_rules(self.db))
        return self._engine

    def get_graph(self, entity_type: str, entity_id: UUID, hops: int = 2) -> dict | None:
        # validate entity exists and build root
        if entity_type not in self.ALLOWED_TYPES:
            return None  # caller will handle 422
        if hops < 1 or hops > self.MAX_HOPS:
            return None

        # Fetch root entity
        root_node = self._fetch_root_node(entity_type, entity_id)
        if root_node is None:
            return None  # 404

        # BFS structures
        # nodes: key -> node dict
        # edges: key -> edge dict
        # hop_map: key -> hop
        nodes: Dict[str, dict] = {}
        edges: Dict[str, dict] = {}
        hop_map: Dict[str, int] = {}

        def node_key(ntype: str, nid: str) -> str:
            return f"{ntype}:{nid}"

        root_key = node_key(entity_type, str(entity_id))
        nodes[root_key] = root_node
        hop_map[root_key] = 0

        frontier: Set[str] = {root_key}

        # Keep transaction risk cache to avoid recompute
        txn_risk_cache: Dict[str, Tuple[float, str]] = {}

        engine = self._get_engine()

        # For batch risk computation for transaction nodes, we will compute as we fetch
        # For non-transaction nodes, we will compute after BFS via batch averages

        current_hop = 0
        while frontier and current_hop < hops:
            next_frontier: Set[str] = set()
            # Group frontier by type
            by_type: Dict[str, List[str]] = defaultdict(list)
            for key in frontier:
                t, nid = key.split(":", 1)
                by_type[t].append(nid)

            # Collect neighbors to add
            # We will batch fetch per type
            # For customer frontier: fetch transactions
            # For merchant frontier: fetch transactions
            # For device frontier: fetch transactions
            # For transaction frontier: fetch customers, merchants, devices, cases
            # For case frontier: fetch transactions

            # Helper to add node if not exists
            def add_node(ntype: str, nid: str, label: str, risk_score: Optional[float], risk_level: str, hop: int):
                key = node_key(ntype, nid)
                if key not in nodes:
                    nodes[key] = {
                        "id": nid,
                        "type": ntype,
                        "label": label,
                        "risk_score": risk_score,
                        "risk_level": risk_level,
                        "hop": hop,
                    }
                    hop_map[key] = hop
                    next_frontier.add(key)
                    return True
                return False

            # Helper to add edge with dedup (undirected via sorted ids + relationship)
            def add_edge(source_id: str, target_id: str, relationship: str, label: str, supporting_txn: Optional[str] = None, supporting_case: Optional[str] = None):
                # Dedup key: sorted ids + relationship
                sorted_ids = tuple(sorted([source_id, target_id]))
                edge_key = f"{sorted_ids[0]}|{sorted_ids[1]}|{relationship}"
                if edge_key in edges:
                    return
                # Also check directed duplicate? sorted handles
                edges[edge_key] = {
                    "source": source_id,
                    "target": target_id,
                    "relationship": relationship,
                    "label": label,
                    "supporting_transaction_ids": [supporting_txn] if supporting_txn else [],
                    "supporting_case_ids": [supporting_case] if supporting_case else [],
                }

            # --- Expand customers ---
            if by_type.get("customer"):
                cust_ids = [UUID(cid) for cid in by_type["customer"]]
                # Batch fetch transactions for these customers, with limit per customer to bound graph
                # Fetch all where customer_id IN, with selectinload
                txns = self.db.execute(
                    select(Transaction)
                    .where(Transaction.customer_id.in_(cust_ids))
                    .options(selectinload(Transaction.customer), selectinload(Transaction.merchant), selectinload(Transaction.device), selectinload(Transaction.case))
                    .order_by(Transaction.created_at.desc())
                ).scalars().all()
                # Group by customer and limit 20 per customer
                grouped: Dict[UUID, List[Transaction]] = defaultdict(list)
                for t in txns:
                    grouped[t.customer_id].append(t)
                for cust_id in cust_ids:
                    cust_key = node_key("customer", str(cust_id))
                    # limit to 20 most recent per customer
                    per_cust_txns = grouped.get(cust_id, [])[:20]
                    for txn in per_cust_txns:
                        txn_id_str = str(txn.id)
                        # compute risk for transaction if not cached
                        if txn_id_str not in txn_risk_cache:
                            score, level = _compute_txn_risk(txn, engine)
                            txn_risk_cache[txn_id_str] = (score, level)
                        else:
                            score, level = txn_risk_cache[txn_id_str]
                        label = txn.provider_event_id[:16] if txn.provider_event_id else str(txn.id)[:8]
                        added = add_node("transaction", txn_id_str, label, round(score, 2), level, current_hop + 1)
                        # edge customer -> transaction
                        # find supporting case if exists
                        case_id = str(txn.case.id) if txn.case else None
                        add_edge(str(cust_id), txn_id_str, "customer_transaction", "Customer placed Transaction", supporting_txn=txn_id_str, supporting_case=case_id)

            # --- Expand merchants ---
            if by_type.get("merchant"):
                merch_ids = [UUID(mid) for mid in by_type["merchant"]]
                txns = self.db.execute(
                    select(Transaction)
                    .where(Transaction.merchant_id.in_(merch_ids))
                    .options(selectinload(Transaction.customer), selectinload(Transaction.merchant), selectinload(Transaction.device), selectinload(Transaction.case))
                    .order_by(Transaction.created_at.desc())
                ).scalars().all()
                grouped = defaultdict(list)
                for t in txns:
                    grouped[t.merchant_id].append(t)
                for merch_id in merch_ids:
                    per_merch_txns = grouped.get(merch_id, [])[:20]
                    for txn in per_merch_txns:
                        txn_id_str = str(txn.id)
                        if txn_id_str not in txn_risk_cache:
                            score, level = _compute_txn_risk(txn, engine)
                            txn_risk_cache[txn_id_str] = (score, level)
                        else:
                            score, level = txn_risk_cache[txn_id_str]
                        label = txn.provider_event_id[:16] if txn.provider_event_id else str(txn.id)[:8]
                        add_node("transaction", txn_id_str, label, round(score, 2), level, current_hop + 1)
                        case_id = str(txn.case.id) if txn.case else None
                        add_edge(str(merch_id), txn_id_str, "merchant_transaction", "Merchant involved in Transaction", supporting_txn=txn_id_str, supporting_case=case_id)

            # --- Expand devices ---
            if by_type.get("device"):
                # filter valid UUIDs
                dev_ids = []
                for did in by_type["device"]:
                    try:
                        dev_ids.append(UUID(did))
                    except:
                        continue
                if dev_ids:
                    txns = self.db.execute(
                        select(Transaction)
                        .where(Transaction.device_id.in_(dev_ids))
                        .options(selectinload(Transaction.customer), selectinload(Transaction.merchant), selectinload(Transaction.device), selectinload(Transaction.case))
                        .order_by(Transaction.created_at.desc())
                    ).scalars().all()
                    grouped = defaultdict(list)
                    for t in txns:
                        if t.device_id:
                            grouped[t.device_id].append(t)
                    for dev_id in dev_ids:
                        per_dev_txns = grouped.get(dev_id, [])[:20]
                        for txn in per_dev_txns:
                            txn_id_str = str(txn.id)
                            if txn_id_str not in txn_risk_cache:
                                score, level = _compute_txn_risk(txn, engine)
                                txn_risk_cache[txn_id_str] = (score, level)
                            else:
                                score, level = txn_risk_cache[txn_id_str]
                            label = txn.provider_event_id[:16] if txn.provider_event_id else str(txn.id)[:8]
                            add_node("transaction", txn_id_str, label, round(score, 2), level, current_hop + 1)
                            case_id = str(txn.case.id) if txn.case else None
                            add_edge(str(dev_id), txn_id_str, "device_transaction", "Device observed in Transaction", supporting_txn=txn_id_str, supporting_case=case_id)

            # --- Expand transactions ---
            if by_type.get("transaction"):
                txn_ids = [UUID(tid) for tid in by_type["transaction"]]
                # Fetch those transaction objects with relationships (we already have some cached, but fetch to get related entities)
                # Instead of refetching, we can use already fetched txns from previous steps? But for transaction frontier that came from previous level, we have transaction objects but not necessarily all have selectinload? We did have selectinload when fetching. So we have them. However for transaction root, we need to fetch it.
                # To simplify, fetch transactions for this frontier with selectinload
                txns = self.db.execute(
                    select(Transaction)
                    .where(Transaction.id.in_(txn_ids))
                    .options(selectinload(Transaction.customer), selectinload(Transaction.merchant), selectinload(Transaction.device), selectinload(Transaction.case))
                ).scalars().all()
                # Also fetch cases for these transactions batch
                case_map: Dict[UUID, Case] = {}
                if txn_ids:
                    cases = self.db.execute(select(Case).where(Case.transaction_id.in_(txn_ids))).scalars().all()
                    case_map = {c.transaction_id: c for c in cases}
                # For each txn, create neighbor nodes
                for txn in txns:
                    txn_id_str = str(txn.id)
                    # Customer
                    if txn.customer_id:
                        cust_id_str = str(txn.customer_id)
                        # Need customer label: fetch if not already? Use relationship
                        cust_label = txn.customer.external_id if txn.customer else cust_id_str[:8]
                        # risk for customer will be computed later, but set placeholder low
                        add_node("customer", cust_id_str, cust_label, 0.0, "low", current_hop + 1)
                        case_id = str(case_map[txn.id].id) if txn.id in case_map else (str(txn.case.id) if txn.case else None)
                        add_edge(txn_id_str, cust_id_str, "customer_transaction", "Transaction belongs to Customer", supporting_txn=txn_id_str, supporting_case=case_id)
                    # Merchant
                    if txn.merchant_id:
                        merch_id_str = str(txn.merchant_id)
                        merch_label = txn.merchant.name if txn.merchant else merch_id_str[:8]
                        add_node("merchant", merch_id_str, merch_label, 0.0, "low", current_hop + 1)
                        case_id = str(case_map[txn.id].id) if txn.id in case_map else (str(txn.case.id) if txn.case else None)
                        add_edge(txn_id_str, merch_id_str, "merchant_transaction", "Transaction at Merchant", supporting_txn=txn_id_str, supporting_case=case_id)
                    # Device
                    if txn.device_id:
                        dev_id_str = str(txn.device_id)
                        dev_label = txn.device.fingerprint_hash[:12] + "…" if txn.device and txn.device.fingerprint_hash else dev_id_str[:8]
                        add_node("device", dev_id_str, dev_label, 0.0, "low", current_hop + 1)
                        case_id = str(case_map[txn.id].id) if txn.id in case_map else (str(txn.case.id) if txn.case else None)
                        add_edge(txn_id_str, dev_id_str, "device_transaction", "Transaction via Device", supporting_txn=txn_id_str, supporting_case=case_id)
                    # Case
                    case_obj = case_map.get(txn.id) or txn.case
                    if case_obj:
                        case_id_str = str(case_obj.id)
                        case_label = f"Case {case_id_str[:8]}"
                        add_node("case", case_id_str, case_label, 0.0, "low", current_hop + 1)
                        add_edge(txn_id_str, case_id_str, "case_transaction", "Transaction linked to Case", supporting_txn=txn_id_str, supporting_case=case_id_str)

            # --- Expand cases ---
            if by_type.get("case"):
                case_ids = [UUID(cid) for cid in by_type["case"]]
                cases = self.db.execute(select(Case).where(Case.id.in_(case_ids))).scalars().all()
                # For each case, fetch its transaction
                txn_ids_for_cases = [c.transaction_id for c in cases]
                if txn_ids_for_cases:
                    txns = self.db.execute(
                        select(Transaction)
                        .where(Transaction.id.in_(txn_ids_for_cases))
                        .options(selectinload(Transaction.customer), selectinload(Transaction.merchant), selectinload(Transaction.device), selectinload(Transaction.case))
                    ).scalars().all()
                    txn_by_id = {t.id: t for t in txns}
                    for case in cases:
                        txn = txn_by_id.get(case.transaction_id)
                        if txn:
                            txn_id_str = str(txn.id)
                            if txn_id_str not in txn_risk_cache:
                                score, level = _compute_txn_risk(txn, engine)
                                txn_risk_cache[txn_id_str] = (score, level)
                            else:
                                score, level = txn_risk_cache[txn_id_str]
                            label = txn.provider_event_id[:16] if txn.provider_event_id else str(txn.id)[:8]
                            add_node("transaction", txn_id_str, label, round(score, 2), level, current_hop + 1)
                            add_edge(str(case.id), txn_id_str, "case_transaction", "Case linked to Transaction", supporting_txn=txn_id_str, supporting_case=str(case.id))

            frontier = next_frontier
            current_hop += 1

        # After BFS, compute risks for non-transaction nodes via batch
        # Collect ids by type
        cust_ids = [UUID(n["id"]) for n in nodes.values() if n["type"] == "customer"]
        merch_ids = [UUID(n["id"]) for n in nodes.values() if n["type"] == "merchant"]
        dev_ids = [UUID(n["id"]) for n in nodes.values() if n["type"] == "device"]
        case_ids = [UUID(n["id"]) for n in nodes.values() if n["type"] == "case"]

        # For customers, fetch all transactions for those customers and compute average risk
        if cust_ids:
            txns = self.db.execute(
                select(Transaction)
                .where(Transaction.customer_id.in_(cust_ids))
                .options(selectinload(Transaction.customer), selectinload(Transaction.merchant), selectinload(Transaction.device))
            ).scalars().all()
            # group
            by_cust: Dict[UUID, List[Transaction]] = defaultdict(list)
            for t in txns:
                by_cust[t.customer_id].append(t)
            for cust_id in cust_ids:
                key = f"customer:{str(cust_id)}"
                node = nodes.get(key)
                if node is None:
                    continue
                c_txns = by_cust.get(cust_id, [])
                if not c_txns:
                    node["risk_score"] = 0.0
                    node["risk_level"] = "low"
                else:
                    scores = []
                    for t in c_txns:
                        # Use cached if available else compute
                        tid = str(t.id)
                        if tid in txn_risk_cache:
                            s, _ = txn_risk_cache[tid]
                        else:
                            s, _ = _compute_txn_risk(t, engine)
                        scores.append(s)
                    avg = sum(scores) / len(scores) if scores else 0.0
                    mx = max(scores) if scores else 0.0
                    # For node risk, use average
                    node["risk_score"] = round(avg, 2)
                    node["risk_level"] = _risk_level_from_score(avg)
                    # could also store max but not needed

        if merch_ids:
            txns = self.db.execute(
                select(Transaction)
                .where(Transaction.merchant_id.in_(merch_ids))
                .options(selectinload(Transaction.customer), selectinload(Transaction.merchant), selectinload(Transaction.device))
            ).scalars().all()
            by_merch: Dict[UUID, List[Transaction]] = defaultdict(list)
            for t in txns:
                by_merch[t.merchant_id].append(t)
            for merch_id in merch_ids:
                key = f"merchant:{str(merch_id)}"
                node = nodes.get(key)
                if node is None:
                    continue
                m_txns = by_merch.get(merch_id, [])
                if not m_txns:
                    node["risk_score"] = 0.0
                    node["risk_level"] = "low"
                else:
                    scores = []
                    for t in m_txns:
                        tid = str(t.id)
                        if tid in txn_risk_cache:
                            s, _ = txn_risk_cache[tid]
                        else:
                            s, _ = _compute_txn_risk(t, engine)
                        scores.append(s)
                    avg = sum(scores) / len(scores)
                    node["risk_score"] = round(avg, 2)
                    node["risk_level"] = _risk_level_from_score(avg)

        if dev_ids:
            txns = self.db.execute(
                select(Transaction)
                .where(Transaction.device_id.in_(dev_ids))
                .options(selectinload(Transaction.customer), selectinload(Transaction.merchant), selectinload(Transaction.device))
            ).scalars().all()
            by_dev: Dict[UUID, List[Transaction]] = defaultdict(list)
            for t in txns:
                if t.device_id:
                    by_dev[t.device_id].append(t)
            for dev_id in dev_ids:
                key = f"device:{str(dev_id)}"
                node = nodes.get(key)
                if node is None:
                    continue
                d_txns = by_dev.get(dev_id, [])
                if not d_txns:
                    node["risk_score"] = 0.0
                    node["risk_level"] = "low"
                else:
                    scores = []
                    for t in d_txns:
                        tid = str(t.id)
                        if tid in txn_risk_cache:
                            s, _ = txn_risk_cache[tid]
                        else:
                            s, _ = _compute_txn_risk(t, engine)
                        scores.append(s)
                    avg = sum(scores) / len(scores)
                    node["risk_score"] = round(avg, 2)
                    node["risk_level"] = _risk_level_from_score(avg)

        if case_ids:
            # For case nodes, risk from its transaction
            cases = self.db.execute(select(Case).where(Case.id.in_(case_ids))).scalars().all()
            txn_ids_for_cases = [c.transaction_id for c in cases]
            if txn_ids_for_cases:
                txns = self.db.execute(
                    select(Transaction)
                    .where(Transaction.id.in_(txn_ids_for_cases))
                    .options(selectinload(Transaction.customer), selectinload(Transaction.merchant), selectinload(Transaction.device))
                ).scalars().all()
                txn_map = {t.id: t for t in txns}
                for case in cases:
                    key = f"case:{str(case.id)}"
                    node = nodes.get(key)
                    if node is None:
                        continue
                    txn = txn_map.get(case.transaction_id)
                    if txn:
                        tid = str(txn.id)
                        if tid in txn_risk_cache:
                            s, lvl = txn_risk_cache[tid]
                        else:
                            s, lvl = _compute_txn_risk(txn, engine)
                            txn_risk_cache[tid] = (s, lvl)
                        node["risk_score"] = round(s, 2)
                        node["risk_level"] = lvl
                    else:
                        node["risk_score"] = 0.0
                        node["risk_level"] = "low"

        # Ensure root risk is accurate (already computed via batch above for its type, but if root is transaction, already cached)
        # If root is transaction, its risk already in cache; ensure node has it
        if entity_type == "transaction":
            root_txn_id = str(entity_id)
            if root_txn_id in txn_risk_cache:
                s, lvl = txn_risk_cache[root_txn_id]
                nodes[root_key]["risk_score"] = round(s, 2)
                nodes[root_key]["risk_level"] = lvl

        # Build stats
        counts = Counter(n["type"] for n in nodes.values())
        stats = {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "customer_count": counts.get("customer", 0),
            "merchant_count": counts.get("merchant", 0),
            "device_count": counts.get("device", 0),
            "transaction_count": counts.get("transaction", 0),
            "case_count": counts.get("case", 0),
            "max_hop": max(hop_map.values()) if hop_map else 0,
        }

        # Deterministic ordering
        sorted_nodes = sorted(nodes.values(), key=lambda n: (n["type"], n["id"]))
        sorted_edges = sorted(edges.values(), key=lambda e: (e["source"], e["target"], e["relationship"]))

        root = nodes[root_key]

        return {
            "root": root,
            "nodes": sorted_nodes,
            "edges": sorted_edges,
            "stats": stats,
        }

    def _fetch_root_node(self, entity_type: str, entity_id: UUID) -> Optional[dict]:
        engine = self._get_engine()
        if entity_type == "customer":
            cust = self.db.execute(select(Customer).where(Customer.id == entity_id)).scalar_one_or_none()
            if not cust:
                return None
            # Compute risk for customer via its transactions (average)
            txns = self.db.execute(
                select(Transaction)
                .where(Transaction.customer_id == entity_id)
                .options(selectinload(Transaction.customer), selectinload(Transaction.merchant), selectinload(Transaction.device))
            ).scalars().all()
            if txns:
                scores = [_compute_txn_risk(t, engine)[0] for t in txns]
                avg = sum(scores) / len(scores)
                level = _risk_level_from_score(avg)
                score = round(avg, 2)
            else:
                score = 0.0
                level = "low"
            return {
                "id": str(cust.id),
                "type": "customer",
                "label": cust.external_id,
                "risk_score": score,
                "risk_level": level,
                "hop": 0,
                "external_id": cust.external_id,
            }
        elif entity_type == "merchant":
            merch = self.db.execute(select(Merchant).where(Merchant.id == entity_id)).scalar_one_or_none()
            if not merch:
                return None
            txns = self.db.execute(
                select(Transaction)
                .where(Transaction.merchant_id == entity_id)
                .options(selectinload(Transaction.customer), selectinload(Transaction.merchant), selectinload(Transaction.device))
            ).scalars().all()
            if txns:
                scores = [_compute_txn_risk(t, engine)[0] for t in txns]
                avg = sum(scores) / len(scores)
                level = _risk_level_from_score(avg)
                score = round(avg, 2)
            else:
                score = 0.0
                level = "low"
            return {
                "id": str(merch.id),
                "type": "merchant",
                "label": merch.name,
                "risk_score": score,
                "risk_level": level,
                "hop": 0,
            }
        elif entity_type == "device":
            dev = self.db.execute(select(Device).where(Device.id == entity_id)).scalar_one_or_none()
            if not dev:
                return None
            txns = self.db.execute(
                select(Transaction)
                .where(Transaction.device_id == entity_id)
                .options(selectinload(Transaction.customer), selectinload(Transaction.merchant), selectinload(Transaction.device))
            ).scalars().all()
            if txns:
                scores = [_compute_txn_risk(t, engine)[0] for t in txns]
                avg = sum(scores) / len(scores)
                level = _risk_level_from_score(avg)
                score = round(avg, 2)
            else:
                score = 0.0
                level = "low"
            label = dev.fingerprint_hash[:12] + "…" if dev.fingerprint_hash else str(dev.id)[:8]
            return {
                "id": str(dev.id),
                "type": "device",
                "label": label,
                "risk_score": score,
                "risk_level": level,
                "hop": 0,
            }
        elif entity_type == "transaction":
            txn = self.db.execute(
                select(Transaction)
                .where(Transaction.id == entity_id)
                .options(selectinload(Transaction.customer), selectinload(Transaction.merchant), selectinload(Transaction.device), selectinload(Transaction.case))
            ).scalar_one_or_none()
            if not txn:
                return None
            score, level = _compute_txn_risk(txn, engine)
            return {
                "id": str(txn.id),
                "type": "transaction",
                "label": txn.provider_event_id[:16] if txn.provider_event_id else str(txn.id)[:8],
                "risk_score": round(score, 2),
                "risk_level": level,
                "hop": 0,
                "provider_event_id": txn.provider_event_id,
            }
        elif entity_type == "case":
            case = self.db.execute(select(Case).where(Case.id == entity_id)).scalar_one_or_none()
            if not case:
                return None
            # Get its transaction for risk
            txn = self.db.execute(
                select(Transaction)
                .where(Transaction.id == case.transaction_id)
                .options(selectinload(Transaction.customer), selectinload(Transaction.merchant), selectinload(Transaction.device))
            ).scalar_one_or_none()
            if txn:
                score, level = _compute_txn_risk(txn, engine)
            else:
                score = 0.0
                level = "low"
            return {
                "id": str(case.id),
                "type": "case",
                "label": f"Case {str(case.id)[:8]}",
                "risk_score": round(score, 2),
                "risk_level": level,
                "hop": 0,
            }
        return None
