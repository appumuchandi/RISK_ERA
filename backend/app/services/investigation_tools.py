from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.models import Transaction, Customer, Device, Merchant
from app.schemas.investigation import (
    TransactionHistoryRequest,
    TransactionHistoryResponse,
    TransactionSummary,
    CustomerProfileRequest,
    CustomerProfileResponse,
    DeviceActivityRequest,
    DeviceActivityResponse,
    ToolResult,
)


class InvestigationTools:
    """Investigation tools with data minimization and validation."""

    def __init__(self, db: Session):
        self.db = db

    # --- Tool 1: get_transaction_history ---
    def get_transaction_history(self, request: TransactionHistoryRequest) -> ToolResult:
        """Get sanitized transaction history for a customer."""
        try:
            # Validate customer exists
            customer = self.db.execute(
                select(Customer).where(Customer.id == request.customer_id)
            ).scalar_one_or_none()
            if not customer:
                return ToolResult(
                    tool_name="get_transaction_history",
                    success=False,
                    error=f"Customer {request.customer_id} not found",
                )

            # Build query with limits
            stmt = (
                select(Transaction, Merchant.name, Merchant.category_code)
                .join(Merchant, Transaction.merchant_id == Merchant.id)
                .where(Transaction.customer_id == request.customer_id)
            )

            if request.date_from:
                stmt = stmt.where(Transaction.created_at >= request.date_from)
            if request.date_to:
                stmt = stmt.where(Transaction.created_at <= request.date_to)

            stmt = stmt.order_by(Transaction.created_at.desc()).limit(request.limit)

            results = self.db.execute(stmt).all()

            transactions = [
                TransactionSummary(
                    transaction_id=txn.id,
                    provider_event_id=txn.provider_event_id,
                    amount=txn.amount,
                    currency=txn.currency,
                    status=txn.status.value,
                    merchant_name=merchant_name,
                    merchant_category_code=merchant_category_code,
                    created_at=txn.created_at,
                )
                for txn, merchant_name, merchant_category_code in results
            ]

            return ToolResult(
                tool_name="get_transaction_history",
                success=True,
                data=TransactionHistoryResponse(
                    customer_id=request.customer_id,
                    transactions=transactions,
                    total_count=len(transactions),
                ).model_dump(),
            )

        except Exception as e:
            return ToolResult(
                tool_name="get_transaction_history",
                success=False,
                error=f"Internal error: {str(e)}",
            )

    # --- Tool 2: get_customer_profile ---
    def get_customer_profile(self, request: CustomerProfileRequest) -> ToolResult:
        """Get sanitized customer profile with aggregated metrics."""
        try:
            customer = self.db.execute(
                select(Customer).where(Customer.id == request.customer_id)
            ).scalar_one_or_none()
            if not customer:
                return ToolResult(
                    tool_name="get_customer_profile",
                    success=False,
                    error=f"Customer {request.customer_id} not found",
                )

            # Aggregate transaction metrics
            txn_stats = self.db.execute(
                select(
                    func.count(Transaction.id),
                    func.sum(Transaction.amount),
                    func.avg(Transaction.amount),
                ).where(Transaction.customer_id == request.customer_id)
            ).one()

            txn_count, total_amount, avg_amount = txn_stats
            txn_count = txn_count or 0
            total_amount = total_amount or Decimal("0")
            avg_amount = avg_amount or Decimal("0")

            # Count unique devices
            unique_devices = self.db.execute(
                select(func.count(func.distinct(Transaction.device_id))).where(
                    Transaction.customer_id == request.customer_id,
                    Transaction.device_id.is_not(None),
                )
            ).scalar() or 0

            # Count unique merchants
            unique_merchants = self.db.execute(
                select(func.count(func.distinct(Transaction.merchant_id))).where(
                    Transaction.customer_id == request.customer_id
                )
            ).scalar() or 0

            return ToolResult(
                tool_name="get_customer_profile",
                success=True,
                data=CustomerProfileResponse(
                    customer_id=customer.id,
                    external_id=customer.external_id,
                    risk_tier=customer.risk_tier,
                    kyc_status=customer.kyc_status,
                    created_at=customer.created_at,
                    transaction_count=txn_count,
                    total_amount=total_amount,
                    average_amount=avg_amount,
                    unique_devices=unique_devices,
                    unique_merchants=unique_merchants,
                ).model_dump(),
            )

        except Exception as e:
            return ToolResult(
                tool_name="get_customer_profile",
                success=False,
                error=f"Internal error: {str(e)}",
            )

    # --- Tool 3: get_device_activity ---
    def get_device_activity(self, request: DeviceActivityRequest) -> ToolResult:
        """Get sanitized device activity with transaction metrics."""
        try:
            device = self.db.execute(
                select(Device).where(Device.id == request.device_id)
            ).scalar_one_or_none()
            if not device:
                return ToolResult(
                    tool_name="get_device_activity",
                    success=False,
                    error=f"Device {request.device_id} not found",
                )

            # Build query with date range
            stmt = select(Transaction).where(Transaction.device_id == request.device_id)

            if request.date_from:
                stmt = stmt.where(Transaction.created_at >= request.date_from)
            if request.date_to:
                stmt = stmt.where(Transaction.created_at <= request.date_to)

            transactions = self.db.execute(stmt).scalars().all()

            txn_count = len(transactions)
            total_amount = sum((t.amount for t in transactions), Decimal("0"))

            # Unique customers
            unique_customers = len({t.customer_id for t in transactions})
            unique_merchants = len({t.merchant_id for t in transactions})

            # First and last seen
            sorted_txns = sorted(transactions, key=lambda t: t.created_at)
            first_seen = sorted_txns[0].created_at if sorted_txns else None
            last_seen = sorted_txns[-1].created_at if sorted_txns else None

            return ToolResult(
                tool_name="get_device_activity",
                success=True,
                data=DeviceActivityResponse(
                    device_id=device.id,
                    fingerprint_hash=device.fingerprint_hash,
                    ip=device.ip,
                    user_agent=device.user_agent,
                    risk_score=float(device.risk_score) if device.risk_score else None,
                    transaction_count=txn_count,
                    total_amount=total_amount,
                    unique_customers=unique_customers,
                    unique_merchants=unique_merchants,
                    first_seen=first_seen,
                    last_seen=last_seen,
                ).model_dump(),
            )

        except Exception as e:
            return ToolResult(
                tool_name="get_device_activity",
                success=False,
                error=f"Internal error: {str(e)}",
            )