# app/utils/tasks.py
import logging
import atexit
from datetime import datetime, timedelta, timezone
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR
from app import db
import pytz

logger = logging.getLogger(__name__)

# FIXED: Store app globally instead of creating new one each time
_app = None
_schedulers = {}

def init_tasks(app):
    """Initialize tasks with the Flask app instance"""
    global _app
    _app = app
    logger.info("Tasks initialized with Flask app context")

def with_app_context(func):
    """Execute function with existing app context"""
    if _app is None:
        raise RuntimeError("Tasks app not initialized. Call init_tasks() first.")
    
    def wrapper(*args, **kwargs):
        with _app.app_context():
            logger.info(f"Running scheduled task: {func.__name__}")
            try:
                start_time = datetime.now(timezone.utc)
                result = func(*args, **kwargs)
                duration = (datetime.now(timezone.utc) - start_time).total_seconds()
                logger.info(f"Completed scheduled task {func.__name__} in {duration:.2f} seconds")
                return result
            except Exception as e:
                logger.exception(f"Error in scheduled task {func.__name__}: {str(e)}")
                raise
    return wrapper

# FIXED: Use a single scheduler instance
def get_scheduler(name):
    """Get or create a scheduler by name"""
    if name not in _schedulers:
        # CRITICAL FIX: Use timezone from config or default to Asia/Kolkata
        timezone_name = 'Asia/Kolkata'
        if _app and 'SCHEDULER_TIMEZONE' in _app.config:
            timezone_name = _app.config.get('SCHEDULER_TIMEZONE', 'Asia/Kolkata')
        
        scheduler_timezone = pytz.timezone(timezone_name)
        
        _schedulers[name] = BackgroundScheduler(
            job_defaults={
                'coalesce': True,
                'misfire_grace_time': 300,
                'max_instances': 1
            },
            timezone=scheduler_timezone
        )
        _schedulers[name].add_listener(_job_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)
    return _schedulers[name]

def _job_listener(event):
    """Log job execution events"""
    now_india = datetime.now(timezone.utc).astimezone(pytz.timezone('Asia/Kolkata'))
    
    if event.exception:
        logger.error(f"❌ Job {event.job_id} crashed at {now_india.strftime('%Y-%m-%d %H:%M:%S %Z')}: {event.exception}")
    else:
        logger.info(f"✅ Job {event.job_id} executed successfully at {now_india.strftime('%Y-%m-%d %H:%M:%S %Z')}")

def setup_classification_scheduler():
    """Set up scheduler for email classification"""
    scheduler = get_scheduler('classification')
    
    # Run classification every 5 minutes
    scheduler.add_job(
        func=with_app_context(_process_email_classification),
        trigger=IntervalTrigger(minutes=5),
        id='email_classification_job',
        replace_existing=True
    )
    
    return scheduler

def setup_auto_reply_scheduler():
    """Set up scheduler for auto-reply processing"""
    scheduler = get_scheduler('auto_reply')
    
    # CRITICAL FIX: Run auto-reply check every 5 minutes (not 2)
    scheduler.add_job(
        func=with_app_context(_process_auto_replies),
        trigger=IntervalTrigger(minutes=5),
        id='auto_reply_job',
        replace_existing=True
    )
    
    # CRITICAL FIX: Check for scheduled auto-replies every 1 minute (not 10)
    scheduler.add_job(
        func=with_app_context(_check_scheduled_auto_replies),
        trigger=IntervalTrigger(minutes=1),
        id='scheduled_auto_replies_job',
        replace_existing=True
    )
    
    return scheduler

def setup_follow_up_scheduler():
    """Set up scheduler for follow-up processing"""
    scheduler = get_scheduler('follow_up')
    
    # CRITICAL FIX: Run follow-up check every 5 minutes (not 1) to prevent excessive runs
    scheduler.add_job(
        func=with_app_context(_process_follow_ups),
        trigger=IntervalTrigger(minutes=5),
        id='follow_up_job',
        replace_existing=True
    )
    
    return scheduler

