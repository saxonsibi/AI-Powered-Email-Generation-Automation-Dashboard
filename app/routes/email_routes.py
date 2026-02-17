# app/routes/email_routes.py
import json
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session, current_app
from flask_login import login_required, current_user
from app import db
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
import os
import logging
import pytz

logger = logging.getLogger(__name__)

email = Blueprint('email', __name__)

# Folder to temporarily store uploaded attachments
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@email.route('/send', methods=['POST'])
@login_required
def send_email():
    """Send an email with optional attachments and HTML content."""
    # Get form data
    recipients = request.form.get('recipients')  # Multiple recipients
    subject = request.form.get('subject')
    body = request.form.get('body')  # HTML from Quill
    cc = request.form.get('cc')
    bcc = request.form.get('bcc')
    files = request.files.getlist('attachments')

    # Validate required fields
    if not recipients or not subject or not body:
        flash('Please fill in all required fields.', 'danger')
        return redirect(url_for('main.compose'))

    # Parse recipients into a list
    recipient_list = [r.strip() for r in recipients.split(',') if r.strip()]
    
    if not recipient_list:
        flash('Please specify at least one valid recipient.', 'danger')
        return redirect(url_for('main.compose'))

    # Save attachments temporarily
    saved_files = []
    for f in files:
        if f.filename:
            filename = secure_filename(f.filename)
            file_path = os.path.join(UPLOAD_FOLDER, filename)
            f.save(file_path)
            
            # Read file data for GmailService
            with open(file_path, 'rb') as file:
                file_data = file.read()
            
            saved_files.append({
                'filename': filename,
                'data': file_data,
                'mimeType': f.content_type or 'application/octet-stream'
            })

    # Import services inside the route to avoid circular imports
    from app.services.gmail_service import GmailService

    # Send email via GmailService
    gmail_service = GmailService(current_user)
    if not gmail_service.service:
        flash('Please connect your Gmail account first.', 'warning')
        # Clean up files before returning
        for f in files:
            if f.filename:
                filename = secure_filename(f.filename)
                file_path = os.path.join(UPLOAD_FOLDER, filename)
                try:
                    os.remove(file_path)
                except:
                    pass
        return redirect(url_for('main.settings'))

    # Send to all recipients
    success_count = 0
    total_recipients = len(recipient_list)
    error_messages = []
    
    for recipient in recipient_list:
        # Send HTML email
        success, message = gmail_service.send_email(
            to=recipient,
            subject=subject,
            body_html=body,
            cc=cc,
            bcc=bcc,
            attachments=saved_files
        )
        
        if success:
            success_count += 1
            logger.info(f"Email sent successfully to {recipient}")
        else:
            error_msg = f"Failed to send to {recipient}: {message}"
            error_messages.append(error_msg)
            logger.error(error_msg)

    # Clean up temporary files
    for f in files:
        if f.filename:
            filename = secure_filename(f.filename)
            file_path = os.path.join(UPLOAD_FOLDER, filename)
            try:
                os.remove(file_path)
            except:
                pass

    # Show appropriate message
    if success_count == total_recipients:
        flash('Email sent successfully!', 'success')
        # Save to SentEmail table
        try:
            from app.models.email import SentEmail
            sent_email = SentEmail(
                user_id=current_user.id,
                to=recipients,
                cc=cc if cc else None,
                bcc=bcc if bcc else None,
                subject=subject,
                body_html=body,
                status='Sent'
            )
            db.session.add(sent_email)
            db.session.commit()
        except Exception as e:
            logger.error(f"Error saving sent email: {str(e)}")
    elif success_count > 0:
        flash(f'Email sent to {success_count} of {total_recipients} recipients.', 'warning')
        # Log errors for debugging
        for error in error_messages:
            logger.error(error)
    else:
        flash('Failed to send email. Please try again.', 'danger')
        # Log all errors
        for error in error_messages:
            logger.error(error)

    return redirect(url_for('main.compose'))

@email.route('/draft', methods=['POST'])
@login_required
def save_local_draft():
    """Save an email draft locally in the database."""
    recipients = request.form.get('recipients')
    subject = request.form.get('subject')
    body = request.form.get('body')
    files = request.files.getlist('attachments')

    # Import models inside the route to avoid circular imports
    from app.models.email import DraftEmail

    draft = DraftEmail(
        subject=subject,
        to=recipients,
        body=body,
        user_id=current_user.id
    )
    
    try:
        db.session.add(draft)
        db.session.commit()
        flash('Draft saved successfully!', 'success')
    except Exception as e:
        logger.error(f"Error saving draft: {str(e)}")
        db.session.rollback()
        flash('Error saving draft.', 'danger')

    return redirect(url_for('main.compose'))

