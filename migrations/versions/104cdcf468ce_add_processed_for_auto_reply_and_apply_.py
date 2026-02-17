"""Add processed_for_auto_reply and apply_to_existing_emails fields

Revision ID: 104cdcf468ce
Revises: c7beaa7a4f98
Create Date: 2023-11-15 10:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision = '104cdcf468ce'
down_revision = 'c7beaa7a4f98'
branch_labels = None
depends_on = None


def upgrade():
    # Check if columns already exist before adding them
    conn = op.get_bind()
    
    # Check if processed_for_auto_reply exists in emails table
    result = conn.execute(text("PRAGMA table_info(emails)"))
    email_columns = [row[1] for row in result]
    
    if 'processed_for_auto_reply' not in email_columns:
        op.add_column('emails', sa.Column('processed_for_auto_reply', sa.Boolean(), nullable=True))
        op.execute("UPDATE emails SET processed_for_auto_reply = 0 WHERE processed_for_auto_reply IS NULL")
        with op.batch_alter_table('emails', schema=None) as batch_op:
            batch_op.alter_column('processed_for_auto_reply', existing_type=sa.Boolean(), nullable=False)
        print("Added processed_for_auto_reply column to emails table")
    else:
        print("processed_for_auto_reply column already exists in emails table")
    
    # Check if apply_to_existing_emails exists in auto_reply_rules table
    result = conn.execute(text("PRAGMA table_info(auto_reply_rules)"))
    rule_columns = [row[1] for row in result]
    
    if 'apply_to_existing_emails' not in rule_columns:
        op.add_column('auto_reply_rules', sa.Column('apply_to_existing_emails', sa.Boolean(), nullable=True))
        op.execute("UPDATE auto_reply_rules SET apply_to_existing_emails = 0 WHERE apply_to_existing_emails IS NULL")
        with op.batch_alter_table('auto_reply_rules', schema=None) as batch_op:
            batch_op.alter_column('apply_to_existing_emails', existing_type=sa.Boolean(), nullable=False)
        print("Added apply_to_existing_emails column to auto_reply_rules table")
    else:
        print("apply_to_existing_emails column already exists in auto_reply_rules table")


def downgrade():
    # Only remove columns if they exist
    conn = op.get_bind()
    
    # Check if processed_for_auto_reply exists in emails table
    result = conn.execute(text("PRAGMA table_info(emails)"))
    email_columns = [row[1] for row in result]
    
    if 'processed_for_auto_reply' in email_columns:
        with op.batch_alter_table('emails', schema=None) as batch_op:
            batch_op.drop_column('processed_for_auto_reply')
        print("Removed processed_for_auto_reply column from emails table")
    
    # Check if apply_to_existing_emails exists in auto_reply_rules table
    result = conn.execute(text("PRAGMA table_info(auto_reply_rules)"))
    rule_columns = [row[1] for row in result]
    
    if 'apply_to_existing_emails' in rule_columns:
        with op.batch_alter_table('auto_reply_rules', schema=None) as batch_op:
            batch_op.drop_column('apply_to_existing_emails')
        print("Removed apply_to_existing_emails column from auto_reply_rules table")