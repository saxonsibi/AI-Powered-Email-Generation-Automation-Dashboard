# app/models/auto_reply.py
from app import db
from datetime import datetime, timezone
import json


class AutoReplyTemplate(db.Model):
    """Model for auto-reply templates."""
    __tablename__ = 'auto_reply_templates'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    reply_subject = db.Column(db.String(255))
    reply_body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # --- Relationships ---
    # A template belongs to one user.
    user = db.relationship('User', back_populates='auto_reply_templates')
    # A template can be used by many rules.
    rules = db.relationship('AutoReplyRule', back_populates='template', lazy='dynamic')
    # A template can be used in many logs.
    logs = db.relationship('AutoReplyLog', back_populates='template', lazy='dynamic')

    def to_dict(self):
        """Converts the template object to a dictionary."""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'name': self.name,
            'reply_subject': self.reply_subject,
            'reply_body': self.reply_body,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self):
        return f'<AutoReplyTemplate {self.name}>'


class AutoReplyRule(db.Model):
    """Model for auto-reply rules."""
    __tablename__ = 'auto_reply_rules'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    priority = db.Column(db.Integer, default=5)
    is_active = db.Column(db.Boolean, default=True)
    template_id = db.Column(db.Integer, db.ForeignKey('auto_reply_templates.id'), nullable=False)
    trigger_conditions = db.Column(db.Text)

    delay_minutes = db.Column(db.Integer, default=0)
    # Custom sender email for auto-replies
    sender_email = db.Column(db.String(255), nullable=True)
    
    # Filter fields for matching emails
    sender_filter = db.Column(db.String(255), nullable=True)
    sender_filter_type = db.Column(db.String(20), default='contains')  # contains, exact, starts_with, regex
    subject_filter = db.Column(db.String(255), nullable=True)
    subject_filter_type = db.Column(db.String(20), default='contains')
    body_filter = db.Column(db.Text, nullable=True)
    body_filter_type = db.Column(db.String(20), default='contains')
    
    # CRITICAL FIX: Removed cooldown_hours as it's no longer needed
    reply_once_per_thread = db.Column(db.Boolean, default=True)
    prevent_auto_reply_to_auto = db.Column(db.Boolean, default=True)
    ignore_mailing_lists = db.Column(db.Boolean, default=True)
    stop_on_sender_reply = db.Column(db.Boolean, default=True)
    apply_to_existing_emails = db.Column(db.Boolean, default=False, nullable=False)

    # CRITICAL FIX: Add schedule fields
    schedule_start = db.Column(db.DateTime)
    schedule_end = db.Column(db.DateTime)
    business_hours_only = db.Column(db.Boolean, default=False)
    business_days_only = db.Column(db.Boolean, default=False)
    business_hours_start = db.Column(db.Time, default=datetime.strptime('09:00', '%H:%M').time())
    business_hours_end = db.Column(db.Time, default=datetime.strptime('18:00', '%H:%M').time())

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    last_triggered = db.Column(db.DateTime)

    # --- Relationships ---
    # A rule belongs to one user.
    user = db.relationship('User', back_populates='auto_reply_rules')
    # A rule uses one template.
    template = db.relationship('AutoReplyTemplate', back_populates='rules')
    # A rule can trigger many logs.
    logs = db.relationship('AutoReplyLog', back_populates='rule', lazy='dynamic')

    def get_trigger_conditions(self):
        """Safely parses the JSON trigger conditions."""
        if not self.trigger_conditions:
            return {}
        try:
            return json.loads(self.trigger_conditions)
        except (json.JSONDecodeError, TypeError):
            # Log the error for debugging purposes
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error decoding trigger_conditions for rule {self.id}: {self.trigger_conditions}")
            return {}

    def set_trigger_conditions(self, conditions_dict):
        """Safely serializes the trigger conditions to JSON."""
        self.trigger_conditions = json.dumps(conditions_dict)
        self.updated_at = datetime.now(timezone.utc)

    def is_apply_to_all_rule(self):
        """Check if this rule applies to all incoming emails."""
        conditions = self.get_trigger_conditions()
        return conditions.get('apply_to_all', False)

    def to_dict(self):
        """Converts the rule object to a dictionary."""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'name': self.name,
            'priority': self.priority,
            'is_active': self.is_active,
            'template_id': self.template_id,
            'trigger_conditions': self.get_trigger_conditions(),
            'delay_minutes': self.delay_minutes,
            # CRITICAL FIX: Removed cooldown_hours
            'reply_once_per_thread': self.reply_once_per_thread,
            'prevent_auto_reply_to_auto': self.prevent_auto_reply_to_auto,
            'ignore_mailing_lists': self.ignore_mailing_lists,
            'stop_on_sender_reply': self.stop_on_sender_reply,
            'schedule_start': self.schedule_start.isoformat() if self.schedule_start else None,
            'schedule_end': self.schedule_end.isoformat() if self.schedule_end else None,
            'business_hours_only': self.business_hours_only,
            'business_days_only': self.business_days_only,
            'business_hours_start': self.business_hours_start.strftime('%H:%M') if self.business_hours_start else None,
            'business_hours_end': self.business_hours_end.strftime('%H:%M') if self.business_hours_end else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'last_triggered': self.last_triggered.isoformat() if self.last_triggered else None,
        }

    def __repr__(self):
        return f'<AutoReplyRule {self.name}>'


