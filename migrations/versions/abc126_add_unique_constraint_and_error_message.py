"""Add unique constraint and error_message to auto_reply_logs

Revision ID: abc126
Revises: abc125
Create Date: 2026-02-12

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'abc126'
down_revision = 'abc125'
branch_labels = None
depends_on = None

def upgrade():
    # Use batch mode for SQLite to support adding constraints
    with op.batch_alter_table('auto_reply_logs', schema=None) as batch_op:
        # Add error_message column
        batch_op.add_column(sa.Column('error_message', sa.Text(), nullable=True))
        # Add unique constraint
        batch_op.create_unique_constraint('unique_rule_gmail', ['rule_id', 'gmail_id'])

def downgrade():
    # Use batch mode for SQLite
    with op.batch_alter_table('auto_reply_logs', schema=None) as batch_op:
        batch_op.drop_constraint('unique_rule_gmail', type_='unique')
        batch_op.drop_column('error_message')