def setup_email_cleanup_scheduler():
    """Set up scheduler for cleaning up old email data"""
    scheduler = get_scheduler('cleanup')
    
    # Run cleanup daily at 2 AM
    scheduler.add_job(
        func=with_app_context(_cleanup_old_email_data),
        trigger=CronTrigger(hour=2, minute=0),
        id='email_cleanup_job',
        replace_existing=True
    )
    
    return scheduler

def setup_email_sync_scheduler():
    """Set up scheduler for syncing emails from Gmail"""
    scheduler = get_scheduler('sync')
    
    # Run email sync every 10 minutes
    scheduler.add_job(
        func=with_app_context(_sync_emails_from_gmail),
        trigger=IntervalTrigger(minutes=10),
        id='email_sync_job',
        replace_existing=True
    )
    
    return scheduler

def setup_user_activity_scheduler():
    """Set up scheduler for tracking user activity"""
    scheduler = get_scheduler('activity')
    
    # Run user activity check every hour
    scheduler.add_job(
        func=with_app_context(_update_user_activity),
        trigger=IntervalTrigger(hours=1),
        id='user_activity_job',
        replace_existing=True
    )
    
    return scheduler

def setup_all_schedulers():
    """Set up all schedulers for the application"""
    if _app is None:
        raise RuntimeError("App not initialized. Call init_tasks() first.")
    
    # Check if schedulers are already running
    if all(scheduler.running for scheduler in _schedulers.values()):
        logger.info("All schedulers are already running")
        return _schedulers
    
    try:
        setup_classification_scheduler()
        setup_auto_reply_scheduler()
        setup_follow_up_scheduler()
        setup_email_cleanup_scheduler()
        setup_email_sync_scheduler()
        setup_user_activity_scheduler()
        
        # Start all schedulers
        for name, scheduler in _schedulers.items():
            if not scheduler.running:
                scheduler.start()
                logger.info(f"Started {name} scheduler")
        
        # Register shutdown function to properly close schedulers
        atexit.register(shutdown_all_schedulers)
        
        logger.info("All schedulers started successfully")
        return _schedulers
        
    except Exception as e:
        logger.error(f"Error setting up schedulers: {str(e)}")
        return {}

def shutdown_all_schedulers():
    """Shutdown all running schedulers"""
    for name, scheduler in _schedulers.items():
        try:
            if scheduler.running:
                scheduler.shutdown(wait=False)
                logger.info(f"Shutdown {name} scheduler")
        except Exception as e:
            logger.error(f"Error shutting down {name} scheduler: {str(e)}")

# FIXED: Direct implementation without creating new app context
def _process_email_classification():
    """Process email classification with proper app context"""
    from app.routes.email_routes import process_new_emails_for_classification
    
    logger.info("🔥 EMAIL CLASSIFICATION SERVICE ACTUALLY EXECUTED 🔥")
    process_new_emails_for_classification()

def _process_auto_replies():
    """Process auto-replies with proper app context"""
    from app.services.auto_reply_service import AutoReplyService
    
    logger.info("🔥 AUTO REPLY SERVICE ACTUALLY EXECUTED 🔥")
    
    # Process auto-replies for all users
    result = AutoReplyService.check_and_send_auto_replies()
    
    if result is not None:
        if isinstance(result, dict):
            processed_count = result.get('count', 0)
        elif isinstance(result, (int, float)):
            processed_count = int(result)
        else:
            processed_count = 0
        
        logger.info(f"Auto-reply check completed. Processed {processed_count} auto-replies.")
    else:
        logger.info("Auto-reply check completed. No auto-replies to process.")

def _check_scheduled_auto_replies():
    """Check for scheduled auto-replies with proper app context"""
    from app.services.auto_reply_service import AutoReplyService
    
    logger.info("🔥 SCHEDULED AUTO REPLY CHECK ACTUALLY EXECUTED 🔥")
    
    # Check for scheduled auto-replies
    result = AutoReplyService.check_scheduled_auto_replies()
    
    if result is not None:
        if isinstance(result, dict):
            processed_count = result.get('count', 0)
        elif isinstance(result, (int, float)):
            processed_count = int(result)
        else:
            processed_count = 0
        
        logger.info(f"Scheduled auto-reply check completed. Processed {processed_count} auto-replies.")
    else:
        logger.info("Scheduled auto-reply check completed. No auto-replies to process.")

