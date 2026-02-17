# app/models/email.py

from app import db
from datetime import datetime
import json
import logging

logger = logging.getLogger(__name__)

class EmailCategory(db.Model):
    """Email category for classification."""
    __tablename__ = 'email_categories'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(50), nullable=False)
    color = db.Column(db.String(7))  # Hex color code
    is_default = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships - Using string references to avoid circular imports
    user = db.relationship('User', back_populates='email_categories')
    email_list = db.relationship('Email', back_populates='category', lazy='dynamic')
    classification_rules = db.relationship('ClassificationRule', back_populates='category', lazy='dynamic')
    email_classifications = db.relationship('EmailClassification', back_populates='category', lazy='dynamic')
    
    def __repr__(self):
        return f'<EmailCategory {self.name}>'
    
    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'name': self.name,
            'color': self.color,
            'is_default': self.is_default,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

class Email(db.Model):
    """Email model for storing email data."""
    __tablename__ = 'emails'
    
    id = db.Column(db.Integer, primary_key=True)
    gmail_id = db.Column(db.String(255), unique=True)  # Gmail message ID
    thread_id = db.Column(db.String(255))
    subject = db.Column(db.Text)
    sender = db.Column(db.String(255))
    # FIXED: Added 'to' field to match what the code expects
    to = db.Column(db.String(255), nullable=False)
    recipients = db.Column(db.Text)  # JSON string of recipients
    body_text = db.Column(db.Text)
    body_html = db.Column(db.Text)
    snippet = db.Column(db.Text)  # Email snippet for preview
    received_at = db.Column(db.DateTime)  # Using received_at to match database schema
    is_read = db.Column(db.Boolean, default=False)
    is_starred = db.Column(db.Boolean, default=False)
    is_draft = db.Column(db.Boolean, default=False)
    is_sent = db.Column(db.Boolean, default=False)
    label = db.Column(db.String(100))  # Gmail label
    processed_for_auto_reply = db.Column(db.Boolean, default=False, nullable=False)
    
    # CRITICAL FIX: Added message_id field for tracking
    message_id = db.Column(db.String(255), index=True)  # Message-ID from email headers
    
    # AI-related fields
    category_id = db.Column(db.Integer, db.ForeignKey('email_categories.id'))
    is_urgent = db.Column(db.Boolean, default=False)
    sentiment_score = db.Column(db.Float)
    
    # Automation tracking fields
    processed = db.Column(db.Boolean, default=False)
    automation_rules_applied = db.Column(db.String(255))  # Comma-separated rule IDs
    processed_at = db.Column(db.DateTime)
    auto_replied = db.Column(db.Boolean, default=False)
    
    # Foreign key to User
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Additional fields for sent emails
    sent_at = db.Column(db.DateTime)  # When the email was sent
    folder = db.Column(db.String(20), default='inbox')  # inbox, sent, drafts, etc.
    sync_status = db.Column(db.String(20), default='synced')  # synced, pending, error
    
    # Relationships - Using string references to avoid circular imports
    user = db.relationship('User', back_populates='emails')
    category = db.relationship('EmailCategory', back_populates='email_list')
    follow_ups = db.relationship('FollowUp', back_populates='email', lazy='dynamic', cascade='all, delete-orphan')
    classifications = db.relationship('EmailClassification', back_populates='email', lazy='dynamic', cascade='all, delete-orphan')
    # FIXED: Added proper relationship to AutoReplyLog
    auto_reply_logs = db.relationship('AutoReplyLog', back_populates='email', lazy='dynamic')
    attachments = db.relationship('EmailAttachment', back_populates='email', lazy='dynamic', cascade='all, delete-orphan')
    
    # Add a property for backward compatibility with code that expects date_received
    @property
    def date_received(self):
        """Property for backward compatibility with code expecting date_received."""
        return self.received_at
    
    @date_received.setter
    def date_received(self, value):
        """Setter for backward compatibility with code expecting date_received."""
        self.received_at = value
    
    # CRITICAL FIX: Add a property for backward compatibility with code that expects has_attachments
    @property
    def has_attachments(self):
        """Property to check if email has attachments."""
        return self.attachments.count() > 0 if self.attachments else False
    
    # CRITICAL FIX: Add a setter for has_attachments to prevent errors
    @has_attachments.setter
    def has_attachments(self, value):
        """Setter for backward compatibility - does nothing."""
        # This setter does nothing to prevent errors
        # The actual value is determined by the attachments relationship
        pass
    
    # NEW: Add a property to get the sender name
    @property
    def sender_name(self):
        """Extract sender name from email address."""
        if not self.sender:
            return ""
        
        # If email has format "Name <email@domain.com>", extract the name
        if '<' in self.sender and '>' in self.sender:
            return self.sender.split('<')[0].strip().strip('"\'')
        # Otherwise, use the part before @
        return self.sender.split('@')[0]
    
    # NEW: Add a property to get the sender email address
    @property
    def sender_email(self):
        """Extract sender email address from sender field."""
        if not self.sender:
            return ""
        
        # If email has format "Name <email@domain.com>", extract the email
        if '<' in self.sender and '>' in self.sender:
            return self.sender.split('<')[1].split('>')[0].strip()
        # Otherwise, return the full sender
        return self.sender
    
    def __repr__(self):
        return f'<Email {self.subject[:30]}...>'
    
    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'gmail_id': self.gmail_id,
            'thread_id': self.thread_id,
            'subject': self.subject,
            'sender': self.sender,
            'sender_name': self.sender_name,  # NEW: Add sender name
            'sender_email': self.sender_email,  # NEW: Add sender email
            'to': self.to,  # Added to field
            'recipients': json.loads(self.recipients) if self.recipients else [],
            'body_text': self.body_text,
            'snippet': self.snippet,
            'received_at': self.received_at.isoformat() if self.received_at else None,
            'date_received': self.received_at.isoformat() if self.received_at else None,  # Add for backward compatibility
            'is_read': self.is_read,
            'is_starred': self.is_starred,
            'is_draft': self.is_draft,
            'is_sent': self.is_sent,
            'label': self.label,
            'category_id': self.category_id,
            'is_urgent': self.is_urgent,
            'sentiment_score': self.sentiment_score,
            'processed': self.processed,
            'auto_replied': self.auto_replied,
            'user_id': self.user_id,
            'has_attachments': self.has_attachments,  # Add for backward compatibility
            'message_id': self.message_id,  # CRITICAL FIX: Add message_id
            'sent_at': self.sent_at.isoformat() if self.sent_at else None,  # Add sent_at
            'folder': self.folder,  # Add folder
            'sync_status': self.sync_status  # Add sync_status
        }
    
    def has_automation_applied(self, rule_id):
        """Check if a specific automation rule has been applied to this email."""
        if not self.automation_rules_applied:
            return False
        return str(rule_id) in self.automation_rules_applied.split(',')
    
    def add_automation_rule(self, rule_id):
        """Add a rule ID to the list of applied automation rules."""
        if not self.automation_rules_applied:
            self.automation_rules_applied = str(rule_id)
        elif not self.has_automation_applied(rule_id):
            self.automation_rules_applied += f',{rule_id}'
        
        self.processed = True
        self.processed_at = datetime.utcnow()
    
    def get_recipients_list(self):
        """Get recipients as a list instead of JSON string."""
        if not self.recipients:
            return []
        try:
            return json.loads(self.recipients)
        except:
            return []
    
    def set_recipients_list(self, recipients_list):
        """Set recipients from a list."""
        self.recipients = json.dumps(recipients_list)
    
    def get_classification(self):
        """Get the most recent classification for this email."""
        # Import inside method to avoid circular imports
        from app.models.email import EmailClassification
        classification = self.classifications.order_by(db.desc(EmailClassification.created_at)).first()
        return classification
    
    def mark_as_read(self):
        """Mark email as read."""
        self.is_read = True
        db.session.commit()
    
    def mark_as_unread(self):
        """Mark email as unread."""
        self.is_read = False
        db.session.commit()
    
    def toggle_star(self):
        """Toggle star status."""
        self.is_starred = not self.is_starred
        db.session.commit()
    
    # NEW: Add method to get thread messages
    def get_thread_messages(self):
        """Get all messages in the same thread."""
        if not self.thread_id:
            return [self]
        
        # Import inside method to avoid circular imports
        from app.models.email import Email
        
        return Email.query.filter_by(
            user_id=self.user_id,
            thread_id=self.thread_id
        ).order_by(Email.received_at).all()
    
    # NEW: Add method to check if email is a reply
    def is_reply(self):
        """Check if this email is a reply to another email."""
        return self.subject and self.subject.lower().startswith('re:')
    
    # NEW: Add method to get the original subject
    def get_original_subject(self):
        """Get the original subject without Re: prefix."""
        if not self.subject:
            return ""
        
        if self.subject.lower().startswith('re:'):
            return self.subject[3:].strip()
        return self.subject

