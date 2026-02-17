# models/follow_up.py

from app import db
from datetime import datetime, timedelta
import logging
from enum import Enum

logger = logging.getLogger(__name__)

class TriggerType(Enum):
    NO_REPLY = "No Reply"
    NO_OPEN = "No Open"
    NO_CLICK = "No Click"

class MessageType(Enum):
    AI_GENERATED = "AI-Generated"
    TEMPLATE_BASED = "Template-Based"

class FollowUpStatus(Enum):
    PENDING = "Pending"
    SENT = "Sent"
    SKIPPED = "Skipped"
    FAILED = "Failed"
    REPLIED = "Replied"

class FollowUpSequence(db.Model):
    """Sequence of follow-up messages for a rule."""
    __tablename__ = 'follow_up_sequences'
    
    id = db.Column(db.Integer, primary_key=True)
    rule_id = db.Column(db.Integer, db.ForeignKey('follow_up_rules.id'), nullable=False)
    sequence_number = db.Column(db.Integer, nullable=False)  # 1st, 2nd, 3rd follow-up
    delay_days = db.Column(db.Integer, nullable=False)
    subject = db.Column(db.String(255))
    message = db.Column(db.Text)
    tone = db.Column(db.String(50))  # For AI-generated: Professional, Friendly, Polite, Urgent
    length = db.Column(db.String(20))  # For AI-generated: Short, Medium, Detailed
    
    def to_dict(self):
        return {
            'id': self.id,
            'rule_id': self.rule_id,
            'sequence_number': self.sequence_number,
            'delay_days': self.delay_days,
            'subject': self.subject,
            'message': self.message,
            'tone': self.tone,
            'length': self.length
        }

class FollowUpLog(db.Model):
    """Log of follow-up actions."""
    __tablename__ = 'follow_up_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    rule_id = db.Column(db.Integer, db.ForeignKey('follow_up_rules.id'), nullable=False)
    original_email_id = db.Column(db.Integer, db.ForeignKey('emails.id'), nullable=False)
    follow_up_id = db.Column(db.Integer, db.ForeignKey('follow_ups.id'), nullable=True)
    follow_up_number = db.Column(db.Integer, nullable=False)
    recipient_email = db.Column(db.String(255), nullable=False)
    status = db.Column(db.Enum(FollowUpStatus), nullable=False)
    reason = db.Column(db.String(255))  # Reason for skipped/failed status
    scheduled_at = db.Column(db.DateTime, nullable=False)
    sent_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    original_email = db.relationship('Email', backref='follow_up_logs')
    follow_up = db.relationship('FollowUp', backref='logs')
    
    def to_dict(self):
        return {
            'id': self.id,
            'rule_id': self.rule_id,
            'original_email_id': self.original_email_id,
            'follow_up_id': self.follow_up_id,
            'follow_up_number': self.follow_up_number,
            'recipient_email': self.recipient_email,
            'status': self.status.value,
            'reason': self.reason,
            'scheduled_at': self.scheduled_at.isoformat(),
            'sent_at': self.sent_at.isoformat() if self.sent_at else None,
            'created_at': self.created_at.isoformat()
        }

