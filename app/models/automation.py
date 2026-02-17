# app/models/automation.py

import re
from app import db
from datetime import datetime, timedelta
from sqlalchemy import and_
from email.utils import parsedate_to_datetime
import json
import logging

logger = logging.getLogger(__name__)

class AutomationRule(db.Model):
    """Automation rules for email processing."""
    __tablename__ = 'automation_rules'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    trigger_condition = db.Column(db.Text)  # JSON string of conditions
    action = db.Column(db.Text)  # JSON string of actions
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())
    
    # Relationships - Using string references to avoid circular imports
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    user = db.relationship('User', back_populates='automation_rules')
    
    def __repr__(self):
        return f'<AutomationRule {self.name}>'

class ClassificationRule(db.Model):
    """Rules for email classification."""
    __tablename__ = 'classification_rules'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('email_categories.id'), nullable=False)
    conditions = db.Column(db.Text, nullable=False)  # JSON: {senders: [], keywords: [], domains: []}
    priority = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships - Using string references to avoid circular imports
    user = db.relationship('User', back_populates='classification_rules')
    category = db.relationship('EmailCategory', back_populates='classification_rules')
    
    def get_conditions(self):
        """Parse and return conditions as a dictionary"""
        if self.conditions:
            try:
                return json.loads(self.conditions)
            except:
                return {}
        return {}
    
    def set_conditions(self, conditions_dict):
        """Set conditions from a dictionary"""
        self.conditions = json.dumps(conditions_dict)
    
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'category_id': self.category_id,
            'priority': self.priority,
            'is_active': self.is_active,
            'conditions': self.get_conditions(),
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
    
    def __repr__(self):
        return f'<ClassificationRule {self.id}>'

# models/automation.py

# ... (keep the rest of the file as is)

class FollowUpRule(db.Model):
    """Rules for follow-up emails."""
    __tablename__ = 'follow_up_rules'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    trigger_type = db.Column(db.String(20), default='No Reply')  # No Reply, No Open, No Click
    delay_hours = db.Column(db.Integer, nullable=False, default=24)
    max_count = db.Column(db.Integer, nullable=False, default=3)
    template_text = db.Column(db.Text, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    conditions = db.Column(db.Text)  # JSON conditions for when to apply this rule
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Additional fields for enhanced follow-up system
    message_type = db.Column(db.String(20), default='Template-Based')  # AI-Generated, Template-Based
    apply_to_all = db.Column(db.Boolean, default=True)
    campaign_id = db.Column(db.Integer, nullable=True)  # Removed ForeignKey to avoid issues
    recipient_emails = db.Column(db.Text)  # JSON array of specific recipient emails
    stop_on_reply = db.Column(db.Boolean, default=True)
    business_days_only = db.Column(db.Boolean, default=True)
    send_window_start = db.Column(db.Time, default=datetime.strptime('09:00', '%H:%M').time())
    send_window_end = db.Column(db.Time, default=datetime.strptime('18:00', '%H:%M').time())
    last_triggered = db.Column(db.DateTime)
    
    # Relationships - Using string references to avoid circular imports
    user = db.relationship('User', back_populates='follow_up_rules')
    follow_ups = db.relationship('FollowUp', backref='rule', foreign_keys='FollowUp.follow_up_rule_id', lazy='dynamic')
    sequences = db.relationship('FollowUpSequence', backref='rule', cascade='all, delete-orphan')
    logs = db.relationship('FollowUpLog', backref='rule', cascade='all, delete-orphan')
    
    def get_conditions(self):
        """Parse and return conditions as a dictionary"""
        if self.conditions:
            try:
                return json.loads(self.conditions)
            except:
                return {}
        return {}
    
    def set_conditions(self, conditions_dict):
        """Set conditions from a dictionary"""
        self.conditions = json.dumps(conditions_dict)
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'trigger_type': self.trigger_type,
            'delay_hours': self.delay_hours,
            'max_count': self.max_count,
            'template_text': self.template_text,
            'is_active': self.is_active,
            'conditions': self.get_conditions(),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'message_type': self.message_type,
            'apply_to_all': self.apply_to_all,
            'campaign_id': self.campaign_id,
            'recipient_emails': self.recipient_emails,
            'stop_on_reply': self.stop_on_reply,
            'business_days_only': self.business_days_only,
            'send_window_start': self.send_window_start.strftime('%H:%M') if self.send_window_start else None,
            'send_window_end': self.send_window_end.strftime('%H:%M') if self.send_window_end else None,
            'last_triggered': self.last_triggered.isoformat() if self.last_triggered else None,
            'sequences': [seq.to_dict() for seq in self.sequences]
        }
    
    def __repr__(self):
        return f'<FollowUpRule {self.name}>'
