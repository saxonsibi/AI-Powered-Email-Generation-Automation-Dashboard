from app import db, logger
from datetime import datetime, timedelta, date, time
import logging
import json
from enum import Enum
import pytz

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
    COMPLETED = "Completed"  # Added for consistency

class FollowUpService:
    # India timezone for all operations
    india_tz = pytz.timezone('Asia/Kolkata')
    
    @staticmethod
    def create_rule(rule_data):
        """
        Create a new follow-up rule with proper timezone handling.
        
        Args:
            rule_data: Dictionary containing rule data
            
        Returns:
            FollowUpRule: The created rule or None if failed
        """
        try:
            # Import models inside method to avoid circular imports
            from app.models.automation import FollowUpRule
            from app.models.follow_up import FollowUpSequence
            
            # Parse recipient emails if provided
            recipient_emails = None
            if 'recipient_emails' in rule_data and rule_data['recipient_emails']:
                recipient_emails = json.dumps(rule_data['recipient_emails'])
            
            # Handle delay unit conversion
            delay_hours = rule_data.get('delay_hours', 24)
            delay_unit = rule_data.get('delay_unit', 'hours')
            
            if delay_unit == 'days':
                delay_hours = delay_hours * 24
            elif delay_unit == 'minutes':
                delay_hours = delay_hours / 60
            
            # Create the rule with timezone-aware timestamps
            now_utc = datetime.now(pytz.UTC)
            now_india = now_utc.astimezone(FollowUpService.india_tz)
            
            # Only include valid fields for FollowUpRule model
            rule = FollowUpRule(
                user_id=rule_data['user_id'],
                name=rule_data['name'],
                trigger_type=rule_data.get('trigger_type', 'No Reply'),
                delay_hours=delay_hours,
                max_count=rule_data.get('max_count', 3),
                template_text=rule_data.get('template_text', ''),
                is_active=rule_data.get('is_active', True),
                conditions=json.dumps(rule_data.get('conditions', {})),
                message_type=rule_data.get('message_type', 'Template-Based'),
                apply_to_all=rule_data.get('apply_to_all', True),
                campaign_id=rule_data.get('campaign_id'),
                recipient_emails=recipient_emails,
                stop_on_reply=rule_data.get('stop_on_reply', True),
                business_days_only=rule_data.get('business_days_only', True),
                send_window_start=datetime.strptime(rule_data.get('send_window_start', '09:00'), '%H:%M').time(),
                send_window_end=datetime.strptime(rule_data.get('send_window_end', '18:00'), '%H:%M').time(),
                created_at=now_utc
                # Removed last_checked as it's not a valid field in the model
            )
            
            db.session.add(rule)
            db.session.flush()  # Get the ID without committing
            
            # Add sequences if provided
            if 'sequences' in rule_data:
                for seq_data in rule_data['sequences']:
                    sequence = FollowUpSequence(
                        rule_id=rule.id,
                        sequence_number=seq_data['sequence_number'],
                        delay_days=seq_data['delay_days'],
                        subject=seq_data.get('subject'),
                        message=seq_data.get('message'),
                        tone=seq_data.get('tone'),
                        length=seq_data.get('length')
                    )
                    db.session.add(sequence)
            
            db.session.commit()
            logger.info(f"Created follow-up rule {rule.id}: {rule.name} with delay {delay_hours} hours")
            return rule
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating follow-up rule: {str(e)}")
            return None
    
    @staticmethod
    def update_rule(rule_id, rule_data):
        """
        Update an existing follow-up rule with proper timezone handling.
        
        Args:
            rule_id: ID of the rule to update
            rule_data: Dictionary containing updated rule data
            
        Returns:
            FollowUpRule: The updated rule or None if failed
        """
        try:
            # Import models inside method to avoid circular imports
            from app.models.automation import FollowUpRule
            from app.models.follow_up import FollowUpSequence
            
            rule = FollowUpRule.query.get(rule_id)
            if not rule:
                logger.error(f"Follow-up rule {rule_id} not found")
                return None
            
            # Handle delay unit conversion
            if 'delay_hours' in rule_data:
                delay_hours = rule_data['delay_hours']
                delay_unit = rule_data.get('delay_unit', 'hours')
                
                if delay_unit == 'days':
                    delay_hours = delay_hours * 24
                elif delay_unit == 'minutes':
                    delay_hours = delay_hours / 60
                
                rule.delay_hours = delay_hours
            
            # Update basic fields
            if 'name' in rule_data:
                rule.name = rule_data['name']
            if 'trigger_type' in rule_data:
                rule.trigger_type = rule_data['trigger_type']
            if 'max_count' in rule_data:
                rule.max_count = rule_data['max_count']
            if 'template_text' in rule_data:
                rule.template_text = rule_data['template_text']
            if 'is_active' in rule_data:
                rule.is_active = rule_data['is_active']
            if 'conditions' in rule_data:
                rule.set_conditions(rule_data['conditions'])
            if 'message_type' in rule_data:
                rule.message_type = rule_data['message_type']
            if 'apply_to_all' in rule_data:
                rule.apply_to_all = rule_data['apply_to_all']
            if 'campaign_id' in rule_data:
                rule.campaign_id = rule_data['campaign_id']
            if 'recipient_emails' in rule_data:
                rule.recipient_emails = json.dumps(rule_data['recipient_emails']) if rule_data['recipient_emails'] else None
            if 'stop_on_reply' in rule_data:
                rule.stop_on_reply = rule_data['stop_on_reply']
            if 'business_days_only' in rule_data:
                rule.business_days_only = rule_data['business_days_only']
            if 'send_window_start' in rule_data:
                rule.send_window_start = datetime.strptime(rule_data['send_window_start'], '%H:%M').time()
            if 'send_window_end' in rule_data:
                rule.send_window_end = datetime.strptime(rule_data['send_window_end'], '%H:%M').time()
            
            # Update sequences if provided
            if 'sequences' in rule_data:
                # Remove existing sequences
                FollowUpSequence.query.filter_by(rule_id=rule_id).delete()
                
                # Add new sequences
                for seq_data in rule_data['sequences']:
                    sequence = FollowUpSequence(
                        rule_id=rule_id,
                        sequence_number=seq_data['sequence_number'],
                        delay_days=seq_data['delay_days'],
                        subject=seq_data.get('subject'),
                        message=seq_data.get('message'),
                        tone=seq_data.get('tone'),
                        length=seq_data.get('length')
                    )
                    db.session.add(sequence)
            
            rule.updated_at = datetime.now(pytz.UTC)
            db.session.commit()
            logger.info(f"Updated follow-up rule {rule_id}: {rule.name}")
            return rule
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating follow-up rule {rule_id}: {str(e)}")
            return None
    
    @staticmethod
    def delete_rule(rule_id, user_id):
        """
        Delete a follow-up rule.
        
        Args:
            rule_id: ID of the rule to delete
            user_id: ID of the user who owns the rule
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Import models inside method to avoid circular imports
            from app.models.automation import FollowUpRule
            
            rule = FollowUpRule.query.filter_by(id=rule_id, user_id=user_id).first()
            if not rule:
                logger.warning(f"Follow-up rule {rule_id} not found for user {user_id}")
                return False
            
            db.session.delete(rule)
            db.session.commit()
            logger.info(f"Deleted follow-up rule {rule_id}: {rule.name}")
            return True
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error deleting follow-up rule {rule_id}: {str(e)}")
            return False
    
    @staticmethod
    def toggle_rule(rule_id, user_id):
        """
        Toggle a follow-up rule's active status.
        
        Args:
            rule_id: ID of the rule to toggle
            user_id: ID of the user who owns the rule
            
        Returns:
            FollowUpRule: The updated rule or None if failed
        """
        try:
            # Import models inside method to avoid circular imports
            from app.models.automation import FollowUpRule
            
            rule = FollowUpRule.query.filter_by(id=rule_id, user_id=user_id).first()
            if not rule:
                logger.warning(f"Follow-up rule {rule_id} not found for user {user_id}")
                return None
            
            rule.is_active = not rule.is_active
            rule.updated_at = datetime.now(pytz.UTC)
            db.session.commit()
            
            status = "activated" if rule.is_active else "deactivated"
            logger.info(f"{status.capitalize()} follow-up rule {rule_id}: {rule.name}")
            return rule
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error toggling follow-up rule {rule_id}: {str(e)}")
            return None
    
    @staticmethod
    def duplicate_rule(rule_id, user_id):
        """
        Duplicate a follow-up rule.
        
        Args:
            rule_id: ID of the rule to duplicate
            user_id: ID of the user who owns the rule
            
        Returns:
            FollowUpRule: The new rule or None if failed
        """
        try:
            # Import models inside method to avoid circular imports
            from app.models.automation import FollowUpRule
            from app.models.follow_up import FollowUpSequence
            
            original_rule = FollowUpRule.query.filter_by(id=rule_id, user_id=user_id).first()
            if not original_rule:
                logger.warning(f"Follow-up rule {rule_id} not found for user {user_id}")
                return None
            
            # Create new rule with copied data
            new_rule = FollowUpRule(
                user_id=user_id,
                name=f"{original_rule.name} (Copy)",
                trigger_type=original_rule.trigger_type,
                delay_hours=original_rule.delay_hours,
                max_count=original_rule.max_count,
                template_text=original_rule.template_text,
                is_active=False,  # Start as inactive
                conditions=original_rule.conditions,
                message_type=original_rule.message_type,
                apply_to_all=original_rule.apply_to_all,
                campaign_id=original_rule.campaign_id,
                recipient_emails=original_rule.recipient_emails,
                stop_on_reply=original_rule.stop_on_reply,
                business_days_only=original_rule.business_days_only,
                send_window_start=original_rule.send_window_start,
                send_window_end=original_rule.send_window_end
            )
            
            db.session.add(new_rule)
            db.session.flush()  # Get the ID without committing
            
            # Copy sequences
            for seq in original_rule.sequences:
                new_seq = FollowUpSequence(
                    rule_id=new_rule.id,
                    sequence_number=seq.sequence_number,
                    delay_days=seq.delay_days,
                    subject=seq.subject,
                    message=seq.message,
                    tone=seq.tone,
                    length=seq.length
                )
                db.session.add(new_seq)
            
            db.session.commit()
            logger.info(f"Duplicated follow-up rule {rule_id} to {new_rule.id}: {new_rule.name}")
            return new_rule
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error duplicating follow-up rule {rule_id}: {str(e)}")
            return None
    
    @staticmethod
    def get_rules_for_user(user_id, active_only=False):
        """
        Get follow-up rules for a user.
        
        Args:
            user_id: ID of the user
            active_only: If True, only return active rules
            
        Returns:
            List of FollowUpRule objects
        """
        try:
            # Import models inside method to avoid circular imports
            from app.models.automation import FollowUpRule
            
            query = FollowUpRule.query.filter_by(user_id=user_id)
            
            if active_only:
                query = query.filter_by(is_active=True)
                
            return query.order_by(FollowUpRule.created_at.desc()).all()
            
        except Exception as e:
            logger.error(f"Error getting follow-up rules for user {user_id}: {str(e)}")
            return []
    
    @staticmethod
    def get_rule_by_id(rule_id, user_id):
        """
        Get a specific follow-up rule by ID.
        
        Args:
            rule_id: ID of the rule
            user_id: ID of the user who owns the rule
            
        Returns:
            FollowUpRule object or None if not found
        """
        try:
            # Import models inside method to avoid circular imports
            from app.models.automation import FollowUpRule
            
            return FollowUpRule.query.filter_by(id=rule_id, user_id=user_id).first()
            
        except Exception as e:
            logger.error(f"Error getting follow-up rule {rule_id}: {str(e)}")
            return None
    
    @staticmethod
    def check_and_process_rules():
        """
        Process all active follow-up rules and create follow-ups for emails that meet the criteria.
        This is the main function called by the scheduler.
        """
        logger.info("=== Starting follow-up rule check ===")
        
        # Create a fresh app context to avoid transaction issues
        from app import create_app
        app = create_app()
        
        with app.app_context():
            try:
                # Import models inside method to avoid circular imports
                from app.models.automation import FollowUpRule
                from app.models.email import Email
                from app.models.follow_up import FollowUp
                
                # Get current time in UTC and India
                now_utc = datetime.now(pytz.UTC)
                now_india = now_utc.astimezone(FollowUpService.india_tz)
                
                logger.info(f"Current time (UTC): {now_utc.strftime('%Y-%m-%d %H:%M:%S %Z')}")
                logger.info(f"Current time (India): {now_india.strftime('%Y-%m-%d %H:%M:%S %Z')}")
                
                # Get all active rules
                rules = FollowUpRule.query.filter_by(is_active=True).all()
                logger.info(f"Found {len(rules)} active follow-up rules")
                
                total_followups_created = 0
                
                for rule in rules:
                    try:
                        logger.info(f"Processing rule {rule.id}: {rule.name}")
                        logger.info(f"  - Trigger type: {rule.trigger_type}")
                        logger.info(f"  - Delay: {rule.delay_hours} hours")
                        
                        # Get emails to check based on rule settings
                        emails_to_check = FollowUpService._get_emails_to_check(rule, now_utc)
                        logger.info(f"  - Found {len(emails_to_check)} emails to check")
                        
                        # Process each email
                        followups_created = 0
                        for email in emails_to_check:
                            # Check if this email already has a follow-up scheduled for this rule
                            existing_followup = FollowUp.query.filter_by(
                                email_id=email.id,
                                follow_up_rule_id=rule.id
                            ).first()
                            
                            if existing_followup:
                                logger.info(f"    - Email {email.id} already has follow-up {existing_followup.id}")
                                continue
                            
                            # Check if enough time has passed since the email was sent
                            email_sent_utc = email.sent_at or email.created_at or datetime.min.replace(tzinfo=pytz.UTC)
                            email_sent_india = email_sent_utc.astimezone(FollowUpService.india_tz)
                            
                            time_since_email = now_utc - email_sent_utc
                            required_delay = timedelta(hours=rule.delay_hours)
                            
                            logger.info(f"    - Email {email.id}: Sent at {email_sent_india.strftime('%Y-%m-%d %H:%M:%S %Z')}")
                            logger.info(f"    - Email {email.id}: Time since sent: {time_since_email}, Required delay: {required_delay}")
                            
                            if time_since_email >= required_delay:
                                # Check if there's been a reply
                                has_reply = FollowUpService._check_for_reply(email, now_utc)
                                
                                if not has_reply:
                                    # Calculate scheduled time in India timezone
                                    scheduled_india = now_india  # Send immediately
                                    
                                    # Adjust for business days if required
                                    if rule.business_days_only and scheduled_india.weekday() >= 5:  # Saturday=5, Sunday=6
                                        # Move to next Monday
                                        days_to_monday = 7 - scheduled_india.weekday()
                                        scheduled_india = scheduled_india + timedelta(days=days_to_monday)
                                        # Set to 9 AM
                                        scheduled_india = scheduled_india.replace(hour=9, minute=0, second=0, microsecond=0)
                                    
                                    # Adjust for send window if specified
                                    if rule.send_window_start and rule.send_window_end:
                                        current_time_india = scheduled_india.time()
                                        if current_time_india < rule.send_window_start:
                                            # Move to start of send window
                                            scheduled_india = scheduled_india.replace(
                                                hour=rule.send_window_start.hour,
                                                minute=rule.send_window_start.minute,
                                                second=0,
                                                microsecond=0
                                            )
                                        elif current_time_india > rule.send_window_end:
                                            # Move to next day's start of send window
                                            scheduled_india = scheduled_india + timedelta(days=1)
                                            # Skip weekends if business_days_only
                                            if rule.business_days_only and scheduled_india.weekday() >= 5:
                                                days_to_monday = 7 - scheduled_india.weekday()
                                                scheduled_india = scheduled_india + timedelta(days=days_to_monday)
                                            
                                            scheduled_india = scheduled_india.replace(
                                                hour=rule.send_window_start.hour,
                                                minute=rule.send_window_start.minute,
                                                second=0,
                                                microsecond=0
                                            )
                                    
                                    # Convert to UTC for storage
                                    scheduled_utc = scheduled_india.astimezone(pytz.UTC)
                                    
                                    # Create follow-up
                                    followup = FollowUp(
                                        user_id=rule.user_id,
                                        email_id=email.id,
                                        follow_up_rule_id=rule.id,
                                        thread_id=email.thread_id,
                                        recipient_email=email.sender,
                                        scheduled_at=scheduled_utc,
                                        content=FollowUpService._generate_follow_up_content(rule, None, email, 1),
                                        status='pending',
                                        count=1,
                                        max_count=rule.max_count,
                                        trigger_type=rule.trigger_type,
                                        message_type=rule.message_type,
                                        sequence_number=1,
                                        stop_on_reply=rule.stop_on_reply,
                                        business_days_only=rule.business_days_only,
                                        send_window_start=rule.send_window_start,
                                        send_window_end=rule.send_window_end
                                    )
                                    
                                    db.session.add(followup)
                                    db.session.flush()  # Get the ID without committing
                                    
                                    logger.info(f"    - Scheduled follow-up {followup.id} for email {email.id} to {email.sender} at {scheduled_india.strftime('%Y-%m-%d %H:%M:%S %Z')}")
                                    followups_created += 1
                                else:
                                    logger.info(f"    - Email {email.id} has reply, skipping")
                            else:
                                logger.info(f"    - Email {email.id} not old enough yet (needs {required_delay - time_since_email} more)")
                        
                        # Update rule's last checked time (store in UTC)
                        rule.updated_at = now_utc
                        db.session.commit()
                        
                        total_followups_created += followups_created
                        logger.info(f"  - Created {followups_created} follow-ups for rule {rule.id}")
                        
                    except Exception as e:
                        logger.error(f"  - Error processing rule {rule.id}: {str(e)}")
                        logger.exception(e)
                        db.session.rollback()
                
                logger.info(f"=== Follow-up rule check completed. Created {total_followups_created} follow-ups ===")
                
            except Exception as e:
                logger.exception("Fatal error in check_and_process_rules")
                db.session.rollback()
    
    @staticmethod
    def _get_emails_to_check(rule, now_utc):
        """
        Get emails to check for a specific rule based on the rule's settings.
        
        Args:
            rule: FollowUpRule object
            now_utc: Current time in UTC
            
        Returns:
            List of Email objects
        """
        from app.models.email import Email
        
        # Calculate the time window to check (24 hours ago from now)
        check_start = now_utc - timedelta(days=1)
        
        # Get emails sent in the last 24 hours
        if rule.apply_to_all:
            emails_to_check = Email.query.filter(
                Email.sender != None,  # Has a sender
                Email.sent_at >= check_start,  # Sent in the last 24 hours
                Email.sent_at <= now_utc  # Sent before now
            ).all()
        else:
            # Get specific recipient IDs
            if rule.recipient_emails:
                try:
                    recipient_emails = json.loads(rule.recipient_emails)
                    # Create a filter for each recipient email
                    filters = []
                    for recipient in recipient_emails:
                        filters.append(Email.sender.like(f'%{recipient}%'))
                    
                    # Combine filters with OR
                    from sqlalchemy import or_
                    emails_to_check = Email.query.filter(
                        Email.sender != None,  # Has a sender
                        Email.sent_at >= check_start,  # Sent in the last 24 hours
                        Email.sent_at <= now_utc,  # Sent before now
                        or_(*filters)  # Sender matches one of the recipients
                    ).all()
                except:
                    emails_to_check = []
            else:
                emails_to_check = []
        
        return emails_to_check
    
    @staticmethod
    def _check_for_reply(email, since_utc):
        """
        Check if there has been a reply to an email since a specific time.
        
        Args:
            email: Email object to check
            since_utc: Check for replies since this time (UTC)
            
        Returns:
            bool: True if a reply was found, False otherwise
        """
        from app.models.email import Email
        
        # Look for emails from the original recipient to the original sender
        # that were sent after the original email
        reply = Email.query.filter(
            Email.sender == email.recipient,  # From original recipient
            Email.recipient == email.sender,  # To original sender
            Email.sent_at > email.sent_at,  # Sent after original email
            Email.sent_at >= since_utc  # Sent since our check time
        ).first()
        
        return reply is not None
    
    @staticmethod
    def check_and_send_follow_ups():
        """
        Process all pending follow-ups that are due to be sent.
        This is the main function called by the scheduler.
        """
        logger.info("=== Starting follow-up check ===")

        # Create a fresh app context to avoid transaction issues
        from app import create_app
        app = create_app()

        with app.app_context():
            try:
                # Import models inside method to avoid circular imports
                from app.models.follow_up import FollowUp, FollowUpLog
                from app.models.user import User

                # Use UTC time consistently
                now_utc = datetime.now(pytz.UTC)
                now_india = now_utc.astimezone(FollowUpService.india_tz)
                
                logger.info(f"Current time (UTC): {now_utc.strftime('%Y-%m-%d %H:%M:%S %Z')}")
                logger.info(f"Current time (India): {now_india.strftime('%Y-%m-%d %H:%M:%S %Z')}")
                
                # Get all pending follow-ups that are scheduled for now or in the past
                pending_follow_ups = FollowUp.query.filter(
                    FollowUp.status == 'pending',
                    FollowUp.scheduled_at <= now_utc
                ).all()

                logger.info(f"Found {len(pending_follow_ups)} pending follow-ups to process")

                if not pending_follow_ups:
                    logger.info("No pending follow-ups to process")
                    return

                for i, follow_up in enumerate(pending_follow_ups):
                    logger.info(f"Processing follow-up {i+1}/{len(pending_follow_ups)}: ID {follow_up.id}")
                    
                    # Convert scheduled time to India for logging
                    scheduled_india = follow_up.scheduled_at.astimezone(FollowUpService.india_tz)
                    logger.info(f"  - Scheduled at (India): {scheduled_india.strftime('%Y-%m-%d %H:%M:%S %Z')}")

                    try:
                        # Check business day constraints (using India time)
                        if follow_up.business_days_only and now_india.weekday() >= 5:  # Saturday=5, Sunday=6
                            logger.info(f"  → Skipping follow-up {follow_up.id}: not a business day in India")
                            continue
                        
                        # Check send window constraints (using India time)
                        if follow_up.send_window_start and follow_up.send_window_end:
                            current_time_india = now_india.time()
                            if current_time_india < follow_up.send_window_start or current_time_india > follow_up.send_window_end:
                                logger.info(f"  → Skipping follow-up {follow_up.id}: outside send window ({current_time_india} vs {follow_up.send_window_start}-{follow_up.send_window_end})")
                                continue
                        
                        # Send the follow-up
                        logger.info(f"  → Sending follow-up {follow_up.id} to {follow_up.recipient_email}")
                        success = FollowUpService.send_follow_up(follow_up)
                        
                        if success:
                            logger.info(f"  ✅ Successfully sent follow-up {follow_up.id}")
                            # Ensure proper status update and timestamp
                            follow_up.status = 'sent'
                            follow_up.sent_at = now_utc
                            db.session.commit()
                            
                            # Update the log
                            log = FollowUpLog.query.filter_by(follow_up_id=follow_up.id).order_by(FollowUpLog.created_at.desc()).first()
                            if log:
                                log.status = FollowUpStatus.SENT
                                log.sent_at = now_utc
                                db.session.commit()
                            
                            # Schedule the next follow-up if applicable
                            FollowUpService._schedule_next_follow_up(follow_up)
                        else:
                            logger.error(f"  ❌ Failed to send follow-up {follow_up.id}")
                            follow_up.status = 'failed'
                            db.session.commit()
                            
                            # Update the log
                            log = FollowUpLog.query.filter_by(follow_up_id=follow_up.id).order_by(FollowUpLog.created_at.desc()).first()
                            if log:
                                log.status = FollowUpStatus.FAILED
                                log.reason = "Failed to send"
                                db.session.commit()
                    
                    except Exception as e:
                        logger.error(f"  ❌ Error processing follow-up {follow_up.id}: {str(e)}")
                        # Rollback this specific follow-up but continue with others
                        db.session.rollback()
                        
                        # Update the log
                        try:
                            log = FollowUpLog.query.filter_by(follow_up_id=follow_up.id).order_by(FollowUpLog.created_at.desc()).first()
                            if log:
                                log.status = FollowUpStatus.FAILED
                                log.reason = str(e)
                                db.session.commit()
                        except:
                            pass
                        
                        follow_up.status = 'failed'
                        db.session.commit()
                
                logger.info("=== Follow-up check completed ===")
            
            except Exception as e:
                logger.exception("Fatal error in check_and_send_follow_ups")
                # Rollback the entire session
                db.session.rollback()
    
    @staticmethod
    def _rule_applies_to_email(rule, email, user_id):
        """
        Check if a rule applies to a specific email.
        
        Args:
            rule: FollowUpRule object
            email: Email object
            user_id: ID of the user
            
        Returns:
            bool: True if the rule applies, False otherwise
        """
        try:
            # Check if the rule is active
            if not rule.is_active:
                return False
            
            # Check if the rule applies to all emails
            if rule.apply_to_all:
                return True
            
            # Check if the rule applies to specific campaigns
            if rule.campaign_id:
                # This would require a campaign relationship in the Email model
                # For now, we'll assume it doesn't apply
                return False
            
            # Check if the rule applies to specific recipients
            if rule.recipient_emails:
                try:
                    recipient_emails = json.loads(rule.recipient_emails)
                    sender_domain = email.sender.split('@')[-1] if '@' in email.sender else ''
                    
                    # Check if the sender's email or domain is in the list
                    for recipient in recipient_emails:
                        if recipient.lower() in email.sender.lower() or recipient.lower() == sender_domain.lower():
                            return True
                    
                    return False
                except:
                    return False
            
            # Check other conditions
            conditions = rule.get_conditions()
            
            # Check sender conditions
            if 'senders' in conditions and conditions['senders']:
                sender_match = False
                for sender_pattern in conditions['senders']:
                    if sender_pattern.lower() in email.sender.lower():
                        sender_match = True
                        break
                if not sender_match:
                    return False
            
            # Check keyword conditions
            if 'keywords' in conditions and conditions['keywords']:
                keyword_match = False
                email_text = f"{email.subject or ''} {email.body_text or ''} {email.snippet or ''}"
                for keyword in conditions['keywords']:
                    if keyword.lower() in email_text.lower():
                        keyword_match = True
                        break
                if not keyword_match:
                    return False
            
            # Check domain conditions
            if 'domains' in conditions and conditions['domains']:
                domain_match = False
                sender_domain = email.sender.split('@')[-1] if '@' in email.sender else ''
                for domain in conditions['domains']:
                    if sender_domain == domain:
                        domain_match = True
                        break
                if not domain_match:
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error checking if rule applies to email: {str(e)}")
            return False
    
    @staticmethod
    def _adjust_for_business_days(dt):
        """
        Adjust a datetime to fall on a business day.
        
        Args:
            dt: Datetime to adjust
            
        Returns:
            Datetime adjusted to fall on a business day
        """
        # If it's a weekend, move to next Monday
        while dt.weekday() >= 5:  # Saturday=5, Sunday=6
            dt = dt + timedelta(days=1)
        
        return dt
    
    @staticmethod
    def _adjust_for_send_window(dt, send_window_start, send_window_end, business_days_only=False):
        """
        Adjust a datetime to fall within the send window.
        
        Args:
            dt: Datetime to adjust
            send_window_start: Start time of the send window
            send_window_end: End time of the send window
            business_days_only: Whether to only send on business days
            
        Returns:
            Datetime adjusted to fall within the send window
        """
        if not send_window_start or not send_window_end:
            return dt
        
        # Convert to time objects for comparison
        current_time = dt.time()
        start_time = send_window_start
        end_time = send_window_end
        
        # If current time is before the start of the window, move to start time
        if current_time < start_time:
            dt = dt.replace(
                hour=start_time.hour,
                minute=start_time.minute,
                second=0,
                microsecond=0
            )
        # If current time is after the end of the window, move to next day's start time
        elif current_time > end_time:
            dt = dt + timedelta(days=1)
            
            # If business days only, skip weekends
            if business_days_only:
                while dt.weekday() >= 5:  # Saturday=5, Sunday=6
                    dt = dt + timedelta(days=1)
            
            dt = dt.replace(
                hour=start_time.hour,
                minute=start_time.minute,
                second=0,
                microsecond=0
            )
        
        return dt
    
    @staticmethod
    def _generate_follow_up_content(rule, sequence, email, follow_up_number):
        """
        Generate the content for a follow-up email.
        
        Args:
            rule: FollowUpRule object
            sequence: FollowUpSequence object or None
            email: Email object
            follow_up_number: The follow-up number (1st, 2nd, etc.)
            
        Returns:
            String: The generated content
        """
        try:
            # If we have a sequence with a message, use it
            if sequence and sequence.message:
                return FollowUpService._replace_placeholders(sequence.message, email, follow_up_number)
            
            # If the rule uses AI generation
            if rule.message_type == 'AI-Generated':
                # This would integrate with your AI service
                # For now, we'll use a template
                return FollowUpService._generate_ai_follow_up(rule, email, follow_up_number)
            
            # Otherwise, use the rule's template text
            return FollowUpService._replace_placeholders(rule.template_text, email, follow_up_number)
            
        except Exception as e:
            logger.error(f"Error generating follow-up content: {str(e)}")
            return "This is a follow-up regarding our previous conversation."
    
    @staticmethod
    def _replace_placeholders(text, email, follow_up_number):
        """
        Replace placeholders in a template with actual values.
        
        Args:
            text: Template text with placeholders
            email: Email object
            follow_up_number: The follow-up number (1st, 2nd, etc.)
            
        Returns:
            String: Text with placeholders replaced
        """
        try:
            # Extract recipient name
            recipient_name = email.sender
            if '<' in email.sender and '>' in email.sender:
                recipient_name = email.sender.split('<')[0].strip()
            elif '@' in email.sender:
                recipient_name = email.sender.split('@')[0]
            
            # Calculate days since last email (using India time)
            now_india = datetime.now(FollowUpService.india_tz)
            email_sent_utc = (email.sent_at or email.received_at or email.created_at or 
                            datetime.now(pytz.UTC))
            email_sent_india = email_sent_utc.astimezone(FollowUpService.india_tz)
            days_since = (now_india - email_sent_india).days
            
            # Replace placeholders
            text = text.replace('{{recipient_name}}', recipient_name)
            text = text.replace('{{previous_subject}}', email.subject or 'our conversation')
            text = text.replace('{{days_since_last_email}}', str(days_since))
            text = text.replace('{{follow_up_number}}', str(follow_up_number))
            
            return text
            
        except Exception as e:
            logger.error(f"Error replacing placeholders: {str(e)}")
            return text
    
    @staticmethod
    def _generate_ai_follow_up(rule, email, follow_up_number):
        """
        Generate an AI-based follow-up.
        
        Args:
            rule: FollowUpRule object
            email: Email object
            follow_up_number: The follow-up number (1st, 2nd, etc.)
            
        Returns:
            String: The generated content
        """
        try:
            # This would integrate with your AI service
            # For now, we'll use a simple template
            
            # Extract recipient name
            recipient_name = email.sender
            if '<' in email.sender and '>' in email.sender:
                recipient_name = email.sender.split('<')[0].strip()
            elif '@' in email.sender:
                recipient_name = email.sender.split('@')[0]
            
            # Calculate days since last email (using India time)
            now_india = datetime.now(FollowUpService.india_tz)
            email_sent_utc =  (email.sent_at or email.received_at or email.created_at or 
                            datetime.now(pytz.UTC))
            email_sent_india = email_sent_utc.astimezone(FollowUpService.india_tz)
            days_since = (now_india - email_sent_india).days
            
            # Generate content based on follow-up number
            if follow_up_number == 1:
                return f"Hi {recipient_name},\n\nJust wanted to follow up on my previous email regarding {email.subject or 'our conversation'}. I'd love to hear your thoughts when you have a moment.\n\nBest regards"
            elif follow_up_number == 2:
                return f"Hi {recipient_name},\n\nI'm following up again regarding {email.subject or 'our conversation'}. It's been {days_since} days since my last email, and I wanted to make sure you received it.\n\nPlease let me know if you have any questions or if there's a better time to connect.\n\nBest regards"
            else:
                return f"Hi {recipient_name},\n\nThis is my final follow-up regarding {email.subject or 'our conversation'}. I'll assume you're not interested at this time, but please feel free to reach out if you change your mind.\n\nBest regards"
            
        except Exception as e:
            logger.error(f"Error generating AI follow-up: {str(e)}")
            return "This is a follow-up regarding our previous conversation."
    
    @staticmethod
    def _get_next_business_day(dt):
        """
        Get the next business day from a given datetime.
        
        Args:
            dt: Datetime to start from
            
        Returns:
            Datetime of the next business day
        """
        next_day = dt + timedelta(days=1)
        while next_day.weekday() >= 5:  # Saturday=5, Sunday=6
            next_day = next_day + timedelta(days=1)
        return next_day
    
    @staticmethod
    def _get_next_available_time_in_window(follow_up):
        """
        Calculate the next available time within the send window.
        
        Args:
            follow_up: The FollowUp object
            
        Returns:
            Datetime of the next available time
        """
        now = datetime.now(pytz.UTC)
        start_time = follow_up.send_window_start
        end_time = follow_up.send_window_end
        
        # If current time is before the start of the window, schedule for today at start time
        if now.time() < start_time:
            next_time = now.replace(
                hour=start_time.hour,
                minute=start_time.minute,
                second=0,
                microsecond=0
            )
        # If current time is after the end of the window, schedule for next business day at start time
        else:
            next_time = now + timedelta(days=1)
            
            # If business days only, skip weekends
            if follow_up.business_days_only:
                while next_time.weekday() >= 5:  # Saturday=5, Sunday=6
                    next_time = next_time + timedelta(days=1)
            
            next_time = next_time.replace(
                hour=start_time.hour,
                minute=start_time.minute,
                second=0,
                microsecond=0
            )
        
        return next_time
    
    @staticmethod
    def _schedule_next_follow_up(current_follow_up):
        """
        Schedule the next follow-up in the sequence if applicable.
        
        Args:
            current_follow_up: The current FollowUp object that was just sent
        """
        try:
            # Import models inside method to avoid circular imports
            from app.models.automation import FollowUpRule
            from app.models.follow_up import FollowUp, FollowUpLog
            
            # Check if we've reached the max count
            if current_follow_up.count >= current_follow_up.max_count:
                current_follow_up.status = 'completed'
                db.session.commit()
                logger.info(f"Follow-up {current_follow_up.id} completed - reached max count")
                return
            
            # Get the rule
            rule = FollowUpRule.query.get(current_follow_up.follow_up_rule_id)
            if not rule:
                logger.error(f"Rule {current_follow_up.follow_up_rule_id} not found")
                return
            
            # Get the next sequence
            next_sequence_number = current_follow_up.sequence_number + 1
            next_sequence = None
            
            if rule.sequences:
                next_sequence = next(
                    (s for s in rule.sequences if s.sequence_number == next_sequence_number),
                    None
                )
            
            # Use the previous follow-up's scheduled time as base to prevent drift
            base_time = current_follow_up.scheduled_at
            
            if next_sequence:
                # Use sequence delay
                scheduled_at = base_time + timedelta(days=next_sequence.delay_days)
            else:
                # Use rule delay_hours
                scheduled_at = base_time + timedelta(hours=rule.delay_hours)
            
            # Adjust for business days if required
            if rule.business_days_only:
                scheduled_at = FollowUpService._adjust_for_business_days(scheduled_at)
            
            # Adjust for send window
            scheduled_at = FollowUpService._adjust_for_send_window(scheduled_at, rule.send_window_start, rule.send_window_end, rule.business_days_only)
            
            # Generate the follow-up content
            content = FollowUpService._generate_follow_up_content(
                rule, 
                next_sequence, 
                current_follow_up.email, 
                next_sequence_number
            )
            
            # Create the next follow-up
            next_follow_up = FollowUp(
                user_id=current_follow_up.user_id,
                email_id=current_follow_up.email_id,
                follow_up_rule_id=current_follow_up.follow_up_rule_id,
                thread_id=current_follow_up.thread_id,
                recipient_email=current_follow_up.recipient_email,
                scheduled_at=scheduled_at,
                content=content,
                status='pending',
                count=current_follow_up.count + 1,
                max_count=current_follow_up.max_count,
                trigger_type=current_follow_up.trigger_type,
                message_type=current_follow_up.message_type,
                sequence_number=next_sequence_number,
                stop_on_reply=current_follow_up.stop_on_reply,
                business_days_only=current_follow_up.business_days_only,
                send_window_start=current_follow_up.send_window_start,
                send_window_end=current_follow_up.send_window_end
            )
            
            db.session.add(next_follow_up)
            db.session.flush()  # Get the ID without committing
            
            # Create a log entry
            log = FollowUpLog(
                rule_id=current_follow_up.follow_up_rule_id,
                original_email_id=current_follow_up.email_id,
                follow_up_id=next_follow_up.id,
                follow_up_number=next_sequence_number,
                recipient_email=current_follow_up.recipient_email,
                status=FollowUpStatus.PENDING,
                scheduled_at=scheduled_at
            )
            db.session.add(log)
            
            db.session.commit()
            logger.info(f"Scheduled next follow-up {next_follow_up.id} for email {current_follow_up.email_id}")
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error scheduling next follow-up: {str(e)}")
    
    @staticmethod
    def has_recipient_replied(thread_id, after_date, user_id):
        """
        Check if the recipient has replied to the thread after a specific date.
        
        Args:
            thread_id: The Gmail thread ID to check
            after_date: Only consider replies after this date
            user_id: ID of the user to check for
            
        Returns:
            bool: True if the recipient has replied, False otherwise
        """
        try:
            if not thread_id:
                return False
                
            # Import models inside method to avoid circular imports
            from app.models.user import User
            from app.models.follow_up import FollowUp
            
            # Get the user
            user = User.query.get(user_id)
            if not user:
                return False
                
            # Get the follow-up to check the recipients
            follow_up = FollowUp.query.filter_by(thread_id=thread_id).first()
            if not follow_up or not follow_up.recipient_email:
                return False
                
            # Use Gmail service to check for replies
            from app.services.gmail_service import GmailService
            gmail_service = GmailService(user)
            thread = gmail_service.get_thread(thread_id)
            
            if not thread or 'messages' not in thread:
                return False
                
            # Parse recipient emails
            recipients = [email.strip() for email in follow_up.recipient_email.split(',')]
            
            # Check each message in the thread
            for message in thread['messages']:
                # Parse the message date
                message_date = datetime.fromtimestamp(int(message['internalDate']) / 1000)
                
                # Skip messages before our check date
                if message_date <= after_date:
                    continue
                    
                # Get the message headers to check sender
                headers = message['payload']['headers']
                sender = None
                
                for header in headers:
                    if header['name'].lower() == 'from':
                        sender = header['value']
                        break
                
                # Extract email address from sender string
                sender_email = None
                if sender:
                    # Extract email from format "Name <email@domain.com>"
                    if '<' in sender and '>' in sender:
                        sender_email = sender.split('<')[1].split('>')[0].strip()
                    else:
                        sender_email = sender.strip()
                
                # If the sender is one of the recipients, they replied
                if sender_email and any(recipient.lower() in sender_email.lower() for recipient in recipients):
                    return True
                    
            return False
            
        except Exception as e:
            logger.error(f"Error checking if recipient replied in thread {thread_id}: {str(e)}")
            return False
    
    @staticmethod
    def send_follow_up(follow_up):
        """
        Send a follow-up email via Gmail API.
        
        Args:
            follow_up: The FollowUp object to send
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Import models inside method to avoid circular imports
            from app.models.user import User
            from app.models.email import SentEmail, Email
            
            # Get the user
            user = User.query.get(follow_up.user_id)
            if not user:
                logger.error(f"User {follow_up.user_id} not found")
                return False
                
            # Get the Gmail service
            from app.services.gmail_service import GmailService
            gmail_service = GmailService(user)
            
            # Parse recipient emails
            recipients = [email.strip() for email in follow_up.recipient_email.split(',')]
            
            # Default subject
            subject = "Follow-up"
            
            # Try to get subject from related email if available
            if follow_up.email_id:
                email = Email.query.get(follow_up.email_id)
                if email:
                    subject = f"Re: {email.subject}"
            
            # Determine if we should use thread_id
            # Only use thread_id if it's a valid Gmail thread ID (from an existing email)
            thread_id = None
            if follow_up.thread_id and follow_up.email_id:
                # Only use thread_id if it's associated with an actual email
                # This ensures it's a real Gmail thread ID
                thread_id = follow_up.thread_id
                logger.info(f"Using thread_id {thread_id} for follow-up {follow_up.id}")
            else:
                logger.info(f"Not using thread_id for follow-up {follow_up.id} (standalone follow-up)")
            
            # Send the follow-up email to each recipient
            success_count = 0
            for recipient in recipients:
                try:
                    # Try to send with thread_id first if available
                    if thread_id:
                        success, message = gmail_service.send_email(
                            to=recipient,
                            subject=subject,
                            body_text=follow_up.content,
                            thread_id=thread_id
                        )
                        
                        # If thread_id is invalid, try without it
                        if not success and "Invalid thread_id" in str(message):
                            logger.warning(f"Invalid thread_id {thread_id}, sending as new thread to {recipient}")
                            success, message = gmail_service.send_email(
                                to=recipient,
                                subject=subject,
                                body_text=follow_up.content,
                                thread_id=None
                            )
                    else:
                        # Send without thread_id
                        success, message = gmail_service.send_email(
                            to=recipient,
                            subject=subject,
                            body_text=follow_up.content,
                            thread_id=None
                        )
                    
                    if success:
                        success_count += 1
                        logger.info(f"Successfully sent follow-up {follow_up.id} to {recipient}")
                        
                        # Create a SentEmail record for this follow-up
                        try:
                            new_sent_email = SentEmail(
                                user_id=user.id,
                                to=recipient,
                                subject=subject,
                                body_text=follow_up.content,
                                thread_id=thread_id,
                                sent_at=datetime.now(pytz.UTC)
                            )
                            db.session.add(new_sent_email)
                        except Exception as e:
                            # If creating SentEmail fails, log the error but don't fail the whole operation
                            logger.error(f"Error creating SentEmail record for follow-up {follow_up.id}: {str(e)}")
                    else:
                        logger.error(f"Failed to send follow-up {follow_up.id} to {recipient}: {message}")
                        
                except Exception as e:
                    logger.error(f"Error sending follow-up {follow_up.id} to {recipient}: {str(e)}")
            
            # Only commit if we have successful sends
            if success_count > 0:
                try:
                    db.session.commit()
                except Exception as e:
                    logger.error(f"Error committing SentEmail records: {str(e)}")
                    db.session.rollback()
            
            # Consider it successful if at least one email was sent
            return success_count > 0
            
        except Exception as e:
            logger.error(f"Error sending follow-up {follow_up.id}: {str(e)}")
            return False
    
    @staticmethod
    def cancel_follow_up(follow_up_id, user_id):
        """
        Cancel a pending follow-up.
        
        Args:
            follow_up_id: ID of the follow-up to cancel
            user_id: ID of the user who owns the follow-up
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Import models inside method to avoid circular imports
            from app.models.follow_up import FollowUp
            
            follow_up = FollowUp.query.filter_by(id=follow_up_id, user_id=user_id).first()
            if not follow_up:
                logger.warning(f"Follow-up {follow_up_id} not found for user {user_id}")
                return False
                
            if follow_up.status not in ['pending']:
                logger.warning(f"Cannot cancel follow-up {follow_up_id} with status {follow_up.status}")
                return False
                
            follow_up.status = 'cancelled'
            db.session.commit()
            
            logger.info(f"Cancelled follow-up {follow_up_id}")
            return True
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error cancelling follow-up {follow_up_id}: {str(e)}")
            return False
    
    @staticmethod
    def cancel_future_follow_ups(email_id, user_id):
        """
        Cancel all future follow-ups for a specific email.
        
        Args:
            email_id: ID of the email
            user_id: ID of the user
            
        Returns:
            int: Number of follow-ups cancelled
        """
        try:
            # Import models inside method to avoid circular imports
            from app.models.follow_up import FollowUp
            
            # Get all pending follow-ups for this email
            follow_ups = FollowUp.query.filter_by(
                email_id=email_id,
                user_id=user_id,
                status='pending'
            ).all()
            
            count = 0
            for follow_up in follow_ups:
                follow_up.status = 'cancelled'
                count += 1
            
            db.session.commit()
            logger.info(f"Cancelled {count} future follow-ups for email {email_id}")
            return count
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error cancelling future follow-ups for email {email_id}: {str(e)}")
            return 0
    
    @staticmethod
    def reschedule_follow_up(follow_up_id, user_id, new_delay_hours):
        """
        Reschedule a pending follow-up with a new delay.
        
        Args:
            follow_up_id: ID of the follow-up to reschedule
            user_id: ID of the user who owns the follow_up
            new_delay_hours: New delay in hours from now
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Import models inside method to avoid circular imports
            from app.models.follow_up import FollowUp
            
            follow_up = FollowUp.query.filter_by(id=follow_up_id, user_id=user_id).first()
            if not follow_up:
                logger.warning(f"Follow-up {follow_up_id} not found for user {user_id}")
                return False
                
            if follow_up.status not in ['pending']:
                logger.warning(f"Cannot reschedule follow-up {follow_up_id} with status {follow_up.status}")
                return False
                
            # Calculate new scheduled time in India timezone
            now_india = datetime.now(FollowUpService.india_tz)
            new_scheduled_india = now_india + timedelta(hours=new_delay_hours)
            
            # Convert to UTC for storage
            new_scheduled_utc = new_scheduled_india.astimezone(pytz.UTC)
            
            # Update the follow-up
            follow_up.scheduled_at = new_scheduled_utc
            db.session.commit()
            
            logger.info(f"Rescheduled follow-up {follow_up_id} to {new_scheduled_india.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            return True
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error rescheduling follow-up {follow_up_id}: {str(e)}")
            return False
    
    @staticmethod
    def get_follow_ups_for_user(user_id, status=None, limit=None):
        """
        Get follow-ups for a user, optionally filtered by status.
        
        Args:
            user_id: ID of the user
            status: Filter by status (optional)
            limit: Maximum number of follow-ups to return (optional)
            
        Returns:
            List of FollowUp objects
        """
        try:
            # Import models inside method to avoid circular imports
            from app.models.follow_up import FollowUp
            
            query = FollowUp.query.filter_by(user_id=user_id)
            
            if status:
                query = query.filter_by(status=status)
                
            if limit:
                query = query.limit(limit)
                
            return query.order_by(FollowUp.scheduled_at.desc()).all()
            
        except Exception as e:
            logger.error(f"Error getting follow-ups for user {user_id}: {str(e)}")
            return []
    
    @staticmethod
    def get_follow_up_by_id(follow_up_id, user_id):
        """
        Get a specific follow-up by ID.
        
        Args:
            follow_up_id: ID of the follow-up
            user_id: ID of the user who owns the follow-up
            
        Returns:
            FollowUp object or None if not found
        """
        try:
            # Import models inside method to avoid circular imports
            from app.models.follow_up import FollowUp
            
            return FollowUp.query.filter_by(id=follow_up_id, user_id=user_id).first()
            
        except Exception as e:
            logger.error(f"Error getting follow-up {follow_up_id}: {str(e)}")
            return None
    
    @staticmethod
    def get_follow_up_logs(user_id, rule_id=None, limit=None):
        """
        Get follow-up logs for a user, optionally filtered by rule.
    
        Args:
            user_id: ID of the user
            rule_id: Filter by rule ID (optional)
            limit: Maximum number of logs to return (optional)
        
        Returns:
            List of FollowUpLog objects
        """
        try:
            # Import models inside method to avoid circular imports
            from app.models.follow_up import FollowUpLog
            from app.models.automation import FollowUpRule
        
            # Get the user's rule IDs
            rule_ids = [rule.id for rule in FollowUpRule.query.filter_by(user_id=user_id).all()]
        
            # Apply order_by before limit
            query = FollowUpLog.query.filter(FollowUpLog.rule_id.in_(rule_ids))
        
            if rule_id:
                query = query.filter_by(rule_id=rule_id)
        
            # Apply order_by before limit
            query = query.order_by(FollowUpLog.created_at.desc())
        
            if limit:
                query = query.limit(limit)
                
            return query.all()
            
        except Exception as e:
            logger.error(f"Error getting follow-up logs for user {user_id}: {str(e)}")
            return []
    
    @staticmethod
    def get_follow_up_stats(user_id):
        """
        Get follow-up statistics for a user.
        
        Args:
            user_id: ID of the user
            
        Returns:
            Dictionary with follow-up statistics
        """
        try:
            # Import models inside method to avoid circular imports
            from app.models.follow_up import FollowUp
            from app.models.automation import FollowUpRule
            from app.models.email import Email
            
            # Get rule stats
            active_rules = FollowUpRule.query.filter_by(user_id=user_id, is_active=True).count()
            total_rules = FollowUpRule.query.filter_by(user_id=user_id).count()
            
            # Get follow-up stats
            pending = FollowUp.query.filter_by(user_id=user_id, status='pending').count()
            
            # Get follow-ups sent today (in India timezone)
            now_india = datetime.now(FollowUpService.india_tz)
            today_start_india = now_india.replace(hour=0, minute=0, second=0, microsecond=0)
            today_start_utc = today_start_india.astimezone(pytz.UTC)
            
            sent_today = FollowUp.query.filter(
                FollowUp.user_id == user_id,
                FollowUp.status == 'sent',
                FollowUp.sent_at >= today_start_utc
            ).count()
            
            # Get responses (follow-ups marked as completed due to replies)
            responses = FollowUp.query.filter_by(user_id=user_id, status='completed').count()
            
            # Get total follow-ups sent
            total_sent = FollowUp.query.filter_by(user_id=user_id, status='sent').count()
            
            # Get follow-ups scheduled for the next 7 days
            next_week_india = now_india + timedelta(days=7)
            next_week_utc = next_week_india.astimezone(pytz.UTC)
            
            upcoming = FollowUp.query.filter(
                FollowUp.user_id == user_id,
                FollowUp.status == 'pending',
                FollowUp.scheduled_at <= next_week_utc
            ).count()
            
            return {
                'active_rules': active_rules,
                'total_rules': total_rules,
                'pending_follow_ups': pending,
                'sent_follow_ups': sent_today,
                'responses_received': responses,
                'total_sent': total_sent,
                'upcoming': upcoming
            }
            
        except Exception as e:
            logger.error(f"Error getting follow-up stats for user {user_id}: {str(e)}")
            return {
                'active_rules': 0,
                'total_rules': 0,
                'pending_follow_ups': 0,
                'sent_follow_ups': 0,
                'responses_received': 0,
                'total_sent': 0,
                'upcoming': 0
            }
    
    @staticmethod
    def test_rule(rule_id, user_id, test_email):
        """
        Test a follow-up rule by sending a test email.
        
        Args:
            rule_id: ID of the rule to test
            user_id: ID of the user who owns the rule
            test_email: Email address to send the test to
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Import models inside method to avoid circular imports
            from app.models.automation import FollowUpRule
            from app.models.follow_up import FollowUpSequence
            from app.models.email import Email
            
            # Get the rule
            rule = FollowUpRule.query.filter_by(id=rule_id, user_id=user_id).first()
            if not rule:
                logger.warning(f"Follow-up rule {rule_id} not found for user {user_id}")
                return False
            
            # Create a mock email for testing
            mock_email = Email(
                sender=test_email,
                subject="Test Email for Follow-Up Rule",
                body_text="This is a test email to verify your follow-up rule.",
                received_at=datetime.now(pytz.UTC)
            )
            
            # Get the first sequence for this rule
            sequence = None
            if rule.sequences:
                sequence = next((s for s in rule.sequences if s.sequence_number == 1), None)
            
            # Generate the follow-up content
            content = FollowUpService._generate_follow_up_content(rule, sequence, mock_email, 1)
            
            # Send the test email
            from app.models.user import User
            from app.services.gmail_service import GmailService
            
            user = User.query.get(user_id)
            gmail_service = GmailService(user)
            
            success, message = gmail_service.send_email(
                to=test_email,
                subject=f"Test Follow-Up: {rule.name}",
                body_text=content,
                thread_id=None
            )
            
            if success:
                logger.info(f"Successfully sent test email for rule {rule_id} to {test_email}")
                return True
            else:
                logger.error(f"Failed to send test email for rule {rule_id}: {message}")
                return False
                
        except Exception as e:
            logger.error(f"Error testing rule {rule_id}: {str(e)}")
            return False
    
    @staticmethod
    def export_rules(user_id):
        """
        Export follow-up rules for a user as CSV.
        
        Args:
            user_id: ID of the user
            
        Returns:
            String: CSV content
        """
        try:
            import csv
            import io
            
            # Import models inside method to avoid circular imports
            from app.models.automation import FollowUpRule
            
            # Get the user's rules
            rules = FollowUpRule.query.filter_by(user_id=user_id).all()
            
            # Create a CSV in memory
            output = io.StringIO()
            writer = csv.writer(output)
            
            # Write header
            writer.writerow([
                'ID', 'Name', 'Trigger Type', 'Delay Hours', 'Max Count',
                'Message Type', 'Is Active', 'Apply To All', 'Stop On Reply',
                'Business Days Only', 'Send Window Start', 'Send Window End',
                'Created At', 'Last Triggered'
            ])
            
            # Write rules
            for rule in rules:
                writer.writerow([
                    rule.id,
                    rule.name,
                    rule.trigger_type,
                    rule.delay_hours,
                    rule.max_count,
                    rule.message_type,
                    rule.is_active,
                    rule.apply_to_all,
                    rule.stop_on_reply,
                    rule.business_days_only,
                    rule.send_window_start.strftime('%H:%M') if rule.send_window_start else '',
                    rule.send_window_end.strftime('%H:%M') if rule.send_window_end else '',
                    rule.created_at.astimezone(FollowUpService.india_tz).strftime('%Y-%m-%d %H:%M:%S') if rule.created_at else '',
                    rule.last_triggered.astimezone(FollowUpService.india_tz).strftime('%Y-%m-%d %H:%M:%S') if rule.last_triggered else ''
                ])
            
            return output.getvalue()
            
        except Exception as e:
            logger.error(f"Error exporting rules for user {user_id}: {str(e)}")
            return ""
    
    @staticmethod
    def export_logs(user_id):
        """
        Export follow-up logs for a user as CSV.
        
        Args:
            user_id: ID of the user
            
        Returns:
            String: CSV content
        """
        try:
            import csv
            import io
            
            # Import models inside method to avoid circular imports
            from app.models.follow_up import FollowUpLog
            from app.models.automation import FollowUpRule
            
            # Get the user's rule IDs
            rule_ids = [rule.id for rule in FollowUpRule.query.filter_by(user_id=user_id).all()]
            
            # Get the logs
            logs = FollowUpLog.query.filter(FollowUpLog.rule_id.in_(rule_ids)).all()
            
            # Create a CSV in memory
            output = io.StringIO()
            writer = csv.writer(output)
            
            # Write header
            writer.writerow([
                'ID', 'Rule ID', 'Original Email ID', 'Follow-Up ID',
                'Follow-Up Number', 'Recipient Email', 'Status', 'Reason',
                'Scheduled At', 'Sent At', 'Created At'
            ])
            
            # Write logs
            for log in logs:
                writer.writerow([
                    log.id,
                    log.rule_id,
                    log.original_email_id,
                    log.follow_up_id,
                    log.follow_up_number,
                    log.recipient_email,
                    log.status.value if hasattr(log.status, 'value') else log.status,
                    log.reason,
                    log.scheduled_at.astimezone(FollowUpService.india_tz).strftime('%Y-%m-%d %H:%M:%S') if log.scheduled_at else '',
                    log.sent_at.astimezone(FollowUpService.india_tz).strftime('%Y-%m-%d %H:%M:%S') if log.sent_at else '',
                    log.created_at.astimezone(FollowUpService.india_tz).strftime('%Y-%m-%d %H:%M:%S') if log.created_at else ''
                ])
            
            return output.getvalue()
            
        except Exception as e:
            logger.error(f"Error exporting logs for user {user_id}: {str(e)}")
            return ""
    
    @staticmethod
    def pause_all_follow_ups(user_id):
        """
        Pause all follow-up rules for a user.
        
        Args:
            user_id: ID of the user
            
        Returns:
            int: Number of rules paused
        """
        try:
            # Import models inside method to avoid circular imports
            from app.models.automation import FollowUpRule
            
            # Get all active rules
            rules = FollowUpRule.query.filter_by(user_id=user_id, is_active=True).all()
            
            count = 0
            for rule in rules:
                rule.is_active = False
                count += 1
            
            db.session.commit()
            logger.info(f"Paused {count} follow-up rules for user {user_id}")
            return count
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error pausing all follow-ups for user {user_id}: {str(e)}")
            return 0
    
    @staticmethod
    def resume_all_follow_ups(user_id):
        """
        Resume all follow-up rules for a user.
        
        Args:
            user_id: ID of the user
            
        Returns:
            int: Number of rules resumed
        """
        try:
            # Import models inside method to avoid circular imports
            from app.models.automation import FollowUpRule
            
            # Get all inactive rules
            rules = FollowUpRule.query.filter_by(user_id=user_id, is_active=False).all()
            
            count = 0
            for rule in rules:
                rule.is_active = True
                count += 1
            
            db.session.commit()
            logger.info(f"Resumed {count} follow-up rules for user {user_id}")
            return count
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error resuming all follow-ups for user {user_id}: {str(e)}")
            return 0
    
    @staticmethod
    def get_recent_emails_for_user(user_id, limit=20):
        """
        Get recent emails for the user to display in the follow-up modal.
        
        Args:
            user_id: ID of the user
            limit: Maximum number of emails to return
            
        Returns:
            List of Email objects
        """
        try:
            # Import models inside method to avoid circular imports
            from app.models.email import Email
            
            return Email.query.filter_by(user_id=user_id).order_by(Email.received_at.desc()).limit(limit).all()
            
        except Exception as e:
            logger.error(f"Error getting recent emails for user {user_id}: {str(e)}")
            return []
    
    @staticmethod
    def schedule_follow_up(email_id, scheduled_at, content, user_id):
        """
        Create a follow-up record based on selected email.
        
        Args:
            email_id: The ID of the email to follow up on
            scheduled_at: Datetime for when the follow-up should be sent (in India timezone)
            content: The follow-up message content
            user_id: ID of the user scheduling the follow-up
            
        Returns:
            FollowUp: The created follow-up record or None if failed
        """
        try:
            # Import models inside method to avoid circular imports
            from app.models.follow_up import FollowUp
            from app.models.email import Email, SentEmail
            
            # Get the email to follow up on
            email = Email.query.get(email_id)
            if not email:
                logger.error(f"Email {email_id} not found")
                return None
            
            # Convert scheduled_at to India timezone if it's not already
            if scheduled_at.tzinfo is None:
                # Assume it's in India time if no timezone info
                scheduled_india = FollowUpService.india_tz.localize(scheduled_at)
            else:
                scheduled_india = scheduled_at.astimezone(FollowUpService.india_tz)
            
            # Convert to UTC for storage
            scheduled_utc = scheduled_india.astimezone(pytz.UTC)
                
            # Create the follow-up record with thread_id
            follow_up = FollowUp(
                user_id=user_id,
                email_id=email_id,
                thread_id=email.thread_id,  # Add thread_id from email
                recipient_email=email.sender,  # Add recipient_email from email
                scheduled_at=scheduled_utc,
                content=content,
                status='pending'
            )
            
            db.session.add(follow_up)
            db.session.commit()
            
            logger.info(f"Scheduled follow-up for email {email_id} at {scheduled_india.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            return follow_up
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error scheduling follow-up: {str(e)}")
            return None
    
    @staticmethod
    def schedule_follow_up_for_recipients(recipient_emails, scheduled_at, content, user_id):
        """
        Create a follow-up record for specific recipients without linking to an email.
        
        Args:
            recipient_emails: Comma-separated list of recipient email addresses
            scheduled_at: Datetime for when the follow-up should be sent (in India timezone)
            content: The follow-up message content
            user_id: ID of the user scheduling the follow-up
            
        Returns:
            FollowUp: The created follow-up record or None if failed
        """
        try:
            # Import models inside method to avoid circular imports
            from app.models.follow_up import FollowUp
            
            # Parse recipient emails
            recipients = [email.strip() for email in recipient_emails.replace('\n', ',').split(',') if email.strip()]
            
            if not recipients:
                logger.error("No valid recipient emails provided")
                return None
            
            # Convert scheduled_at to India timezone if it's not already
            if scheduled_at.tzinfo is None:
                # Assume it's in India time if no timezone info
                scheduled_india = FollowUpService.india_tz.localize(scheduled_at)
            else:
                scheduled_india = scheduled_at.astimezone(FollowUpService.india_tz)
            
            # Convert to UTC for storage
            scheduled_utc = scheduled_india.astimezone(pytz.UTC)
                
            # Create the follow-up record without linking to an email
            # IMPORTANT: Set thread_id to None for standalone follow-ups
            follow_up = FollowUp(
                user_id=user_id,
                email_id=None,  # No email to follow up on
                thread_id=None,  # Set to None for standalone follow-ups
                recipient_email=', '.join(recipients),  # Store all recipients
                scheduled_at=scheduled_utc,
                content=content,
                status='pending'
            )
            
            db.session.add(follow_up)
            db.session.commit()
            
            logger.info(f"Scheduled follow-up for recipients {', '.join(recipients)} at {scheduled_india.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            return follow_up
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error scheduling follow-up for recipients: {str(e)}")
            return None
    
    @staticmethod
    def schedule_follow_up_for_sent_email(sent_email_id, scheduled_at, content, user_id):
        """
        Create a follow-up record based on a sent email.
        
        Args:
            sent_email_id: The ID of the sent email to follow up on
            scheduled_at: Datetime for when the follow-up should be sent (in India timezone)
            content: The follow-up message content
            user_id: ID of the user scheduling the follow-up
            
        Returns:
            FollowUp: The created follow-up record or None if failed
        """
        try:
            # Import models inside method to avoid circular imports
            from app.models.follow_up import FollowUp
            from app.models.email import SentEmail
            
            # Get the sent email to follow up on
            sent_email = SentEmail.query.get(sent_email_id)
            if not sent_email:
                logger.error(f"Sent email {sent_email_id} not found")
                return None
            
            # Convert scheduled_at to India timezone if it's not already
            if scheduled_at.tzinfo is None:
                # Assume it's in India time if no timezone info
                scheduled_india = FollowUpService.india_tz.localize(scheduled_at)
            else:
                scheduled_india = scheduled_at.astimezone(FollowUpService.india_tz)
            
            # Convert to UTC for storage
            scheduled_utc = scheduled_india.astimezone(pytz.UTC)
                
            # Create the follow-up record with thread_id
            follow_up = FollowUp(
                user_id=user_id,
                sent_email_id=sent_email_id,
                email_id=sent_email.email_id,
                thread_id=sent_email.thread_id,  # Add thread_id from sent email
                recipient_email=sent_email.to,  # Add recipient_email from sent email
                scheduled_at=scheduled_utc,
                content=content,
                status='pending'
            )
            
            db.session.add(follow_up)
            db.session.commit()
            
            logger.info(f"Scheduled follow-up for sent email {sent_email_id} at {scheduled_india.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            return follow_up
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error scheduling follow-up for sent email {sent_email_id}: {str(e)}")
            return None

# Legacy function for backward compatibility
def process_follow_ups():
    """Legacy function for backward compatibility."""
    return FollowUpService.check_and_send_follow_ups()