class AutoReplyLog(db.Model):
    """Model for logging auto-reply actions."""
    __tablename__ = 'auto_reply_logs'
    __table_args__ = (
        db.UniqueConstraint('rule_id', 'gmail_id', name='unique_rule_gmail'),
        {'extend_existing': True}
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    email_id = db.Column(db.Integer, db.ForeignKey('emails.id'), nullable=True)
    rule_id = db.Column(db.Integer, db.ForeignKey('auto_reply_rules.id'), nullable=True)
    template_id = db.Column(db.Integer, db.ForeignKey('auto_reply_templates.id'), nullable=True)

    thread_id = db.Column(db.String(255))
    # CRITICAL FIX: Changed from message_id to gmail_id as the primary identifier
    gmail_id = db.Column(db.String(255), nullable=False, index=True)  # Gmail API message ID
    # Keep message_id as a backup for reference
    message_id = db.Column(db.String(255), nullable=True)  # RFC Message-ID header
    
    recipient_email = db.Column(db.String(255), nullable=False)
    incoming_subject = db.Column(db.String(500), nullable=True)  # Store subject for display
    status = db.Column(db.String(20), default='Sent')
    skip_reason = db.Column(db.Text)
    error_message = db.Column(db.Text, nullable=True)  # Store error message for failed sends
    sent_at = db.Column(db.DateTime, nullable=True)  # When the auto-reply was sent
    reply_content = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # --- Relationships ---
    # A log belongs to one user.
    user = db.relationship('User', back_populates='auto_reply_logs')
    # A log belongs to one email (the original email that triggered the reply).
    email = db.relationship('Email', back_populates='auto_reply_logs')
    # A log is created by one rule.
    rule = db.relationship('AutoReplyRule', back_populates='logs')
    # A log uses one template.
    template = db.relationship('AutoReplyTemplate', back_populates='logs')

    def to_dict(self):
        """Converts the log object to a dictionary."""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'email_id': self.email_id,
            'rule_id': self.rule_id,
            'template_id': self.template_id,
            'thread_id': self.thread_id,
            # CRITICAL FIX: Added gmail_id to dictionary
            'gmail_id': self.gmail_id,
            # Keep message_id for reference
            'message_id': self.message_id,
            'recipient_email': self.recipient_email,
            'status': self.status,
            'skip_reason': self.skip_reason,
            'reply_content': self.reply_content,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f'<AutoReplyLog {self.status} to {self.recipient_email}>'


# CRITICAL FIX: Add ScheduledAutoReply model for delayed replies
class ScheduledAutoReply(db.Model):
    """Model for scheduled auto-replies."""
    __tablename__ = 'scheduled_auto_replies'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    email_id = db.Column(db.Integer, db.ForeignKey('emails.id'), nullable=False)
    rule_id = db.Column(db.Integer, db.ForeignKey('auto_reply_rules.id'), nullable=True)  # FIXED: Made nullable
    template_id = db.Column(db.Integer, db.ForeignKey('auto_reply_templates.id'), nullable=False)
    
    scheduled_at = db.Column(db.DateTime, nullable=False)
    sent_at = db.Column(db.DateTime)
    status = db.Column(db.String(20), default='Scheduled')  # Scheduled, Sent, Failed, Cancelled
    failure_reason = db.Column(db.Text)
    skip_reason = db.Column(db.Text)  # CRITICAL FIX: Added skip_reason for consistency
    
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # --- Relationships ---
    user = db.relationship('User', backref='scheduled_auto_replies')
    email = db.relationship('Email', backref='scheduled_auto_replies')
    rule = db.relationship('AutoReplyRule', backref='scheduled_auto_replies')
    template = db.relationship('AutoReplyTemplate', backref='scheduled_auto_replies')
    
    def to_dict(self):
        """Converts the scheduled reply object to a dictionary."""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'email_id': self.email_id,
            'rule_id': self.rule_id,
            'template_id': self.template_id,
            'scheduled_at': self.scheduled_at.isoformat() if self.scheduled_at else None,
            'sent_at': self.sent_at.isoformat() if self.sent_at else None,
            'status': self.status,
            'failure_reason': self.failure_reason,
            'skip_reason': self.skip_reason,  # CRITICAL FIX: Added skip_reason to dictionary
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
    
    def __repr__(self):
        return f'<ScheduledAutoReply {self.id} for email {self.email_id}>'