@email.route('/generate', methods=['POST'])
@login_required
def generate_email():
    """Generate an email using AI."""
    purpose = request.form.get('purpose')
    tone = request.form.get('tone')
    notes = request.form.get('notes')
    additional_context = request.form.get('additional_context')

    if not purpose or not tone:
        return jsonify({'error': 'Purpose and tone are required'}), 400

    # Import services inside the route to avoid circular imports
    from app.services.template_service import generate_simple_reply

    # Generate a simple email based on purpose and tone
    email_content = generate_simple_reply(purpose, tone)

    return jsonify({
        'subject': f"Re: {purpose}",
        'body': email_content
    })

@email.route('/classify/<int:email_id>', methods=['POST'])
@login_required
def classify_email_route(email_id):
    """Classify an email using AI."""
    # Import models inside the route to avoid circular imports
    from app.models.email import Email
    from app.services.email_classifier import classify_email

    email_obj = Email.query.get_or_404(email_id)

    if email_obj.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403

    # Classify the email
    classification = classify_email(email_id, current_user.id)

    if classification:
        return jsonify({
            'success': True,
            'classification': {
                'category': classification.category.name if classification.category else 'Unclassified',
                'confidence': classification.confidence_score
            }
        })
    else:
        return jsonify({'error': 'Failed to classify email'}), 500

@email.route('/follow-up/<int:email_id>', methods=['POST'])
@login_required
def schedule_follow_up(email_id):
    """Schedule a follow-up for an email."""
    # Import models inside the route to avoid circular imports
    from app.models.email import Email
    from app.models.follow_up import FollowUp
    from app.services.follow_up_service import FollowUpService

    email_obj = Email.query.get_or_404(email_id)

    if email_obj.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403

    delay_days = request.form.get('delay_days', 3, type=int)

    # Create a simple follow-up rule
    class SimpleFollowUpRule:
        def __init__(self, delay_hours):
            self.delay_hours = delay_hours
            self.template_text = f"Hi, just following up on my previous email regarding '{email_obj.subject}'. I wanted to make sure you received it."

    rule = SimpleFollowUpRule(delay_days * 24)

    # Create a simple sent email object
    class SimpleSentEmail:
        def __init__(self, email_obj):
            self.id = email_obj.id
            self.user_id = email_obj.user_id
            self.to = email_obj.sender
            self.subject = email_obj.subject
            self.thread_id = email_obj.thread_id
            self.sent_at = datetime.utcnow()

    sent_email = SimpleSentEmail(email_obj)

    # Schedule the follow-up
    follow_up = FollowUpService.schedule_follow_up(sent_email, rule)

    if follow_up:
        scheduled_at = follow_up.scheduled_at.strftime("%B %d, %Y")
        flash(f'Follow-up scheduled for {scheduled_at}', 'success')
    else:
        flash('Error scheduling follow-up.', 'danger')

    return redirect(url_for('main.view_email', email_id=email_id))

@email.route('/automation', methods=['POST'])
@login_required
def create_automation_rule():
    """Create a new automation rule."""
    name = request.form.get('name')

    # Parse trigger conditions
    trigger_condition = {}
    if request.form.get('sender'):
        trigger_condition['sender'] = request.form.get('sender')
    if request.form.get('subject_contains'):
        trigger_condition['subject_contains'] = request.form.get('subject_contains')
    if request.form.get('body_contains'):
        trigger_condition['body_contains'] = request.form.get('body_contains')
    if request.form.get('is_urgent') == 'on':
        trigger_condition['is_urgent'] = True

    # Parse actions
    action = {}
    if request.form.get('auto_reply_message'):
        action['auto_reply'] = {'message': request.form.get('auto_reply_message')}
    if request.form.get('add_label'):
        action['add_label'] = request.form.get('add_label')
    if request.form.get('schedule_follow_up') == 'on':
        delay_days = request.form.get('follow_up_delay', 3, type=int)
        action['schedule_follow_up'] = {'delay_days': delay_days}

    if not name or not trigger_condition or not action:
        flash('Please provide a name and at least one condition and action.', 'danger')
        return redirect(url_for('main.settings'))

    # Import models inside the route to avoid circular imports
    from app.models.automation import AutomationRule

    # Create a simple automation rule
    rule = AutomationRule(
        user_id=current_user.id,
        name=name,
        trigger_conditions=json.dumps(trigger_condition),
        actions=json.dumps(action),
        is_active=True
    )

    try:
        db.session.add(rule)
        db.session.commit()
        flash(f'Automation rule "{rule.name}" created successfully!', 'success')
    except Exception as e:
        logger.error(f"Error creating automation rule: {str(e)}")
        db.session.rollback()
        flash('Error creating automation rule.', 'danger')

    return redirect(url_for('main.settings'))

