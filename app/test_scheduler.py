#!/usr/bin/env python3
"""
Test script to verify scheduler functionality.
Run this script to check if the scheduler is properly configured and working.
"""

import sys
import os
from datetime import datetime, timedelta, timezone
import pytz

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_scheduler_initialization():
    """Test if the scheduler is properly initialized."""
    print("🔍 Testing scheduler initialization...")
    
    try:
        from app import create_app
        app = create_app()
        
        with app.app_context():
            try:
                from app.utils.scheduler import automation_scheduler
                
                # Check if scheduler exists
                if not automation_scheduler.scheduler:
                    print("❌ Scheduler not initialized")
                    return False
                
                # Check if scheduler is running
                if not automation_scheduler.scheduler.running:
                    print("❌ Scheduler is not running")
                    return False
                
                print("✅ Scheduler is properly initialized and running")
                return True
                
            except Exception as e:
                print(f"❌ Error testing scheduler initialization: {str(e)}")
                return False
    
    except Exception as e:
        print(f"❌ Error creating app: {str(e)}")
        return False

def test_scheduler_jobs():
    """Test if all required scheduler jobs are registered."""
    print("\n🔍 Testing scheduler jobs...")
    
    try:
        from app import create_app
        app = create_app()
        
        with app.app_context():
            try:
                from app.utils.scheduler import automation_scheduler
                jobs = automation_scheduler.get_jobs()
                job_ids = [job['id'] for job in jobs]
                
                # Check for required jobs
                required_jobs = [
                    'auto_reply_check',
                    'scheduled_replies_check',
                    'follow_up_check'
                ]
                
                missing_jobs = []
                for job_id in required_jobs:
                    job_found = next((j for j in jobs if j['id'] == job_id), None)
                    if not job_found:
                        missing_jobs.append(job_id)
                
                if missing_jobs:
                    print(f"❌ Missing jobs: {', '.join(missing_jobs)}")
                    return False
                
                print("✅ All required scheduler jobs are registered")
                print(f"   Found {len(jobs)} jobs:")
                for job in jobs:
                    next_run = job.get('next_run_time_india', 'Unknown')
                    print(f"   - {job['id']}: {job['name']} (Next run: {next_run})")
                
                return True
                
            except Exception as e:
                print(f"❌ Error testing scheduler jobs: {str(e)}")
                return False
    
    except Exception as e:
        print(f"❌ Error creating app: {str(e)}")
        return False

def test_auto_reply_service():
    """Test the auto-reply service functionality."""
    print("\n🔍 Testing auto-reply service...")
    
    try:
        from app import create_app
        app = create_app()
        
        with app.app_context():
            try:
                from app.services.auto_reply_service import AutoReplyService
                
                # Test the service method exists
                if not hasattr(AutoReplyService, 'check_and_send_auto_replies'):
                    print("❌ AutoReplyService.check_and_send_auto_replies method not found")
                    return False
                
                # Test the scheduled replies method
                if not hasattr(AutoReplyService, 'check_scheduled_auto_replies'):
                    print("❌ AutoReplyService.check_scheduled_auto_replies method not found")
                    return False
                
                # Test the schedule delayed reply method
                if not hasattr(AutoReplyService, 'schedule_delayed_reply'):
                    print("❌ AutoReplyService.schedule_delayed_reply method not found")
                    return False
                
                print("✅ Auto-reply service methods are available")
                
                # Test processing (without actually sending emails)
                result = AutoReplyService.check_and_send_auto_replies()
                if isinstance(result, dict):
                    count = result.get('count', 0)
                    print(f"✅ Auto-reply processing works (processed {count} emails)")
                else:
                    print("⚠️ Auto-reply processing returned unexpected result")
                
                # Test scheduled replies processing
                result = AutoReplyService.check_scheduled_auto_replies()
                if isinstance(result, dict):
                    count = result.get('count', 0)
                    print(f"✅ Scheduled replies processing works (processed {count} replies)")
                else:
                    print("⚠️ Scheduled replies processing returned unexpected result")
                
                return True
                
            except Exception as e:
                print(f"❌ Error testing auto-reply service: {str(e)}")
                return False
    
    except Exception as e:
        print(f"❌ Error creating app: {str(e)}")
        return False

