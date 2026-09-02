"""add alerts table

Revision ID: d4e5f6a7b8c9
Revises: cca7e425ef0a
Create Date: 2026-09-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'a4fc36b9ad5f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enums will be created automatically via table creation; no manual create to avoid duplicate
    op.create_table('alerts',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('transaction_id', sa.UUID(), nullable=True),
        sa.Column('case_id', sa.UUID(), nullable=True),
        sa.Column('rule_id', sa.UUID(), nullable=True),
        sa.Column('alert_type', sa.String(length=100), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('severity', sa.Enum('LOW', 'MEDIUM', 'HIGH', 'CRITICAL', name='alert_severity'), nullable=False),
        sa.Column('risk_score', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('decision', sa.String(length=20), nullable=False),
        sa.Column('status', sa.Enum('OPEN', 'ACKNOWLEDGED', 'IN_PROGRESS', 'RESOLVED', 'DISMISSED', name='alert_status'), nullable=False),
        sa.Column('priority', sa.Integer(), nullable=False),
        sa.Column('assigned_to', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('resolution_reason', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['case_id'], ['cases.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['rule_id'], ['rules.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['transaction_id'], ['transactions.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_alerts_alert_type', 'alerts', ['alert_type'], unique=False)
    op.create_index('ix_alerts_assigned_to', 'alerts', ['assigned_to'], unique=False)
    op.create_index('ix_alerts_case_id', 'alerts', ['case_id'], unique=False)
    op.create_index('ix_alerts_created_at', 'alerts', ['created_at'], unique=False)
    op.create_index('ix_alerts_priority', 'alerts', ['priority'], unique=False)
    op.create_index('ix_alerts_severity', 'alerts', ['severity'], unique=False)
    op.create_index('ix_alerts_status', 'alerts', ['status'], unique=False)
    op.create_index('ix_alerts_transaction_id', 'alerts', ['transaction_id'], unique=False)
    # Deduplication index: transaction + rule + alert_type for open alerts (partial unique)
    op.create_index('ix_alerts_dedup', 'alerts', ['transaction_id', 'rule_id', 'alert_type'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_alerts_dedup', table_name='alerts')
    op.drop_index('ix_alerts_transaction_id', table_name='alerts')
    op.drop_index('ix_alerts_status', table_name='alerts')
    op.drop_index('ix_alerts_severity', table_name='alerts')
    op.drop_index('ix_alerts_priority', table_name='alerts')
    op.drop_index('ix_alerts_created_at', table_name='alerts')
    op.drop_index('ix_alerts_case_id', table_name='alerts')
    op.drop_index('ix_alerts_assigned_to', table_name='alerts')
    op.drop_index('ix_alerts_alert_type', table_name='alerts')
    op.drop_table('alerts')
    # Drop enums
    sa.Enum(name='alert_status').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='alert_severity').drop(op.get_bind(), checkfirst=True)