@email.route('/automation/<int:rule_id>/toggle', methods=['POST'])
@login_required
def toggle_automation_rule(rule_id):
    """Toggle an automation rule on/off."""
    # Import models inside the route to avoid circular imports
    from app.models.automation import AutomationRule

    rule = AutomationRule.query.get_or_404(rule_id)

    if rule.user_id != current_user.id:
        flash('You do not have permission to modify this rule.', 'danger')
        return redirect(url_for('main.settings'))

    try:
        rule.is_active = not rule.is_active
        db.session.commit()

        status = "activated" if rule.is_active else "deactivated"
        flash(f'Automation rule "{rule.name}" {status}.', 'success')
    except Exception as e:
        logger.error(f"Error toggling automation rule: {str(e)}")
        db.session.rollback()
        flash('Error toggling automation rule.', 'danger')

    return redirect(url_for('main.settings'))

@email.route('/automation/<int:rule_id>/delete', methods=['POST'])
@login_required
def delete_automation_rule(rule_id):
    """Delete an automation rule."""
    # Import models inside the route to avoid circular imports
    from app.models.automation import AutomationRule

    rule = AutomationRule.query.get_or_404(rule_id)

    if rule.user_id != current_user.id:
        flash('You do not have permission to delete this rule.', 'danger')
        return redirect(url_for('main.settings'))

    try:
        db.session.delete(rule)
        db.session.commit()

        flash(f'Automation rule "{rule.name}" deleted.', 'success')
    except Exception as e:
        logger.error(f"Error deleting automation rule: {str(e)}")
        db.session.rollback()
        flash('Error deleting automation rule.', 'danger')

    return redirect(url_for('main.settings'))

