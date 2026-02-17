# app/routes/api.py

from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from app import db
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

api = Blueprint('api', __name__)

@api.route('/emails', methods=['GET'])
@login_required
def get_emails():
    """API endpoint to get emails."""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    label = request.args.get('label', 'INBOX')
    
    # Import models inside the route to avoid circular imports
    from app.models.email import Email
    from app.services.gmail_service import GmailService
    
    gmail_service = GmailService(current_user)
    if not gmail_service.service:
        return jsonify({'error': 'Gmail not connected'}), 400
    
    emails = gmail_service.fetch_emails(label=label, max_results=per_page)
    
    email_data = []
    for email in emails:
        email_data.append({
            'id': email.id,
            'gmail_id': email.gmail_id,
            'subject': email.subject,
            'sender': email.sender,
            'date_received': email.date_received.isoformat(),  # Using backward compatibility property
            'received_at': email.received_at.isoformat() if email.received_at else None,
            'is_read': email.is_read,
            'is_starred': email.is_starred,
            'is_urgent': email.is_urgent,
            'label': email.label
        })
    
    return jsonify({
        'emails': email_data,
        'total': len(email_data)
    })

@api.route('/emails/<int:email_id>', methods=['GET'])
@login_required
def get_email(email_id):
    """API endpoint to get a specific email."""
    # Import models inside the route to avoid circular imports
    from app.models.email import Email
    
    email = Email.query.get_or_404(email_id)
    
    # Check if user owns the email
    if email.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    return jsonify({
        'id': email.id,
        'gmail_id': email.gmail_id,
        'thread_id': email.thread_id,
        'subject': email.subject,
        'sender': email.sender,
        'recipients': email.get_recipients_list(),
        'body_text': email.body_text,
        'body_html': email.body_html,
        'date_received': email.date_received.isoformat(),  # Using backward compatibility property
        'received_at': email.received_at.isoformat() if email.received_at else None,
        'is_read': email.is_read,
        'is_starred': email.is_starred,
        'is_urgent': email.is_urgent,
        'label': email.label
    })

@api.route('/emails/generate', methods=['POST'])
@login_required
def generate_email():
    """API endpoint to generate an email using AI."""
    data = request.get_json()
    
    if not data or 'purpose' not in data or 'tone' not in data:
        return jsonify({'error': 'Purpose and tone are required'}), 400
    
    purpose = data.get('purpose')
    tone = data.get('tone')
    notes = data.get('notes', '')
    additional_context = data.get('additional_context', '')
    
    # Import services inside the route to avoid circular imports
    from app.services.ai_service import AIService
    
    ai_service = AIService()
    email_data = ai_service.generate_email(purpose, tone, notes, additional_context)
    
    return jsonify(email_data)

@api.route('/emails/<int:email_id>/classify', methods=['POST'])
@login_required
def classify_email(email_id):
    """API endpoint to classify an email using AI."""
    # Import models inside the route to avoid circular imports
    from app.models.email import Email
    
    email = Email.query.get_or_404(email_id)
    
    # Check if user owns the email
    if email.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    # Import services inside the route to avoid circular imports
    from app.services.ai_service import AIService
    
    ai_service = AIService()
    classification = ai_service.classify_email(email.body_text)
    
    # Update email with classification results
    email.is_urgent = classification.get('is_urgent', False)
    # Add more fields as needed
    
    db.session.commit()
    
    return jsonify(classification)