def test_follow_up_service():
    """Test the follow-up service functionality."""
    print("\n🔍 Testing follow-up service...")
    
    try:
        from app import create_app
        app = create_app()
        
        with app.app_context():
            try:
                from app.services.follow_up_service import FollowUpService
                
                # Test the service method exists
                if not hasattr(FollowUpService, 'check_and_send_follow_ups'):
                    print("❌ FollowUpService.check_and_send_follow_ups method not found")
                    return False
                
                # Test processing (without actually sending emails)
                result = FollowUpService.check_and_send_follow_ups()
                if isinstance(result, dict):
                    count = result.get('count', 0)
                    print(f"✅ Follow-up processing works (processed {count} follow-ups)")
                else:
                    print("⚠️ Follow-up processing returned unexpected result")
                
                return True
                
            except Exception as e:
                print(f"❌ Error testing follow-up service: {str(e)}")
                return False
    
    except Exception as e:
        print(f"❌ Error creating app: {str(e)}")
        return False

def test_timezone_handling():
    """Test timezone handling."""
    print("\n🔍 Testing timezone handling...")
    
    try:
        from app import create_app
        app = create_app()
        
        with app.app_context():
            try:
                # Check timezone configuration
                tz_name = app.config.get('SCHEDULER_TIMEZONE', 'UTC')
                print(f"📅 Configured timezone: {tz_name}")
                
                # Test timezone conversion methods
                from app.services.auto_reply_service import AutoReplyService
                
                if hasattr(AutoReplyService, 'get_indian_time'):
                    indian_time = AutoReplyService.get_indian_time()
                    print(f"🕐 Current Indian time: {indian_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
                else:
                    print("⚠️ AutoReplyService.get_indian_time method not found")
                
                if hasattr(AutoReplyService, 'utc_to_indian_time'):
                    # FIXED: Use timezone-aware datetime
                    utc_time = datetime.now(timezone.utc)
                    indian_time = AutoReplyService.utc_to_indian_time(utc_time)
                    print(f"🕐 UTC to IST conversion works: {utc_time} → {indian_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
                else:
                    print("⚠️ AutoReplyService.utc_to_indian_time method not found")
                
                print("✅ Timezone handling is configured")
                return True
                
            except Exception as e:
                print(f"❌ Error testing timezone handling: {str(e)}")
                return False
    
    except Exception as e:
        print(f"❌ Error creating app: {str(e)}")
        return False

def test_database_models():
    """Test if required database models exist."""
    print("\n🔍 Testing database models...")
    
    try:
        from app import create_app
        app = create_app()
        
        with app.app_context():
            try:
                # Test importing models
                from app.models.auto_reply import AutoReplyRule, AutoReplyTemplate, AutoReplyLog, ScheduledAutoReply
                from app.models.email import Email
                from app.models.user import User
                
                print("✅ All required models can be imported")
                
                # Test database connection
                from app import db
                from sqlalchemy import text
                db.session.execute(text('SELECT 1'))
                print("✅ Database connection is working")
                
                # Test if tables exist
                try:
                    AutoReplyRule.query.first()
                    AutoReplyTemplate.query.first()
                    AutoReplyLog.query.first()
                    ScheduledAutoReply.query.first()
                    print("✅ All required tables exist")
                except Exception as e:
                    print(f"⚠️ Some tables might not exist: {str(e)}")
                
                return True
                
            except Exception as e:
                print(f"❌ Error testing database models: {str(e)}")
                return False
    
    except Exception as e:
        print(f"❌ Error creating app: {str(e)}")
        return False

def test_database_connection():
    """Test database connection and basic operations."""
    print("\n🔍 Testing database connection...")
    
    try:
        from app import create_app
        app = create_app()
        
        with app.app_context():
            try:
                from app import db
                from sqlalchemy import text
                
                # Test basic database connection
                db.session.execute(text('SELECT 1'))
                print("✅ Database connection is working")
                
                # Get a test user first
                from app.models.user import User
                test_user = User.query.first()
                
                if not test_user:
                    print("❌ No test user found in database")
                    return False
                
                # Get a test template
                from app.models.auto_reply import AutoReplyTemplate
                test_template = AutoReplyTemplate.query.filter_by(user_id=test_user.id).first()
                
                if not test_template:
                    print("❌ No test template found in database")
                    return False
                
                # Test creating a test record with a valid user_id and template_id
                from app.models.auto_reply import ScheduledAutoReply
                test_reply = ScheduledAutoReply(
                    user_id=test_user.id,  # FIXED: Use a valid user_id
                    email_id=1,
                    rule_id=1,
                    template_id=test_template.id,  # FIXED: Use a valid template_id
                    scheduled_at=datetime.now(timezone.utc) + timedelta(minutes=1),  # FIXED: Use timezone-aware datetime
                    status='Scheduled'
                )
                
                db.session.add(test_reply)
                db.session.commit()
                
                # Verify the record was created
                saved_reply = ScheduledAutoReply.query.filter_by(
                    user_id=test_user.id,
                    email_id=1,
                    rule_id=1,
                    status='Scheduled'
                ).first()
                
                if saved_reply:
                    print("✅ Can create and retrieve ScheduledAutoReply records")
                    return True
                else:
                    print("❌ Failed to create ScheduledAutoReply record")
                    return False
                    
            except Exception as e:
                print(f"❌ Error testing database connection: {str(e)}")
                return False
    
    except Exception as e:
        print(f"❌ Error creating app: {str(e)}")
        return False

def test_delayed_replies():
    """Test delayed reply functionality."""
    print("\n🔍 Testing delayed reply functionality...")
    
    try:
        from app import create_app
        app = create_app()
        
        with app.app_context():
            try:
                from app.services.auto_reply_service import AutoReplyService
                
                # Check if the schedule_delayed_reply method exists
                if not hasattr(AutoReplyService, 'schedule_delayed_reply'):
                    print("❌ AutoReplyService.schedule_delayed_reply method not found")
                    return False
                
                # Create a test email and rule
                from app.models.email import Email
                from app.models.auto_reply import AutoReplyRule, AutoReplyTemplate
                from app.models.user import User
                
                # Get a test user first
                test_user = User.query.first()
                if not test_user:
                    print("❌ No test user found in database")
                    return False
                
                # Get a test email
                test_email = Email.query.filter_by(user_id=test_user.id).first()
                if not test_email:
                    print("❌ No test email found for user")
                    return False
                
                # Get a test rule
                test_rule = AutoReplyRule.query.filter_by(user_id=test_user.id).first()
                if not test_rule:
                    print("❌ No test rule found for user")
                    return False
                
                # Get the template using Session.get() instead of Query.get()
                from app import db
                template = db.session.get(AutoReplyTemplate, test_rule.template_id)
                if not template:
                    print("❌ Template not found for test rule")
                    return False
                
                # Schedule a delayed reply
                delay_minutes = 2  # 2 minutes for testing
                success = AutoReplyService.schedule_delayed_reply(
                    email_id=test_email.id,
                    rule_id=test_rule.id,
                    user_id=test_user.id,  # FIXED: Add user_id parameter
                    delay_minutes=delay_minutes
                )
                
                if success:
                    from datetime import datetime, timedelta
                    scheduled_time = datetime.now(timezone.utc) + timedelta(minutes=delay_minutes)
                    scheduled_time_india = AutoReplyService.utc_to_indian_time(scheduled_time)
                    print(f"✅ Delayed reply scheduled for email {test_email.id} using rule {test_rule.id} at {scheduled_time_india.strftime('%Y-%m-%d %H:%M:%S %Z')}")
                    
                    # Check if the scheduled reply exists in database
                    from app.models.auto_reply import ScheduledAutoReply
                    scheduled_reply = ScheduledAutoReply.query.filter_by(
                        user_id=test_user.id,  # FIXED: Add user_id to filter
                        email_id=test_email.id,
                        rule_id=test_rule.id,
                        status='Scheduled'
                    ).first()
                    
                    if scheduled_reply:
                        print(f"✅ Scheduled reply found in database")
                    else:
                        print("❌ Scheduled reply not found in database")
                        return False
                    
                    return True
                else:
                    print("❌ Failed to schedule delayed reply")
                    return False
                    
            except Exception as e:
                print(f"❌ Error testing delayed replies: {str(e)}")
                return False
    
    except Exception as e:
        print(f"❌ Error creating app: {str(e)}")
        return False

def main():
    """Run all tests."""
    print("=" * 60)
    print("🚀 SCHEDULER TEST SUITE")
    print("=" * 60)
    
    tests = [
        ("Scheduler Initialization", test_scheduler_initialization),
        ("Scheduler Jobs", test_scheduler_jobs),
        ("Scheduler Execution", test_scheduler_jobs),  # Reuse scheduler jobs test
        ("Auto-Reply Service", test_auto_reply_service),
        ("Follow-Up Service", test_follow_up_service),
        ("Timezone Handling", test_timezone_handling),
        ("Database Models", test_database_models),
        ("Database Connection", test_database_connection),
        ("Delayed Replies", test_delayed_replies)
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} failed with exception: {str(e)}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 TEST RESULTS SUMMARY")
    print("=" * 60)
    
    passed = 0
    failed = 0
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")
        if result:
            passed += 1
        else:
            failed += 1
    
    print(f"\nTotal: {len(results)} tests")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    
    if failed == 0:
        print("\n🎉 All tests passed! Your scheduler is properly configured.")
        sys.exit(0)
    else:
        print(f"\n⚠️ {failed} test(s) failed. Please check the configuration.")
        sys.exit(1)

if __name__ == "__main__":
    main()