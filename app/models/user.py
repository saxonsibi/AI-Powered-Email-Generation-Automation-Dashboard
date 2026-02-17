# app/models/user.py

from app import db, login_manager
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import json
import calendar
import logging

from app.models.auto_reply import AutoReplyLog, AutoReplyRule, AutoReplyTemplate

logger = logging.getLogger(__name__)

class User(UserMixin, db.Model):
    """User model for authentication and profile information."""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, index=True)
    email = db.Column(db.String(120), unique=True, index=True)
    password_hash = db.Column(db.String(128))
    name = db.Column(db.String(100))  # User's display name
    gmail_credentials = db.Column(db.Text)  # Store Gmail OAuth credentials
    theme_preference = db.Column(db.String(20), default='light')
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    last_login = db.Column(db.DateTime)
    last_email_sync_time = db.Column(db.DateTime, nullable=True, default=datetime.utcnow)
    
    # Add this new field for tracking sent email sync
    last_sent_email_sync = db.Column(db.Float, nullable=True, default=0)
    
    # Auto-reply settings
    business_hours = db.Column(db.Text)  # JSON: {"days": ["Monday", "Tuesday"], "start_time": "09:00", "end_time": "17:00"}
    auto_reply_enabled = db.Column(db.Boolean, default=True)
    auto_reply_cooldown = db.Column(db.Integer, default=24)  # Hours between auto-replies to same sender
    
    # Follow-up settings
    follow_up_enabled = db.Column(db.Boolean, default=True)
    default_follow_up_delay = db.Column(db.Integer, default=48)  # Hours
    max_follow_ups = db.Column(db.Integer, default=3)
    
    # Classification settings
    classification_enabled = db.Column(db.Boolean, default=True)
    primary_category_senders = db.Column(db.Text)  # JSON array of sender domains/emails
    
    # Relationships - Using string references to avoid circular imports
    emails = db.relationship('Email', back_populates='user', lazy='dynamic')
    sent_emails = db.relationship('SentEmail', back_populates='user', lazy='dynamic')
    automation_rules = db.relationship('AutomationRule', back_populates='user', lazy='dynamic')
    
    # Auto-reply relationships with proper cascade
    auto_reply_templates = db.relationship('AutoReplyTemplate', back_populates='user', lazy='dynamic', cascade='all, delete-orphan')
    auto_reply_rules = db.relationship('AutoReplyRule', back_populates='user', lazy='dynamic', cascade='all, delete-orphan')
    auto_reply_logs = db.relationship('AutoReplyLog', back_populates='user', lazy='dynamic', cascade='all, delete-orphan')
    
    # Other relationships
    follow_ups = db.relationship('FollowUp', back_populates='user', lazy='dynamic')
    follow_up_rules = db.relationship('FollowUpRule', back_populates='user', lazy='dynamic')
    follow_up_templates = db.relationship('FollowUpTemplate', back_populates='user', lazy='dynamic')
    email_categories = db.relationship('EmailCategory', back_populates='user', lazy='dynamic')
    classification_rules = db.relationship('ClassificationRule', back_populates='user', lazy='dynamic')
    draft_emails = db.relationship('DraftEmail', back_populates='user', lazy='dynamic')
    
    def set_password(self, password):
        """Set password hash."""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """Check if provided password matches hash."""
        return check_password_hash(self.password_hash, password)
    
    def update_last_login(self):
        """Update the last login timestamp."""
        self.last_login = datetime.utcnow()
        db.session.commit()
    
    def update_last_sent_email_sync(self):
        """Update the last sent email sync timestamp."""
        self.last_sent_email_sync = datetime.utcnow().timestamp()
        db.session.commit()
    
    def get_business_hours(self):
        """Get business hours as a dictionary."""
        if not self.business_hours:
            return {
                'days': ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'],
                'start_time': '09:00',
                'end_time': '17:00'
            }
        try:
            return json.loads(self.business_hours)
        except:
            return {
                'days': ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'],
                'start_time': '09:00',
                'end_time': '17:00'
            }
    
    def set_business_hours(self, days, start_time, end_time):
        """Set business hours."""
        self.business_hours = json.dumps({
            'days': days,
            'start_time': start_time,
            'end_time': end_time
        })
        db.session.commit()
    
    def get_primary_category_senders(self):
        """Get list of primary category senders."""
        if not self.primary_category_senders:
            return []
        try:
            return json.loads(self.primary_category_senders)
        except:
            return []
    
    def set_primary_category_senders(self, senders):
        """Set list of primary category senders."""
        self.primary_category_senders = json.dumps(senders)
        db.session.commit()
    
    def is_within_business_hours(self, check_time=None):
        """Check if current time is within user's business hours."""
        business_hours = self.get_business_hours()
        now = check_time or datetime.utcnow()
        current_day = now.strftime('%A')
        current_time = now.time()
        
        # Check if today is a business day
        if current_day not in business_hours.get('days', []):
            return False
        
        # Check if current time is within business hours
        from datetime import time as dt_time
        start_time = dt_time.fromisoformat(business_hours['start_time'])
        end_time = dt_time.fromisoformat(business_hours['end_time'])
        
        return start_time <= current_time <= end_time
    
    def can_send_auto_reply_to(self, sender_email):
        """Check if we can send auto-reply to this sender (cooldown check)."""
        if not self.auto_reply_enabled:
            return False
        
        # Import models inside the method to avoid circular imports
        from app.models.auto_reply import AutoReplyLog
        
        # Check if we've sent an auto-reply to this sender recently
        cooldown_period = timedelta(hours=self.auto_reply_cooldown)
        recent_reply = AutoReplyLog.query.filter_by(
            user_id=self.id,
            sender_email=sender_email
        ).filter(
            AutoReplyLog.created_at >= datetime.utcnow() - cooldown_period
        ).first()
        
        return recent_reply is None
    
    def can_send_follow_up_to(self, recipient_email, thread_id):
        """Check if we can send a follow-up to this recipient/thread."""
        if not self.follow_up_enabled:
            return False
        
        # Import models inside the method to avoid circular imports
        from app.models.follow_up import FollowUp
        
        # Check if we've already sent the maximum number of follow-ups for this thread
        follow_up_count = FollowUp.query.filter_by(
            user_id=self.id,
            thread_id=thread_id,
            recipient_email=recipient_email,
            status='sent'
        ).count()
        
        if follow_up_count >= self.max_follow_ups:
            return False
        
        return True
    
    def get_next_business_hour(self):
        """Calculate the next business hour based on user's business hours."""
        now = datetime.utcnow()
        business_hours = self.get_business_hours()
        
        # If no business hours are set, return tomorrow at 9 AM
        if not business_hours:
            tomorrow = now + timedelta(days=1)
            return tomorrow.replace(hour=9, minute=0, second=0, microsecond=0)
        
        # Get current day of week (0=Monday, 6=Sunday)
        current_day = now.weekday()
        
        # Check if today is a business day
        today_key = calendar.day_name[current_day]
        if today_key in business_hours.get('days', []):
            # Get today's business hours
            start_hour = int(business_hours['start_time'].split(':')[0])
            end_hour = int(business_hours['end_time'].split(':')[0])
            
            # If current time is before business hours, return today's start time
            if now.hour < start_hour:
                return now.replace(hour=start_hour, minute=0, second=0, microsecond=0)
            
            # If current time is during business hours, return now + 1 hour
            if start_hour <= now.hour < end_hour:
                return now + timedelta(hours=1)
        
        # Find the next business day
        days_ahead = 1
        while days_ahead <= 7:
            next_day = (current_day + days_ahead) % 7
            next_day_key = calendar.day_name[next_day]
            
            if next_day_key in business_hours.get('days', []):
                next_date = now + timedelta(days=days_ahead)
                start_hour = int(business_hours['start_time'].split(':')[0])
                return next_date.replace(hour=start_hour, minute=0, second=0, microsecond=0)
            
            days_ahead += 1
        
        # If no business days found (unlikely), return tomorrow at 9 AM
        tomorrow = now + timedelta(days=1)
        return tomorrow.replace(hour=9, minute=0, second=0, microsecond=0)
    
    def get_active_follow_up_rules(self):
        """Get all active follow-up rules for this user."""
        # Import models inside the method to avoid circular imports
        from app.models.automation import FollowUpRule
        return FollowUpRule.query.filter_by(user_id=self.id, is_active=True).all()
    
    def create_follow_up_rule(self, name, delay_hours, max_count, template_text, conditions=None):
        """Create a new follow-up rule for this user."""
        # Import models inside the method to avoid circular imports
        from app.models.automation import FollowUpRule
        
        try:
            new_rule = FollowUpRule(
                user_id=self.id,
                name=name,
                delay_hours=delay_hours,
                max_count=max_count,
                template_text=template_text,
                conditions=json.dumps(conditions) if conditions else None
            )
            
            db.session.add(new_rule)
            db.session.commit()
            
            logger.info(f"Created follow-up rule '{name}' for user {self.id}")
            return new_rule
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating follow-up rule: {str(e)}")
            return None
    
    def get_pending_follow_ups(self):
        """Get all pending follow-ups for this user."""
        # Import models inside the method to avoid circular imports
        from app.models.follow_up import FollowUp
        
        return FollowUp.query.filter_by(
            user_id=self.id,
            status='pending'
        ).order_by(FollowUp.scheduled_at).all()
    
    def get_email_categories(self):
        """Get all email categories for this user."""
        # Import models inside the method to avoid circular imports
        from app.models.email import EmailCategory
        return EmailCategory.query.filter_by(user_id=self.id).all()
    
    def create_email_category(self, name, color=None, is_default=False):
        """Create a new email category for this user."""
        # Import models inside the method to avoid circular imports
        from app.models.email import EmailCategory
        
        try:
            # If this is set as default, unset any existing default
            if is_default:
                EmailCategory.query.filter_by(user_id=self.id, is_default=True).update({'is_default': False})
            
            new_category = EmailCategory(
                user_id=self.id,
                name=name,
                color=color or '#3498db',  # Default blue color
                is_default=is_default
            )
            
            db.session.add(new_category)
            db.session.commit()
            
            logger.info(f"Created email category '{name}' for user {self.id}")
            return new_category
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating email category: {str(e)}")
            return None
    
    def get_classification_rules(self):
        """Get all classification rules for this user."""
        # Import models inside the method to avoid circular imports
        from app.models.automation import ClassificationRule
        return ClassificationRule.query.filter_by(user_id=self.id, is_active=True).all()
    
    def create_classification_rule(self, category_id, conditions, priority=0):
        """Create a new classification rule for this user."""
        # Import models inside the method to avoid circular imports
        from app.models.automation import ClassificationRule
        
        try:
            new_rule = ClassificationRule(
                user_id=self.id,
                category_id=category_id,
                conditions=json.dumps(conditions),
                priority=priority
            )
            
            db.session.add(new_rule)
            db.session.commit()
            
            logger.info(f"Created classification rule for category {category_id} for user {self.id}")
            return new_rule
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating classification rule: {str(e)}")
            return None
    
    # Auto-reply specific methods
    def get_auto_reply_templates(self):
        """Get all auto-reply templates for this user."""
        return self.auto_reply_templates.all()
    
    def create_auto_reply_template(self, name, reply_subject, reply_body):
        """Create a new auto-reply template for this user."""
        try:
            new_template = AutoReplyTemplate(
                user_id=self.id,
                name=name,
                reply_subject=reply_subject,
                reply_body=reply_body
            )
            
            db.session.add(new_template)
            db.session.commit()
            
            logger.info(f"Created auto-reply template '{name}' for user {self.id}")
            return new_template
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating auto-reply template: {str(e)}")
            return None
    
    def get_auto_reply_rules(self):
        """Get all auto-reply rules for this user."""
        return self.auto_reply_rules.all()
    
    def create_auto_reply_rule(self, name, template_id, priority=5, trigger_conditions=None, 
                              delay_minutes=0, cooldown_hours=24, reply_once_per_thread=True,
                              prevent_auto_reply_to_auto=True, ignore_mailing_lists=True,
                              stop_on_sender_reply=True):
        """Create a new auto-reply rule for this user."""
        try:
            new_rule = AutoReplyRule(
                user_id=self.id,
                name=name,
                template_id=template_id,
                priority=priority,
                trigger_conditions=json.dumps(trigger_conditions) if trigger_conditions else None,
                delay_minutes=delay_minutes,
                cooldown_hours=cooldown_hours,
                reply_once_per_thread=reply_once_per_thread,
                prevent_auto_reply_to_auto=prevent_auto_reply_to_auto,
                ignore_mailing_lists=ignore_mailing_lists,
                stop_on_sender_reply=stop_on_sender_reply
            )
            
            db.session.add(new_rule)
            db.session.commit()
            
            logger.info(f"Created auto-reply rule '{name}' for user {self.id}")
            return new_rule
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating auto-reply rule: {str(e)}")
            return None
    
    def get_auto_reply_logs(self, limit=100):
        """Get auto-reply logs for this user."""
        return self.auto_reply_logs.order_by(AutoReplyLog.created_at.desc()).limit(limit).all()
    
    def to_dict(self):
        """Convert user object to dictionary."""
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'name': self.name,
            'theme_preference': self.theme_preference,
            'business_hours': self.get_business_hours(),
            'auto_reply_enabled': self.auto_reply_enabled,
            'auto_reply_cooldown': self.auto_reply_cooldown,
            'follow_up_enabled': self.follow_up_enabled,
            'default_follow_up_delay': self.default_follow_up_delay,
            'max_follow_ups': self.max_follow_ups,
            'classification_enabled': self.classification_enabled,
            'primary_category_senders': self.get_primary_category_senders(),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_login': self.last_login.isoformat() if self.last_login else None,
            'last_sent_email_sync': self.last_sent_email_sync
        }
    
    # Static methods for database queries
    @staticmethod
    def username_exists(username):
        """Check if a username already exists."""
        return User.query.filter_by(username=username).first() is not None
    
    @staticmethod
    def email_exists(email):
        """Check if an email already exists."""
        return User.query.filter_by(email=email).first() is not None
    
    @staticmethod
    def get_by_username(username):
        """Get user by username."""
        return User.query.filter_by(username=username).first()
    
    @staticmethod
    def get_by_email(email):
        """Get user by email."""
        return User.query.filter_by(email=email).first()
    
    @staticmethod
    def get_by_username_or_email(identifier):
        """Get user by username or email."""
        return User.query.filter(
            (User.username == identifier) | (User.email == identifier)
        ).first()
    
    @staticmethod
    def create_user(username, email, password, name=None):
        """
        Create a new user with validation.
        
        Args:
            username (str): The username for the new user
            email (str): The email for the new user
            password (str): The password for the new user
            name (str, optional): The display name for the new user
            
        Returns:
            tuple: (success: bool, user: User or None, error: str or None)
        """
        # Validate input
        if not username or not email or not password:
            return False, None, "All fields are required"
        
        if len(username) < 3:
            return False, None, "Username must be at least 3 characters long"
        
        if len(password) < 6:
            return False, None, "Password must be at least 6 characters long"
        
        # Check if username already exists
        if User.username_exists(username):
            return False, None, "Username already exists"
        
        # Check if email already exists
        if User.email_exists(email):
            return False, None, "Email already exists"
        
        # Create new user
        try:
            new_user = User(username=username, email=email, name=name)
            new_user.set_password(password)
            
            # Set default business hours
            new_user.set_business_hours(
                days=['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'],
                start_time='09:00',
                end_time='17:00'
            )
            
            db.session.add(new_user)
            db.session.commit()
            
            # Create default email categories after the user is committed
            # Import models inside the method to avoid circular imports
            from app.models.email import EmailCategory
            default_categories = [
                {'name': 'Important', 'color': '#e74c3c', 'is_default': False},
                {'name': 'Work', 'color': '#3498db', 'is_default': False},
                {'name': 'Personal', 'color': '#2ecc71', 'is_default': False},
                {'name': 'Promotional', 'color': '#f39c12', 'is_default': False},
                {'name': 'Newsletter', 'color': '#9b59b6', 'is_default': False},
                {'name': 'Finance', 'color': '#1abc9c', 'is_default': False},
                {'name': 'Travel', 'color': '#34495e', 'is_default': False},
                {'name': 'Default', 'color': '#95a5a6', 'is_default': True}
            ]
            
            for category_data in default_categories:
                new_user.create_email_category(
                    name=category_data['name'],
                    color=category_data['color'],
                    is_default=category_data['is_default']
                )
            
            return True, new_user, None
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating user: {str(e)}")
            return False, None, str(e)
    
    @staticmethod
    def authenticate_user(identifier, password):
        """
        Authenticate a user with username/email and password.
        
        Args:
            identifier (str): Username or email
            password (str): Password
            
        Returns:
            tuple: (success: bool, user: User or None, error: str or None)
        """
        if not identifier or not password:
            return False, None, "Username/email and password are required"
        
        user = User.get_by_username_or_email(identifier)
        
        if not user:
            return False, None, "Invalid username/email or password"
        
        if not user.check_password(password):
            return False, None, "Invalid username/email or password"
        
        # Update last login time
        user.update_last_login()
        
        return True, user, None
    
    @staticmethod
    def change_password(user_id, current_password, new_password):
        """
        Change user password.
        
        Args:
            user_id (int): ID of the user
            current_password (str): Current password for verification
            new_password (str): New password
            
        Returns:
            tuple: (success: bool, error: str or None)
        """
        if not current_password or not new_password:
            return False, "Current password and new password are required"
        
        if len(new_password) < 6:
            return False, "New password must be at least 6 characters long"
        
        user = User.query.get(user_id)
        if not user:
            return False, "User not found"
        
        if not user.check_password(current_password):
            return False, "Current password is incorrect"
        
        try:
            user.set_password(new_password)
            db.session.commit()
            return True, None
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error changing password: {str(e)}")
            return False, str(e)
    
    @staticmethod
    def update_profile(user_id, data):
        """
        Update user profile.
        
        Args:
            user_id (int): ID of the user
            data (dict): Dictionary of fields to update
            
        Returns:
            tuple: (success: bool, error: str or None)
        """
        user = User.query.get(user_id)
        if not user:
            return False, "User not found"
        
        try:
            # Update allowed fields
            if 'username' in data and data['username'] != user.username:
                if User.username_exists(data['username']):
                    return False, "Username already exists"
                if len(data['username']) < 3:
                    return False, "Username must be at least 3 characters long"
                user.username = data['username']
            
            if 'email' in data and data['email'] != user.email:
                if User.email_exists(data['email']):
                    return False, "Email already exists"
                user.email = data['email']
            
            if 'name' in data:
                user.name = data['name']
            
            if 'theme_preference' in data:
                user.theme_preference = data['theme_preference']
            
            # Update automation settings
            if 'auto_reply_enabled' in data:
                user.auto_reply_enabled = data['auto_reply_enabled']
            
            if 'auto_reply_cooldown' in data:
                user.auto_reply_cooldown = data['auto_reply_cooldown']
            
            if 'business_hours' in data:
                days = data['business_hours'].get('days', [])
                start_time = data['business_hours'].get('start_time', '09:00')
                end_time = data['business_hours'].get('end_time', '17:00')
                user.set_business_hours(days, start_time, end_time)
            
            if 'follow_up_enabled' in data:
                user.follow_up_enabled = data['follow_up_enabled']
            
            if 'default_follow_up_delay' in data:
                user.default_follow_up_delay = data['default_follow_up_delay']
            
            if 'max_follow_ups' in data:
                user.max_follow_ups = data['max_follow_ups']
            
            if 'classification_enabled' in data:
                user.classification_enabled = data['classification_enabled']
            
            if 'primary_category_senders' in data:
                user.set_primary_category_senders(data['primary_category_senders'])
            
            db.session.commit()
            return True, None
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating profile: {str(e)}")
            return False, str(e)
    
    def __repr__(self):
        return f'<User {self.username}>'

@login_manager.user_loader
def load_user(user_id):
    """Load user by ID for Flask-Login."""
    return User.query.get(int(user_id))