@api.route('/emails/<int:email_id>/follow-up', methods=['POST'])
@login_required
def schedule_follow_up(email_id):
    """API endpoint to schedule a follow-up for an email."""
    # Import models inside the route to avoid circular imports
    from app.models.email import Email
    from app.models.follow_up import FollowUp
    
    email = Email.query.get_or_404(email_id)
    
    # Check if user owns the email
    if email.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    data = request.get_json()
    delay_days = data.get('delay_days', 3)
    
    # Import services inside the route to avoid circular imports
    from app.services.ai_service import AIService
    
    ai_service = AIService()
    follow_up_content = ai_service.generate_follow_up(email, delay_days)
    
    # Create follow-up record
    scheduled_at = datetime.now() + timedelta(days=delay_days)
    follow_up = FollowUp(
        user_id=current_user.id,
        email_id=email.id,
        thread_id=email.thread_id,
        recipient_email=email.sender,
        scheduled_at=scheduled_at,
        status='pending'
    )
    
    db.session.add(follow_up)
    db.session.commit()
    
    return jsonify({
        'id': follow_up.id,
        'scheduled_date': follow_up.scheduled_date.isoformat(),  # Using backward compatibility property
        'scheduled_at': follow_up.scheduled_at.isoformat(),
        'content': follow_up_content
    })

@api.route('/automation/rules', methods=['GET'])
@login_required
def get_automation_rules():
    """API endpoint to get automation rules."""
    # Import models inside the route to avoid circular imports
    from app.models.automation import AutomationRule
    
    rules = AutomationRule.query.filter_by(user_id=current_user.id).all()
    
    rules_data = []
    for rule in rules:
        rules_data.append({
            'id': rule.id,
            'name': rule.name,
            'trigger_condition': rule.trigger_condition,
            'action': rule.action,
            'is_active': rule.is_active,
            'created_at': rule.created_at.isoformat()
        })
    
    return jsonify({'rules': rules_data})

@api.route('/automation/rules', methods=['POST'])
@login_required
def create_automation_rule():
    """API endpoint to create an automation rule."""
    data = request.get_json()
    
    if not data or 'name' not in data or 'trigger_condition' not in data or 'action' not in data:
        return jsonify({'error': 'Name, trigger condition, and action are required'}), 400
    
    # Import services inside the route to avoid circular imports
    from app.services.automation_service import AutomationService
    
    automation_service = AutomationService()
    rule = automation_service.create_automation_rule(
        user_id=current_user.id,
        name=data['name'],
        trigger_condition=data['trigger_condition'],
        action=data['action']
    )
    
    return jsonify({
        'id': rule.id,
        'name': rule.name,
        'trigger_condition': rule.trigger_condition,
        'action': rule.action,
        'is_active': rule.is_active,
        'created_at': rule.created_at.isoformat()
    }), 201

@api.route('/automation/rules/<int:rule_id>', methods=['PUT'])
@login_required
def update_automation_rule(rule_id):
    """API endpoint to update an automation rule."""
    # Import models inside the route to avoid circular imports
    from app.models.automation import AutomationRule
    
    rule = AutomationRule.query.get_or_404(rule_id)
    
    # Check if user owns the rule
    if rule.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    data = request.get_json()
    
    # Import services inside the route to avoid circular imports
    from app.services.automation_service import AutomationService
    
    automation_service = AutomationService()
    updated_rule = automation_service.update_automation_rule(
        rule_id=rule_id,
        name=data.get('name'),
        trigger_condition=data.get('trigger_condition'),
        action=data.get('action'),
        is_active=data.get('is_active')
    )
    
    if not updated_rule:
        return jsonify({'error': 'Rule not found'}), 404
    
    return jsonify({
        'id': updated_rule.id,
        'name': updated_rule.name,
        'trigger_condition': updated_rule.trigger_condition,
        'action': updated_rule.action,
        'is_active': updated_rule.is_active
    })

@api.route('/automation/rules/<int:rule_id>', methods=['DELETE'])
@login_required
def delete_automation_rule(rule_id):
    """API endpoint to delete an automation rule."""
    # Import models inside the route to avoid circular imports
    from app.models.automation import AutomationRule
    
    rule = AutomationRule.query.get_or_404(rule_id)
    
    # Check if user owns the rule
    if rule.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    # Import services inside the route to avoid circular imports
    from app.services.automation_service import AutomationService
    
    automation_service = AutomationService()
    success = automation_service.delete_automation_rule(rule_id)
    
    if not success:
        return jsonify({'error': 'Failed to delete rule'}), 500
    
    return jsonify({'message': 'Rule deleted successfully'})

