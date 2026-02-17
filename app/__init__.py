# app/__init__.py
import logging
from flask import Flask
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from config import config
import os

# Initialize extensions
db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()

# Create logger
logger = logging.getLogger(__name__)

# Global app instance for background tasks
app_instance = None

def create_app(config_name='development'):
    """Create and configure the Flask application."""
    global app_instance
    app = Flask(__name__)
    app_instance = app
    app.config.from_object(config[config_name])
    
    # CRITICAL: Ensure SECRET_KEY is set
    if not app.config.get('SECRET_KEY') or app.config['SECRET_KEY'] == 'a-default-secret-key-for-dev-only-change-me':
        print("WARNING: Using a default or missing SECRET_KEY. Set a permanent SECRET_KEY for production.")

    # Initialize extensions with app
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    
    # Configure login manager
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'
    login_manager.session_protection = 'strong'
    
    # Set up user loader function
    @login_manager.user_loader
    def load_user(user_id):
        # Use the modern db.session.get() method
        from app.models.user import User
        return db.session.get(User, int(user_id))
    
    # FIXED: Import all models BEFORE registering blueprints to ensure proper model registration
    # Import User model first as it's referenced by other models
    from app.models.user import User
    
    # Import Email-related models
    from app.models.email import Email, EmailCategory, EmailClassification, SentEmail, DraftEmail, EmailAttachment
    
    # CRITICAL FIX: Import all auto-reply models including the missing ones
    from app.models.auto_reply import AutoReplyTemplate, AutoReplyRule, AutoReplyLog, ScheduledAutoReply
    
    # Import automation models
    from app.models.automation import AutomationRule, ClassificationRule, FollowUpRule, FollowUpTemplate
    
    # Import FollowUp model
    from app.models.follow_up import FollowUp, FollowUpSequence, FollowUpLog
    
    # Register blueprints AFTER importing all models
    from app.routes.auth import auth as auth_blueprint
    app.register_blueprint(auth_blueprint, url_prefix='/auth')
    
    from app.routes.main import main as main_blueprint
    app.register_blueprint(main_blueprint)
    
    from app.routes.email_routes import email as email_blueprint
    app.register_blueprint(email_blueprint, url_prefix='/email')
    
    from app.routes.api import api as api_blueprint
    app.register_blueprint(api_blueprint, url_prefix='/api')
    
    # Create database tables if they don't exist
    with app.app_context():
        db.create_all()
    
    # Initialize utilities
    from app.utils.environment import init_app as init_env
    from app.utils.database import init_db
    
    # Initialize environment and database utilities
    init_env(app)
    init_db(app)
    
    # CRITICAL FIX: Initialize scheduler only when not in testing mode
    if not app.testing:
        try:
            # Initialize scheduler with default jobs
            from app.utils.scheduler import automation_scheduler
            automation_scheduler.init_app(app)
            
            # CRITICAL FIX: Verify scheduler was properly initialized
            if automation_scheduler.scheduler and automation_scheduler.scheduler.running:
                logger.info("✅ Scheduler initialized and started successfully")
                
                # CRITICAL FIX: Verify all required jobs are registered
                jobs = automation_scheduler.get_jobs()
                job_ids = [job['id'] for job in jobs]
                required_jobs = ['auto_reply_check', 'scheduled_replies_check', 'follow_up_check', 'email_sync']
                
                missing_jobs = [job_id for job_id in required_jobs if job_id not in job_ids]
                
                if missing_jobs:
                    logger.error(f"❌ Missing scheduler jobs: {', '.join(missing_jobs)}")
                    
                    # CRITICAL FIX: Try to add missing jobs directly
                    logger.info("Attempting to add missing scheduler jobs...")
                    
                    # Add missing auto-reply job
                    if 'auto_reply_check' in missing_jobs:
                        automation_scheduler.schedule_auto_reply_check(
                            minutes=app.config.get('AUTO_REPLY_CHECK_INTERVAL_MINUTES', 5)
                        )
                        logger.info("✅ Added missing auto-reply job")
                    
                    # Add missing scheduled replies job
                    if 'scheduled_replies_check' in missing_jobs:
                        automation_scheduler.schedule_scheduled_replies_check(
                            minutes=1
                        )
                        logger.info("✅ Added missing scheduled replies job")
                    
                    # Add missing follow-up job
                    if 'follow_up_check' in missing_jobs:
                        automation_scheduler.schedule_follow_up_check(
                            minutes=5
                        )
                        logger.info("✅ Added missing follow-up job")
                    
                    # Add missing email sync job
                    if 'email_sync' in missing_jobs:
                        automation_scheduler.schedule_email_sync(
                            minutes=app.config.get('EMAIL_CHECK_INTERVAL_MINUTES', 60)
                        )
                        logger.info("✅ Added missing email sync job")
            else:
                logger.error("❌ Scheduler object is None or not running")
                
                # FALLBACK: Try direct APScheduler initialization
                try:
                    logger.info("Attempting fallback scheduler initialization...")
                    from apscheduler.schedulers.background import BackgroundScheduler
                    from app.services.follow_up_service import FollowUpService
                    from app.services.auto_reply_service import AutoReplyService
                    
                    # CRITICAL FIX: Get timezone from config
                    timezone_name = app.config.get('SCHEDULER_TIMEZONE', 'Asia/Kolkata')
                    import pytz
                    scheduler_timezone = pytz.timezone(timezone_name)
                    
                    # Create a new scheduler with correct timezone
                    scheduler = BackgroundScheduler(
                        job_defaults={
                            'coalesce': True,
                            'misfire_grace_time': 300,
                            'max_instances': 1
                        },
                        timezone=scheduler_timezone
                    )
                    
                    # CRITICAL FIX: Add ALL the required jobs with correct IDs
                    scheduler.add_job(
                        func=process_with_context(FollowUpService.check_and_send_follow_ups),
                        trigger='interval',
                        minutes=5,
                        id='follow_up_check'
                    )
                    
                    scheduler.add_job(
                        func=process_with_context(AutoReplyService.check_and_send_auto_replies),
                        trigger='interval',
                        minutes=5,
                        id='auto_reply_check'  # CRITICAL: Use the correct ID
                    )
                    
                    scheduler.add_job(
                        func=process_with_context(AutoReplyService.check_scheduled_auto_replies),
                        trigger='interval',
                        minutes=1,
                        id='scheduled_replies_check'  # CRITICAL: Use the correct ID
                    )
                    
                    # Start the scheduler
                    scheduler.start()
                    
                    # Store the scheduler in the app context
                    app.scheduler = scheduler
                    
                    logger.info("✅ Fallback APScheduler initialized and started successfully")
                except Exception as fallback_e:
                    logger.error(f"Fallback scheduler initialization also failed: {str(fallback_e)}")
        
        # FIXED: Added missing except block for the outer try
        except Exception as e:
            logger.error(f"Scheduler initialization failed: {str(e)}")
    
    # Register error handlers, context processors, etc.
    register_error_handlers(app)
    register_template_context(app)
    register_template_filters(app)
    register_cli_commands(app)
    
    return app

