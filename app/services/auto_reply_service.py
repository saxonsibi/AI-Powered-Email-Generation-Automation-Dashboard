# app/services/auto_reply_service.py

import logging
import re
from datetime import datetime, timedelta, time
from pytz import timezone

from app import db
from flask import current_app
from app.models.email import Email
from app.models.auto_reply import (
    AutoReplyRule,
    AutoReplyTemplate,
    AutoReplyLog,
    ScheduledAutoReply
)
from app.models.user import User
from app.services.gmail_service import GmailService

logger = logging.getLogger(__name__)

STATUS_SENT      = "Sent"
STATUS_FAILED    = "Failed"
STATUS_SKIPPED   = "Skipped"
STATUS_NOT_MATCHED = "Not_Matched"
STATUS_SCHEDULED = "Scheduled"
STATUS_CANCELLED = "Cancelled"

UTC_TZ = timezone('UTC')


class AutoReplyService:
    """
    Auto-reply service – production-ready version (2025 style)
    • thread-safe (static methods only)
    • proper transaction handling
    • safety guards against loops & spam
    • supports delayed replies & business hours (including overnight ranges)
    """

    @staticmethod
    def check_and_send_auto_replies(specific_rule_id=None):
        """
        Process active rules — either all or one specific rule
        
        🔧 FIXED: Now properly logs ALL outcomes (sent, skipped, failed, not_matched)
        """
        try:
            msg = "Starting auto-reply processing"
            if specific_rule_id:
                msg += f" for rule {specific_rule_id}"
            logger.info(f"🔍 {msg}")

            q = AutoReplyRule.query.filter_by(is_active=True)
            if specific_rule_id is not None:
                q = q.filter_by(id=specific_rule_id)

            rules = q.all()

            processed = sent = skipped = failed = not_matched = 0

            for rule in rules:
                try:
                    emails = AutoReplyService._get_emails_for_rule(rule)
                    logger.info(f"📧 Rule '{rule.name or rule.id}': {len(emails)} matching emails")

                    for email in emails:
                        try:
                            outcome = AutoReplyService._process_email_for_rule(email, rule)
                            if outcome == 'sent':       sent += 1
                            elif outcome == 'skipped':  skipped += 1
                            elif outcome == 'failed':   failed += 1
                            elif outcome == 'not_matched': not_matched += 1
                            processed += 1
                        except Exception as e:
                            logger.error(f"Email {email.id} failed under rule {rule.id}: {e}")
                            
                            # 🔧 FIXED: Log failures too
                            AutoReplyService._create_log_for_outcome(
                                email, rule, 'failed', str(e)
                            )
                            failed += 1

                except Exception as e:
                    logger.error(f"Rule {rule.id} processing failed: {e}")
                    continue

            result = {
                'processed': processed,
                'sent': sent,
                'skipped': skipped,
                'failed': failed,
                'not_matched': not_matched,
                'rules': len(rules)
            }
            logger.info(f"✅ Completed: {result}")
            return result

        except Exception as e:
            logger.exception("Critical failure in auto-reply processing")
            return {'error': str(e), 'rules': 0}


    @staticmethod
    def _create_log_for_outcome(email, rule, outcome, error_message=None, skip_reason=None):
        """
        🔧 NEW: Create log entry for any outcome (sent, skipped, failed, not_matched)
        """
        try:
            # Extract email fields safely
            recipient = email.sender if email else None
            subject = email.subject if email else None
            gmail_id = email.gmail_id if email else None
            email_id = email.id if email else None
            
            # 🔧 FIX: Check if log already exists before inserting
            existing = AutoReplyLog.query.filter_by(
                rule_id=rule.id,
                gmail_id=gmail_id
            ).first()
            if existing:
                logger.debug(f"📝 Log already exists for rule {rule.id}, gmail {gmail_id}, skipping duplicate")
                return
            
            log = AutoReplyLog(
                user_id=rule.user_id,
                rule_id=rule.id,
                email_id=email_id,
                gmail_id=gmail_id,
                template_id=rule.template_id,
                recipient_email=recipient or '',  # NOT NULL field
                incoming_subject=subject or '',   # NOT NULL field
                status=outcome.upper() if outcome != 'not_matched' else STATUS_NOT_MATCHED,
                sent_at=datetime.now(UTC_TZ) if outcome == 'sent' else None,
                skip_reason=skip_reason,
                error_message=error_message
            )
            db.session.add(log)
            db.session.commit()
            logger.debug(f"📝 Created log for outcome '{outcome}' for email {email_id or 'N/A'}")
        except Exception as e:
            logger.error(f"Failed to create log for outcome: {e}")
            db.session.rollback()


    @staticmethod
    def check_scheduled_auto_replies():
        try:
            logger.info("⏰ Checking due scheduled replies")

            now = datetime.now(UTC_TZ)
            due = ScheduledAutoReply.query.filter(
                ScheduledAutoReply.scheduled_at <= now,
                ScheduledAutoReply.status == STATUS_SCHEDULED
            ).all()

            processed = sent = failed = 0

            for item in due:
                try:
                    email = Email.query.get(item.email_id)
                    rule  = AutoReplyRule.query.get(item.rule_id)
                    user  = User.query.get(item.user_id)

                    if not (email and rule and user):
                        logger.error(f"Missing entities for scheduled {item.id}")
                        item.status = STATUS_FAILED
                        db.session.commit()
                        failed += 1
                        continue

                    if not AutoReplyService._validate_scheduled_reply(email, rule, user):
                        logger.info(f"Scheduled {item.id} no longer valid → skipped")
                        item.status = STATUS_SKIPPED
                        db.session.commit()
                        continue

                    tpl = AutoReplyTemplate.query.get(rule.template_id)
                    if not tpl:
                        logger.error(f"Missing template {rule.template_id}")
                        item.status = STATUS_FAILED
                        db.session.commit()
                        failed += 1
                        continue

                    ok = AutoReplyService.send_auto_reply(email, tpl, user, rule)

                    if ok:
                        item.status = STATUS_SENT
                        item.sent_at = datetime.now(UTC_TZ)
                        sent += 1
                        logger.info(f"Sent scheduled reply {item.id}")
                    else:
                        item.status = STATUS_FAILED
                        failed += 1

                    db.session.commit()
                    processed += 1

                except Exception as e:
                    logger.error(f"Scheduled {item.id} failed: {e}")
                    db.session.rollback()
                    failed += 1

            result = {'processed': processed, 'sent': sent, 'failed': failed, 'due': len(due)}
            logger.info(f"Scheduled check done: {result}")
            return result

        except Exception as e:
            logger.exception("Critical error in scheduled check")
            return {'error': str(e)}


    @staticmethod
    def should_process_email_for_rule(email, rule):
        try:
            if not rule.apply_to_existing_emails:
                if email.received_at and rule.updated_at:
                    # 🔧 FIX: Ensure both datetimes are timezone-aware for comparison
                    email_time = email.received_at
                    rule_time = rule.updated_at
                    
                    # 🔧 DEBUG: Log timestamps for debugging
                    logger.debug(f"📅 DEBUG: email.received_at={email_time}, rule.updated_at={rule_time}")
                    
                    # Make both timezone-aware if they're naive
                    if email_time is None:
                        logger.warning(f"📅 DEBUG: email.received_at is None for email {email.id}")
                        # Allow None received_at (newly synced emails)
                    elif email_time.tzinfo is None:
                        email_time = UTC_TZ.localize(email_time)
                    if rule_time.tzinfo is None:
                        rule_time = UTC_TZ.localize(rule_time)
                    
                    if email_time is not None and email_time < rule_time:
                        logger.info(f"📅 Skip: email older than rule (email: {email_time}, rule: {rule_time})")
                        return False, "email older than rule"

            # 🔧 FIXED: Check if already replied with rule_id parameter
            if AutoReplyService.has_email_gmail_id_been_replied(email.gmail_id, rule.user_id, rule.id):
                return False, "already replied"

            if email.folder == 'sent':
                return False, "sent folder"

            if not email.gmail_id:
                return False, "missing gmail_id"

            return True, "ok"

        except Exception as e:
            logger.error(f"should_process check failed: {e}")
            return False, "error"


    @staticmethod
    def is_safe_to_reply(email, gmail_service):
        try:
            if email.sender:
                domain = email.sender.split('@')[-1].lower()
                if any(kw in domain for kw in [
                    'noreply','no-reply','donotreply','do-not-reply',
                    'notification','alert','mailer','bounce'
                ]):
                    return False, "no-reply address"

                if domain in {
                    'mailchimp.com','campaignmonitor.com','constantcontact.com',
                    'sendgrid.com','mailgun.com','postmarkapp.com'
                }:
                    return False, "newsletter provider"

            if email.subject:
                s = email.subject.lower()
                if any(p in s for p in [
                    'auto-reply','automatic reply','out of office','ooo',
                    'vacation','away','delivery status','undeliverable'
                ]):
                    return False, "looks like auto/generated message"

            # best-effort thread check
            if email.thread_id:
                try:
                    user_email = gmail_service.user.email.lower() if gmail_service.user and gmail_service.user.email else None
                    
                    thread = gmail_service.get_thread(email.thread_id)
                    for msg in thread.get('messages', []):
                        if msg.get('id') != email.gmail_id:
                            for h in msg.get('payload',{}).get('headers',[]):
                                if h.get('name','').lower() == 'from':
                                    from_value = h.get('value','').lower()
                                    if user_email and user_email in from_value:
                                        return False, "already replied in thread"
                except Exception:
                    pass  # continue anyway

            return True, "safe"

        except Exception as e:
            logger.error(f"safety check failed: {e}")
            return False, "safety check error"


    @staticmethod
    def _get_emails_for_rule(rule):
        """
        Get all emails that should be processed for this rule.
        
        🔧 FIXED: Now uses DATABASE instead of Gmail API.
        This ensures proper duplicate detection and logging.
        
        Email sync happens via /api/check-new-emails endpoint.
        This function only processes emails already stored in DB.
        """
        try:
            from app.models.email import Email
            
            logger.info(f"🔍 DEBUG: _get_emails_for_rule called for rule {rule.id}")
            
            # Get user for the rule
            user = User.query.get(rule.user_id)
            if not user:
                logger.error(f"❌ User {rule.user_id} not found for rule {rule.id}")
                return []
            
            # CRITICAL FIX: Query from DATABASE, not Gmail API
            # Only get emails that have NOT been processed yet
            emails = Email.query.filter_by(
                user_id=rule.user_id,
                folder='inbox'
            ).filter(
                # Only get emails that haven't been processed for auto-reply
                Email.processed_for_auto_reply == False
            ).all()
            
            logger.info(f"📧 DB Query: Found {len(emails)} unprocessed emails for user {rule.user_id}")
            
            if not emails:
                logger.info(f"📭 No unprocessed emails in DB for user {rule.user_id}")
                logger.info(f"💡 Tip: Run /api/check-new-emails to sync emails from Gmail first")
                return []
            
            # Apply rule filters (sender, subject, etc.)
            # Log which emails match and which don't for debugging
            matched = []
            not_matched_reasons = {}
            for e in emails:
                if AutoReplyService.does_email_match_rule(e, rule):
                    matched.append(e)
                else:
                    # Try to get the reason
                    sender_filter_value = getattr(rule, 'sender_filter', None) or getattr(rule, 'sender_email', None)
                    subject_filter = getattr(rule, 'subject_filter', None)
                    reason = "filter mismatch"
                    if sender_filter_value:
                        if sender_filter_value.lower() not in (e.sender or '').lower():
                            reason = f"sender filter: '{sender_filter_value}' not in '{e.sender}'"
                    elif subject_filter:
                        if subject_filter.lower() not in (e.subject or '').lower():
                            reason = f"subject filter: '{subject_filter}' not in '{e.subject}'"
                    not_matched_reasons[e.id] = reason
            
            logger.info(f"✅ After rule matching: {len(matched)} emails matched, {len(not_matched_reasons)} not matched")
            
            # Log a few examples of why emails don't match
            if not_matched_reasons:
                examples = list(not_matched_reasons.items())[:3]
                for email_id, reason in examples:
                    logger.info(f"   📧 Email {email_id}: {reason}")
            
            return matched
        
        except Exception as e:
            logger.error(f"_get_emails_for_rule failed: {e}", exc_info=True)
            return []


    @staticmethod
    def _process_email_for_rule(email, rule):
        """
        Process a single email for a rule.
        
        🔧 FIXED: Now logs ALL outcomes including skipped and not_matched
        """
        try:
            # 🔍 DEBUG: Log start of processing
            logger.info(f"🔍 Processing email {email.id} for rule {rule.id} ('{rule.name}')")
            logger.info(f"   ↳ From: {email.sender}, Subject: {email.subject[:50] if email.subject else 'N/A'}")
            
            # Check if email matches rule conditions
            if not AutoReplyService.does_email_match_rule(email, rule):
                logger.info(f"❌ Skip {email.id}: rule conditions not matched")
                AutoReplyService._create_log_for_outcome(email, rule, 'not_matched')
                return 'not_matched'
            
            ok, reason = AutoReplyService.should_process_email_for_rule(email, rule)
            if not ok:
                logger.info(f"❌ Skip {email.id}: {reason}")
                AutoReplyService._create_log_for_outcome(email, rule, 'skipped', reason)
                return 'skipped'

            user = User.query.get(rule.user_id)
            if not user:
                logger.error(f"❌ User {rule.user_id} missing")
                AutoReplyService._create_log_for_outcome(email, rule, 'failed', 'User missing')
                return 'failed'

            gs = GmailService(user)
            safe, msg = AutoReplyService.is_safe_to_reply(email, gs)
            if not safe:
                logger.info(f"⚠️  Skip {email.id}: {msg}")
                AutoReplyService._create_log_for_outcome(email, rule, 'skipped', msg)
                return 'skipped'

            # Business hours check (supports overnight ranges)
            if rule.business_hours_start and rule.business_hours_end:
                try:
                    user_tz = timezone(user.timezone) if hasattr(user, 'timezone') and user.timezone else UTC_TZ
                except Exception:
                    logger.warning(f"Invalid timezone '{getattr(user, 'timezone', None)}' for user {user.id}, falling back to UTC")
                    user_tz = UTC_TZ
                
                now_local = datetime.now(user_tz)
                now_t = now_local.time()
                start = rule.business_hours_start
                end   = rule.business_hours_end

                if start <= end:
                    inside = start <= now_t <= end
                else:
                    inside = now_t >= start or now_t <= end

                if not inside:
                    logger.info(f"⏰ Skip {email.id}: outside business hours {start}–{end} "
                               f"(current time: {now_t} {user_tz.zone})")
                    AutoReplyService._create_log_for_outcome(email, rule, 'skipped', 'outside business hours')
                    return 'skipped'
                else:
                    logger.info(f"✓ Inside business hours: {now_t} {user_tz.zone} is within {start}–{end}")

            # delay?
            if rule.delay_minutes and rule.delay_minutes > 0:
                logger.info(f"⏱️  Scheduling delayed reply for email {email.id} ({rule.delay_minutes} minutes)")
                job = AutoReplyService.schedule_delayed_reply(email, rule, user, rule.delay_minutes)
                if job:
                    AutoReplyService._create_log_for_outcome(email, rule, 'skipped', 'scheduled for later')
                else:
                    AutoReplyService._create_log_for_outcome(email, rule, 'failed', 'failed to schedule')
                return 'skipped' if job else 'failed'

            # immediate
            logger.info(f"📤 Preparing to send immediate auto-reply for email {email.id}")
            tpl = AutoReplyTemplate.query.get(rule.template_id)
            if not tpl:
                logger.error(f"❌ Template {rule.template_id} missing")
                AutoReplyService._create_log_for_outcome(email, rule, 'failed', 'template missing')
                return 'failed'

            # 🔧 CRITICAL FIX: Create log BEFORE sending (atomic operation)
            # Check for duplicates first
            existing_log = AutoReplyLog.query.filter_by(
                rule_id=rule.id,
                gmail_id=email.gmail_id,
                status=STATUS_SENT
            ).first()
            
            if existing_log:
                logger.warning(f"⚠️ Duplicate detected! Email {email.gmail_id} already replied under rule {rule.id}")
                AutoReplyService._create_log_for_outcome(email, rule, 'skipped', 'duplicate - already sent')
                return 'skipped'

            # Create log with status 'Processing' BEFORE sending
            log = AutoReplyLog(
                user_id=user.id,
                rule_id=rule.id,
                email_id=email.id,
                gmail_id=email.gmail_id,
                template_id=tpl.id,
                recipient_email=email.sender or '',  # NOT NULL field
                incoming_subject=email.subject or '',   # NOT NULL field
                status='Processing',
                sent_at=datetime.now(UTC_TZ)
            )
            db.session.add(log)
            db.session.commit()
            logger.info(f"📝 Created processing log for email {email.id}")

            success = AutoReplyService.send_auto_reply(email, tpl, user, rule)
            
            if success:
                log.status = STATUS_SENT
                log.sent_at = datetime.now(UTC_TZ)
                db.session.commit()
                logger.info(f"✅ Successfully sent auto-reply to {email.sender}")
                return 'sent'
            else:
                log.status = STATUS_FAILED
                log.error_message = "Failed to send reply"
                db.session.commit()
                logger.error(f"❌ Failed to send auto-reply to {email.sender}")
                return 'failed'

        except Exception as e:
            logger.error(f"❌ Process email {email.id} failed: {str(e)}", exc_info=True)
            AutoReplyService._create_log_for_outcome(email, rule, 'failed', str(e))
            return 'failed'


    @staticmethod
    def send_auto_reply(email, template, user, rule):
        try:
            gs = GmailService(user)
            subj = AutoReplyService._prepare_reply_subject(email, template)
            body = AutoReplyService._prepare_reply_body(email, template, user)

            logger.info(f"🚀 Attempting to send auto-reply to {email.sender} for email {email.id}")
            
            # Determine if body is HTML or plain text - template uses 'reply_body' field
            is_html = template.reply_body and ('<' in template.reply_body and '>' in template.reply_body)
            
            success, error_msg, reply_id = gs.send_reply(
                message_id=email.gmail_id,
                body_html=body if is_html else None,
                body_text=body if not is_html else None
            )

            if success and reply_id:
                logger.info(f"✅ Successfully sent auto-reply to {email.sender} (reply_id: {reply_id})")
                return True
            else:
                logger.error(f"❌ Send failed to {email.sender}: {error_msg}")
                return False

        except Exception as e:
            logger.exception(f"❌ send_auto_reply failed for email {email.id}: {str(e)}")
            return False


    @staticmethod
    def schedule_delayed_reply(email, rule, user, delay_minutes):
        try:
            from app.utils.scheduler import get_scheduler
            sch = get_scheduler()
            if not sch:
                logger.error("No scheduler available")
                return None

            record = ScheduledAutoReply(
                user_id      = user.id,
                rule_id      = rule.id,
                email_id     = email.id,
                gmail_id     = email.gmail_id,
                scheduled_at = datetime.now(UTC_TZ) + timedelta(minutes=delay_minutes),
                status       = STATUS_SCHEDULED
            )
            db.session.add(record)
            db.session.commit()

            job_id = sch.schedule_delayed_reply(email.id, rule.id, user.id, delay_minutes)
            if job_id:
                logger.info(f"Scheduled delay for email {email.id}")
                return job_id

            db.session.delete(record)
            db.session.commit()
            return None

        except Exception as e:
            logger.exception("schedule_delayed_reply failed")
            return None


    @staticmethod
    def _validate_scheduled_reply(email, rule, user):
        try:
            if not rule.is_active: return False
            if not AutoReplyService.does_email_match_rule(email, rule): return False

            gs = GmailService(user)
            safe, _ = AutoReplyService.is_safe_to_reply(email, gs)
            if not safe: return False

            # 🔧 FIXED: Pass rule_id to prevent sending to same rule
            if AutoReplyService.has_email_gmail_id_been_replied(email.gmail_id, user.id, rule.id):
                return False

            return True
        except:
            return False


    @staticmethod
    def has_email_gmail_id_been_replied(gmail_id, user_id, rule_id=None):
        """
        🔧 FIXED: Now checks for ANY existing log status (Processing, Sent, Failed)
        to prevent UNIQUE constraint violations when creating logs BEFORE sending.
        Returns True if this exact gmail_id + rule_id combination already has any log entry.
        """
        if not gmail_id: return False
        try:
            # Check AutoReplyLog for this specific rule - check ANY status, not just Sent
            # This prevents duplicate log creation when status is 'Processing'
            q = AutoReplyLog.query.filter_by(gmail_id=gmail_id, user_id=user_id)
            if rule_id is not None:
                q = q.filter_by(rule_id=rule_id)
            if q.first():
                return True
            
            # Check ScheduledAutoReply using email_id (not gmail_id)
            # We need to find the email record first to get its ID
            from app.models.email import Email
            email_record = Email.query.filter_by(gmail_id=gmail_id, user_id=user_id).first()
            if email_record:
                q = ScheduledAutoReply.query.filter_by(email_id=email_record.id, user_id=user_id)
                if rule_id is not None:
                    q = q.filter_by(rule_id=rule_id)
                if q.filter(ScheduledAutoReply.status.in_([STATUS_SCHEDULED, STATUS_SENT])).first():
                    return True
            
            return False
        except Exception as e:
            logger.error(f"Error checking replied status: {e}")
            return False


    @staticmethod
    def does_email_match_rule(email, rule):
        """
        Check if the email matches all active filters of the rule.
        Returns True only if ALL conditions are satisfied.
        
        🔧 FIX: Now checks sender filter even when apply_to_all is true.
        The user can set sender_email to filter by specific sender.
        """
        try:
            # Check sender filter FIRST (this is critical - user wants to filter by sender)
            sender_filter_value = getattr(rule, 'sender_filter', None) or getattr(rule, 'sender_email', None)
            if sender_filter_value:
                email_sender = (email.sender or '').lower()
                filter_lower = sender_filter_value.lower()
                if filter_lower not in email_sender:
                    logger.debug(f"❌ Sender filter mismatch: '{filter_lower}' not in '{email_sender}'")
                    return False
                else:
                    logger.debug(f"✅ Sender filter matched: '{filter_lower}' in '{email_sender}'")
            
            # Check apply_to_all override - only if no sender filter or sender filter passed
            if hasattr(rule, 'is_apply_to_all_rule') and callable(rule.is_apply_to_all_rule):
                if rule.is_apply_to_all_rule():
                    return True
            
            # Check trigger_conditions dict
            if hasattr(rule, 'get_trigger_conditions'):
                conditions = rule.get_trigger_conditions()
                if isinstance(conditions, dict) and conditions.get('apply_to_all'):
                    return True

            # Check subject filter
            if hasattr(rule, 'subject_filter') and rule.subject_filter:
                email_subject = (email.subject or '').lower()
                filter_lower = rule.subject_filter.lower()
                if filter_lower not in email_subject:
                    logger.debug(f"❌ Subject filter mismatch: '{filter_lower}' not in '{email_subject}'")
                    return False

            return True

        except Exception as e:
            logger.error(f"Error matching rule: {e}")
            return False


    @staticmethod
    def _prepare_reply_subject(email, template):
        """Prepare subject with reply prefix"""
        # Handle both template.reply_subject and template.subject
        reply_subject = getattr(template, 'reply_subject', None) or getattr(template, 'subject', '')
        if not reply_subject:
            reply_subject = f"Re: {email.subject}"
        return reply_subject


    @staticmethod
    def _prepare_reply_body(email, template, user):
        """Prepare body with placeholders - handles None values safely"""
        body = template.reply_body or ''
        
        # Common placeholders - ensure all values are strings
        placeholders = {
            '{{sender_name}}': str(email.sender.split('@')[0]) if email.sender else '',
            '{{sender_email}}': str(email.sender) if email.sender else '',
            '{{subject}}': str(email.subject) if email.subject else '',
            '{{user_name}}': str(user.name) if user and user.name else '',
            '{{user_email}}': str(user.email) if user and user.email else '',
        }
        
        for placeholder, value in placeholders.items():
            body = body.replace(placeholder, value)
        
        return body


    @staticmethod
    def immediate_check_for_new_rule(rule_id):
        """
        🔧 NEW: Immediate check for a newly created rule.
        Called in background thread to not block UI.
        
        NOTE: Must be called within app.app_context() by the caller.
        """
        try:
            logger.info(f"🚀 Immediate check started for new rule {rule_id}")
            
            # The caller MUST provide app context - we can't create it in background thread
            # Verify we're in app context
            try:
                _ = current_app.name
            except Exception:
                logger.error(f"❌ No application context for immediate check on rule {rule_id}")
                return
                
            result = AutoReplyService.check_and_send_auto_replies(specific_rule_id=rule_id)
            logger.info(f"✅ Immediate check completed for rule {rule_id}: {result}")
            
        except Exception as e:
            logger.error(f"❌ Immediate check failed for rule {rule_id}: {e}", exc_info=True)
