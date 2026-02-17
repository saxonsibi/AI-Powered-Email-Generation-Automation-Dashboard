"""Add filter fields to auto_reply_rules table

Revision ID: abc124
Revises: c48c39e1e802
Create Date: 2026-02-12 13:50:00

"""
from alembic import op
import sqlalchemy as sa

revision = 'abc124'
down_revision = 'c48c39e1e802'
branch_labels = None
depends_on = None

def upgrade():
    with op.batch_alter_table('auto_reply_rules', schema=None) as batch_op:
        batch_op.add_column(sa.Column('sender_filter', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('sender_filter_type', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('subject_filter', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('subject_filter_type', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('body_filter', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('body_filter_type', sa.String(length=20), nullable=True))

def downgrade():
    with op.batch_alter_table('auto_reply_rules', schema=None) as batch_op:
        batch_op.drop_column('body_filter_type')
        batch_op.drop_column('body_filter')
        batch_op.drop_column('subject_filter_type')
        batch_op.drop_column('subject_filter')
        batch_op.drop_column('sender_filter_type')
        batch_op.drop_column('sender_filter')