class FollowUpTemplate(db.Model):
    """Template for follow-up emails."""
    __tablename__ = 'follow_up_templates'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    first_follow_up_days = db.Column(db.Integer, default=3)
    second_follow_up_days = db.Column(db.Integer, default=7)
    subsequent_follow_up_days = db.Column(db.Integer, default=14)
    max_follow_ups = db.Column(db.Integer, default=3)
    first_follow_up_body = db.Column(db.Text)
    second_follow_up_body = db.Column(db.Text)
    subsequent_follow_up_body = db.Column(db.Text)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    
    # Relationships - Using string references to avoid circular imports
    user = db.relationship('User', back_populates='follow_up_templates')
    
    def __repr__(self):
        return f'<FollowUpTemplate {self.name}>'

class EmailService:
    """Service for handling email operations and notifications."""
    
    @staticmethod
    def process_new_emails(user_id, gmail_service):
        """
        Process new emails for a user and count only those received after the last sync time.
        Updates the last_email_sync_time after processing.
        Returns the count of new emails.
        """
        # Import models inside the method to avoid circular imports
        from app.models.user import User
        from app.models.email import Email
        
        user = User.query.get(user_id)
        if not user:
            return {"success": False, "error": "User not found"}
        
        try:
            # Get the last sync time
            last_sync = user.last_email_sync_time
            
            # Fetch emails from Gmail API
            if not gmail_service:
                return {"success": False, "error": "Failed to connect to Gmail"}
            
            # Get messages list - only fetch emails after last sync time
            query = f"after:{int(last_sync.timestamp())}" if last_sync else None
            messages_result = gmail_service.users().messages().list(
                userId='me',
                q=query
            ).execute()
            
            messages = messages_result.get('messages', [])
            new_email_count = 0
            
            # Process each message
            for message_ref in messages:
                msg_id = message_ref['id']
                
                # Get full message details
                message = gmail_service.users().messages().get(
                    userId='me',
                    id=msg_id,
                    format='metadata',
                    metadataHeaders=['Date', 'From', 'Subject']
                ).execute()
                
                # Extract date
                headers = message.get('payload', {}).get('headers', [])
                date_str = next((h['value'] for h in headers if h['name'] == 'Date'), None)
                
                if date_str:
                    # Parse the date and check if it's after our last sync
                    email_date = EmailService._parse_gmail_date(date_str)
                    
                    if not last_sync or email_date > last_sync:
                        # This is a new email
                        new_email_count += 1
                        
                        # Save to database if not already exists
                        if not Email.query.filter_by(gmail_id=msg_id, user_id=user_id).first():
                            EmailService._save_email_to_db(message, user_id)
            
            # Update the last sync time
            user.last_email_sync_time = datetime.utcnow()
            db.session.commit()
            
            return {
                "success": True,
                "new_email_count": new_email_count,
                "total_email_count": Email.query.filter_by(user_id=user_id).count()
            }
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error processing new emails: {str(e)}")
            return {"success": False, "error": str(e)}
    
    @staticmethod
    def _parse_gmail_date(date_str):
        """Parse Gmail date string to datetime object."""
        # Gmail date format example: "Tue, 15 Jun 2021 16:30:00 -0700"
        try:
            return parsedate_to_datetime(date_str)
        except:
            return datetime.utcnow()
    
    @staticmethod
    def _save_email_to_db(message, user_id):
        """Save email to database."""
        # Import models inside the method to avoid circular imports
        from app.models.email import Email
        
        try:
            # Extract headers
            headers = message.get('payload', {}).get('headers', [])
            subject = next((h['value'] for h in headers if h['name'] == 'Subject'), '(No Subject)')
            from_email = next((h['value'] for h in headers if h['name'] == 'From'), '')
            date_str = next((h['value'] for h in headers if h['name'] == 'Date'), '')
            
            # Parse date
            date_received = EmailService._parse_gmail_date(date_str)
            
            # Get snippet
            snippet = message.get('snippet', '')
            
            # Get thread ID
            thread_id = message.get('threadId', '')
            
            # Create new email record
            new_email = Email(
                gmail_id=message['id'],
                thread_id=thread_id,
                user_id=user_id,
                sender=from_email,
                subject=subject,
                snippet=snippet,
                received_at=date_received,  # Updated to match the Email model
                is_read=False
            )
            
            db.session.add(new_email)
            db.session.commit()
            
            return True
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error saving email to database: {str(e)}")
            return False
    
    @staticmethod
    def check_for_new_emails(user_id):
        """
        Check for new emails without fetching from Gmail API.
        Returns the count of emails received after the last sync time.
        """
        # Import models inside the method to avoid circular imports
        from app.models.user import User
        from app.models.email import Email
        
        user = User.query.get(user_id)
        if not user:
            return {"success": False, "error": "User not found"}
        
        try:
            # Get the last sync time
            last_sync = user.last_email_sync_time
            
            if not last_sync:
                # If no last sync time, return 0 to avoid showing all emails as new
                return {
                    "success": True,
                    "new_email_count": 0,
                    "total_email_count": Email.query.filter_by(user_id=user_id).count()
                }
            
            # Count emails received after last sync time
            new_email_count = Email.query.filter(
                and_(
                    Email.user_id == user_id,
                    Email.received_at > last_sync  # Updated to match the Email model
                )
            ).count()
            
            return {
                "success": True,
                "new_email_count": new_email_count,
                "total_email_count": Email.query.filter_by(user_id=user_id).count()
            }
            
        except Exception as e:
            logger.error(f"Error checking for new emails: {str(e)}")
            return {"success": False, "error": str(e)}