class EmailClassification(db.Model):
    """Email classification model for storing classification results."""
    __tablename__ = 'email_classifications'
    
    id = db.Column(db.Integer, primary_key=True)
    email_id = db.Column(db.Integer, db.ForeignKey('emails.id'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('email_categories.id'), nullable=False)
    confidence_score = db.Column(db.Float, default=0.0)
    is_manual = db.Column(db.Boolean, default=False)  # True if user manually classified
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships - Using string references to avoid circular imports
    email = db.relationship('Email', back_populates='classifications')
    category = db.relationship('EmailCategory', back_populates='email_classifications')
    
    # Add a property for backward compatibility with code that expects classification
    @property
    def classification(self):
        """Property for backward compatibility with code expecting classification."""
        return self.category.name if self.category else None
    
    # FIXED: Added a 'label' property to match the dashboard query
    @property
    def label(self):
        """Property to match the dashboard query."""
        return self.category.name if self.category else None
    
    # NEW: Add a property to get urgency level based on confidence score
    @property
    def urgency_level(self):
        """Get urgency level based on confidence score."""
        if self.confidence_score > 0.8:
            return 'High'
        elif self.confidence_score > 0.5:
            return 'Medium'
        else:
            return 'Low'
    
    def __repr__(self):
        return f'<EmailClassification {self.category.name if self.category else "Unknown"}>'
    
    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'email_id': self.email_id,
            'category_id': self.category_id,
            'category_name': self.category.name if self.category else None,
            'classification': self.category.name if self.category else None,  # Add for backward compatibility
            'label': self.category.name if self.category else None,  # Add for dashboard query
            'confidence_score': self.confidence_score,
            'urgency_level': self.urgency_level,  # NEW: Add urgency level
            'is_manual': self.is_manual,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

class SentEmail(db.Model):
    """Model for tracking sent emails."""
    __tablename__ = 'sent_emails'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    gmail_id = db.Column(db.String(255), unique=True)
    to = db.Column(db.Text)  # Recipients as a string
    cc = db.Column(db.Text, nullable=True)  # CC recipients
    bcc = db.Column(db.Text, nullable=True)  # BCC recipients
    subject = db.Column(db.String(255))
    snippet = db.Column(db.Text)  # Email snippet for preview
    body_text = db.Column(db.Text, nullable=True)  # Plain text body
    body_html = db.Column(db.Text, nullable=True)  # HTML body
    thread_id = db.Column(db.String(255))
    sent_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='Sent')  # Sent, Delivered, etc.
    resent_at = db.Column(db.DateTime, nullable=True)  # When the email was resent
    
    # Tracking fields
    tracking_id = db.Column(db.String(255), nullable=True)  # Unique ID for tracking opens/clicks
    opened_at = db.Column(db.DateTime, nullable=True)  # When the email was opened
    clicked_at = db.Column(db.DateTime, nullable=True)  # When a link was clicked
    
    # Relationships - Using string references to avoid circular imports
    user = db.relationship('User', back_populates='sent_emails')
    follow_ups = db.relationship('FollowUp', back_populates='sent_email', lazy='dynamic', cascade='all, delete-orphan')
    
    # NEW: Add a property to check if email was opened
    @property
    def is_opened(self):
        """Check if email was opened."""
        return self.opened_at is not None
    
    # NEW: Add a property to check if email was clicked
    @property
    def is_clicked(self):
        """Check if email was clicked."""
        return self.clicked_at is not None
    
    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'gmail_id': self.gmail_id,
            'to': self.to,
            'subject': self.subject,
            'snippet': self.snippet,
            'thread_id': self.thread_id,
            'sent_at': self.sent_at.isoformat() if self.sent_at else None,
            'status': self.status,
            'resent_at': self.resent_at.isoformat() if self.resent_at else None,
            'tracking_id': self.tracking_id,
            'opened_at': self.opened_at.isoformat() if self.opened_at else None,
            'clicked_at': self.clicked_at.isoformat() if self.clicked_at else None,
            'is_opened': self.is_opened,  # NEW: Add is_opened
            'is_clicked': self.is_clicked  # NEW: Add is_clicked
        }
    
    def get_recipients_list(self):
        """Get recipients as a list instead of JSON string."""
        if not self.to:
            return []
        try:
            return json.loads(self.to)
        except:
            return [self.to] if self.to else []
    
    def set_recipients_list(self, recipients_list):
        """Set recipients from a list."""
        self.to = json.dumps(recipients_list)
    
    def mark_as_opened(self):
        """Mark email as opened."""
        if not self.opened_at:
            self.opened_at = datetime.utcnow()
            db.session.commit()
    
    def mark_as_clicked(self):
        """Mark email as clicked."""
        if not self.clicked_at:
            self.clicked_at = datetime.utcnow()
            db.session.commit()
    
    def __repr__(self):
        return f'<SentEmail {self.subject[:20]}>'