def process_with_context(func):
    """Execute a function within the application context."""
    def wrapper():
        try:
            # Use the global app_instance instead of creating a new one
            with app_instance.app_context():
                return func()
        except Exception as e:
            logger.error(f"Error in scheduled task {func.__name__}: {str(e)}")
            return None
    
    return wrapper  # Return the wrapper function, not the result of calling it

def register_error_handlers(app):
    """Register custom error handlers."""
    
    @app.errorhandler(404)
    def not_found_error(error):
        from flask import render_template
        return render_template('errors/404.html'), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        from flask import render_template
        db.session.rollback()
        return render_template('errors/500.html'), 500
    
    @app.errorhandler(403)
    def forbidden_error(error):
        from flask import render_template
        return render_template('errors/403.html'), 403

def register_template_context(app):
    """Register custom template context processors."""
    
    @app.context_processor
    def inject_now():
        from datetime import datetime
        return {'now': datetime.utcnow()}
    
    @app.context_processor
    def inject_config():
        return {
            'APP_NAME': app.config.get('APP_NAME', 'AI Email Dashboard'),
            'VERSION': app.config.get('VERSION', '1.0.0')
        }

def register_template_filters(app):
    """Register custom template filters."""
    
    @app.template_filter('format_date')
    def format_date(date):
        """Format a datetime object for display."""
        if not date:
            return ''
        
        # If it's already a string, try to parse it
        if isinstance(date, str):
            try:
                from datetime import datetime
                # Try to parse ISO format
                date = datetime.fromisoformat(date.replace('Z', '+00:00'))
            except:
                return date  # Return as-is if parsing fails
        
        # Format the datetime
        from datetime import datetime
        if isinstance(date, datetime):
            # If today, show time only
            if date.date() == datetime.utcnow().date():
                return date.strftime('%I:%M %p').lstrip('0')
            # If this year, show month and day
            elif date.year == datetime.utcnow().year:
                return date.strftime('%b %d')
            # Otherwise show full date
            else:
                return date.strftime('%b %d, %Y')
        
        return str(date)
    
    @app.template_filter('format_datetime')
    def format_datetime(date):
        """Format a datetime object with time for display."""
        if not date:
            return ''
        
        # If it's already a string, try to parse it
        if isinstance(date, str):
            try:
                from datetime import datetime
                # Try to parse ISO format
                date = datetime.fromisoformat(date.replace('Z', '+00:00'))
            except:
                return date  # Return as-is if parsing fails
        
        # Format the datetime
        from datetime import datetime
        if isinstance(date, datetime):
            return date.strftime('%b %d, %Y at %I:%M %p').lstrip('0')
        
        return str(date)