@api.route('/follow-ups', methods=['GET'])
@login_required
def get_follow_ups():
    """API endpoint to get scheduled follow-ups."""
    # Import models inside the route to avoid circular imports
    from app.models.follow_up import FollowUp
    
    follow_ups = FollowUp.query.filter_by(user_id=current_user.id, status='pending').all()
    
    follow_ups_data = []
    for follow_up in follow_ups:
        follow_ups_data.append({
            'id': follow_up.id,
            'email_id': follow_up.email_id,
            'scheduled_date': follow_up.scheduled_date.isoformat(),  # Using backward compatibility property
            'scheduled_at': follow_up.scheduled_at.isoformat(),
            'status': follow_up.status,
            'created_at': follow_up.created_at.isoformat()
        })
    
    return jsonify({'follow_ups': follow_ups_data})

@api.route('/sent-emails')
@login_required
def get_sent_emails():
    # Import models inside the route to avoid circular imports
    from app.models.email import SentEmail
    
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    sent_emails = SentEmail.query.filter_by(
        user_id=current_user.id
    ).order_by(SentEmail.sent_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return jsonify({
        'success': True,
        'emails': [email.to_dict() for email in sent_emails.items]
    })

@api.route('/drafts')
@login_required
def get_drafts():
    # Import models inside the route to avoid circular imports
    from app.models.email import DraftEmail
    
    drafts = DraftEmail.query.filter_by(
        user_id=current_user.id
    ).order_by(DraftEmail.created_at.desc()).all()
    
    return jsonify({
        'success': True,
        'drafts': [draft.to_dict() for draft in drafts]
    })

# Auto-reply template routes
@api.route('/auto-reply/create-template', methods=['POST'])
@login_required
def create_auto_reply_template():
    """API endpoint to create an auto-reply template."""
    try:
        # DEBUG: Log the raw request data
        print("RAW DATA:", request.data)
        print("FORM DATA:", request.form)
        print("JSON DATA:", request.get_json(silent=True))
        
        # Import models inside the route to avoid circular imports
        from app.services.auto_reply_service import AutoReplyTemplate
        
        # Handle both JSON and form data
        data = request.get_json(silent=True) or request.form
        
        # Extract fields from data
        name = data.get("name")
        subject = data.get("subject")
        content = data.get("content")
        
        # HARD VALIDATION: Return early if name is missing or empty
        if not name:
            return jsonify({"error": "Template name is required"}), 400
        
        if not content:
            return jsonify({"error": "Template content is required"}), 400
        
        # Create template with minimal required fields
        template = AutoReplyTemplate(
            user_id=current_user.id,
            name=name,
            subject=subject,
            content=content,
            trigger_conditions=data.get("trigger_conditions", {}),
            is_active=data.get("is_active", False),
            sender_email=data.get("sender_email")
        )
        
        # Only add to session and commit after validation passes
        db.session.add(template)
        db.session.commit()
        
        return jsonify({'success': True, 'template_id': template.id})
    except Exception as e:
        logger.error(f"Error creating auto-reply template: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@api.route('/auto-reply/templates', methods=['GET'])
@login_required
def get_auto_reply_templates():
    """API endpoint to get all auto-reply templates for the current user."""
    # Import models inside the route to avoid circular imports
    from app.services.auto_reply_service import AutoReplyTemplate
    
    templates = AutoReplyTemplate.query.filter_by(user_id=current_user.id).all()
    
    templates_data = []
    for template in templates:
        templates_data.append(template.to_dict())
    
    return jsonify({'templates': templates_data})

@api.route('/auto-reply/templates/<int:template_id>', methods=['GET'])
@login_required
def get_auto_reply_template(template_id):
    """API endpoint to get a specific auto-reply template."""
    # Import models inside the route to avoid circular imports
    from app.services.auto_reply_service import AutoReplyTemplate
    
    template = AutoReplyTemplate.query.filter_by(id=template_id, user_id=current_user.id).first()
    if not template:
        return jsonify({'success': False, 'error': 'Template not found'}), 404
    
    return jsonify({'success': True, 'template': template.to_dict()})

@api.route('/auto-reply/templates/<int:template_id>', methods=['PUT'])
@login_required
def update_auto_reply_template(template_id):
    """API endpoint to update an auto-reply template."""
    # Import models inside the route to avoid circular imports
    from app.services.auto_reply_service import AutoReplyTemplate
    
    template = AutoReplyTemplate.query.filter_by(id=template_id, user_id=current_user.id).first()
    if not template:
        return jsonify({'success': False, 'error': 'Template not found'}), 404
    
    try:
        # Update fields
        if 'name' in request.form:
            template.name = request.form.get('name')
        if 'subject' in request.form:
            template.subject = request.form.get('subject')
        if 'content' in request.form:
            template.content = request.form.get('content')
        
        # Update is_active status
        if 'is_active' in request.form:
            template.is_active = request.form.get('is_active') == 'on'
        
        # Update trigger conditions
        trigger_conditions = {}
        if request.form.get('trigger_all') == 'on':
            trigger_conditions['all'] = True
        if request.form.get('trigger_urgent') == 'on':
            trigger_conditions['urgent'] = True
        if request.form.get('trigger_unread') == 'on':
            trigger_conditions['unread'] = True
        
        # Use the model method to set trigger conditions
        template.set_trigger_conditions(trigger_conditions)
        
        # Update schedule
        schedule_active = request.form.get('schedule_active') == 'on'
        if schedule_active:
            schedule_start_str = request.form.get('schedule_start')
            schedule_end_str = request.form.get('schedule_end')
            
            if schedule_start_str:
                template.schedule_start = datetime.fromisoformat(schedule_start_str)
            if schedule_end_str:
                template.schedule_end = datetime.fromisoformat(schedule_end_str)
        else:
            template.schedule_start = None
            template.schedule_end = None
        
        template.updated_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({'success': True, 'template': template.to_dict()})
    except Exception as e:
        logger.error(f"Error updating auto-reply template: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@api.route('/auto-reply/toggle-rule/<int:template_id>', methods=['POST'])
@login_required
def toggle_auto_reply_template(template_id):
    """API endpoint to toggle the active status of an auto-reply template."""
    # Import models inside the route to avoid circular imports
    from app.services.auto_reply_service import AutoReplyTemplate
    
    template = AutoReplyTemplate.query.filter_by(id=template_id, user_id=current_user.id).first()
    if not template:
        return jsonify({'success': False, 'error': 'Template not found'}), 404
    
    try:
        template.is_active = not template.is_active
        template.updated_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({'success': True, 'is_active': template.is_active})
    except Exception as e:
        logger.error(f"Error toggling auto-reply template: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@api.route('/auto-reply/delete-template/<int:template_id>', methods=['DELETE'])
@login_required
def delete_auto_reply_template(template_id):
    """API endpoint to delete an auto-reply template."""
    # Import models inside the route to avoid circular imports
    from app.services.auto_reply_service import AutoReplyTemplate
    
    template = AutoReplyTemplate.query.filter_by(id=template_id, user_id=current_user.id).first()
    if not template:
        return jsonify({'success': False, 'error': 'Template not found'}), 404
    
    try:
        db.session.delete(template)
        db.session.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error deleting auto-reply template: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@api.route('/auto-reply/stats', methods=['GET'])
@login_required
def get_auto_reply_stats():
    """API endpoint to get auto-reply statistics for the current user."""
    try:
        # Import models inside the route to avoid circular imports
        from app.services.auto_reply_service import AutoReplyTemplate, AutoReplyLog
        
        # Get active templates count
        active_count = AutoReplyTemplate.query.filter_by(user_id=current_user.id, is_active=True).count()
        
        # Get total templates count
        total_count = AutoReplyTemplate.query.filter_by(user_id=current_user.id).count()
        
        # Get sent today count
        today = datetime.utcnow().date()
        sent_today = AutoReplyLog.query.filter(
            AutoReplyLog.user_id == current_user.id,
            db.func.date(AutoReplyLog.created_at) == today
        ).count()
        
        # Get sent this week count
        week_ago = datetime.utcnow() - timedelta(days=7)
        sent_this_week = AutoReplyLog.query.filter(
            AutoReplyLog.user_id == current_user.id,
            AutoReplyLog.created_at >= week_ago
        ).count()
        
        return jsonify({
            'success': True,
            'stats': {
                'active': active_count,
                'templates': total_count,
                'sent_today': sent_today,
                'this_week': sent_this_week
            }
        })
    except Exception as e:
        logger.error(f"Error getting auto-reply stats: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@api.route('/auto-reply/logs', methods=['GET'])
@login_required
def get_auto_reply_logs():
    """API endpoint to get auto-reply logs for the current user."""
    # Import models inside the route to avoid circular imports
    from app.services.auto_reply_service import AutoReplyLog
    
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    logs = AutoReplyLog.query.filter_by(user_id=current_user.id).order_by(
        AutoReplyLog.created_at.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)
    
    logs_data = []
    for log in logs.items:
        logs_data.append(log.to_dict())
    
    return jsonify({
        'success': True,
        'logs': logs_data,
        'total': logs.total,
        'pages': logs.pages,
        'current_page': logs.page
    })

@api.route('/auto-reply/logs/<int:log_id>', methods=['GET'])
@login_required
def get_auto_reply_log(log_id):
    """API endpoint to get a specific auto-reply log."""
    # Import models inside the route to avoid circular imports
    from app.services.auto_reply_service import AutoReplyLog
    
    log = AutoReplyLog.query.filter_by(id=log_id, user_id=current_user.id).first()
    if not log:
        return jsonify({'success': False, 'error': 'Log not found'}), 404
    
    return jsonify({'success': True, 'log': log.to_dict()})

@api.route('/auto-reply/logs/<int:log_id>', methods=['DELETE'])
@login_required
def delete_auto_reply_log(log_id):
    """API endpoint to delete an auto-reply log."""
    # Import models inside the route to avoid circular imports
    from app.services.auto_reply_service import AutoReplyLog
    
    log = AutoReplyLog.query.filter_by(id=log_id, user_id=current_user.id).first()
    if not log:
        return jsonify({'success': False, 'error': 'Log not found'}), 404
    
    try:
        db.session.delete(log)
        db.session.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error deleting auto-reply log: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@api.route('/auto-reply/test/<int:template_id>', methods=['POST'])
@login_required
def test_auto_reply_template(template_id):
    """API endpoint to test an auto-reply template."""
    # Import models inside the route to avoid circular imports
    from app.services.auto_reply_service import AutoReplyTemplate
    
    template = AutoReplyTemplate.query.filter_by(id=template_id, user_id=current_user.id).first()
    if not template:
        return jsonify({'success': False, 'error': 'Template not found'}), 404
    
    try:
        # Get test email data from request
        data = request.get_json()
        if not data or 'sender' not in data or 'subject' not in data:
            return jsonify({'success': False, 'error': 'Sender and subject are required'}), 400
        
        # Create test email data
        email_data = {
            'sender': data.get('sender'),
            'subject': data.get('subject'),
            'thread_id': data.get('thread_id', 'test_thread_id'),
            'body_text': data.get('body_text', 'Test email body'),
            'is_read': data.get('is_read', False)
        }
        
        # Import services inside the route to avoid circular imports
        from app.services.auto_reply_service import AutoReplyService
        
        # Check if template would trigger for this email
        would_trigger = AutoReplyService.should_reply_with_template(email_data, template)
        
        if would_trigger:
            # Generate the reply content
            subject = template.subject or f"Re: {email_data.get('subject', '')}"
            content = template.content
            
            return jsonify({
                'success': True,
                'would_trigger': True,
                'subject': subject,
                'content': content
            })
        else:
            return jsonify({
                'success': True,
                'would_trigger': False,
                'message': 'Template would not trigger for this email based on its conditions'
            })
    except Exception as e:
        logger.error(f"Error testing auto-reply template: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500