class DraftEmail(db.Model):
    """Model for tracking draft emails."""
    __tablename__ = 'draft_emails'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    gmail_id = db.Column(db.String(255), unique=True)
    to = db.Column(db.String(255))
    cc = db.Column(db.String(255), nullable=True)
    bcc = db.Column(db.String(255), nullable=True)
    subject = db.Column(db.String(255))
    body = db.Column(db.Text)
    html_body = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    synced_at = db.Column(db.DateTime, nullable=True)  # When the draft was last synced with Gmail
    
    # Relationships - Using string references to avoid circular imports
    user = db.relationship('User', back_populates='draft_emails')
    attachments = db.relationship('DraftAttachment', back_populates='draft', lazy='dynamic', cascade='all, delete-orphan')
    
    @property
    def recipients(self):
        """Get recipients as a formatted string."""
        recipients = []
        if self.to:
            recipients.append(f"To: {self.to}")
        if self.cc:
            recipients.append(f"Cc: {self.cc}")
        if self.bcc:
            recipients.append(f"Bcc: {self.bcc}")
        return ", ".join(recipients) if recipients else "No recipients"
    
    def __repr__(self):
        return f'<DraftEmail {self.subject[:20]}>'

class DraftAttachment(db.Model):
    """Model for storing draft email attachment information."""
    __tablename__ = 'draft_attachments'
    
    id = db.Column(db.Integer, primary_key=True)
    draft_id = db.Column(db.Integer, db.ForeignKey('draft_emails.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    size = db.Column(db.Integer, default=0)
    content_type = db.Column(db.String(100))
    data = db.Column(db.LargeBinary)  # Store the actual file data
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationship
    draft = db.relationship('DraftEmail', back_populates='attachments')
    
    def __repr__(self):
        return f'<DraftAttachment {self.filename}>'
class EmailAttachment(db.Model):
    """Model for storing email attachment information."""
    
    __tablename__ = 'email_attachments'
    
    id = db.Column(db.Integer, primary_key=True)
    email_id = db.Column(db.Integer, db.ForeignKey('emails.id'), nullable=False)
    gmail_id = db.Column(db.String(255), nullable=False)  # Gmail attachment ID
    filename = db.Column(db.String(255), nullable=False)
    size = db.Column(db.Integer, default=0)
    mime_type = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationship
    email = db.relationship('Email', back_populates='attachments')
    
    # NEW: Add a property to get the file extension
    @property
    def extension(self):
        """Get the file extension."""
        if not self.filename:
            return ""
        
        parts = self.filename.split('.')
        return parts[-1] if len(parts) > 1 else ""
    
    # NEW: Add a property to check if the attachment is an image
    @property
    def is_image(self):
        """Check if the attachment is an image."""
        if not self.mime_type:
            return False
        return self.mime_type.startswith('image/')
    
    # NEW: Add a property to check if the attachment is a PDF
    @property
    def is_pdf(self):
        """Check if the attachment is a PDF."""
        if not self.mime_type:
            return False
        return self.mime_type == 'application/pdf'
    
    # NEW: Add a property to format the file size
    @property
    def formatted_size(self):
        """Format the file size in human-readable format."""
        if not self.size:
            return "0 B"
        
        # Define size units
        units = ['B', 'KB', 'MB', 'GB']
        unit_index = 0
        size = float(self.size)
        
        # Find the appropriate unit
        while size >= 1024 and unit_index < len(units) - 1:
            size /= 1024
            unit_index += 1
        
        # Format with 2 decimal places
        return f"{size:.2f} {units[unit_index]}"
    
    def __repr__(self):
        return f'<EmailAttachment {self.filename}>'
    
# Add this to your existing models file (e.g., app/models/email.py)
class Cache(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(255), unique=True, nullable=False)
    value = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.Float, nullable=False)
    
    def __repr__(self):
        return f'<Cache {self.key}>'