def register_cli_commands(app):
    """Register custom CLI commands."""
    
    @app.cli.command()
    def init_db():
        """Initialize the database."""
        # FIXED: Import all models to ensure they are registered
        from app.models.user import User
        from app.models.email import Email, EmailCategory, EmailClassification, SentEmail, DraftEmail, EmailAttachment
        from app.models.auto_reply import AutoReplyTemplate, AutoReplyRule, AutoReplyLog, ScheduledAutoReply  # CRITICAL FIX: Add missing models
        from app.models.automation import AutomationRule, ClassificationRule, FollowUpRule, FollowUpTemplate
        from app.models.follow_up import FollowUp, FollowUpSequence, FollowUpLog
        
        db.create_all()
        print('Database initialized.')
    
    @app.cli.command()
    def check_gmail_config():
        """Check Gmail configuration."""
        from app.utils.environment import get_client_secrets_path
        path = get_client_secrets_path()
        
        if os.path.exists(path):
            print(f"client_secrets.json found at: {path}")
        else:
            print(f"client_secrets.json NOT found at: {path}")
            print("Please download it from Google Cloud Console and place it in the project root.")
    
    @app.cli.command()
    def reset_db():
        """Reset the database."""
        from app.models.user import User
        from app.models.email import Email, EmailCategory, EmailClassification, SentEmail, DraftEmail, EmailAttachment
        from app.models.auto_reply import AutoReplyTemplate, AutoReplyRule, AutoReplyLog, ScheduledAutoReply  # CRITICAL FIX: Add missing models
        from app.models.automation import AutomationRule, ClassificationRule, FollowUpRule, FollowUpTemplate
        from app.models.follow_up import FollowUp, FollowUpSequence, FollowUpLog
        
        db.drop_all()
        db.create_all()
        print('Database reset.')
    
    @app.cli.command()
    def sync_emails():
        """Sync emails from Gmail."""
        with app.app_context():
            from app.services.gmail_service import GmailService
            from app.models.user import User
            
            # Get all users with Gmail credentials
            users = User.query.filter(User.gmail_credentials.isnot(None)).all()
            
            for user in users:
                try:
                    gmail_service = GmailService(user)
                    count = gmail_service.sync_emails()
                    print(f"Synced {count} emails for user {user.username}")
                except Exception as e:
                    print(f"Error syncing emails for user {user.username}: {str(e)}")
            
            print('Email sync completed.')
    
    @app.cli.command()
    def process_classifications():
        """Process email classifications manually."""
        with app.app_context():
            from app.routes.email_routes import process_new_emails_for_classification
            process_new_emails_for_classification()
            print('Email classification processing completed.')
    
    @app.cli.command()
    def process_auto_replies():
        """Process auto-replies manually."""
        with app.app_context():
            from app.services.auto_reply_service import AutoReplyService
            result = AutoReplyService.check_and_send_auto_replies()
            print(f'Auto-reply processing completed. Processed {result.get("count", 0)} emails.')
    
    @app.cli.command()
    def process_follow_ups():
        """Process follow-ups manually."""
        with app.app_context():
            from app.services.follow_up_service import FollowUpService
            result = FollowUpService.check_and_send_follow_ups()
            print(f'Follow-up processing completed. Processed {result.get("count", 0)} follow-ups.')
    
    @app.cli.command()
    def check_scheduled_auto_replies():
        """Check scheduled auto-replies manually."""
        with app.app_context():
            from app.services.auto_reply_service import AutoReplyService
            result = AutoReplyService.check_scheduled_auto_replies()
            print(f'Scheduled auto-replies check completed. Processed {result.get("count", 0)} replies.')
    
    @app.cli.command()
    def test_scheduler():
        """Test the scheduler functionality."""
        with app.app_context():
            try:
                from app.utils.scheduler import automation_scheduler
                jobs = automation_scheduler.get_jobs()
                print(f"Current scheduled jobs: {len(jobs)}")
                for job in jobs:
                    print(f"- {job.id}: {job.name} (Next run: {job.get('next_run_time_india', job.get('next_run_time'))}")
                    
                # CRITICAL FIX: Check specifically for auto-reply jobs
                auto_reply_job = next((j for j in jobs if j['id'] == 'auto_reply_check'), None)
                if auto_reply_job:
                    print("✅ Auto-reply job is registered")
                else:
                    print("❌ Auto-reply job is NOT registered")
                    
                # CRITICAL FIX: Check specifically for scheduled replies job
                scheduled_replies_job = next((j for j in jobs if j['id'] == 'scheduled_replies_check'), None)
                if scheduled_replies_job:
                    print("✅ Scheduled replies job is registered")
                else:
                    print("❌ Scheduled replies job is NOT registered")
                    
                # CRITICAL FIX: Check specifically for follow-up job
                follow_up_job = next((j for j in jobs if j['id'] == 'follow_up_check'), None)
                if follow_up_job:
                    print("✅ Follow-up job is registered")
                else:
                    print("❌ Follow-up job is NOT registered")
                    
                # CRITICAL FIX: Check specifically for email sync job
                email_sync_job = next((j for j in jobs if j['id'] == 'email_sync'), None)
                if email_sync_job:
                    print("✅ Email sync job is registered")
                else:
                    print("❌ Email sync job is NOT registered")
                    
            except Exception as e:
                print(f"Error checking automation_scheduler: {str(e)}")
                
                # Try to check the fallback scheduler
                try:
                    if hasattr(app_instance, 'scheduler'):
                        jobs = app_instance.scheduler.get_jobs()
                        print(f"Fallback scheduler jobs: {len(jobs)}")
                        for job in jobs:
                            print(f"- {job.id}: {job.name} (Next run: {job.next_run_time})")
                    else:
                        print("No scheduler found")
                except Exception as fallback_e:
                    print(f"Error checking fallback scheduler: {str(fallback_e)}")
    
    @app.cli.command()
    def start_scheduler():
        """Start the scheduler manually."""
        with app.app_context():
            try:
                from app.utils.scheduler import automation_scheduler
                automation_scheduler.start()
                print('Automation scheduler started.')
            except Exception as e:
                print(f"Error starting automation_scheduler: {str(e)}")
                
                # Try to start the fallback scheduler
                try:
                    if hasattr(app_instance, 'scheduler'):
                        app_instance.scheduler.start()
                        print('Fallback scheduler started.')
                    else:
                        print("No scheduler found to start")
                except Exception as fallback_e:
                    print(f"Error starting fallback scheduler: {str(fallback_e)}")
    
    @app.cli.command()
    def stop_scheduler():
        """Stop the scheduler manually."""
        with app.app_context():
            try:
                from app.utils.scheduler import automation_scheduler
                automation_scheduler.shutdown()
                print('Automation scheduler stopped.')
            except Exception as e:
                print(f"Error stopping automation_scheduler: {str(e)}")
                
                # Try to stop the fallback scheduler
                try:
                    if hasattr(app_instance, 'scheduler'):
                        app_instance.scheduler.shutdown()
                        print('Fallback scheduler stopped.')
                    else:
                        print("No scheduler found to stop")
                except Exception as fallback_e:
                    print(f"Error stopping fallback scheduler: {str(fallback_e)}")
    
    @app.cli.command()
    def check_followups():
        """Check and send follow-ups manually."""
        with app.app_context():
            from app.services.follow_up_service import FollowUpService
            result = FollowUpService.check_and_send_follow_ups()
            print(f'Follow-ups checked and sent if due. Processed {result.get("count", 0)} follow-ups.')
    
    # CRITICAL FIX: Add a new command to test auto-reply functionality
    @app.cli.command()
    def test_auto_reply():
        """Test auto-reply functionality."""
        with app.app_context():
            from app.services.auto_reply_service import AutoReplyService
            
            # Test auto-reply processing
            result = AutoReplyService.check_and_send_auto_replies()
            print(f"Auto-reply test completed. Processed {result.get('count', 0)} emails.")
            
            # Test scheduled replies
            result = AutoReplyService.check_scheduled_auto_replies()
            print(f"Scheduled replies test completed. Processed {result.get('count', 0)} replies.")
    
    # CRITICAL FIX: Import and register the CLI commands
    @app.cli.command()
    def debug_scheduler():
        """Debug scheduler configuration and job registration."""
        with app.app_context():
            try:
                from app.utils.scheduler import automation_scheduler
                
                print("🔍 Debugging scheduler configuration...")
                
                # Check if scheduler exists and is running
                if not automation_scheduler.scheduler:
                    print("❌ Scheduler is not initialized")
                    return
                
                if not automation_scheduler.scheduler.running:
                    print("❌ Scheduler is not running")
                    return
                
                print("✅ Scheduler is initialized and running")
                
                # List all jobs
                jobs = automation_scheduler.get_jobs()
                print(f"Found {len(jobs)} jobs:")
                
                # Check for required jobs
                required_jobs = [
                    'auto_reply_check',
                    'scheduled_replies_check',
                    'follow_up_check',
                    'email_sync'
                ]
                
                missing_jobs = []
                for job_id in required_jobs:
                    job_found = next((j for j in jobs if j['id'] == job_id), None)
                    if not job_found:
                        missing_jobs.append(job_id)
                
                if missing_jobs:
                    print(f"❌ Missing jobs: {', '.join(missing_jobs)}")
                    
                    # Try to add missing jobs
                    for job_id in missing_jobs:
                        if job_id == 'auto_reply_check':
                            automation_scheduler.schedule_auto_reply_check(
                                minutes=app.config.get('AUTO_REPLY_CHECK_INTERVAL_MINUTES', 5)
                            )
                            print(f"✅ Added missing auto-reply job")
                        elif job_id == 'scheduled_replies_check':
                            automation_scheduler.schedule_scheduled_replies_check(
                                minutes=1
                            )
                            print(f"✅ Added missing scheduled replies job")
                        elif job_id == 'follow_up_check':
                            automation_scheduler.schedule_follow_up_check(
                                minutes=5
                            )
                            print(f"✅ Added missing follow-up job")
                        elif job_id == 'email_sync':
                            automation_scheduler.schedule_email_sync(
                                minutes=app.config.get('EMAIL_CHECK_INTERVAL_MINUTES', 60)
                            )
                            print(f"✅ Added missing email sync job")
                
                # Show job details
                for job in jobs:
                    next_run = job.get('next_run_time_india', 'Unknown')
                    print(f"- {job['id']}: {job['name']} (Next run: {next_run})")
                
                # Test job execution
                print("\n🧪 Testing job execution...")
                
                # Test auto-reply job
                try:
                    from app.services.auto_reply_service import AutoReplyService
                    result = AutoReplyService.check_and_send_auto_replies()
                    print(f"✅ Auto-reply job executed successfully (processed {result.get('count', 0)} emails)")
                except Exception as e:
                    print(f"❌ Error executing auto-reply job: {str(e)}")
                
                # Test scheduled replies job
                try:
                    from app.services.auto_reply_service import AutoReplyService
                    result = AutoReplyService.check_scheduled_auto_replies()
                    print(f"✅ Scheduled replies job executed successfully (processed {result.get('count', 0)} replies)")
                except Exception as e:
                    print(f"❌ Error executing scheduled replies job: {str(e)}")
                
                # Test follow-up job
                try:
                    from app.services.follow_up_service import FollowUpService
                    result = FollowUpService.check_and_send_follow_ups()
                    print(f"✅ Follow-up job executed successfully (processed {result.get('count', 0)} follow-ups)")
                except Exception as e:
                    print(f"❌ Error executing follow-up job: {str(e)}")
                
            except Exception as e:
                print(f"❌ Error debugging scheduler: {str(e)}")
    
    # Import and register the CLI commands
    try:
        from app.cli import register_cli
        register_cli(app)
    except ImportError:
        # If app.cli doesn't exist, skip this step
        pass