def _process_follow_ups():
    """Process follow-ups with proper app context"""
    from app.models.follow_up import FollowUp
    from app.services.follow_up_service import FollowUpService
    
    logger.info("🔥 FOLLOW UP SERVICE ACTUALLY EXECUTED 🔥")
    
    now = datetime.now(timezone.utc)
    now_india = now.astimezone(pytz.timezone('Asia/Kolkata'))
    
    # Get all pending follow-ups that are due
    pending_followups = FollowUp.query.filter(
        FollowUp.status == 'pending',
        FollowUp.scheduled_at <= now
    ).all()
    
    logger.info(f"Found {len(pending_followups)} pending follow-ups that are due at {now_india.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    
    for fu in pending_followups:
        try:
            # Check if it's a business day if required (using India time)
            if fu.business_days_only and now_india.weekday() >= 5:  # Saturday=5, Sunday=6
                logger.info(f"Skipping follow-up {fu.id}: not a business day in India")
                continue
            
            # Check if within send window (using India time)
            if fu.send_window_start and fu.send_window_end:
                current_time_india = now_india.time()
                if current_time_india < fu.send_window_start or current_time_india > fu.send_window_end:
                    logger.info(f"Skipping follow-up {fu.id}: outside send window ({current_time_india} vs {fu.send_window_start}-{fu.send_window_end})")
                    continue
            
            # Send the follow-up
            success = FollowUpService.send_follow_up(fu)
            
            if success:
                fu.status = 'sent'
                fu.sent_at = now
                db.session.commit()
                logger.info(f"Successfully sent follow-up {fu.id} to {fu.recipient_email}")
            else:
                fu.status = 'failed'
                db.session.commit()
                logger.error(f"Failed to send follow-up {fu.id} to {fu.recipient_email}")
                
        except Exception as e:
            fu.status = 'failed'
            db.session.commit()
            logger.error(f"Error sending follow-up {fu.id}: {str(e)}")

def _cleanup_old_email_data():
    """Clean up old email data with proper app context"""
    from app.models.email import Email
    
    logger.info("Starting cleanup of old email data...")
    
    # Define retention period (e.g., 1 year)
    retention_period = datetime.now(timezone.utc) - timedelta(days=365)
    
    # Find old emails
    old_emails = Email.query.filter(
        Email.received_at < retention_period
    ).all()
    
    # Count emails to be deleted
    email_count = len(old_emails)
    
    if email_count > 0:
        # Delete old emails
        for email in old_emails:
            db.session.delete(email)
        
        db.session.commit()
        logger.info(f"Deleted {email_count} old emails")
    else:
        logger.info("No old emails to delete")
    
    logger.info("Email cleanup completed")

def _sync_emails_from_gmail():
    """Sync emails from Gmail with proper app context"""
    from app.models.user import User
    from app.services.gmail_service import GmailService
    
    logger.info("Starting email sync from Gmail...")
    
    # Get all users with Gmail credentials
    users = User.query.filter(User.gmail_credentials.isnot(None)).all()
    
    for user in users:
        try:
            gmail_service = GmailService(user)
            count = gmail_service.sync_emails()
            logger.info(f"Synced {count} emails for user {user.username}")
        except Exception as e:
            logger.error(f"Error syncing emails for user {user.username}: {str(e)}")
    
    logger.info("Email sync from Gmail completed")

def _update_user_activity():
    """Update user activity with proper app context"""
    from app.models.user import User
    from app.models.email import Email, SentEmail
    
    logger.info("Starting user activity update...")
    
    # Get all users
    users = User.query.all()
    
    for user in users:
        try:
            # Calculate activity metrics
            now = datetime.now(timezone.utc)
            day_ago = now - timedelta(days=1)
            week_ago = now - timedelta(days=7)
            month_ago = now - timedelta(days=30)
            
            # Count emails received and sent in different time periods
            emails_received_day = Email.query.filter(
                Email.user_id == user.id,
                Email.received_at >= day_ago
            ).count()
            
            emails_sent_day = SentEmail.query.filter(
                SentEmail.user_id == user.id,
                SentEmail.sent_at >= day_ago
            ).count()
            
            emails_received_week = Email.query.filter(
                Email.user_id == user.id,
                Email.received_at >= week_ago
            ).count()
            
            emails_sent_week = SentEmail.query.filter(
                SentEmail.user_id == user.id,
                SentEmail.sent_at >= week_ago
            ).count()
            
            emails_received_month = Email.query.filter(
                Email.user_id == user.id,
                Email.received_at >= month_ago
            ).count()
            
            emails_sent_month = SentEmail.query.filter(
                SentEmail.user_id == user.id,
                SentEmail.sent_at >= month_ago
            ).count()
            
            # Update user activity stats
            user.last_activity = now
            user.emails_received_day = emails_received_day
            user.emails_sent_day = emails_sent_day
            user.emails_received_week = emails_received_week
            user.emails_sent_week = emails_sent_week
            user.emails_received_month = emails_received_month
            user.emails_sent_month = emails_sent_month
            
            db.session.commit()
            logger.info(f"Updated activity for user {user.id}")
            
        except Exception as e:
            logger.error(f"Error updating activity for user {user.id}: {str(e)}")
            db.session.rollback()
    
    logger.info("User activity update completed")

# FIXED: Test rule execution without scheduling
def execute_test_rule_immediately(email_id, rule_id):
    """Execute a test rule immediately without scheduling"""
    if _app is None:
        raise RuntimeError("App not initialized. Call init_tasks() first.")
    
    with _app.app_context():
        from app.models.email import Email
        from app.models.auto_reply import AutoReplyRule, AutoReplyTemplate
        from app.services.auto_reply_service import AutoReplyService
        
        logger.info(f"🔥 EXECUTING TEST RULE {rule_id} FOR EMAIL {email_id} 🔥")
        
        # Get the email and rule
        email = Email.query.get(email_id)
        rule = AutoReplyRule.query.get(rule_id)
        
        if not email:
            logger.error(f"Email {email_id} not found")
            return False
        
        if not rule:
            logger.error(f"Rule {rule_id} not found")
            return False
        
        # Get the user
        from app.models.user import User
        user = User.query.get(email.user_id)
        if not user:
            logger.error(f"User {email.user_id} not found")
            return False
        
        # Get the template
        template = AutoReplyTemplate.query.get(rule.template_id)
        if not template:
            logger.error(f"Template {rule.template_id} not found")
            return False
        
        # Send the auto-reply immediately with bypass flags
        success = AutoReplyService.send_auto_reply(
            email=email, 
            template=template, 
            user=user, 
            rule=rule,
            bypass_delay=True,
            bypass_scheduler=True  # CRITICAL FIX: Removed bypass_cooldown
        )
        
        if success:
            logger.info(f"✅ Test rule {rule_id} executed successfully for email {email_id}")
        else:
            logger.error(f"❌ Test rule {rule_id} failed for email {email_id}")
        
        return success

# FIXED: Schedule delayed reply with proper app context
def schedule_delayed_reply(email_id, rule_id, delay_minutes):
    """Schedule a delayed reply with proper app context"""
    # CRITICAL FIX: Always use UTC for scheduling
    scheduled_time = datetime.now(timezone.utc) + timedelta(minutes=delay_minutes)
    scheduled_time_india = scheduled_time.astimezone(pytz.timezone('Asia/Kolkata'))
    job_id = f"delayed_reply_{email_id}_{rule_id}"
    
    # Get the auto-reply scheduler
    scheduler = get_scheduler('auto_reply')
    
    # Schedule the job
    scheduler.add_job(
        func=with_app_context(lambda: _send_delayed_reply(email_id, rule_id)),
        trigger=DateTrigger(run_date=scheduled_time),
        id=job_id,
        replace_existing=True,
        misfire_grace_time=300
    )
    
    logger.info(f"📅 Scheduled delayed reply for email {email_id} using rule {rule_id} at {scheduled_time_india.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    return job_id

def _send_delayed_reply(email_id, rule_id):
    """Send a delayed reply with proper app context"""
    from app.models.email import Email
    from app.models.auto_reply import AutoReplyRule, AutoReplyTemplate, ScheduledAutoReply
    from app.models.user import User
    from app.services.auto_reply_service import AutoReplyService
    
    logger.info(f"🔥 DELAYED REPLY ACTUALLY EXECUTED FOR EMAIL {email_id} RULE {rule_id} 🔥")
    
    # Get the email and rule
    email = Email.query.get(email_id)
    rule = AutoReplyRule.query.get(rule_id)
    
    if not email:
        logger.error(f"❌ Email {email_id} not found")
        return
    
    if not rule:
        logger.error(f"❌ Rule {rule_id} not found")
        return
    
    # Get the user
    user = User.query.get(email.user_id)
    if not user:
        logger.error(f"❌ User {email.user_id} not found")
        return
    
    # CRITICAL FIX: Check if auto-reply is still needed using gmail_id instead of message_id
    if AutoReplyService.has_email_gmail_id_been_replied(email.gmail_id, user.id):
        logger.info(f"⚠️ Email {email_id} with Gmail ID {email.gmail_id} already has auto-reply sent")
        return
    
    # Get the template
    template = AutoReplyTemplate.query.get(rule.template_id)
    if not template:
        logger.error(f"❌ Template {rule.template_id} not found for rule {rule.id}")
        return
    
    # CRITICAL FIX: Check if there's a scheduled reply in the database
    scheduled_reply = ScheduledAutoReply.query.filter_by(
        email_id=email_id,
        rule_id=rule_id,
        status='Scheduled'
    ).first()
    
    if scheduled_reply:
        # Update the status to 'Processing'
        scheduled_reply.status = 'Processing'
        db.session.commit()
        
        # CRITICAL FIX: Check if this is an "apply_to_all" rule and if this template has already been sent to this email
        # ONLY check this for "apply_to_all" rules, not for sender-specific rules
        if AutoReplyService.is_apply_to_all_rule(rule):
            if AutoReplyService.has_current_template_been_sent_to_email(email.sender, template.id, user.id, template.updated_at):
                logger.info(f"  SKIPPING: Current version of template {template.id} already sent to {email.sender} via 'apply to all' rule")
                scheduled_reply.status = 'Cancelled'
                db.session.commit()
                return
        
        # Send the delayed reply
        success = AutoReplyService.send_auto_reply(
            email=email, 
            template=template, 
            user=user, 
            rule=rule,
            bypass_delay=True,      # Bypass delay check (already delayed)
            bypass_scheduler=True   # CRITICAL FIX: Removed bypass_cooldown
        )
        
        if success:
            # Update the scheduled reply status
            scheduled_reply.status = 'Sent'
            scheduled_reply.sent_at = datetime.now(timezone.utc)
            db.session.commit()
            
            # Update the last_triggered timestamp for the rule
            rule.last_triggered = datetime.now(timezone.utc)
            db.session.commit()
            
            logger.info(f"✅ Successfully sent delayed reply for email {email_id}")
        else:
            # Update the scheduled reply status
            scheduled_reply.status = 'Failed'
            db.session.commit()
            
            logger.error(f"❌ Failed to send delayed reply for email {email_id}")
    else:
        # No scheduled reply found in database, create one and send
        logger.warning(f"⚠️ No scheduled reply found in database for email {email_id}, rule {rule_id}")
        
        # CRITICAL FIX: Check if this is an "apply_to_all" rule and if this template has already been sent to this email
        # ONLY check this for "apply_to_all" rules, not for sender-specific rules
        if AutoReplyService.is_apply_to_all_rule(rule):
            if AutoReplyService.has_current_template_been_sent_to_email(email.sender, template.id, user.id, template.updated_at):
                logger.info(f"  SKIPPING: Current version of template {template.id} already sent to {email.sender} via 'apply to all' rule")
                return
        
        # Send the delayed reply
        success = AutoReplyService.send_auto_reply(
            email=email, 
            template=template, 
            user=user, 
            rule=rule,
            bypass_delay=True,      # Bypass delay check (already delayed)
            bypass_scheduler=True   # CRITICAL FIX: Removed bypass_cooldown
        )
        
        if success:
            # Create a scheduled reply record
            scheduled_reply = ScheduledAutoReply(
                user_id=user.id,
                email_id=email_id,
                rule_id=rule_id,
                template_id=template.id,
                scheduled_at=datetime.now(timezone.utc),
                status='Sent',
                sent_at=datetime.now(timezone.utc)
            )
            db.session.add(scheduled_reply)
            
            # Update the last_triggered timestamp for the rule
            rule.last_triggered = datetime.now(timezone.utc)
            db.session.commit()
            
            logger.info(f"✅ Successfully sent delayed reply for email {email_id}")
        else:
            logger.error(f"❌ Failed to send delayed reply for email {email_id}")

def get_scheduler_status():
    """Get the status of all schedulers"""
    status = {}
    india_tz = pytz.timezone('Asia/Kolkata')
    
    for name, scheduler in _schedulers.items():
        try:
            status[name] = {
                'running': scheduler.running,
                'jobs': []
            }
            
            # Get job information
            for job in scheduler.get_jobs():
                next_run_india = None
                if job.next_run_time:
                    next_run_india = job.next_run_time.astimezone(india_tz).strftime('%Y-%m-%d %H:%M:%S %Z')
                
                status[name]['jobs'].append({
                    'id': job.id,
                    'name': job.name,
                    'next_run_time_utc': job.next_run_time.isoformat() if job.next_run_time else None,
                    'next_run_time_india': next_run_india
                })
                
        except Exception as e:
            status[name] = {
                'error': str(e)
            }
    
    return status

def restart_scheduler(scheduler_name):
    """Restart a specific scheduler"""
    if scheduler_name not in _schedulers:
        logger.error(f"Scheduler {scheduler_name} not found")
        return False
    
    try:
        # Shutdown the existing scheduler
        _schedulers[scheduler_name].shutdown(wait=False)
        
        # Create and start a new scheduler
        if scheduler_name == 'classification':
            setup_classification_scheduler()
        elif scheduler_name == 'auto_reply':
            setup_auto_reply_scheduler()
        elif scheduler_name == 'follow_up':
            setup_follow_up_scheduler()
        elif scheduler_name == 'cleanup':
            setup_email_cleanup_scheduler()
        elif scheduler_name == 'sync':
            setup_email_sync_scheduler()
        elif scheduler_name == 'activity':
            setup_user_activity_scheduler()
        else:
            logger.error(f"Unknown scheduler name: {scheduler_name}")
            return False
        
        # Start the scheduler
        _schedulers[scheduler_name].start()
        logger.info(f"Restarted {scheduler_name} scheduler")
        return True
        
    except Exception as e:
        logger.error(f"Error restarting {scheduler_name} scheduler: {str(e)}")
        return False

def pause_scheduler(scheduler_name):
    """Pause a specific scheduler"""
    if scheduler_name not in _schedulers:
        logger.error(f"Scheduler {scheduler_name} not found")
        return False
    
    try:
        _schedulers[scheduler_name].pause()
        logger.info(f"Paused {scheduler_name} scheduler")
        return True
        
    except Exception as e:
        logger.error(f"Error pausing {scheduler_name} scheduler: {str(e)}")
        return False

def resume_scheduler(scheduler_name):
    """Resume a paused scheduler"""
    if scheduler_name not in _schedulers:
        logger.error(f"Scheduler {scheduler_name} not found")
        return False
    
    try:
        _schedulers[scheduler_name].resume()
        logger.info(f"Resumed {scheduler_name} scheduler")
        return True
        
    except Exception as e:
        logger.error(f"Error resuming {scheduler_name} scheduler: {str(e)}")
        return False