class AutomationService:
    """Service for managing automation rules and processing emails."""
    
    def __init__(self, user_id=None):
        self.user_id = user_id
    
    def create_automation_rule(self, user_id, name, trigger_condition, action):
        """Create a new automation rule."""
        rule = AutomationRule(
            user_id=user_id,
            name=name,
            trigger_condition=json.dumps(trigger_condition),
            action=json.dumps(action)
        )
        
        db.session.add(rule)
        db.session.commit()
        return rule
    
    def get_automation_rules(self, user_id):
        """Get all automation rules for a user."""
        return AutomationRule.query.filter_by(user_id=user_id).all()
    
    def check_and_execute_rules(self):
        """Check all active automation rules and execute them for new emails."""
        if not self.user_id:
            return
        
        # Import models inside the method to avoid circular imports
        from app.models.email import Email
        from app.models.follow_up import FollowUp
        
        # Get all active rules for the user
        rules = AutomationRule.query.filter_by(
            user_id=self.user_id,
            is_active=True
        ).all()
        
        # Get all emails that haven't been processed for automation
        unprocessed_emails = Email.query.filter_by(
            user_id=self.user_id,
            processed=False  # Updated to match the Email model
        ).all()
        
        # Process each email with each rule
        for email in unprocessed_emails:
            for rule in rules:
                trigger_condition = json.loads(rule.trigger_condition)
                action = json.loads(rule.action)
                
                if self._check_trigger_condition(email, trigger_condition):
                    self._execute_action(email, action)
                    email.add_automation_rule(rule.id)
            
            # Mark the email as processed
            email.processed = True  # Updated to match the Email model
            email.processed_at = datetime.utcnow()  # Updated to match the Email model
        
        db.session.commit()
    
    def _check_trigger_condition(self, email, condition):
        """Check if an email meets the trigger condition."""
        # Check sender
        if 'sender' in condition:
            if condition['sender'].lower() not in email.sender.lower():
                return False
        
        # Check subject contains
        if 'subject_contains' in condition:
            if condition['subject_contains'].lower() not in email.subject.lower():
                return False
        
        # Check body contains
        if 'body_contains' in condition:
            if condition['body_contains'].lower() not in email.body_text.lower():
                return False
        
        # Check urgency
        if 'is_urgent' in condition and condition['is_urgent']:
            if not email.is_urgent:
                return False
        
        return True
    
    def _execute_action(self, email, action):
        """Execute an automation action on an email."""
        # Import models inside the method to avoid circular imports
        from app.models.follow_up import FollowUp
        
        # Auto reply
        if 'auto_reply' in action:
            from app.services.gmail_service import GmailService
            from flask_login import current_user
            
            gmail_service = GmailService(current_user)
            gmail_service.send_email(
                to=email.sender,
                subject=f"Re: {email.subject}",
                body_text=action['auto_reply']['message']
            )
        
        # Add label
        if 'add_label' in action:
            from app.services.gmail_service import GmailService
            from flask_login import current_user
            
            gmail_service = GmailService(current_user)
            gmail_service.add_label(email.gmail_id, action['add_label'])
        
        # Schedule follow up - FIXED: Updated to use FollowUp from follow_up.py
        if 'schedule_follow_up' in action:
            from app.services.ai_service import AIService
            
            delay_days = action['schedule_follow_up']['delay_days']
            ai_service = AIService()
            follow_up_content = ai_service.generate_follow_up(email, delay_days)
            
            scheduled_date = datetime.now() + timedelta(days=delay_days)
            follow_up = FollowUp(
                user_id=email.user_id,
                sent_email_id=None,  # Will be set when email is sent
                thread_id=email.thread_id,
                recipient_email=email.sender,
                scheduled_at=scheduled_date,
                status='pending'
            )
            db.session.add(follow_up)