class FollowUp(db.Model):
    """Follow-up emails for automation."""
    __tablename__ = 'follow_ups'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    sent_email_id = db.Column(db.Integer, db.ForeignKey('sent_emails.id'), nullable=True)
    follow_up_rule_id = db.Column(db.Integer, db.ForeignKey('follow_up_rules.id'), nullable=True)
    
    # CRITICAL: Make this foreign key nullable to allow follow-ups without an associated email
    email_id = db.Column(db.Integer, db.ForeignKey('emails.id'), nullable=True)
    
    thread_id = db.Column(db.String(255), nullable=True)  # Make nullable for standalone follow-ups
    recipient_email = db.Column(db.String(255), nullable=False)
    scheduled_at = db.Column(db.DateTime, nullable=False)
    sent_at = db.Column(db.DateTime)
    status = db.Column(db.String(20), default='pending')  # pending, sent, completed, cancelled, failed
    content = db.Column(db.Text, nullable=False)
    count = db.Column(db.Integer, default=1)
    max_count = db.Column(db.Integer, default=3)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Additional fields for enhanced follow-up system
    trigger_type = db.Column(db.Enum(TriggerType), nullable=True)  # Type of trigger
    message_type = db.Column(db.Enum(MessageType), nullable=True)  # AI-Generated or Template-Based
    sequence_number = db.Column(db.Integer, default=1)  # 1st, 2nd, 3rd follow-up
    stop_on_reply = db.Column(db.Boolean, default=True)  # Stop follow-ups if recipient replies
    business_days_only = db.Column(db.Boolean, default=True)  # Send only on business days
    send_window_start = db.Column(db.Time, default=datetime.strptime('09:00', '%H:%M').time())
    send_window_end = db.Column(db.Time, default=datetime.strptime('18:00', '%H:%M').time())
    
    # Relationships - Using string references to avoid circular imports
    user = db.relationship('User', back_populates='follow_ups')
    sent_email = db.relationship('SentEmail', back_populates='follow_ups')
    email = db.relationship('Email', back_populates='follow_ups')
    
    # Add a property for backward compatibility with code that expects scheduled_date
    @property
    def scheduled_date(self):
        """Property for backward compatibility with code expecting scheduled_date."""
        return self.scheduled_at
    
    @scheduled_date.setter
    def scheduled_date(self, value):
        """Setter for backward compatibility with code expecting scheduled_date."""
        self.scheduled_at = value
    
    def __init__(self, **kwargs):
        """Initialize the FollowUp model with default values."""
        super(FollowUp, self).__init__(**kwargs)
        # Ensure sequence_number is never None
        if self.sequence_number is None:
            self.sequence_number = 1
    
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'sent_email_id': self.sent_email_id,
            'follow_up_rule_id': self.follow_up_rule_id,
            'email_id': self.email_id,
            'thread_id': self.thread_id,
            'recipient_email': self.recipient_email,
            'scheduled_at': self.scheduled_at.isoformat() if self.scheduled_at else None,
            'scheduled_date': self.scheduled_at.isoformat() if self.scheduled_at else None,  # Add for backward compatibility
            'sent_at': self.sent_at.isoformat() if self.sent_at else None,
            'status': self.status,
            'content': self.content,
            'count': self.count,
            'max_count': self.max_count,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'trigger_type': self.trigger_type.value if self.trigger_type else None,
            'message_type': self.message_type.value if self.message_type else None,
            'sequence_number': self.sequence_number if self.sequence_number else 1,  # Default to 1 if None
            'stop_on_reply': self.stop_on_reply,
            'business_days_only': self.business_days_only,
            'send_window_start': self.send_window_start.strftime('%H:%M') if self.send_window_start else None,
            'send_window_end': self.send_window_end.strftime('%H:%M') if self.send_window_end else None
        }
    
    def __repr__(self):
        if self.email_id:
            return f'<FollowUp for Email {self.email_id}>'
        else:
            return f'<FollowUp to {self.recipient_email}>'
    
    def mark_as_sent(self):
        """Mark follow-up as sent."""
        self.status = 'sent'
        self.sent_at = datetime.utcnow()
        self.count += 1
        db.session.commit()
    
    def mark_as_completed(self):
        """Mark follow-up as completed."""
        self.status = 'completed'
        self.sent_at = datetime.utcnow()
        db.session.commit()
    
    def mark_as_cancelled(self):
        """Mark follow-up as cancelled."""
        self.status = 'cancelled'
        db.session.commit()
    
    def mark_as_failed(self):
        """Mark follow-up as failed."""
        self.status = 'failed'
        db.session.commit()
    
    def can_be_sent(self):
        """Check if this follow-up can be sent."""
        if self.status not in ['pending', 'skipped']:
            return False
        
        # Check if we're within business hours if required
        if self.business_days_only:
            now = datetime.utcnow()
            # Check if it's a weekend (Saturday=5, Sunday=6)
            if now.weekday() >= 5:
                return False
            
            # Check if we're within the sending time window
            current_time = now.time()
            if current_time < self.send_window_start or current_time > self.send_window_end:
                return False
        
        # Check if we've exceeded the maximum count
        if self.count >= self.max_count:
            return False
        
        return True
    
    def is_overdue(self):
        """Check if this follow-up is overdue."""
        if self.status not in ['pending', 'skipped']:
            return False
        return datetime.utcnow() > self.scheduled_at
    
    def get_next_scheduled_time(self):
        """Get the next scheduled time for this follow-up."""
        if self.status not in ['pending', 'skipped']:
            return None
        return self.scheduled_at
    
    def get_time_until_due(self):
        """Get the time until this follow-up is due."""
        if self.status not in ['pending', 'skipped']:
            return None
        if datetime.utcnow() > self.scheduled_at:
            return datetime.utcnow() - self.scheduled_at
        return None
    
    def schedule_next_follow_up(self, delay_hours):
        """Schedule the next follow-up if within max count."""
        if self.count >= self.max_count:
            self.mark_as_completed()
            return False
        
        # Calculate new scheduled time
        self.scheduled_at = datetime.utcnow() + timedelta(hours=delay_hours)
        self.status = 'pending'
        self.sequence_number += 1
        db.session.commit()
        return True
    
    def get_recipients(self):
        """Get a list of recipients from the recipient_email field."""
        return [email.strip() for email in self.recipient_email.split(',')]
    
    def has_multiple_recipients(self):
        """Check if this follow-up has multiple recipients."""
        return len(self.get_recipients()) > 1
    
    def is_business_day(self):
        """Check if today is a business day."""
        today = datetime.utcnow().weekday()
        return today < 5  # Monday=0, Friday=4
    
    def is_within_send_window(self):
        """Check if current time is within the sending time window."""
        now = datetime.utcnow().time()
        return self.send_window_start <= now <= self.send_window_end
    
    def should_send_now(self):
        """Determine if this follow-up should be sent now."""
        if not self.can_be_sent():
            return False
        
        if not self.is_overdue():
            return False
        
        # Check business days and time window
        if self.business_days_only and not self.is_business_day():
            return False
        
        if not self.is_within_send_window():
            return False
        
        return True