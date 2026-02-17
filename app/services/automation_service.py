# app/services/automation_service.py
from datetime import datetime, timedelta
from app import db
import json
from email.utils import parsedate_to_datetime
from sqlalchemy import and_
import logging

logger = logging.getLogger(__name__)

class AutomationService:
    """Service for email automation tasks."""
    
    def __init__(self, user=None):
        self.user = user
        # Import AI service inside the method to avoid circular imports
        from app.services.ai_service import AIService
        self.ai_service = AIService()
    
    def process_new_emails(self, user_id):
        """
        Process new emails for a user and count only those received after the last sync time.
        Updates the last_email_sync_time after processing.
        Returns the count of new emails.
        """
        # Import models inside the method to avoid circular imports
        from app.models.user import User
        from app.models.email import Email
        from app.services.gmail_service import GmailService
        
        user = User.query.get(user_id)
        if not user:
            return {"success": False, "error": "User not found"}
        
        gmail_service = GmailService(user)
        if not gmail_service.service:
            return {"success": False, "error": "Failed to connect to Gmail"}
        
        try:
            # Get the last sync time
            last_sync = user.last_email_sync_time
            
            # Fetch emails from Gmail API
            # Only fetch emails after last sync time
            query = f"after:{int(last_sync.timestamp())}" if last_sync else None
            messages_result = gmail_service.service.users().messages().list(
                userId='me',
                q=query
            ).execute()
            
            messages = messages_result.get('messages', [])
            new_email_count = 0
            
            # Get active automation rules for the user
            # Import models inside the method to avoid circular imports
            from app.models.automation import AutomationRule
            
            rules = AutomationRule.query.filter_by(user_id=user_id, is_active=True).all()
            
            # Process each message
            for message_ref in messages:
                msg_id = message_ref['id']
                
                # Get full message details
                message = gmail_service.service.users().messages().get(
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
                    email_date = self._parse_gmail_date(date_str)
                    
                    if not last_sync or email_date > last_sync:
                        # This is a new email
                        new_email_count += 1
                        
                        # Save to database if not already exists
                        if not Email.query.filter_by(gmail_id=msg_id, user_id=user_id).first():
                            email = self._save_email_to_db(message, user_id)
                            
                            if email:
                                # Apply classification
                                classification = self.ai_service.classify_email(email.body_text)
                                email.is_urgent = classification.get('is_urgent', False)
                                
                                # Apply automation rules
                                for rule in rules:
                                    if self._evaluate_rule(rule, email):
                                        self._execute_action(rule, email, gmail_service)
            
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
    
    def check_and_execute_rules(self):
        """
        Check emails against automation rules and execute matching rules.
        This method is designed to be called by the scheduler.
        """
        if not self.user:
            logger.error("No user provided for automation check")
            return
        
        try:
            # Import models inside the method to avoid circular imports
            from app.models.automation import AutomationRule
            from app.models.email import Email
            
            # Get the user's active automation rules
            rules = AutomationRule.query.filter_by(
                user_id=self.user.id, 
                is_active=True
            ).all()
            
            if not rules:
                logger.info(f"No active rules for user {self.user.id}")
                return
            
            # Get recent emails that haven't been processed by automation
            # Check emails received in the last 24 hours
            since = datetime.utcnow() - timedelta(days=1)
            recent_emails = Email.query.filter(
                and_(
                    Email.user_id == self.user.id,
                    Email.received_at >= since,  # Using received_at instead of date_received
                    Email.processed == False  # Using processed instead of automation_processed
                )
            ).all()
            
            logger.info(f"Checking {len(recent_emails)} emails against {len(rules)} rules for user {self.user.id}")
            
            for email in recent_emails:
                self.process_email_against_rules(email, rules)
            
            logger.info(f"Completed automation check for user {self.user.id}")
        except Exception as e:
            logger.error(f"Error in automation check for user {self.user.id}: {str(e)}")
    
    def process_email_against_rules(self, email, rules):
        """Process a single email against all rules"""
        matched_rules = []
        
        for rule in rules:
            if self._evaluate_rule(rule, email):
                matched_rules.append(rule)
                
                # Execute actions
                # Import services inside the method to avoid circular imports
                from app.services.gmail_service import GmailService
                
                gmail_service = GmailService(self.user)
                self._execute_action(rule, email, gmail_service)
        
        # Mark email as processed
        if matched_rules:
            rule_ids = ",".join([str(rule.id) for rule in matched_rules])
            email.processed = True  # Using processed instead of automation_processed
            email.automation_rules_applied = rule_ids
            email.processed_at = datetime.utcnow()  # Using processed_at instead of automation_processed_at
            db.session.commit()
            
            logger.info(f"Applied automation rules {rule_ids} to email {email.id}")
    
    def check_for_new_emails(self, user_id):
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
                    Email.received_at > last_sync  # Using received_at instead of date_received
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
    
    def _parse_gmail_date(self, date_str):
        """Parse Gmail date string to datetime object."""
        # Gmail date format example: "Tue, 15 Jun 2021 16:30:00 -0700"
        try:
            return parsedate_to_datetime(date_str)
        except:
            return datetime.utcnow()
    
    def _save_email_to_db(self, message, user_id):
        """Save email to database."""
        try:
            # Extract headers
            headers = message.get('payload', {}).get('headers', [])
            subject = next((h['value'] for h in headers if h['name'] == 'Subject'), '(No Subject)')
            from_email = next((h['value'] for h in headers if h['name'] == 'From'), '')
            date_str = next((h['value'] for h in headers if h['name'] == 'Date'), '')
            
            # Parse date
            date_received = self._parse_gmail_date(date_str)
            
            # Get snippet
            snippet = message.get('snippet', '')
            
            # Create new email record
            # Import models inside the method to avoid circular imports
            from app.models.email import Email
            
            new_email = Email(
                gmail_id=message['id'],
                user_id=user_id,
                sender=from_email,
                subject=subject,
                snippet=snippet,
                received_at=date_received,  # Using received_at instead of date_received
                is_read=False
            )
            
            db.session.add(new_email)
            db.session.commit()
            
            return new_email
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error saving email to database: {str(e)}")
            return None
    
    def _evaluate_rule(self, rule, email):
        """Evaluate if an automation rule should be triggered for an email."""
        try:
            # Check if this rule has already been applied to this email
            if email.automation_rules_applied and str(rule.id) in email.automation_rules_applied:
                return False
            
            conditions = json.loads(rule.trigger_condition)
            
            # Check sender condition
            if 'sender' in conditions:
                if conditions['sender'].lower() not in email.sender.lower():
                    return False
            
            # Check subject condition
            if 'subject_contains' in conditions:
                if conditions['subject_contains'].lower() not in email.subject.lower():
                    return False
            
            # Check body condition
            if 'body_contains' in conditions:
                if not email.body_text or conditions['body_contains'].lower() not in email.body_text.lower():
                    return False
            
            # Check category condition
            if 'category' in conditions:
                # This would require the email to be classified first
                # For now, we'll skip this check
                pass
            
            # Check urgency condition
            if 'is_urgent' in conditions:
                if conditions['is_urgent'] != email.is_urgent:
                    return False
            
            return True
        
        except Exception as e:
            logger.error(f"Error evaluating rule: {str(e)}")
            return False
    
    def _execute_action(self, rule, email, gmail_service):
        """Execute the action specified in an automation rule."""
        try:
            actions = json.loads(rule.action)
            
            # Auto-reply action
            if 'auto_reply' in actions:
                reply_data = actions['auto_reply']
                success, message = gmail_service.send_email(
                    to=email.sender,
                    subject=f"Re: {email.subject}",
                    body_text=reply_data['message'],
                    thread_id=email.gmail_id  # Using gmail_id instead of message_id
                )
                
                # Log the action
                # Import models inside the method to avoid circular imports
                from app.models.automation_log import AutomationLog
                
                log = AutomationLog(
                    user_id=email.user_id,
                    rule_id=rule.id,
                    email_id=email.id,
                    action_type='auto_reply',
                    status='success' if success else 'failed',
                    message=message
                )
                db.session.add(log)
                db.session.commit()
            
            # Label action
            if 'add_label' in actions:
                label = actions['add_label']
                # This would require implementing Gmail API label functionality
                # For now, we'll just update the local email record
                email.label = label
                
                # Log the action
                # Import models inside the method to avoid circular imports
                from app.models.automation_log import AutomationLog
                
                log = AutomationLog(
                    user_id=email.user_id,
                    rule_id=rule.id,
                    email_id=email.id,
                    action_type='add_label',
                    status='success',
                    message=f"Added label: {label}"
                )
                db.session.add(log)
                db.session.commit()
            
            # Follow-up action
            if 'schedule_follow_up' in actions:
                follow_up_data = actions['schedule_follow_up']
                delay_days = follow_up_data.get('delay_days', 3)
                
                # Generate follow-up content
                follow_up_content = self.ai_service.generate_follow_up(email, delay_days)
                
                # Create follow-up using the new FollowUpService
                from app.services.follow_up_service import FollowUpService
                
                follow_up = FollowUpService.create_follow_up(
                    email_id=email.id,
                    user_id=email.user_id,
                    follow_up_rule_id=rule.id,
                    delay_hours=delay_days * 24,  # Convert days to hours
                    template_text=follow_up_content.get('body', '')
                )
                
                if follow_up:
                    # Log the action
                    # Import models inside the method to avoid circular imports
                    from app.models.automation import AutomationLog
                    
                    log = AutomationLog(
                        user_id=email.user_id,
                        rule_id=rule.id,
                        email_id=email.id,
                        action_type='schedule_follow_up',
                        status='success',
                        message=f"Scheduled follow-up in {delay_days} days"
                    )
                    db.session.add(log)
                    db.session.commit()
        
        except Exception as e:
            logger.error(f"Error executing action: {str(e)}")
            
            # Log the error
            # Import models inside the method to avoid circular imports
            from app.models.automation import AutomationLog
            
            log = AutomationLog(
                user_id=email.user_id,
                rule_id=rule.id,
                email_id=email.id,
                action_type='error',
                status='failed',
                message=str(e)
            )
            db.session.add(log)
            db.session.commit()
    
    def send_follow_up(self, rule, email):
        """Send a follow-up email based on a rule and email."""
        try:
            # Get the follow-up data from the rule
            actions = json.loads(rule.action)
            follow_up_data = actions.get('schedule_follow_up', {})
            
            if not follow_up_data:
                logger.error(f"No follow-up data found in rule {rule.id}")
                return False
            
            # Generate follow-up content
            follow_up_content = self.ai_service.generate_follow_up(email, follow_up_data.get('delay_days', 3))
            
            # Create the follow-up email
            follow_up_subject = f"Follow-up: {email.subject}" if email.subject else "Follow-up to our conversation"
            
            # Send the email via Gmail API
            # Import services inside the method to avoid circular imports
            from app.services.gmail_service import GmailService
            
            gmail_service = GmailService(self.user)
            success, message = gmail_service.send_email(
                to=email.sender,
                subject=follow_up_subject,
                body_text=follow_up_content.get('body', ''),
                thread_id=email.gmail_id  # Using gmail_id instead of message_id
            )
            
            if success:
                # Log the action
                # Import models inside the method to avoid circular imports
                from app.models.automation_log import AutomationLog
                
                log = AutomationLog(
                    user_id=self.user.id,
                    rule_id=rule.id,
                    email_id=email.id,
                    action_type='follow_up',
                    status='success',
                    message=f"Follow-up sent to {email.sender}"
                )
                db.session.add(log)
                db.session.commit()
                
                logger.info(f"Follow-up sent for rule {rule.id} to {email.sender}")
                return True
            else:
                # Log the failure
                # Import models inside the method to avoid circular imports
                from app.models.automation import AutomationLog
                
                log = AutomationLog(
                    user_id=self.user.id,
                    rule_id=rule.id,
                    email_id=email.id,
                    action_type='follow_up',
                    status='failed',
                    message=message
                )
                db.session.add(log)
                db.session.commit()
                
                logger.error(f"Failed to send follow-up for rule {rule.id}: {message}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending follow-up for rule {rule.id}: {str(e)}")
            
            # Log the error
            # Import models inside the method to avoid circular imports
            from app.models.automation import AutomationLog
            
            log = AutomationLog(
                user_id=self.user.id,
                rule_id=rule.id,
                email_id=email.id,
                action_type='follow_up',
                status='failed',
                message=str(e)
            )
            db.session.add(log)
            db.session.commit()
            
            return False
    
    def send_scheduled_follow_up(self, follow_up_id):
        """Send a scheduled follow-up email."""
        # Import models inside the method to avoid circular imports
        from app.models.follow_up import FollowUp
        from app.models.automation_log import AutomationLog
        from app.services.gmail_service import GmailService
        
        follow_up = FollowUp.query.get(follow_up_id)
        if not follow_up or follow_up.status == 'sent':  # Using status instead of is_sent
            return
        
        try:
            gmail_service = GmailService(self.user)
            
            if gmail_service.service:
                # Get the original email for context
                email = follow_up.email
                
                success, message = gmail_service.send_email(
                    to=follow_up.recipient_email,
                    subject=f"Follow-up: {email.subject if email else 'Follow-up'}",
                    body_text=follow_up.content,
                    thread_id=follow_up.thread_id
                )
                
                if success:
                    follow_up.status = 'sent'  # Using status instead of is_sent
                    follow_up.sent_at = datetime.utcnow()
                    db.session.commit()
                    
                    # Log the action
                    log = AutomationLog(
                        user_id=follow_up.user_id,
                        rule_id=follow_up.follow_up_rule_id,
                        email_id=follow_up.email_id,
                        action_type='follow_up',
                        status='success',
                        message="Follow-up sent successfully"
                    )
                    db.session.add(log)
                    db.session.commit()
                else:
                    # Log the failure
                    log = AutomationLog(
                        user_id=follow_up.user_id,
                        rule_id=follow_up.follow_up_rule_id,
                        email_id=follow_up.email_id,
                        action_type='follow_up',
                        status='failed',
                        message=message
                    )
                    db.session.add(log)
                    db.session.commit()
        except Exception as e:
            logger.error(f"Error sending scheduled follow-up: {str(e)}")
            
            # Log the error
            # Import models inside the method to avoid circular imports
            from app.models.automation import AutomationLog
            
            log = AutomationLog(
                user_id=follow_up.user_id,
                rule_id=follow_up.follow_up_rule_id,
                email_id=follow_up.email_id,
                action_type='follow_up',
                status='failed',
                message=str(e)
            )
            db.session.add(log)
            db.session.commit()
    
    def create_automation_rule(self, user_id, name, trigger_condition, action):
        """Create a new automation rule for a user."""
        # Import models inside the method to avoid circular imports
        from app.models.automation import AutomationRule
        
        rule = AutomationRule(
            name=name,
            trigger_condition=json.dumps(trigger_condition),
            action=json.dumps(action),
            user_id=user_id
        )
        db.session.add(rule)
        db.session.commit()
        return rule
    
    def update_automation_rule(self, rule_id, name=None, trigger_condition=None, action=None, is_active=None):
        """Update an existing automation rule."""
        # Import models inside the method to avoid circular imports
        from app.models.automation import AutomationRule
        
        rule = AutomationRule.query.get(rule_id)
        if not rule:
            return None
        
        if name is not None:
            rule.name = name
        if trigger_condition is not None:
            rule.trigger_condition = json.dumps(trigger_condition)
        if action is not None:
            rule.action = json.dumps(action)
        if is_active is not None:
            rule.is_active = is_active
        
        db.session.commit()
        return rule
    
    def delete_automation_rule(self, rule_id):
        """Delete an automation rule."""
        # Import models inside the method to avoid circular imports
        from app.models.automation import AutomationRule
        
        rule = AutomationRule.query.get(rule_id)
        if rule:
            db.session.delete(rule)
            db.session.commit()
            return True
        return False
    
    def get_automation_rules(self, user_id):
        """Get all automation rules for a user."""
        # Import models inside the method to avoid circular imports
        from app.models.automation import AutomationRule
        
        return AutomationRule.query.filter_by(user_id=user_id).all()
    
    def get_automation_logs(self, user_id, limit=50):
        """Get automation logs for a user."""
        # Import models inside the method to avoid circular imports
        from app.models.automation_log import AutomationLog
        
        return AutomationLog.query.filter_by(user_id=user_id).order_by(
            AutomationLog.created_at.desc()
        ).limit(limit).all()