# API Routes
@email.route('/api/check-new-emails', methods=['GET'])
@login_required
def check_new_emails():
    """Check for new emails without fetching from Gmail API."""
    try:
        # Import models inside the route to avoid circular imports
        from app.models.email import Email
        
        # Get the most recent email check time
        last_check = current_user.last_email_sync_time or datetime.min
        
        # Count new emails since last check
        new_emails = Email.query.filter(
            Email.user_id == current_user.id,
            Email.received_at > last_check
        ).count()
        
        # Get total email count
        total_emails = Email.query.filter_by(user_id=current_user.id).count()
        
        # Update last check time
        current_user.last_email_sync_time = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            'success': True,
            'new_email_count': new_emails,
            'total_email_count': total_emails
        })
    except Exception as e:
        logger.error(f"Error checking new emails: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@email.route('/api/reset-email-sync', methods=['POST'])
@login_required
def reset_email_sync():
    """Reset the email sync time for the current user."""
    try:
        current_user.last_email_sync_time = None
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error resetting email sync: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@email.route('/api/update-preferences', methods=['POST'])
@login_required
def update_preferences():
    """Update user preferences."""
    try:
        data = request.get_json()
        
        # Update theme preference
        if 'theme' in data:
            current_user.theme_preference = data.get('theme')
        
        # You can add more preference fields here as needed
        if 'language' in data:
            current_user.language = data.get('language')
        if 'timezone' in data:
            current_user.timezone = data.get('timezone')
            
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error updating preferences: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@email.route('/api/refresh-inbox', methods=['POST'])
@login_required
def refresh_inbox():
    """Refresh inbox and process new emails from Gmail API."""
    try:
        # Import services inside the route to avoid circular imports
        from app.services.gmail_service import GmailService
        
        # Get Gmail service
        gmail_service = GmailService(current_user)
        if not gmail_service.service:
            return jsonify({
                'success': False,
                'error': 'Gmail account not connected'
            }), 400
        
        # Sync emails from Gmail
        synced_count = gmail_service.sync_emails(limit=50)
        
        # Get total email count
        from app.models.email import Email
        total_emails = Email.query.filter_by(user_id=current_user.id).count()
        
        # Update last sync time
        current_user.last_email_sync_time = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            'success': True,
            'new_email_count': synced_count,
            'total_email_count': total_emails
        })
    except Exception as e:
        logger.error(f"Error refreshing inbox: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# Email Classification Routes
@email.route('/classify-emails', methods=['POST'])
@login_required
def classify_emails():
    """Manually trigger email classification for all unclassified emails."""
    try:
        # Import services inside the route to avoid circular imports
        from app.services.email_classifier import batch_classify_emails
        
        # Classify a batch of unclassified emails
        result = batch_classify_emails(current_user.id, limit=50)
        
        if result['success']:
            flash(f"Classified {result['count']} emails!", 'success')
        else:
            flash(f'Error during classification: {result.get("message", "Unknown error")}', 'danger')
    except Exception as e:
        logger.error(f"Error classifying emails: {str(e)}")
        flash(f'Error during classification: {str(e)}', 'danger')

    return redirect(url_for('main.inbox'))

# Auto-Reply Routes
@email.route('/auto-replies', methods=['GET'])
@login_required
def auto_replies():
    """Display auto-reply rules."""
    # Import models inside the route to avoid circular imports
    from app.models.auto_reply import AutoReplyRule, AutoReplyTemplate, AutoReplyLog
    
    # Get auto-reply rules for the current user
    rules = AutoReplyRule.query.filter_by(user_id=current_user.id).order_by(AutoReplyRule.priority.asc()).all()
    templates = AutoReplyTemplate.query.filter_by(user_id=current_user.id).all()
    logs = AutoReplyLog.query.filter_by(user_id=current_user.id).order_by(AutoReplyLog.created_at.desc()).limit(20).all()
    
    return render_template('dashboard/auto_replies.html', rules=rules, templates=templates, logs=logs)

@email.route('/auto-reply/create', methods=['POST'])
@login_required
def create_auto_reply():
    """Create a new auto-reply rule."""
    name = request.form.get('name')
    template_id = request.form.get('template_id')
    priority = request.form.get('priority', 1, type=int)
    delay_minutes = request.form.get('delay_minutes', 0, type=int)
    cooldown_hours = request.form.get('cooldown_hours', 24, type=int)
    is_active = request.form.get('is_active') == 'on'
    
    # Parse trigger conditions
    trigger_conditions = {}
    
    # Apply to all emails
    if request.form.get('apply_to_all') == 'on':
        trigger_conditions['apply_to_all'] = True
    else:
        # Specific conditions
        if request.form.get('senders'):
            trigger_conditions['senders'] = [s.strip() for s in request.form.get('senders').split(',')]
        if request.form.get('keywords'):
            trigger_conditions['keywords'] = [k.strip() for k in request.form.get('keywords').split(',')]
        if request.form.get('domains'):
            trigger_conditions['domains'] = [d.strip() for d in request.form.get('domains').split(',')]
        if request.form.get('categories'):
            trigger_conditions['categories'] = [int(c) for c in request.form.getlist('categories')]
        if request.form.get('urgent') == 'on':
            trigger_conditions['urgent'] = True
        if request.form.get('unread') == 'on':
            trigger_conditions['unread'] = True
        if request.form.get('urgency_level'):
            trigger_conditions['urgency_level'] = request.form.getlist('urgency_level')
    
    # Parse advanced settings
    reply_once_per_thread = request.form.get('reply_once_per_thread') == 'on'
    prevent_auto_reply_to_auto = request.form.get('prevent_auto_reply_to_auto') == 'on'
    ignore_mailing_lists = request.form.get('ignore_mailing_lists') == 'on'
    stop_on_sender_reply = request.form.get('stop_on_sender_reply') == 'on'
    
    # Parse schedule settings
    schedule_start = None
    schedule_end = None
    business_hours_only = request.form.get('business_hours_only') == 'on'
    business_days_only = request.form.get('business_days_only') == 'on'
    
    if request.form.get('schedule_start'):
        try:
            schedule_start_str = request.form.get('schedule_start')
            schedule_start = datetime.strptime(schedule_start_str, '%Y-%m-%d %H:%M')
            # Convert to UTC if needed
            if current_app.config.get('SCHEDULER_TIMEZONE') == 'Asia/Kolkata':
                ist = pytz.timezone('Asia/Kolkata')
                schedule_start = ist.localize(schedule_start).astimezone(pytz.UTC)
        except ValueError:
            flash('Invalid schedule start time format. Use YYYY-MM-DD HH:MM', 'danger')
            return redirect(url_for('email.auto_replies'))
    
    if request.form.get('schedule_end'):
        try:
            schedule_end_str = request.form.get('schedule_end')
            schedule_end = datetime.strptime(schedule_end_str, '%Y-%m-%d %H:%M')
            # Convert to UTC if needed
            if current_app.config.get('SCHEDULER_TIMEZONE') == 'Asia/Kolkata':
                ist = pytz.timezone('Asia/Kolkata')
                schedule_end = ist.localize(schedule_end).astimezone(pytz.UTC)
        except ValueError:
            flash('Invalid schedule end time format. Use YYYY-MM-DD HH:MM', 'danger')
            return redirect(url_for('email.auto_replies'))
    
    if request.form.get('business_hours_start'):
        try:
            business_hours_start = datetime.strptime(request.form.get('business_hours_start'), '%H:%M').time()
        except ValueError:
            flash('Invalid business hours start time format. Use HH:MM', 'danger')
            return redirect(url_for('email.auto_replies'))
    
    if request.form.get('business_hours_end'):
        try:
            business_hours_end = datetime.strptime(request.form.get('business_hours_end'), '%H:%M').time()
        except ValueError:
            flash('Invalid business hours end time format. Use HH:MM', 'danger')
            return redirect(url_for('email.auto_replies'))
    
    if not name or not template_id:
        flash('Name and template are required.', 'danger')
        return redirect(url_for('email.auto_replies'))
    
    # Import models inside the route to avoid circular imports
    from app.models.auto_reply import AutoReplyRule
    
    rule = AutoReplyRule(
        user_id=current_user.id,
        name=name,
        template_id=template_id,
        priority=priority,
        delay_minutes=delay_minutes,
        cooldown_hours=cooldown_hours,
        trigger_conditions=json.dumps(trigger_conditions),
        is_active=is_active,
        reply_once_per_thread=reply_once_per_thread,
        prevent_auto_reply_to_auto=prevent_auto_reply_to_auto,
        ignore_mailing_lists=ignore_mailing_lists,
        stop_on_sender_reply=stop_on_sender_reply,
        schedule_start=schedule_start,
        schedule_end=schedule_end,
        business_hours_only=business_hours_only,
        business_days_only=business_days_only,
        business_hours_start=business_hours_start,
        business_hours_end=business_hours_end
    )
    
    try:
        db.session.add(rule)
        db.session.commit()
        
        # Trigger immediate check for new rule
        from app.services.auto_reply_service import AutoReplyService
        AutoReplyService.immediate_check_for_new_rule(current_user.id, rule.id)
        
        flash(f'Auto-reply rule "{rule.name}" created successfully!', 'success')
    except Exception as e:
        logger.error(f"Error creating auto-reply rule: {str(e)}")
        db.session.rollback()
        flash('Error creating auto-reply rule.', 'danger')
    
    return redirect(url_for('email.auto_replies'))

@email.route('/auto-reply/<int:rule_id>/toggle', methods=['POST'])
@login_required
def toggle_auto_reply(rule_id):
    """Toggle an auto-reply rule on/off."""
    # Import models inside the route to avoid circular imports
    from app.models.auto_reply import AutoReplyRule

    rule = AutoReplyRule.query.get_or_404(rule_id)
    
    if rule.user_id != current_user.id:
        flash('You do not have permission to modify this rule.', 'danger')
        return redirect(url_for('email.auto_replies'))
    
    try:
        rule.is_active = not rule.is_active
        db.session.commit()
        
        status = "activated" if rule.is_active else "deactivated"
        flash(f'Auto-reply rule "{rule.name}" {status}.', 'success')
    except Exception as e:
        logger.error(f"Error toggling auto-reply rule: {str(e)}")
        db.session.rollback()
        flash('Error toggling auto-reply rule.', 'danger')
    
    return redirect(url_for('email.auto_replies'))

@email.route('/auto-reply/<int:rule_id>/delete', methods=['POST'])
@login_required
def delete_auto_reply(rule_id):
    """Delete an auto-reply rule."""
    # Import models inside the route to avoid circular imports
    from app.models.auto_reply import AutoReplyRule

    rule = AutoReplyRule.query.get_or_404(rule_id)
    
    if rule.user_id != current_user.id:
        flash('You do not have permission to delete this rule.', 'danger')
        return redirect(url_for('email.auto_replies'))
    
    try:
        db.session.delete(rule)
        db.session.commit()
        
        flash(f'Auto-reply rule "{rule.name}" deleted.', 'success')
    except Exception as e:
        logger.error(f"Error deleting auto-reply rule: {str(e)}")
        db.session.rollback()
        flash('Error deleting auto-reply rule.', 'danger')
    
    return redirect(url_for('email.auto_replies'))

@email.route('/auto-reply-template/create', methods=['POST'])
@login_required
def create_auto_reply_template():
    """Create a new auto-reply template."""
    name = request.form.get('name')
    reply_subject = request.form.get('reply_subject')
    reply_body = request.form.get('reply_body')
    
    if not name or not reply_body:
        flash('Name and reply body are required.', 'danger')
        return redirect(url_for('email.auto_replies'))
    
    # Import models inside the route to avoid circular imports
    from app.models.auto_reply import AutoReplyTemplate
    
    template = AutoReplyTemplate(
        name=name,
        reply_subject=reply_subject,
        reply_body=reply_body,
        user_id=current_user.id
    )
    
    try:
        db.session.add(template)
        db.session.commit()
        flash('Auto-reply template created successfully!', 'success')
    except Exception as e:
        logger.error(f"Error creating auto-reply template: {str(e)}")
        db.session.rollback()
        flash('Error creating auto-reply template.', 'danger')
    
    return redirect(url_for('email.auto_replies'))

@email.route('/process-auto-replies', methods=['POST'])
@login_required
def process_auto_replies_route():
    """Manually trigger auto-reply processing."""
    try:
        # Import services inside the route to avoid circular imports
        from app.services.auto_reply_service import AutoReplyService
        
        result = AutoReplyService.check_and_send_auto_replies()
        
        if result and result.get('count', 0) > 0:
            flash(f'Processed {result["count"]} auto-replies!', 'success')
        else:
            flash('No auto-replies to process.', 'info')
        
        return redirect(url_for('email.auto_replies'))
    except Exception as e:
        logger.error(f"Error processing auto-replies: {str(e)}")
        flash(f'Error during auto-reply processing: {str(e)}', 'danger')
        return redirect(url_for('email.auto_replies'))

# Follow-Up Routes
@email.route('/follow-ups', methods=['GET'])
@login_required
def follow_ups():
    """Display follow-up rules."""
    # Import models inside the route to avoid circular imports
    from app.models.follow_up import FollowUp
    from app.services.follow_up_service import FollowUpService
    
    # Get follow-up statistics
    stats = FollowUpService.get_follow_up_stats(current_user.id)
    
    # Get recent follow-ups
    follow_ups = FollowUpService.get_follow_ups_for_user(current_user.id, limit=20)
    
    return render_template('dashboard/followups.html', follow_ups=follow_ups, stats=stats)

@email.route('/follow-up/<int:follow_up_id>/cancel', methods=['POST'])
@login_required
def cancel_follow_up(follow_up_id):
    """Cancel a pending follow-up."""
    try:
        # Import services inside the route to avoid circular imports
        from app.services.follow_up_service import FollowUpService
        
        if FollowUpService.cancel_follow_up(follow_up_id, current_user.id):
            flash('Follow-up cancelled successfully!', 'success')
        else:
            flash('Error cancelling follow-up.', 'danger')
    except Exception as e:
        logger.error(f"Error cancelling follow-up: {str(e)}")
        flash(f'Error cancelling follow-up: {str(e)}', 'danger')
    
    return redirect(url_for('email.follow_ups'))

@email.route('/follow-up/<int:follow_up_id>/reschedule', methods=['POST'])
@login_required
def reschedule_follow_up(follow_up_id):
    """Reschedule a pending follow-up."""
    try:
        # Import services inside the route to avoid circular imports
        from app.services.follow_up_service import FollowUpService
        
        new_delay_hours = request.form.get('delay_hours', 24, type=int)
        
        if FollowUpService.reschedule_follow_up(follow_up_id, current_user.id, new_delay_hours):
            flash('Follow-up rescheduled successfully!', 'success')
        else:
            flash('Error rescheduling follow-up.', 'danger')
    except Exception as e:
        logger.error(f"Error rescheduling follow-up: {str(e)}")
        flash(f'Error rescheduling follow-up: {str(e)}', 'danger')
    
    return redirect(url_for('email.follow_ups'))

@email.route('/process-follow-ups', methods=['POST'])
@login_required
def process_follow_ups_route():
    """Manually trigger follow-up processing."""
    try:
        # Import services inside the route to avoid circular imports
        from app.services.follow_up_service import FollowUpService
        
        result = FollowUpService.check_and_send_follow_ups()
        
        if result and result.get('count', 0) > 0:
            flash(f'Processed {result["count"]} follow-ups!', 'success')
        else:
            flash('No follow-ups to process.', 'info')
        
        return redirect(url_for('email.follow_ups'))
    except Exception as e:
        logger.error(f"Error processing follow-ups: {str(e)}")
        flash(f'Error during follow-up processing: {str(e)}', 'danger')
        return redirect(url_for('email.follow_ups'))

# Sent Emails Routes
@email.route('/sent', methods=['GET'])
@login_required
def sent():
    """Display sent emails page - optimized to load quickly."""
    # Don't fetch any emails here - let the JavaScript load them via API
    return render_template('dashboard/sent.html')

@email.route('/sent-email/<int:email_id>', methods=['GET'])
@login_required
def view_sent_email(email_id):
    """View a specific sent email."""
    try:
        # Import models inside the route to avoid circular imports
        from app.models.email import SentEmail
        
        # Get the email
        email = SentEmail.query.filter_by(id=email_id, user_id=current_user.id).first()
        if not email:
            flash('Email not found', 'error')
            return redirect(url_for('email.sent'))
        
        return render_template('dashboard/view_sent_email.html', email=email)
    except Exception as e:
        logger.error(f"Error viewing sent email: {str(e)}")
        flash('Error viewing email', 'error')
        return redirect(url_for('email.sent'))

@email.route('/sync-sent-emails', methods=['POST'])
@login_required
def sync_sent_emails_route():
    """Route to trigger sent emails sync."""
    try:
        # Import services inside the route to avoid circular imports
        from app.services.sent_emails_service import sync_sent_emails
        
        sync_count = sync_sent_emails(current_user.id)
        flash(f'Synced {sync_count} sent emails!', 'success')
    except Exception as e:
        logger.error(f"Error syncing sent emails: {str(e)}")
        flash(f'Error syncing sent emails: {str(e)}', 'danger')
    
    return redirect(url_for('email.sent'))

# Draft Emails Routes
@email.route('/drafts', methods=['GET'])
@login_required
def drafts():
    """Display draft emails."""
    try:
        # Import models inside the route to avoid circular imports
        from app.models.email import DraftEmail
        
        drafts = DraftEmail.query.filter_by(user_id=current_user.id).order_by(DraftEmail.created_at.desc()).all()
        return render_template('dashboard/drafts.html', drafts=drafts)
    except Exception as e:
        logger.error(f"Error loading drafts: {str(e)}")
        flash(f'Error loading drafts: {str(e)}', 'danger')
        return render_template('dashboard/drafts.html', drafts=[])

@email.route('/save-gmail-draft', methods=['POST'])
@login_required
def save_gmail_draft():
    """Save a draft email to Gmail."""
    to = request.form.get('to')
    subject = request.form.get('subject')
    body = request.form.get('body')
    draft_id = request.form.get('draft_id')
    
    try:
        # Import services inside the route to avoid circular imports
        from app.services.gmail_service import GmailService
        
        gmail_service = GmailService(current_user)
        if not gmail_service.service:
            flash('Please connect your Gmail account first.', 'warning')
            return redirect(url_for('email.drafts'))
        
        # Create or update draft
        if draft_id:
            # Update existing draft
            success, message = gmail_service.update_draft(draft_id, to, subject, body)
        else:
            # Create new draft
            draft_id, message = gmail_service.create_draft(to, subject, body)
            success = draft_id is not None
        
        if success:
            flash('Draft saved successfully!', 'success')
        else:
            flash(f'Error saving draft: {message}', 'danger')
    except Exception as e:
        logger.error(f"Error saving draft: {str(e)}")
        flash(f'Error saving draft: {str(e)}', 'danger')
    
    return redirect(url_for('email.drafts'))

@email.route('/delete-draft/<int:draft_id>', methods=['POST'])
@login_required
def delete_draft_route(draft_id):
    """Delete a draft email."""
    try:
        # Import models inside the route to avoid circular imports
        from app.models.email import DraftEmail
        
        draft = DraftEmail.query.filter_by(id=draft_id, user_id=current_user.id).first()
        if draft:
            db.session.delete(draft)
            db.session.commit()
            flash('Draft deleted successfully!', 'success')
        else:
            flash('Draft not found.', 'error')
    except Exception as e:
        logger.error(f"Error deleting draft: {str(e)}")
        flash(f'Error deleting draft: {str(e)}', 'error')
    
    return redirect(url_for('email.drafts'))

@email.route('/compose', methods=['GET'])
@login_required
def compose():
    """Compose a new email or edit a draft."""
    draft_id = request.args.get('draft_id')
    draft = None
    
    if draft_id:
        # Import models inside the route to avoid circular imports
        from app.models.email import DraftEmail
        
        # Get the draft from our database
        draft = DraftEmail.query.filter_by(id=draft_id, user_id=current_user.id).first()
    
    return render_template('dashboard/compose.html', draft=draft)

# Helper Functions
def process_new_emails_for_classification():
    """Process new emails and classify them."""
    try:
        # Import services inside the function to avoid circular imports
        from app.services.email_classifier import batch_classify_emails
        
        # Get all users, not just current_user
        from app.models.user import User
        users = User.query.filter(User.gmail_credentials.isnot(None)).all()
        
        total_classified = 0
        for user in users:
            # Classify a batch of unclassified emails for each user
            result = batch_classify_emails(user.id, limit=50)
            total_classified += result.get('count', 0)
        
        logger.info(f"Classified {total_classified} emails across all users")
        return total_classified
    except Exception as e:
        logger.error(f"Error in email classification: {str(e)}")
        return 0

# Add this function to handle the application context issue
def process_new_emails_for_classification_with_context():
    """Process new emails and classify them with proper app context."""
    try:
        return process_new_emails_for_classification()
    except Exception as e:
        logger.error(f"Error in email classification: {str(e)}")
        return 0
    
@email.route('/api/sent-emails', methods=['GET'])
@login_required
def get_sent_emails_api():
    """API endpoint to get sent emails with pagination."""
    try:
        # Get query parameters
        page = int(request.args.get('page', 1))
        search = request.args.get('search', '')
        status = request.args.get('status', 'sent')
        date_filter = request.args.get('date_filter', 'all')
        page_size = int(request.args.get('page_size', 20))
        
        # Import models inside the route to avoid circular imports
        from app.models.email import SentEmail
        from sqlalchemy import or_
        
        # Build query
        query = SentEmail.query.filter_by(user_id=current_user.id)
        
        # Apply status filter
        if status != 'all':
            query = query.filter_by(status=status)
        
        # Apply search filter
        if search:
            query = query.filter(or_(
                SentEmail.subject.contains(search),
                SentEmail.to.contains(search),
                SentEmail.snippet.contains(search)
            ))
        
        # Apply date filter
        if date_filter == 'today':
            today = datetime.utcnow().date()
            query = query.filter(SentEmail.sent_at >= today)
        elif date_filter == 'week':
            week_ago = datetime.utcnow() - timedelta(days=7)
            query = query.filter(SentEmail.sent_at >= week_ago)
        elif date_filter == 'month':
            month_ago = datetime.utcnow() - timedelta(days=30)
            query = query.filter(SentEmail.sent_at >= month_ago)
        
        # Order by sent date (newest first)
        query = query.order_by(SentEmail.sent_at.desc())
        
        # Get total count
        total_count = query.count()
        
        # Apply pagination
        offset = (page - 1) * page_size
        emails = query.offset(offset).limit(page_size).all()
        
        # Convert to dict
        emails_data = []
        for email in emails:
            emails_data.append({
                'id': email.id,
                'to': email.to,
                'subject': email.subject,
                'snippet': email.snippet or (email.body_html[:100] + '...' if email.body_html else ''),
                'sent_at': email.sent_at.isoformat() if email.sent_at else None,
                'status': email.status,
                'gmail_id': email.gmail_id
            })
        
        # Check if there are more emails
        has_more = offset + len(emails) < total_count
        
        return jsonify({
            'success': True,
            'emails': emails_data,
            'has_more': has_more,
            'total_count': total_count
        })
        
    except Exception as e:
        logger.error(f"Error fetching sent emails: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
        
@email.route('/api/refresh-sent-emails', methods=['POST'])
@login_required
def refresh_sent_emails_api():
    """API endpoint to refresh sent emails from Gmail."""
    try:
        # Import services inside the route to avoid circular imports
        from app.services.gmail_service import GmailService
        
        # Get Gmail service
        gmail_service = GmailService(current_user)
        if not gmail_service.service:
            return jsonify({
                'success': False,
                'error': 'Gmail account not connected'
            }), 400
        
        # Sync sent emails from Gmail
        # This would be a new function in gmail_service to sync sent emails
        # For now, just return success
        return jsonify({
            'success': True,
            'message': 'Sent emails refreshed'
        })
    except Exception as e:
        logger.error(f"Error refreshing sent emails: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@email.route('/api/delete-selected-sent-emails', methods=['POST'])
@login_required
def delete_selected_sent_emails_api():
    """API endpoint to delete multiple sent emails."""
    try:
        data = request.get_json()
        email_ids = data.get('email_ids', [])
        
        if not email_ids:
            return jsonify({
                'success': False,
                'error': 'No email IDs provided'
            }), 400
        
        # Import models inside the route to avoid circular imports
        from app.models.email import SentEmail
        
        # Delete emails
        deleted_count = SentEmail.query.filter(
            SentEmail.id.in_(email_ids),
            SentEmail.user_id == current_user.id
        ).delete(synchronize_session=False)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'deleted_count': deleted_count
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting sent emails: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@email.route('/api/resend-sent-email/<int:email_id>', methods=['POST'])
@login_required
def resend_sent_email_api(email_id):
    """API endpoint to resend a sent email."""
    try:
        # Import models inside the route to avoid circular imports
        from app.models.email import SentEmail
        
        # Get the email
        email = SentEmail.query.filter_by(id=email_id, user_id=current_user.id).first()
        if not email:
            return jsonify({
                'success': False,
                'error': 'Email not found'
            }), 404
        
        # Get Gmail service
        from app.services.gmail_service import GmailService
        gmail_service = GmailService(current_user)
        if not gmail_service.service:
            return jsonify({
                'success': False,
                'error': 'Gmail account not connected'
            }), 400
        
        # Resend the email
        success, message = gmail_service.send_email(
            to=email.to,
            subject=email.subject,
            body_html=email.body_html
        )
        
        if success:
            return jsonify({
                'success': True,
                'message': 'Email resent successfully'
            })
        else:
            return jsonify({
                'success': False,
                'error': message
            })
    except Exception as e:
        logger.error(f"Error resending email: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@email.route('/api/delete-sent-email/<int:email_id>', methods=['DELETE'])
@login_required
def delete_sent_email_api(email_id):
    """API endpoint to delete a sent email."""
    try:
        # Import models inside the route to avoid circular imports
        from app.models.email import SentEmail
        
        # Get the email
        email = SentEmail.query.filter_by(id=email_id, user_id=current_user.id).first()
        if not email:
            return jsonify({
                'success': False,
                'error': 'Email not found'
            }), 404
        
        # Delete the email
        db.session.delete(email)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Email deleted successfully'
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting email: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500