class AutoReplyService:
    """Service for managing auto-reply templates and processing."""
    
    @staticmethod
    def create_auto_reply_template(user_id, name, subject, content, trigger_conditions=None, is_active=False, 
                                  sender_email=None, schedule_start=None, schedule_end=None, delay_reply=0):
        """Create a new auto-reply template."""
        # Import models inside the method to avoid circular imports
        from app.models.email import AutoReplyTemplate
        
        template = AutoReplyTemplate(
            user_id=user_id,
            name=name,
            subject=subject,
            content=content,
            trigger_conditions=json.dumps(trigger_conditions) if trigger_conditions else None,
            is_active=is_active,
            sender_email=sender_email,
            schedule_start=schedule_start,
            schedule_end=schedule_end,
            delay_reply=delay_reply
        )
        
        db.session.add(template)
        db.session.commit()
        return template
    
    @staticmethod
    def get_auto_reply_templates(user_id):
        """Get all auto-reply templates for a user."""
        # Import models inside the method to avoid circular imports
        from app.models.email import AutoReplyTemplate
        
        return AutoReplyTemplate.query.filter_by(user_id=user_id).all()
    
    @staticmethod
    def get_active_auto_reply_templates(user_id):
        """Get all active auto-reply templates for a user."""
        # Import models inside the method to avoid circular imports
        from app.models.email import AutoReplyTemplate
        
        return AutoReplyTemplate.query.filter_by(user_id=user_id, is_active=True).all()
    
    @staticmethod
    def get_scheduled_auto_reply_templates(user_id):
        """Get all scheduled auto-reply templates for a user."""
        # Import models inside the method to avoid circular imports
        from app.models.email import AutoReplyTemplate
        
        return AutoReplyTemplate.query.filter(
            AutoReplyTemplate.user_id == user_id,
            AutoReplyTemplate.schedule_start != None,
            AutoReplyTemplate.schedule_end != None
        ).all()
    
    @staticmethod
    def update_auto_reply_template(template_id, name=None, subject=None, content=None, trigger_conditions=None, 
                                 is_active=None, sender_email=None, schedule_start=None, schedule_end=None, delay_reply=None):
        """Update an auto-reply template."""
        # Import models inside the method to avoid circular imports
        from app.models.email import AutoReplyTemplate
        
        template = AutoReplyTemplate.query.get(template_id)
        if not template:
            return None
        
        if name is not None:
            template.name = name
        if subject is not None:
            template.subject = subject
        if content is not None:
            template.content = content
        if trigger_conditions is not None:
            template.set_trigger_conditions(trigger_conditions)
        if is_active is not None:
            template.is_active = is_active
        if sender_email is not None:
            template.sender_email = sender_email
        if schedule_start is not None:
            template.schedule_start = schedule_start
        if schedule_end is not None:
            template.schedule_end = schedule_end
        if delay_reply is not None:
            template.delay_reply = delay_reply
        
        template.updated_at = datetime.utcnow()
        db.session.commit()
        return template
    
    @staticmethod
    def delete_auto_reply_template(template_id):
        """Delete an auto-reply template."""
        # Import models inside the method to avoid circular imports
        from app.models.email import AutoReplyTemplate
        
        template = AutoReplyTemplate.query.get(template_id)
        if not template:
            return False
        
        db.session.delete(template)
        db.session.commit()
        return True
    
    @staticmethod
    def log_auto_reply(user_id, email_id, template_id, thread_id, sender_email, action='auto_reply', 
                      details=None, from_email=None, is_successful=None):
        """Log an auto-reply action."""
        # Import models inside the method to avoid circular imports
        from app.models.email import AutoReplyLog
        
        log = AutoReplyLog(
            user_id=user_id,
            email_id=email_id,
            template_id=template_id,
            thread_id=thread_id,
            sender_email=sender_email,
            action=action,
            details=details,
            from_email=from_email,
            is_successful=is_successful,
            created_at=datetime.utcnow()  # Ensure correct timestamp
        )
        
        db.session.add(log)
        db.session.commit()
        return log
    
    @staticmethod
    def is_template_scheduled_now(template):
        """
        Check if a template is scheduled to be active at the current time
        """
        try:
            # If template doesn't have schedule fields, it's always active
            if not hasattr(template, 'schedule_start') or not hasattr(template, 'schedule_end'):
                return True
            
            # If no schedule is set, it's always active
            if not template.schedule_start and not template.schedule_end:
                return True
            
            now = datetime.utcnow()
            
            # If only start time is set, check if we're after it
            if template.schedule_start and not template.schedule_end:
                return now >= template.schedule_start
            
            # If only end time is set, check if we're before it
            if not template.schedule_start and template.schedule_end:
                return now <= template.schedule_end
            
            # If both are set, check if we're in the range
            return template.schedule_start <= now <= template.schedule_end
            
        except Exception as e:
            logger.error(f"Error checking template schedule: {str(e)}")
            return True  # Default to allowing the reply
    
    @staticmethod
    def check_scheduled_auto_replies():
        """Check for scheduled auto-replies that need to be activated or deactivated."""
        try:
            # Import models inside the method to avoid circular imports
            from app.models.email import AutoReplyTemplate
            
            now = datetime.utcnow()
            
            # Activate templates that should start now
            templates_to_activate = AutoReplyTemplate.query.filter(
                AutoReplyTemplate.schedule_start <= now,
                AutoReplyTemplate.schedule_start != None,
                AutoReplyTemplate.is_active == False
            ).all()
            
            for template in templates_to_activate:
                # Check if the end time hasn't passed yet
                if not template.schedule_end or template.schedule_end > now:
                    template.is_active = True
                    logger.info(f"Activated scheduled template: {template.name}")
            
            # Deactivate templates that should end now
            templates_to_deactivate = AutoReplyTemplate.query.filter(
                AutoReplyTemplate.schedule_end <= now,
                AutoReplyTemplate.schedule_end != None,
                AutoReplyTemplate.is_active == True
            ).all()
            
            for template in templates_to_deactivate:
                template.is_active = False
                logger.info(f"Deactivated scheduled template: {template.name}")
            
            db.session.commit()
            return True
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error checking scheduled auto-replies: {str(e)}")
            return False
    
    @staticmethod
    def process_auto_replies():
        """
        Process unread emails and send auto-replies based on templates
        This is called by the scheduler every 5 minutes
        """
        try:
            # Import models inside the method to avoid circular imports
            from app.models.user import User
            from app.models.email import Email, EmailClassification, AutoReplyTemplate, AutoReplyLog
            
            # Get all users with Gmail credentials and active templates
            users_with_templates = db.session.query(User.id).join(
                AutoReplyTemplate, User.id == AutoReplyTemplate.user_id
            ).filter(
                AutoReplyTemplate.is_active == True,
                User.gmail_credentials.isnot(None)
            ).distinct().all()
            
            for user_id_tuple in users_with_templates:
                user_id = user_id_tuple[0]
                
                # Get the user
                user = User.query.get(user_id)
                if not user:
                    continue
                
                # Get active templates for this user
                templates = AutoReplyTemplate.query.filter_by(
                    user_id=user_id, 
                    is_active=True
                ).all()
                
                for template in templates:
                    # Only process emails received after template creation
                    # And only check emails from the last 5 minutes (for scheduler)
                    five_minutes_ago = datetime.utcnow() - timedelta(minutes=5)
                    unread_emails = Email.query.filter(
                        Email.user_id == user_id,
                        Email.is_read == False,
                        Email.received_at >= template.created_at,  # Only emails after template creation
                        Email.received_at >= five_minutes_ago  # Only recent emails for scheduler
                    ).all()
                    
                    for email in unread_emails:
                        try:
                            # Check if we've already replied to this email
                            if AutoReplyService.has_email_been_replied(email.id, user_id):
                                logger.info(f"Skipping email {email.id} - already replied")
                                continue
                            
                            # Check if this is a reply to our own email (avoid loops)
                            if AutoReplyService.is_reply_to_our_email(email, user_id):
                                logger.info(f"Skipping email {email.id} - appears to be a reply to our own email")
                                continue
                            
                            # Check if we can send an auto-reply to this sender (daily cooldown)
                            if not AutoReplyService.can_send_auto_reply_to(email.sender, user_id):
                                logger.info(f"Skipping auto-reply for email {email.id} - cooldown period not elapsed")
                                continue
                            
                            # Check if template is scheduled to be active now
                            if not AutoReplyService.is_template_scheduled_now(template):
                                logger.info(f"Skipping auto-reply for email {email.id} - template not scheduled for this time")
                                continue
                            
                            # Get email classification if available
                            classification = EmailClassification.query.filter_by(email_id=email.id).first()
                            
                            # Check if this template matches the email
                            if not AutoReplyService.should_reply_with_template(email, template, classification):
                                logger.info(f"Skipping email {email.id} - template conditions not met")
                                continue
                            
                            # Apply delay if configured
                            delay_minutes = template.delay_reply if hasattr(template, 'delay_reply') else 0
                            if delay_minutes > 0:
                                # Check if enough time has passed since email was received
                                if datetime.utcnow() - email.received_at < timedelta(minutes=delay_minutes):
                                    logger.info(f"Delaying auto-reply for email {email.id} - waiting for {delay_minutes} minutes")
                                    continue
                            
                            # Send the reply
                            success = AutoReplyService.send_auto_reply(email, template, user)
                            
                            if success:
                                # Record the auto-reply in a dedicated log table
                                AutoReplyService.log_auto_reply(
                                    user_id=user_id,
                                    email_id=email.id,
                                    template_id=template.id,
                                    thread_id=email.thread_id,
                                    recipient_email=email.sender,
                                    from_email=template.sender_email,
                                    is_successful=True
                                )
                                
                                logger.info(f"Auto-reply sent to {email.sender} for email {email.id}")
                            else:
                                logger.error(f"Failed to send auto-reply to {email.sender} for email {email.id}")
                            
                            # Commit changes for this email
                            db.session.commit()
                            
                        except Exception as e:
                            logger.exception(f"Error processing email {email.id}: {str(e)}")
                            db.session.rollback()
                            continue
                
        except Exception as e:
            logger.exception("Error processing auto-replies")
            db.session.rollback()
    
    @staticmethod
    def has_email_been_replied(email_id, user_id):
        """
        Check if we've already sent an auto-reply to this email
        """
        try:
            # Import models inside the method to avoid circular imports
            from app.models.email import AutoReplyLog
            
            # Check if we have a log entry for this email
            return AutoReplyLog.query.filter_by(
                email_id=email_id
            ).first() is not None
        except Exception as e:
            logger.exception("Error checking if email has been replied")
            return False
    
    @staticmethod
    def can_send_auto_reply_to(recipient_email, user_id):
        """
        Check if we can send an auto-reply to this recipient (cooldown check)
        Changed to daily cooldown instead of 5 minutes
        """
        try:
            # Import models inside the method to avoid circular imports
            from app.models.email import AutoReplyLog
            from datetime import datetime, timedelta
            
            # Get the most recent auto-reply log for this recipient
            last_reply = AutoReplyLog.query.filter_by(
                sender_email=recipient_email,
                action='auto_reply'
            ).order_by(AutoReplyLog.created_at.desc()).first()
            
            if last_reply:
                # Check cooldown period (24 hours)
                cooldown_period = timedelta(hours=24)
                if datetime.utcnow() - last_reply.created_at < cooldown_period:
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error checking auto-reply cooldown: {str(e)}")
            return True  # Default to allowing the reply
    
    @staticmethod
    def should_reply_with_template(email, template, classification=None):
        """
        Check if a template should be used for this email.
        """
        try:
            # Get trigger conditions from template
            conditions = {}
            if template.trigger_conditions:
                # Parse JSON if it's a string
                if isinstance(template.trigger_conditions, str):
                    try:
                        conditions = json.loads(template.trigger_conditions)
                    except json.JSONDecodeError:
                        logger.error(f"Invalid trigger_conditions JSON for template {template.id}")
                        return False
                else:
                    conditions = template.trigger_conditions
            
            # Don't use "all": true as a default trigger
            # Instead, require at least one specific condition
            if not conditions or not any(conditions.values()):
                logger.warning(f"Template {template.id} has no valid trigger conditions")
                return False
                
            # Check category conditions if classification is available
            if classification and 'categories' in conditions and conditions['categories']:
                if classification.category_id not in conditions['categories']:
                    return False
            
            # Check if this is an urgent email
            if conditions.get('urgent', False):
                subject = email.subject.lower() if email.subject else ''
                if 'urgent' not in subject:
                    return False
                    
            # Check if this is an unread email
            if conditions.get('unread', False):
                if email.is_read:
                    return False
            
            # Check sender conditions
            if 'senders' in conditions and conditions['senders']:
                sender_match = False
                sender = email.sender
                for sender_pattern in conditions['senders']:
                    if re.search(sender_pattern, sender, re.IGNORECASE):
                        sender_match = True
                        break
                if not sender_match:
                    return False
            
            # Check keyword conditions
            if 'keywords' in conditions and conditions['keywords']:
                keyword_match = False
                email_text = f"{email.subject or ''} {email.body_text or ''} {email.snippet or ''}"
                for keyword in conditions['keywords']:
                    if re.search(r'\b' + re.escape(keyword) + r'\b', email_text, re.IGNORECASE):
                        keyword_match = True
                        break
                if not keyword_match:
                    return False
            
            # Check domain conditions
            if 'domains' in conditions and conditions['domains']:
                domain_match = False
                sender = email.sender
                sender_domain = sender.split('@')[-1] if '@' in sender else ''
                for domain in conditions['domains']:
                    if sender_domain == domain:
                        domain_match = True
                        break
                if not domain_match:
                    return False
            
            return True
        except Exception as e:
            logger.error(f"Error checking if template should reply: {str(e)}")
            return False
    
    @staticmethod
    def send_auto_reply(email, template, user):
        """
        Send an auto-reply using the specified template.
        """
        try:
            # Prepare the email content
            subject = AutoReplyService.prepare_reply_subject(email.subject, template.subject)
            body = AutoReplyService.prepare_reply_body_from_email(email, template.content, user)
            
            # Send the reply via Gmail API
            from app.services.gmail_service import GmailService
            
            # Use template's sender_email if available
            sender_email = template.sender_email if hasattr(template, 'sender_email') and template.sender_email else None
            
            gmail_service = GmailService(user, sender_email=sender_email)
            if not gmail_service.service:
                logger.error(f"Gmail service not available for user: {user.id}")
                return False
            
            success, message = gmail_service.send_email(
                to=email.sender,
                subject=subject,
                body_text=body,
                thread_id=email.thread_id
            )
            
            if success:
                # Log the action
                from app.models.email import AutoReplyLog
                
                log = AutoReplyLog(
                    user_id=user.id,
                    email_id=email.id,
                    template_id=template.id,
                    thread_id=email.thread_id,
                    sender_email=email.sender,
                    action='auto_reply',
                    details=f"Auto-reply sent successfully: {message}",
                    from_email=sender_email,  # Store which email we sent from
                    is_successful=True
                )
                db.session.add(log)
                db.session.commit()
                
                logger.info(f"Auto-reply sent to {email.sender} for email {email.id}")
                return True
            else:
                # Log the failure
                from app.models.email import AutoReplyLog
                
                log = AutoReplyLog(
                    user_id=user.id,
                    email_id=email.id,
                    template_id=template.id,
                    thread_id=email.thread_id,
                    sender_email=email.sender,
                    action='auto_reply',
                    details=f"Failed to send auto-reply: {message}",
                    from_email=sender_email,
                    is_successful=False
                )
                db.session.add(log)
                db.session.commit()
                
                logger.error(f"Failed to send auto-reply to {email.sender} for email {email.id}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending auto-reply: {str(e)}")
            
            # Log the error
            from app.models.email import AutoReplyLog
            
            log = AutoReplyLog(
                user_id=user.id,
                email_id=email.id,
                template_id=template.id if template else None,
                thread_id=email.thread_id,
                sender_email=email.sender,
                action='auto_reply',
                details=f"Error sending auto-reply: {str(e)}",
                from_email=template.sender_email if hasattr(template, 'sender_email') else None,
                is_successful=False
            )
            db.session.add(log)
            db.session.commit()
            
            return False
    
    @staticmethod
    def is_reply_to_our_email(email, user_id):
        """
        Check if this email appears to be a reply to our own email
        """
        try:
            # Handle both email object and dictionary
            if isinstance(email, dict):
                subject = email.get('subject', '')
            else:
                subject = email.subject or ''
            
            # If the subject starts with "Re:" and we sent an email with that subject
            if subject and subject.lower().startswith('re:'):
                original_subject = subject[3:].strip()
                
                # Import models inside the method to avoid circular imports
                from app.models.email import SentEmail
                
                return SentEmail.query.filter_by(
                    user_id=user_id,
                    subject=original_subject
                ).first() is not None
            return False
        except Exception as e:
            logger.error(f"Error checking if email is reply to our own: {str(e)}")
            return False
    
    @staticmethod
    def prepare_reply_subject(original_subject, template_subject):
        """
        Prepare the subject line for the reply
        """
        try:
            # If template has a custom subject, use it
            if template_subject and template_subject.strip():
                return template_subject
            
            # Add "Re:" prefix if not already present
            if original_subject and not original_subject.lower().startswith('re:'):
                return f"Re: {original_subject}"
            
            return original_subject or "No Subject"
        except Exception as e:
            logger.error(f"Error preparing reply subject: {str(e)}")
            return "Re: No Subject"
    
    @staticmethod
    def prepare_reply_body_from_email(email, template_body, user):
        """
        Prepare the body of the reply from email object, replacing placeholders with actual values
        """
        email_data = {
            'sender': email.sender,
            'subject': email.subject or '',
            'body_text': email.body_text if hasattr(email, 'body_text') else email.body,
            'snippet': email.snippet,
            'id': email.id
        }
        return AutoReplyService.prepare_reply_body_from_data(email_data, template_body, user)
    
    @staticmethod
    def prepare_reply_body_from_data(email_data, template_body, user):
        """
        Prepare the body of the reply from email data, replacing placeholders with actual values
        """
        try:
            # Get email classification if available
            classification = None
            if 'id' in email_data:
                # Import models inside the method to avoid circular imports
                from app.models.email import EmailClassification
                
                classification = EmailClassification.query.filter_by(email_id=email_data['id']).first()
            
            # Ensure all replacement values are strings, even if they're None
            sender_name = AutoReplyService.extract_name_from_email(email_data.get('sender', '')) or "there"
            sender_email = email_data.get('sender', '') or "unknown@example.com"
            original_subject = email_data.get('subject', '') or "No Subject"
            user_name = user.name if hasattr(user, 'name') and user.name else user.username
            date = datetime.now().strftime('%A, %B %d, %Y')
            
            # Replace placeholders in template
            body = template_body.replace('{{name}}', sender_name)
            body = body.replace('{{sender_email}}', sender_email)
            body = body.replace('{{original_subject}}', original_subject)
            body = body.replace('{{user_name}}', user_name)
            body = body.replace('{{date}}', date)
            
            # Add classification info if available
            if classification and classification.category:
                body = body.replace('{{category}}', classification.category.name)
                body = body.replace('{{urgency}}', 'Urgent' if classification.confidence_score > 0.7 else 'Normal')
            else:
                body = body.replace('{{category}}', 'Unclassified')
                body = body.replace('{{urgency}}', 'Unknown')
            
            return body
        except Exception as e:
            logger.error(f"Error preparing reply body from data: {str(e)}")
            return template_body
    
    @staticmethod
    def extract_name_from_email(email):
        """
        Extract name from email address
        """
        try:
            # If email has format "Name <email@domain.com>", extract the name
            if '<' in email and '>' in email:
                return email.split('<')[0].strip().strip('"\'')
            # Otherwise, use the part before @
            return email.split('@')[0]
        except:
            return email