"""Add sender_email to auto_reply_rules table

Revision ID: abc123
Revises: fbbc9169a9ed
Create Date: 2026-02-12 12:33:00

"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime
from sqlalchemy import orm
from sqlalchemy.ext.declarative import declarative_base

# revision identifiers, used by alembic
revision = 'abc123'
down_revision = 'fbbc9169a9ed'
branch_labels = None
depends_on = None

Base = declarative_base()

def upgrade():
    # Add sender_email column to auto_reply_rules
    with op.batch_alter_table('auto_reply_rules', schema=None) as batch_op:
        batch_op.add_column(sa.Column('sender_email', sa.String(length=255), nullable=True))
    
    # Also add sender_email to auto_reply_templates if not exists
    try:
        with op.batch_alter_table('auto_reply_templates', schema=None) as batch_op:
            batch_op.add_column(sa.Column('sender_email', sa.String(length=255), nullable=True))
    except Exception:
        pass  # Column might already exist

def downgrade():
    with op.batch_alter_table('auto_reply_rules', schema=None) as batch_op:
        batch_op.drop_column('sender_email')
    
    try:
        with op.batch_alter_table('auto_reply_templates', schema=None) as batch_op:
            batch_op.drop_column('sender_email')
    except Exception:
        pass
