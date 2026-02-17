# app/cli.py
import click
from flask import current_app
from app.utils.scheduler import automation_scheduler
from app.services.auto_reply_service import AutoReplyService
from app.services.follow_up_service import FollowUpService

def register_cli(app):
    """Register all CLI commands with the Flask app."""
    
    @app.cli.command()
    @click.option('--verbose', is_flag=True, help='Show detailed job information')
    def test_scheduler(verbose):
        """Test scheduler configuration and jobs."""
        click.echo("🔍 Testing scheduler configuration...")
        
        # Check scheduler timezone
        timezone = current_app.config.get('SCHEDULER_TIMEZONE', 'UTC')
        click.echo(f"📅 Scheduler timezone: {timezone}")
        
        # Check intervals
        auto_reply_interval = current_app.config.get('AUTO_REPLY_CHECK_INTERVAL_MINUTES', 1)
        follow_up_interval = current_app.config.get('FOLLOW_UP_CHECK_INTERVAL_MINUTES', 1)
        click.echo(f"⏱️ Auto-reply check interval: {auto_reply_interval} minutes")
        click.echo(f"⏱️ Follow-up check interval: {follow_up_interval} minutes")
        
        # List all jobs
        try:
            jobs = automation_scheduler.get_jobs()
            click.echo(f"📋 Found {len(jobs)} scheduled jobs:")
            
            for job in jobs:
                if verbose:
                    click.echo(f"  - ID: {job['id']}")
                    click.echo(f"    Name: {job['name']}")
                    click.echo(f"    Next run: {job['next_run_time_india']}")
                    click.echo(f"    Trigger: {job['trigger']}")
                else:
                    click.echo(f"  - {job['id']} (Next run: {job['next_run_time_india']})")
            
            # Check for critical jobs
            auto_reply_job = next((j for j in jobs if j['id'] == 'auto_reply_job'), None)
            if auto_reply_job:
                click.echo("✅ Auto-reply job is registered")
            else:
                click.echo("❌ Auto-reply job is NOT registered")
            
            scheduled_replies_job = next((j for j in jobs if j['id'] == 'scheduled_replies_job'), None)
            if scheduled_replies_job:
                click.echo("✅ Scheduled replies job is registered")
            else:
                click.echo("❌ Scheduled replies job is NOT registered")
            
            follow_up_job = next((j for j in jobs if j['id'] == 'follow_up_check'), None)
            if follow_up_job:
                click.echo("✅ Follow-up job is registered")
            else:
                click.echo("❌ Follow-up job is NOT registered")
                
        except Exception as e:
            click.echo(f"❌ Error checking scheduler: {str(e)}")
    
    @app.cli.command()
    def run_auto_reply_now():
        """Manually run auto-reply processing."""
        click.echo("🔄 Running auto-reply processing...")
        try:
            result = AutoReplyService.check_and_send_auto_replies()
            count = result.get('count', 0) if result else 0
            click.echo(f"✅ Processed {count} auto-replies")
        except Exception as e:
            click.echo(f"❌ Error: {str(e)}")
    
    @app.cli.command()
    def run_scheduled_replies_now():
        """Manually run scheduled replies processing."""
        click.echo("⏰ Running scheduled replies processing...")
        try:
            result = AutoReplyService.check_scheduled_auto_replies()
            count = result.get('count', 0) if result else 0
            click.echo(f"✅ Processed {count} scheduled replies")
        except Exception as e:
            click.echo(f"❌ Error: {str(e)}")
    
    @app.cli.command()
    def run_follow_ups_now():
        """Manually run follow-up processing."""
        click.echo("🔄 Running follow-up processing...")
        try:
            result = FollowUpService.check_and_send_follow_ups()
            count = result.get('count', 0) if result else 0
            click.echo(f"✅ Processed {count} follow-ups")
        except Exception as e:
            click.echo(f"❌ Error: {str(e)}")
    
    @app.cli.command()
    @click.argument('email_id', type=int)
    @click.argument('rule_id', type=int)
    def test_auto_reply_rule(email_id, rule_id):
        """Test a specific auto-reply rule on a specific email."""
        click.echo(f"🧪 Testing auto-reply rule {rule_id} on email {email_id}...")
        try:
            from app.models.email import Email
            from app.models.auto_reply import AutoReplyRule, AutoReplyTemplate
            from app.models.user import User
            
            # Get the email
            email = Email.query.get(email_id)
            if not email:
                click.echo(f"❌ Email {email_id} not found")
                return
            
            # Get the rule
            rule = AutoReplyRule.query.get(rule_id)
            if not rule:
                click.echo(f"❌ Rule {rule_id} not found")
                return
            
            # Get the user
            user = User.query.get(email.user_id)
            if not user:
                click.echo(f"❌ User {email.user_id} not found")
                return
            
            # Get the template
            template = AutoReplyTemplate.query.get(rule.template_id)
            if not template:
                click.echo(f"❌ Template {rule.template_id} not found")
                return
            
            # Send the test auto-reply
            success = AutoReplyService.send_auto_reply(
                email=email,
                template=template,
                user=user,
                rule=rule,
                bypass_delay=True,
                bypass_cooldown=True,
                bypass_scheduler=True
            )
            
            if success:
                click.echo(f"✅ Test auto-reply sent successfully to {email.sender}")
            else:
                click.echo(f"❌ Failed to send test auto-reply")
                
        except Exception as e:
            click.echo(f"❌ Error: {str(e)}")
    
    @app.cli.command()
    @click.option('--hours', default=24, help='Hours of logs to show')
    def show_auto_reply_logs(hours):
        """Show recent auto-reply logs."""
        click.echo(f"📋 Showing auto-reply logs from the last {hours} hours...")
        try:
            from app.models.auto_reply import AutoReplyLog
            from datetime import datetime, timedelta
            
            cutoff_time = datetime.utcnow() - timedelta(hours=hours)
            logs = AutoReplyLog.query.filter(
                AutoReplyLog.created_at >= cutoff_time
            ).order_by(AutoReplyLog.created_at.desc()).limit(50).all()
            
            if not logs:
                click.echo("No logs found in the specified time range.")
                return
            
            for log in logs:
                status_icon = "✅" if log.status == 'Sent' else "❌"
                click.echo(f"{status_icon} {log.created_at.strftime('%Y-%m-%d %H:%M:%S')} - {log.status}")
                if log.skip_reason:
                    click.echo(f"    Reason: {log.skip_reason}")
                if log.sender_email:
                    click.echo(f"    To: {log.sender_email}")
                    
        except Exception as e:
            click.echo(f"❌ Error: {str(e)}")
    
    @app.cli.command()
    def show_scheduled_replies():
        """Show all scheduled auto-replies."""
        click.echo("📋 Showing all scheduled auto-replies...")
        try:
            from app.models.auto_reply import ScheduledAutoReply
            from app.utils.scheduler import AutoReplyService
            
            scheduled = ScheduledAutoReply.query.filter_by(status='Scheduled').all()
            
            if not scheduled:
                click.echo("No scheduled auto-replies found.")
                return
            
            for reply in scheduled:
                scheduled_time = AutoReplyService.utc_to_indian_time(reply.scheduled_at)
                click.echo(f"📅 Email {reply.email_id} - Rule {reply.rule_id}")
                click.echo(f"   Scheduled: {scheduled_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
                
        except Exception as e:
            click.echo(f"❌ Error: {str(e)}")
    
    @app.cli.command()
    def clear_scheduled_replies():
        """Clear all scheduled auto-replies."""
        click.echo("🗑️ Clearing all scheduled auto-replies...")
        try:
            from app.models.auto_reply import ScheduledAutoReply
            
            count = ScheduledAutoReply.query.filter_by(status='Scheduled').count()
            ScheduledAutoReply.query.filter_by(status='Scheduled').delete()
            from app import db
            db.session.commit()
            
            click.echo(f"✅ Cleared {count} scheduled auto-replies")
            
        except Exception as e:
            click.echo(f"❌ Error: {str(e)}")