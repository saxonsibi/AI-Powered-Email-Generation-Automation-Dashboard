"""Add incoming_subject to auto_reply_logs table

Revision ID: abc125
Revises: abc124
Create Date: 2026-02-12 13:30:00

"""
from alembic import op
import sqlalchemy as sa

revision = 'abc125'
down_revision = 'abc124'
branch_labels = None
depends_on = None

def upgrade():
    with op.batch_alter_table('auto_reply_logs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('incoming_subject', sa.String(length=500), nullable=True))

def downgrade():
    with op.batch_alter_table('auto_reply_logs', schema=None) as batch_op:
        batch_op.drop_column('incoming_subject')
