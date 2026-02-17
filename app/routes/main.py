# app/routes/main.py
from flask import Blueprint, make_response, render_template, request, redirect, url_for, flash, jsonify, session, current_app
from flask_login import login_required, current_user
import pytz
from app import db
from datetime import datetime, timedelta, timezone
import logging
import json
import base64

from app.models.email import EmailCategory

logger = logging.getLogger(__name__)

main = Blueprint('main', __name__)

@main.route('/')
def index():
    """Redirect to dashboard or show home page."""
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    return redirect(url_for('auth.login'))

# app/routes/main.py

@main.route('/dashboard')
@login_required
def dashboard():
    emails = []
    gmail_connected = False
    stats = {
        'total_emails': 0,
        'unread_emails': 0,
        'auto_replies_active': 0,
        'follow_ups_pending': 0,
        'classifications': {}
    }

    try:
        # Import models and services inside the route to avoid circular imports
        from app.models.email import Email, EmailClassification
        from app.models.auto_reply import AutoReplyTemplate,AutoReplyRule
        from app.models.follow_up import FollowUp
        from app.services.gmail_service import GmailService
        
        if current_user.gmail_credentials:
            gmail_service = GmailService(current_user)
            if gmail_service.service:
                emails, _ = gmail_service.fetch_emails(max_results=10)
                gmail_connected = True
                
                # Get email statistics
                stats['total_emails'] = Email.query.filter_by(user_id=current_user.id).count()
                stats['unread_emails'] = Email.query.filter_by(user_id=current_user.id, is_read=False).count()
                stats['auto_replies_active'] = AutoReplyRule.query.filter_by(user_id=current_user.id, is_active=True).count()
                stats['follow_ups_pending'] = FollowUp.query.filter_by(user_id=current_user.id).filter(FollowUp.scheduled_at >= datetime.utcnow()).count()
                
                # FIXED: Get classification statistics with explicit JOIN
                # Using the category name directly from the relationship
                classifications = db.session.query(
                    EmailCategory.name,  # Use category name directly
                    db.func.count(EmailClassification.id).label('count')
                ).select_from(
                    Email  # Explicitly select from Email
                ).join(
                    EmailClassification, 
                    Email.id == EmailClassification.email_id  # Explicit JOIN condition
                ).join(
                    EmailCategory,
                    EmailClassification.category_id == EmailCategory.id  # Join with category
                ).filter(
                    Email.user_id == current_user.id  # Filter by user
                ).group_by(
                    EmailCategory.name  # Group by category name
                ).all()
                
                stats['classifications'] = {c[0]: c[1] for c in classifications}
                
    except Exception as e:
        logger.exception("Error fetching Gmail emails")
        flash(f"Error fetching Gmail emails: {str(e)}", "error")

    # Import models inside the route to avoid circular imports
    from app.models.automation import AutomationRule
    
    rules_count = AutomationRule.query.filter_by(user_id=current_user.id, is_active=True).count()

    return render_template('dashboard/index.html',
                           emails=emails,
                           rules_count=rules_count,
                           gmail_connected=gmail_connected,
                           stats=stats)
@main.route('/inbox')
@login_required
def inbox():
    direction = request.args.get('direction')   # 'next' or 'prev'
    page_token = request.args.get('page_token') # token passed in URL
    search = request.args.get('search', '')
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'  # Check if AJAX request

    # Initialize token stack in session if not exists
    if 'token_stack' not in session:
        session['token_stack'] = []

    emails = []
    pagination = {}
    gmail_connected = False

    try:
        # Import services inside the route to avoid circular imports
        from app.services.gmail_service import GmailService
        
        if current_user.gmail_credentials:
            gmail_service = GmailService(current_user)

            # Handle pagination stack more efficiently
            if direction == 'next' and page_token:
                # For Next: add current token to stack if not already there
                if not session['token_stack'] or session['token_stack'][-1] != page_token:
                    session['token_stack'].append(page_token)
                session.modified = True
            elif direction == 'prev':
                # For Previous: pop current token and use the previous one
                if len(session['token_stack']) > 1:
                    # Remove the current token from the top of the stack
                    session['token_stack'].pop()
                    session.modified = True
                    # Get the new top token (previous page)
                    page_token = session['token_stack'][-1] if session['token_stack'] else None
            elif page_token:
                # Direct navigation with page_token
                # Check if token is already in stack
                if page_token in session['token_stack']:
                    # Truncate stack at this token
                    index = session['token_stack'].index(page_token)
                    session['token_stack'] = session['token_stack'][:index+1]
                else:
                    # Add to stack
                    session['token_stack'].append(page_token)
                session.modified = True
            else:
                # First page - clear the stack
                session['token_stack'] = []
                session.modified = True

            # Fetch emails from Gmail with metadata only for faster loading
            # Use a smaller batch size for faster initial loading
            emails, next_page_token = gmail_service.fetch_emails(
                max_results=15,  # Reduced from 20 to 15 for faster loading
                page_token=page_token, 
                query=search if search else None,
                metadata_only=True  # Only fetch metadata for list view
            )

            gmail_connected = True
            has_prev = len(session['token_stack']) > 0
            
            # Get previous page token if available
            prev_page_token = None
            if has_prev and len(session['token_stack']) > 1:
                prev_page_token = session['token_stack'][-2]

            pagination = {
                'next_page_token': next_page_token,
                'has_next': bool(next_page_token),
                'has_prev': has_prev,
                'prev_page_token': prev_page_token,
                'current_page_token': page_token
            }

    except Exception as e:
        logger.exception("Error loading inbox")
        if is_ajax:
            return jsonify({'success': False, 'error': str(e)})
        flash(str(e), "error")

    if is_ajax:
        # Return partial template for AJAX requests
        return jsonify({
            'success': True,
            'html': render_template(
                'dashboard/inbox.html',
                emails=emails,
                pagination=pagination,
                gmail_connected=gmail_connected,
                search=search
            ),
            'pagination': pagination
        })
    
    # Return full template for regular requests
    return render_template(
        'dashboard/inbox.html',
        emails=emails,
        pagination=pagination,
        gmail_connected=gmail_connected,
        search=search
    )

@main.route('/refresh-inbox', methods=['POST'])
@login_required
def refresh_inbox():
    try:
        # Import services inside the route to avoid circular imports
        from app.services.gmail_service import GmailService
        
        gmail_service = GmailService(current_user)
        if not gmail_service.service:
            return jsonify({'success': False, 'error': 'Gmail not connected'})

        # Clear the token stack for a fresh start
        session['token_stack'] = []
        session.modified = True
        
        # Fetch fresh emails with metadata only for faster loading
        emails, next_page_token = gmail_service.fetch_emails(
            max_results=15,  # Reduced from 20 to 15 for faster loading
            metadata_only=True  # Only fetch metadata for list view
        )
        
        # Prepare pagination data
        pagination = {
            'next_page_token': next_page_token,
            'has_next': bool(next_page_token),
            'has_prev': False,
            'prev_page_token': None,
            'current_page_token': None
        }

        # Return the updated email list and pagination
        return jsonify({
            'success': True, 
            'html': render_template(
                'dashboard/inbox.html',
                emails=emails,
                pagination=pagination,
                gmail_connected=True,
                search=""
            ),
            'pagination': pagination,
            'emails_count': len(emails), 
            'message': 'Inbox refreshed successfully'
        })
    except Exception as e:
        logger.exception("Error refreshing inbox")
        return jsonify({'success': False, 'error': str(e)})

@main.route('/view-email/<message_id>')
@login_required
def view_email(message_id):
    from flask import current_app  # Import current_app instead of using app directly
    page_token = request.args.get('page_token')  # capture token from inbox
    
    # Import services inside the route to avoid circular imports
    from app.services.gmail_service import GmailService
    
    gmail_service = GmailService(current_user)
    if not gmail_service.service:
        flash('Gmail not connected', 'error')
        return redirect(url_for('main.inbox', page_token=page_token))
    
    try:
        # Get the full message with minimal fields for faster loading
        message = gmail_service.service.users().messages().get(
            userId='me', 
            id=message_id, 
            format='metadata',  # Start with metadata only
            metadataHeaders=['From', 'To', 'Subject', 'Date']
        ).execute()
        
        # Parse the message
        email_dict = gmail_service._parse_message(message)
        
        # Ensure the email dict has the expected structure
        if not email_dict:
            email_dict = {}
        
        # Make sure we have a body dictionary
        if 'body' not in email_dict or not isinstance(email_dict['body'], dict):
            email_dict['body'] = {}
        
        # For the view page, we need the full content, so fetch it separately
        full_message = gmail_service.service.users().messages().get(
            userId='me', 
            id=message_id, 
            format='full'
        ).execute()
        
        # Extract the message parts if they exist in the raw message
        if 'payload' in full_message and 'parts' in full_message['payload']:
            # This is a multipart message
            text_content = ""
            html_content = ""
            
            def extract_parts(parts):
                nonlocal text_content, html_content
                
                for part in parts:
                    mime_type = part.get('mimeType', '')
                    
                    if mime_type == 'text/plain' and 'data' in part.get('body', {}):
                        # Decode base64 text content
                        import base64
                        text_data = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
                        text_content += text_data
                    
                    elif mime_type == 'text/html' and 'data' in part.get('body', {}):
                        # Decode base64 HTML content
                        import base64
                        html_data = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
                        html_content += html_data
                    
                    # Handle nested parts
                    if 'parts' in part:
                        extract_parts(part['parts'])
            
            extract_parts(full_message['payload']['parts'])
            
            # Update the email_dict with extracted content
            if text_content:
                email_dict['body']['text'] = text_content
            if html_content:
                email_dict['body']['html'] = html_content
        
        # If it's not a multipart message, try to get the body directly
        elif 'payload' in full_message and 'body' in full_message['payload'] and 'data' in full_message['payload']['body']:
            import base64
            mime_type = full_message['payload'].get('mimeType', '')
            
            if mime_type == 'text/plain':
                text_data = base64.urlsafe_b64decode(full_message['payload']['body']['data']).decode('utf-8')
                email_dict['body']['text'] = text_data
            elif mime_type == 'text/html':
                html_data = base64.urlsafe_b64decode(full_message['payload']['body']['data']).decode('utf-8')
                email_dict['body']['html'] = html_data
        
        # Ensure we have at least some content
        if not email_dict.get('body', {}).get('text') and not email_dict.get('body', {}).get('html'):
            # Try to get the snippet as fallback
            if 'snippet' in message:
                email_dict['body']['text'] = message['snippet']
            else:
                email_dict['body']['text'] = "No content available"
        
        # Mark as read
        gmail_service.mark_as_read(message_id)
        
        return render_template(
            'dashboard/view_email.html', 
            email=email_dict, 
            page_token=page_token
        )
    except Exception as e:
        logger.exception("Error viewing email")
        flash(f"Error viewing email: {str(e)}", 'error')
        return redirect(url_for('main.inbox', page_token=page_token))

@main.route('/compose')
@login_required
def compose():
    draft_id = request.args.get('draft_id')
    draft = None
    
    if draft_id:
        # Import models inside the route to avoid circular imports
        from app.models.email import DraftEmail
        
        # Get the draft from our database
        draft = DraftEmail.query.filter_by(gmail_id=draft_id, user_id=current_user.id).first()
    
    return render_template('dashboard/compose.html', draft=draft)

@main.route('/send-email', methods=['POST'])
@login_required
def send_email():
    try:
        to = request.form.get('to', '')
        subject = request.form.get('subject', '')
        body_text = request.form.get('body_text', '')
        body_html = request.form.get('body_html', '')
        cc = request.form.get('cc', '')
        bcc = request.form.get('bcc', '')

        attachments = []
        if 'attachments' in request.files:
            for file in request.files.getlist('attachments'):
                if file.filename:
                    attachments.append({
                        'filename': file.filename,
                        'data': file.read(),
                        'mime_type': file.mimetype or 'application/octet-stream'
                    })

        # Import services inside the route to avoid circular imports
        from app.services.gmail_service import GmailService

        gmail_service = GmailService(current_user)
        if gmail_service.service:
            success, message = gmail_service.send_email(
                to=to, subject=subject, body_text=body_text,
                body_html=body_html, cc=cc, bcc=bcc, attachments=attachments
            )
            if success:
                flash(message, 'success')
                return redirect(url_for('main.inbox'))
            else:
                flash(message, 'error')
        else:
            flash('Gmail not connected', 'error')

        return redirect(url_for('main.compose'))
    except Exception as e:
        logger.exception("Error sending email")
        flash(f"Error sending email: {str(e)}", 'error')
        return redirect(url_for('main.compose'))

@main.route('/settings')
@login_required
def settings():
    # Import models and services inside the route to avoid circular imports
    from app.models.auto_reply import AutoReplyLog, AutoReplyTemplate
    from app.models.automation import AutomationRule
    from app.services.gmail_service import GmailService
    
    gmail_service = GmailService(current_user)
    gmail_connected = bool(gmail_service.service)

    rules = AutomationRule.query.filter_by(user_id=current_user.id).all()
    auto_replies = AutoReplyLog.query.filter_by(user_id=current_user.id).all()
    templates = AutoReplyTemplate.query.filter_by(user_id=current_user.id).all()

    labels = []
    if gmail_connected:
        try:
            labels = gmail_service.get_labels()
        except Exception as e:
            logger.exception("Error fetching labels")

    return render_template('dashboard/settings.html',
                           gmail_connected=gmail_connected,
                           rules=rules,
                           auto_replies=auto_replies,
                           templates=templates,
                           labels=labels)

@main.route('/create-label', methods=['POST'])
@login_required
def create_label():
    try:
        name = request.form.get('name', '')
        color = request.form.get('color', '')

        if not name:
            flash('Label name is required', 'error')
            return redirect(url_for('main.settings'))

        # Import services inside the route to avoid circular imports
        from app.services.gmail_service import GmailService

        gmail_service = GmailService(current_user)
        if gmail_service.service:
            label = gmail_service.create_label(name, color)
            if label:
                flash(f"Label '{name}' created successfully", 'success')
            else:
                flash("Failed to create label", 'error')
        else:
            flash('Gmail not connected', 'error')

        return redirect(url_for('main.settings'))
    except Exception as e:
        logger.exception("Error creating label")
        flash(f"Error creating label: {str(e)}", 'error')
        return redirect(url_for('main.settings'))

@main.route('/profile')
@login_required
def profile():
    return render_template('dashboard/profile.html')

# --- AJAX endpoints -------------------------------------------------------

@main.route('/api/toggle-star/<message_id>', methods=['POST'])
@login_required
def toggle_star(message_id):
    try:
        # Import services inside the route to avoid circular imports
        from app.services.gmail_service import GmailService
        
        gmail_service = GmailService(current_user)
        if not gmail_service.service:
            return jsonify({'success': False, 'error': 'Gmail not connected'})

        message = gmail_service.service.users().messages().get(
            userId='me', id=message_id, format='metadata', metadataHeaders=['labelIds']).execute()

        is_starred = 'STARRED' in message.get('labelIds', [])
        result = gmail_service.toggle_star(message_id, not is_starred)

        if result:
            return jsonify({'success': True, 'is_starred': not is_starred, 'message': 'Star status updated'})
        else:
            return jsonify({'success': False, 'error': 'Failed to update star status'})
    except Exception as e:
        logger.exception("Error toggling star")
        return jsonify({'success': False, 'error': str(e)})

@main.route('/api/mark-read/<message_id>', methods=['POST'])
@login_required
def mark_read(message_id):
    try:
        # Import services inside the route to avoid circular imports
        from app.services.gmail_service import GmailService
        
        gmail_service = GmailService(current_user)
        if not gmail_service.service:
            return jsonify({'success': False, 'error': 'Gmail not connected'})

        result = gmail_service.mark_as_read(message_id)
        if result:
            return jsonify({'success': True, 'message': 'Email marked as read'})
        else:
            return jsonify({'success': False, 'error': 'Failed to mark as read'})
    except Exception as e:
        logger.exception("Error marking as read")
        return jsonify({'success': False, 'error': str(e)})

@main.route('/api/archive/<message_id>', methods=['POST'])
@login_required
def archive_email(message_id):
    try:
        # Import services inside the route to avoid circular imports
        from app.services.gmail_service import GmailService
        
        gmail_service = GmailService(current_user)
        if not gmail_service.service:
            return jsonify({'success': False, 'error': 'Gmail not connected'})

        result = gmail_service.archive_email(message_id)
        if result:
            return jsonify({'success': True, 'message': 'Email archived successfully'})
        else:
            return jsonify({'success': False, 'error': 'Failed to archive email'})
    except Exception as e:
        logger.exception("Error archiving email")
        return jsonify({'success': False, 'error': str(e)})

@main.route('/api/delete/<message_id>', methods=['DELETE'])
@login_required
def delete_email(message_id):
    try:
        # Import services inside the route to avoid circular imports
        from app.services.gmail_service import GmailService
        
        gmail_service = GmailService(current_user)
        if not gmail_service.service:
            return jsonify({'success': False, 'error': 'Gmail not connected'})

        result = gmail_service.delete_email(message_id)
        if result:
            return jsonify({'success': True, 'message': 'Email deleted successfully'})
        else:
            return jsonify({'success': False, 'error': 'Failed to delete email'})
    except Exception as e:
        logger.exception("Error deleting email")
        return jsonify({'success': False, 'error': str(e)})

# ---------------- AI-powered endpoints ----------------

# generate email (keeps backward-compatible route and adds alias)
@main.route('/api/generate-email', methods=['POST'])
@main.route('/api/emails/generate', methods=['POST'])
@login_required
def generate_email():
    try:
        data = request.get_json() or {}
        purpose = data.get('purpose', '')
        tone = data.get('tone', 'professional')
        notes = data.get('notes', '')

        if not purpose:
            return jsonify({'success': False, 'error': 'Purpose is required'})

        # Import services inside the route to avoid circular imports
        from app.services.ai_service import AIService

        ai_service = AIService()
        email_data = ai_service.generate_email_with_context(purpose, tone, notes, user=current_user)

        # Ensure we return success flag and consistent fields
        return jsonify({'success': True, 'email': email_data, 'subject': email_data.get('subject', ''), 'body': email_data.get('body', '')})
    except Exception as e:
        logger.exception("Error generating email")
        return jsonify({'success': False, 'error': str(e)})

@main.route('/api/summarize-email', methods=['POST'])
@login_required
def summarize_email():
    try:
        payload = request.get_json() or {}
        message_id = payload.get('message_id', '')
        if not message_id:
            return jsonify({'success': False, 'error': 'Message ID is required'})

        # Import services inside the route to avoid circular imports
        from app.services.gmail_service import GmailService
        from app.services.ai_service import AIService
        
        gmail_service = GmailService(current_user)
        if not gmail_service.service:
            return jsonify({'success': False, 'error': 'Gmail not connected'})

        message = gmail_service.service.users().messages().get(
            userId='me', id=message_id, format='full').execute()
        email_dict = gmail_service._parse_message(message)
        body_text = email_dict.get('body', {}).get('text', '') or email_dict.get('snippet', '')

        if not body_text:
            return jsonify({'success': False, 'error': 'No email body to summarize'})

        ai_service = AIService()

        # Use a safe prompt for summarization
        prompt = f"Summarize the following email in 2-3 short bullet points:\n\n{body_text}"
        summary = ai_service._gpt(prompt) if hasattr(ai_service, '_gpt') else ai_service.generate_email(body_text, 'concise', '')

        return jsonify({'success': True, 'summary': summary})
    except Exception as e:
        logger.exception("Error summarizing email")
        return jsonify({'success': False, 'error': str(e)})

@main.route('/api/suggest-reply', methods=['POST'])
@login_required
def suggest_reply():
    try:
        payload = request.get_json() or {}
        message_id = payload.get('message_id', '')
        if not message_id:
            return jsonify({'success': False, 'error': 'Message ID is required'})

        # Import services inside the route to avoid circular imports
        from app.services.gmail_service import GmailService
        from app.services.ai_service import AIService
        
        gmail_service = GmailService(current_user)
        if not gmail_service.service:
            return jsonify({'success': False, 'error': 'Gmail not connected'})

        message = gmail_service.service.users().messages().get(
            userId='me', id=message_id, format='full').execute()
        email_dict = gmail_service._parse_message(message)
        body_text = email_dict.get('body', {}).get('text', '') or email_dict.get('snippet', '')

        ai_service = AIService()
        prompt = (
            "Given the following email, draft a short professional reply (2-4 sentences) "
            "and include a suggested subject line. Return JSON with keys: subject, body.\n\n"
            f"Email:\n{body_text}"
        )

        reply_text = ai_service._gpt(prompt) if hasattr(ai_service, '_gpt') else ai_service.generate_email(body_text, 'concise', '')
        # Try to parse JSON if model returned JSON, otherwise return raw text in body
        try:
            parsed = json.loads(reply_text)
            reply = parsed
        except Exception:
            reply = {'subject': '', 'body': reply_text}

        return jsonify({'success': True, 'reply': reply})
    except Exception as e:
        logger.exception("Error suggesting reply")
        return jsonify({'success': False, 'error': str(e)})

# Modify the check_new_emails endpoint to save emails to database
@main.route('/api/check-new-emails', methods=['GET'])
@login_required
def check_new_emails():
    try:
        # Get the last seen email ID from session
        last_seen_email_id = session.get('last_seen_email_id')
        
        # Import models and services inside the route to avoid circular imports
        from app.models.email import Email
        from app.services.gmail_service import GmailService
        
        # Get current user's Gmail service
        gmail_service = GmailService(current_user)
        if not gmail_service.service:
            return jsonify({'success': False, 'error': 'Gmail not connected'})
        
        # Fetch the most recent emails to check for new ones
        emails, _ = gmail_service.fetch_emails(max_results=10)
        
        # Initialize counters
        new_emails_count = 0
        latest_email_id = None
        
        # Process each email to check if it's new
        for email in emails:
            email_id = email.get('id')
            
            # Check if this email exists in our database
            existing_email = Email.query.filter_by(gmail_id=email_id).first()
            
            if not existing_email:
                # This is a new email
                new_emails_count += 1
                
                # Save to database to track it
                new_email = Email(
                    user_id=current_user.id,
                    gmail_id=email_id,
                    sender=email.get('sender', ''),
                    subject=email.get('subject', ''),
                    snippet=email.get('snippet', ''),
                    received_at=datetime.utcnow(),  # Using received_at instead of date_received
                    is_read=False,
                    is_starred=email.get('is_starred', False),
                    is_urgent=email.get('is_urgent', False)
                )
                db.session.add(new_email)
                
                # Update latest email ID if this is newer
                if latest_email_id is None or email_id != latest_email_id:
                    latest_email_id = email_id
        
        # Commit the new emails to database
        if new_emails_count > 0:
            db.session.commit()
            
            # Process new emails for classification
            process_new_emails_for_classification()
            
            # Trigger automation check for new emails
            from app.services.automation_service import AutomationService
            automation_service = AutomationService(current_user)
            automation_service.check_and_execute_rules()
        
        # Update the last seen email ID in session
        if latest_email_id:
            session['last_seen_email_id'] = latest_email_id
            session.modified = True
        
        return jsonify({
            'success': True,
            'new_emails': new_emails_count,
            'latest_email_id': latest_email_id
        })
        
    except Exception as e:
        logger.exception("Error checking for new emails")
        return jsonify({'success': False, 'error': str(e)})

# Add this endpoint to main.py
@main.route('/api/run-automation', methods=['POST'])
@login_required
def run_automation():
    try:
        # Import services inside the route to avoid circular imports
        from app.services.automation_service import AutomationService
        
        automation_service = AutomationService(current_user)
        automation_service.check_and_execute_rules()
        
        return jsonify({
            'success': True, 
            'message': 'Automation rules executed successfully'
        })
    except Exception as e:
        logger.exception("Error running automation")
        return jsonify({
            'success': False, 
            'error': str(e)
        })

# ENHANCED SENT EMAILS FUNCTIONALITY

@main.route('/sent-emails')
@main.route('/sent-emails')
@login_required
def sent_emails():
    import base64
    import json
    
    # Get query parameters
    page_token = request.args.get('page_token')
    page_size = request.args.get('page_size', 20, type=int)
    search = request.args.get('search', '')
    date_filter = request.args.get('date_filter', 'all')
    status = request.args.get('status', 'sent')
    force_refresh = request.args.get('refresh', 'false').lower() == 'true'
    
    try:
        # Import models and services inside the route to avoid circular imports
        from app.models.email import SentEmail
        from app.services.gmail_service import GmailService
        from app.services.sent_emails_service import sync_sent_emails, get_sent_emails_count
        
        # Get Gmail service
        gmail_service = GmailService(current_user)
        if not gmail_service.service:
            flash('Gmail not connected', 'error')
            return render_template('dashboard/sent.html', 
                                 sent_emails=[], 
                                 pagination=None,
                                 total_count=0,
                                 page_size=page_size,
                                 search=search,
                                 date_filter=date_filter,
                                 status=status)
        
        # Only sync with Gmail on first page load or when force_refresh is true
        # Use a rate limit to avoid excessive API calls
        if not page_token or force_refresh:
            # Check if we need to sync (rate limiting)
            last_sync = current_user.last_sent_email_sync or 0
            now = datetime.utcnow().timestamp()
            
            # Only sync if the last sync was more than 5 minutes ago, or if force_refresh is true
            if force_refresh or now - last_sync > 300:
                # Sync emails in the background - just metadata, not full content
                sync_sent_emails(user_id=current_user.id, limit=50, min_sync_interval=0)
                
                # Update last sync time
                current_user.last_sent_email_sync = now
                db.session.commit()
        
        # Now get emails from database with proper ordering
        query = SentEmail.query.filter_by(user_id=current_user.id)
        
        # Filter by status if provided
        if status and status != 'all':
            status_filter = status.capitalize() if status.lower() in ['sent', 'scheduled', 'failed'] else status
            query = query.filter_by(status=status_filter)
        
        # Apply search to database query
        if search:
            query = query.filter(
                db.or_(
                    SentEmail.subject.contains(search),
                    SentEmail.to.contains(search),
                    SentEmail.snippet.contains(search)
                    # Note: Removed body_text from search for performance
                )
            )
        
        # Apply date filter to database query
        if date_filter == 'today':
            query = query.filter(db.func.date(SentEmail.sent_at) == datetime.utcnow().date())
        elif date_filter == 'week':
            week_ago = datetime.utcnow() - timedelta(days=7)
            query = query.filter(SentEmail.sent_at >= week_ago)
        elif date_filter == 'month':
            month_ago = datetime.utcnow() - timedelta(days=30)
            query = query.filter(SentEmail.sent_at >= month_ago)
        
        # IMPORTANT: Order by sent_at DESC for Gmail-style ordering
        query = query.order_by(SentEmail.sent_at.desc())
        
        # Get total count
        total_count = query.count()
        
        # Apply pagination
        if page_token:
            try:
                offset = json.loads(base64.b64decode(page_token.encode()).decode()).get('offset', 0)
            except:
                offset = 0
        else:
            offset = 0
        
        # Get emails from database
        db_emails = query.offset(offset).limit(page_size).all()
        
        # Check if there are more emails
        has_next = (offset + page_size) < total_count
        has_prev = offset > 0
        
        # Generate pagination tokens
        pagination = {
            'has_next': has_next,
            'has_prev': has_prev,
            'next_page_token': base64.b64encode(json.dumps({'offset': offset + page_size}).encode()).decode() if has_next else None,
            'prev_page_token': base64.b64encode(json.dumps({'offset': max(0, offset - page_size)}).encode()).decode() if has_prev else None,
            'current_page': (offset // page_size) + 1,
            'start_index': offset + 1,
            'end_index': min(offset + len(db_emails), total_count)
        }
        
        return render_template(
            'dashboard/sent.html', 
            sent_emails=db_emails,
            pagination=pagination,
            total_count=total_count,
            page_size=page_size,
            search=search,
            date_filter=date_filter,
            status=status
        )
    except Exception as e:
        logger.exception("Error loading sent emails")
        flash(f"Error loading sent emails: {str(e)}", "error")
        return render_template('dashboard/sent.html', 
                             sent_emails=[], 
                             pagination=None,
                             total_count=0,
                             page_size=page_size,
                             search=search,
                             date_filter=date_filter,
                             status=status)

@main.route('/resync-sent-emails')
@login_required
def resync_sent_emails():
    """Route to clear and resync sent emails"""
    try:
        # Import models inside the route to avoid circular imports
        from app.models.email import SentEmail
        from app.services.sent_emails_service import sync_sent_emails
        
        # Delete all existing sent emails for this user
        deleted_count = SentEmail.query.filter_by(user_id=current_user.id).delete()
        db.session.commit()
        flash(f"Deleted {deleted_count} old sent emails. Resyncing...", "info")
        
        # Force sync
        sync_sent_emails(user_id=current_user.id, limit=50, min_sync_interval=0)
        
        # Redirect to sent emails page
        return redirect(url_for('main.sent_emails'))
    except Exception as e:
        logger.exception("Error resyncing sent emails")
        flash(f"Error resyncing: {str(e)}", "error")
        return redirect(url_for('main.sent_emails'))

@main.route('/api/refresh-sent-emails', methods=['POST'])
@login_required
def refresh_sent_emails():
    """API endpoint to refresh sent emails"""
    try:
        # Import the sync function
        from app.services.sent_emails_service import sync_sent_emails
        
        # Force sync
        sync_sent_emails(user_id=current_user.id, limit=50, min_sync_interval=0)
        
        return jsonify({
            'success': True, 
            'message': 'Sent emails refreshed successfully'
        })
    except Exception as e:
        logger.exception("Error refreshing sent emails")
        return jsonify({'success': False, 'error': str(e)})

@main.route('/sent-emails/<int:email_id>')
@login_required
def view_sent_email(email_id):
    try:
        # Import models and services inside the route to avoid circular imports
        from app.models.email import SentEmail
        from app.services.gmail_service import GmailService
        from app.services.sent_emails_service import get_sent_email_by_id
        
        # Get the sent email with body content
        sent_email = get_sent_email_by_id(email_id, user_id=current_user.id, fetch_body=True)
        
        if not sent_email:
            flash('Email not found', 'error')
            return redirect(url_for('main.sent_emails'))
        
        # Check if email belongs to current user
        if sent_email.user_id != current_user.id:
            flash('You do not have permission to view this email', 'error')
            return redirect(url_for('main.sent_emails'))
        
        # Get Gmail service to fetch full email details if needed
        gmail_service = GmailService(current_user)
        email_details = None
        
        if gmail_service.service and sent_email.gmail_id and (not sent_email.body_text and not sent_email.body_html):
            try:
                message = gmail_service.service.users().messages().get(
                    userId='me', id=sent_email.gmail_id, format='full').execute()
                email_details = gmail_service._parse_message(message)
            except Exception as e:
                logger.exception(f"Error fetching email details from Gmail: {str(e)}")
                email_details = None
        
        # Check if this email was opened or clicked (if tracking is enabled)
        tracking_info = {}
        # Only check tracking if the attribute exists
        if hasattr(sent_email, 'tracking_id') and sent_email.tracking_id:
            tracking_info = {
                'opened': hasattr(sent_email, 'opened_at') and sent_email.opened_at is not None,
                'opened_at': sent_email.opened_at.isoformat() if hasattr(sent_email, 'opened_at') and sent_email.opened_at else None,
                'clicked': hasattr(sent_email, 'clicked_at') and sent_email.clicked_at is not None,
                'clicked_at': sent_email.clicked_at.isoformat() if hasattr(sent_email, 'clicked_at') and sent_email.clicked_at else None
            }
        
        return render_template(
            'dashboard/view_sent_email.html',
            sent_email=sent_email,
            email_details=email_details,
            tracking_info=tracking_info
        )
    except Exception as e:
        logger.exception("Error viewing sent email")
        flash(f"Error viewing sent email: {str(e)}", "error")
        return redirect(url_for('main.sent_emails'))

@main.route('/api/resend-sent-email/<int:email_id>', methods=['POST'])
@login_required
def resend_sent_email(email_id):
    try:
        # Import models and services inside the route to avoid circular imports
        from app.models.email import SentEmail
        from app.services.gmail_service import GmailService
        from app.services.sent_emails_service import get_sent_email_by_id
        
        # Get the sent email with body content
        sent_email = get_sent_email_by_id(email_id, user_id=current_user.id, fetch_body=True)
        
        if not sent_email:
            return jsonify({'success': False, 'error': 'Email not found'}), 404
        
        # Check if email belongs to current user
        if sent_email.user_id != current_user.id:
            return jsonify({'success': False, 'error': 'Unauthorized'}), 403
        
        # Get Gmail service
        gmail_service = GmailService(current_user)
        if not gmail_service.service:
            return jsonify({'success': False, 'error': 'Gmail not connected'})
        
        # Resend the email
        success, message = gmail_service.send_email(
            to=sent_email.to,
            subject=sent_email.subject,
            body_text=sent_email.body_text,
            body_html=sent_email.body_html,
            cc=getattr(sent_email, 'cc', ''),
            bcc=getattr(sent_email, 'bcc', '')
        )
        
        if success:
            # Update the original email status
            sent_email.status = 'Sent'  # Keep as 'Sent' to match your model
            sent_email.resent_at = datetime.utcnow()
            db.session.commit()
            
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
        logger.exception("Error resending email")
        return jsonify({'success': False, 'error': str(e)})

@main.route('/api/delete-sent-email/<int:email_id>', methods=['DELETE'])
@login_required
def delete_sent_email(email_id):
    try:
        # Import models and services inside the route to avoid circular imports
        from app.models.email import SentEmail
        from app.services.gmail_service import GmailService
        
        # Get the sent email
        sent_email = SentEmail.query.get_or_404(email_id)
        
        # Check if email belongs to current user
        if sent_email.user_id != current_user.id:
            return jsonify({'success': False, 'error': 'Unauthorized'}), 403
        
        # Try to delete from Gmail first
        gmail_service = GmailService(current_user)
        if gmail_service.service and sent_email.gmail_id:
            try:
                gmail_service.delete_email(sent_email.gmail_id)
            except Exception as e:
                logger.exception(f"Error deleting email from Gmail: {str(e)}")
                # Continue with database deletion even if Gmail deletion fails
        
        # Delete from database
        db.session.delete(sent_email)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Email deleted successfully'
        })
    except Exception as e:
        logger.exception("Error deleting sent email")
        return jsonify({'success': False, 'error': str(e)})

@main.route('/api/delete-selected-sent-emails', methods=['POST'])
@login_required
def delete_selected_sent_emails():
    try:
        data = request.get_json()
        email_ids = data.get('email_ids', [])
        
        if not email_ids:
            return jsonify({'success': False, 'error': 'No email IDs provided'})
        
        # Import models and services inside the route to avoid circular imports
        from app.models.email import SentEmail
        from app.services.gmail_service import GmailService
        
        # Get Gmail service
        gmail_service = GmailService(current_user)
        
        # Get emails to delete
        emails_to_delete = SentEmail.query.filter(
            SentEmail.id.in_(email_ids),
            SentEmail.user_id == current_user.id
        ).all()
        
        if not emails_to_delete:
            return jsonify({'success': False, 'error': 'No valid emails found'})
        
        # Try to delete from Gmail
        if gmail_service.service:
            for email in emails_to_delete:
                if email.gmail_id:
                    try:
                        gmail_service.delete_email(email.gmail_id)
                    except Exception as e:
                        logger.exception(f"Error deleting email {email.gmail_id} from Gmail: {str(e)}")
                        # Continue with other emails even if one fails
        
        # Delete from database
        for email in emails_to_delete:
            db.session.delete(email)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'{len(emails_to_delete)} email(s) deleted successfully'
        })
    except Exception as e:
        logger.exception("Error deleting selected sent emails")
        return jsonify({'success': False, 'error': str(e)})

@main.route('/api/schedule-email', methods=['POST'])
@login_required
def schedule_email():
    try:
        data = request.get_json()
        to = data.get('to', '')
        subject = data.get('subject', '')
        body_text = data.get('body_text', '')
        body_html = data.get('body_html', '')
        cc = data.get('cc', '')
        bcc = data.get('bcc', '')
        scheduled_at_str = data.get('scheduled_at', '')
        
        if not all([to, subject, (body_text or body_html), scheduled_at_str]):
            return jsonify({'success': False, 'error': 'Missing required fields'})
        
        # Convert string date to datetime
        try:
            scheduled_at = datetime.fromisoformat(scheduled_at_str)
        except ValueError:
            return jsonify({'success': False, 'error': 'Invalid date format'})
        
        # Import models inside the route to avoid circular imports
        from app.models.email import SentEmail
        
        # Create a new scheduled email record
        scheduled_email = SentEmail(
            user_id=current_user.id,
            to=to,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            cc=cc,
            bcc=bcc,
            status='scheduled',
            scheduled_at=scheduled_at
        )
        
        db.session.add(scheduled_email)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'email_id': scheduled_email.id,
            'message': 'Email scheduled successfully'
        })
    except Exception as e:
        logger.exception("Error scheduling email")
        return jsonify({'success': False, 'error': str(e)})

@main.route('/api/send-scheduled-email/<int:email_id>', methods=['POST'])
@login_required
def send_scheduled_email(email_id):
    try:
        # Import models and services inside the route to avoid circular imports
        from app.models.email import SentEmail
        from app.services.gmail_service import GmailService
        
        # Get the scheduled email
        scheduled_email = SentEmail.query.get_or_404(email_id)
        
        # Check if email belongs to current user
        if scheduled_email.user_id != current_user.id:
            return jsonify({'success': False, 'error': 'Unauthorized'}), 403
        
        # Check if email is scheduled
        if scheduled_email.status != 'scheduled':
            return jsonify({'success': False, 'error': 'Email is not scheduled'})
        
        # Get Gmail service
        gmail_service = GmailService(current_user)
        if not gmail_service.service:
            return jsonify({'success': False, 'error': 'Gmail not connected'})
        
        # Send the email
        success, message, gmail_id = gmail_service.send_email(
            to=scheduled_email.to,
            subject=scheduled_email.subject,
            body_text=scheduled_email.body_text,
            body_html=scheduled_email.body_html,
            cc=scheduled_email.cc,
            bcc=scheduled_email.bcc
        )
        
        if success:
            # Update the email status
            scheduled_email.status = 'sent'
            scheduled_email.sent_at = datetime.utcnow()
            scheduled_email.gmail_id = gmail_id
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': 'Email sent successfully'
            })
        else:
            # Update the email status to failed
            scheduled_email.status = 'failed'
            scheduled_email.error_message = message
            db.session.commit()
            
            return jsonify({
                'success': False,
                'error': message
            })
    except Exception as e:
        logger.exception("Error sending scheduled email")
        return jsonify({'success': False, 'error': str(e)})

@main.route('/api/email-tracking/<tracking_id>')
def track_email_open(tracking_id):
    """Endpoint to track email opens"""
    try:
        # Import models inside the route to avoid circular imports
        from app.models.email import SentEmail
        
        # Find the email with this tracking ID
        sent_email = SentEmail.query.filter_by(tracking_id=tracking_id).first()
        
        if sent_email:
            # Update the opened timestamp
            sent_email.opened_at = datetime.utcnow()
            db.session.commit()
        
        # Return a 1x1 transparent pixel
        from flask import Response
        transparent_pixel = b'\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02\x04\x01\x00\x3b'
        return Response(transparent_pixel, mimetype='image/gif')
    except Exception as e:
        logger.exception("Error tracking email open")
        return '', 204

@main.route('/api/link-tracking/<tracking_id>/<link_id>')
def track_link_click(tracking_id, link_id):
    """Endpoint to track link clicks"""
    try:
        # Import models inside the route to avoid circular imports
        from app.models.email import SentEmail
        
        # Find the email with this tracking ID
        sent_email = SentEmail.query.filter_by(tracking_id=tracking_id).first()
        
        if sent_email:
            # Update the clicked timestamp
            sent_email.clicked_at = datetime.utcnow()
            db.session.commit()
        
        # Get the original URL from the link_id
        # This would require storing the original URLs when creating the email
        # For now, redirect to a placeholder
        return redirect('https://example.com')
    except Exception as e:
        logger.exception("Error tracking link click")
        return redirect('https://example.com')

# Add this endpoint to process scheduled emails
@main.route('/api/process-scheduled-emails', methods=['POST'])
@login_required
def process_scheduled_emails():
    """Process and send scheduled emails that are due"""
    try:
        # Import models and services inside the route to avoid circular imports
        from app.models.email import SentEmail
        from app.services.gmail_service import GmailService
        
        # Get all scheduled emails that are due
        now = datetime.utcnow()
        scheduled_emails = SentEmail.query.filter_by(
            user_id=current_user.id,
            status='scheduled'
        ).filter(
            SentEmail.scheduled_at <= now
        ).all()
        
        # Get Gmail service
        gmail_service = GmailService(current_user)
        if not gmail_service.service:
            return jsonify({'success': False, 'error': 'Gmail not connected'})
        
        sent_count = 0
        failed_count = 0
        
        for email in scheduled_emails:
            # Send the email
            success, message, gmail_id = gmail_service.send_email(
                to=email.to,
                subject=email.subject,
                body_text=email.body_text,
                body_html=email.body_html,
                cc=email.cc,
                bcc=email.bcc
            )
            
            if success:
                # Update the email status
                email.status = 'sent'
                email.sent_at = now
                email.gmail_id = gmail_id
                sent_count += 1
            else:
                # Update the email status to failed
                email.status = 'failed'
                email.error_message = message
                failed_count += 1
        
        # Commit all changes
        db.session.commit()
        
        return jsonify({
            'success': True,
            'sent_count': sent_count,
            'failed_count': failed_count,
            'message': f'Processed {len(scheduled_emails)} scheduled emails'
        })
    except Exception as e:
        logger.exception("Error processing scheduled emails")
        return jsonify({'success': False, 'error': str(e)})

@main.route('/drafts')
@login_required
def drafts():
    # Get query parameters
    page_token = request.args.get('page_token')
    page_size = request.args.get('page_size', 20, type=int)
    search = request.args.get('search', '')
    
    try:
        # Import models and services inside the route to avoid circular imports
        from app.models.email import DraftEmail
        from app.services.draft_service import DraftService
        
        # Calculate offset
        if page_token:
            try:
                import base64
                import json
                offset = json.loads(base64.b64decode(page_token.encode()).decode()).get('offset', 0)
            except:
                offset = 0
        else:
            offset = 0
        
        # Get drafts from database
        query = DraftEmail.query.filter_by(user_id=current_user.id)
        
        # Apply search filter
        if search:
            query = query.filter(
                db.or_(
                    DraftEmail.subject.contains(search),
                    DraftEmail.to.contains(search),
                    DraftEmail.body.contains(search)
                )
            )
        
        # Order by updated_at desc
        query = query.order_by(DraftEmail.updated_at.desc())
        
        # Get total count
        total_count = query.count()
        
        # Get paginated drafts
        drafts = query.offset(offset).limit(page_size).all()
        
        # Check if there are more drafts
        has_next = (offset + page_size) < total_count
        has_prev = offset > 0
        
        # Generate pagination tokens
        pagination = {
            'has_next': has_next,
            'has_prev': has_prev,
            'next_page_token': base64.b64encode(json.dumps({'offset': offset + page_size}).encode()).decode() if has_next else None,
            'prev_page_token': base64.b64encode(json.dumps({'offset': max(0, offset - page_size)}).encode()).decode() if has_prev else None,
            'current_page': (offset // page_size) + 1,
            'start_index': offset + 1,
            'end_index': min(offset + len(drafts), total_count)
        }
        
        return render_template(
            'dashboard/drafts.html', 
            drafts=drafts,
            pagination=pagination,
            total_count=total_count,
            page_size=page_size,
            search=search
        )
    except Exception as e:
        logger.exception("Error loading drafts")
        flash(f"Error loading drafts: {str(e)}", "error")
        return render_template(
            'dashboard/drafts.html', 
            drafts=[], 
            pagination=None,
            total_count=0,
            page_size=page_size,
            search=search
        )

@main.route('/drafts/<int:draft_id>')
@login_required
def view_draft(draft_id):
    try:
        # Import models and services inside the route to avoid circular imports
        from app.models.email import DraftEmail
        from app.services.draft_service import DraftService
        
        # Get the draft from database
        draft = DraftService.get_draft_by_id(draft_id, current_user.id)
        if not draft:
            flash('Draft not found', 'error')
            return redirect(url_for('main.drafts'))
        
        return render_template('dashboard/view_draft.html', draft=draft)
    except Exception as e:
        logger.exception("Error viewing draft")
        flash(f"Error viewing draft: {str(e)}", "error")
        return redirect(url_for('main.drafts'))

@main.route('/drafts/<int:draft_id>/edit')
@login_required
def edit_draft(draft_id):
    try:
        # Import models and services inside the route to avoid circular imports
        from app.models.email import DraftEmail
        from app.services.draft_service import DraftService
        
        # Get the draft from database
        draft = DraftService.get_draft_by_id(draft_id, current_user.id)
        if not draft:
            flash('Draft not found', 'error')
            return redirect(url_for('main.drafts'))
        
        # Redirect to compose page with draft data
        return redirect(url_for('main.compose', draft_id=draft.id))
    except Exception as e:
        logger.exception("Error editing draft")
        flash(f"Error editing draft: {str(e)}", "error")
        return redirect(url_for('main.drafts'))

@main.route('/api/refresh-drafts', methods=['POST'])
@login_required
def refresh_drafts():
    """API endpoint to refresh drafts from Gmail"""
    try:
        # Import services inside the route to avoid circular imports
        from app.services.draft_service import DraftService
        
        # Sync drafts from Gmail
        DraftService._sync_drafts_from_gmail(current_user, limit=50)
        
        return jsonify({
            'success': True, 
            'message': 'Drafts refreshed successfully'
        })
    except Exception as e:
        logger.exception("Error refreshing drafts")
        return jsonify({'success': False, 'error': str(e)})

@main.route('/api/duplicate-draft/<int:draft_id>', methods=['POST'])
@login_required
def duplicate_draft(draft_id):
    """API endpoint to duplicate a draft"""
    try:
        # Import models and services inside the route to avoid circular imports
        from app.models.email import DraftEmail
        from app.services.draft_service import DraftService
        
        # Get the original draft
        original_draft = DraftService.get_draft_by_id(draft_id, current_user.id)
        if not original_draft:
            return jsonify({'success': False, 'error': 'Draft not found'})
        
        # Create a new draft with the same content
        new_draft = DraftService.create_local_draft(
            to=original_draft.to,
            cc=original_draft.cc,
            bcc=original_draft.bcc,
            subject=f"[Copy] {original_draft.subject}" if original_draft.subject else "(No Subject)",
            body=original_draft.body,
            html_body=original_draft.html_body,
            user_id=current_user.id
        )
        
        if new_draft:
            return jsonify({
                'success': True,
                'message': 'Draft duplicated successfully',
                'draft_id': new_draft.id
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to duplicate draft'
            })
    except Exception as e:
        logger.exception("Error duplicating draft")
        return jsonify({'success': False, 'error': str(e)})

@main.route('/api/delete-draft/<int:draft_id>', methods=['DELETE'])
@login_required
def delete_draft(draft_id):
    """API endpoint to delete a draft"""
    try:
        # Import services inside the route to avoid circular imports
        from app.services.draft_service import DraftService
        
        # Delete the draft
        success = DraftService.delete_draft(draft_id, current_user.id)
        
        if success:
            return jsonify({
                'success': True,
                'message': 'Draft deleted successfully'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to delete draft'
            })
    except Exception as e:
        logger.exception("Error deleting draft")
        return jsonify({'success': False, 'error': str(e)})

@main.route('/api/save-draft', methods=['POST'])
@login_required
def save_draft():
    """API endpoint to save a draft"""
    try:
        # Get draft data from request
        data = request.get_json()
        draft_id = data.get('draft_id')
        to = data.get('to', '')
        cc = data.get('cc', '')
        bcc = data.get('bcc', '')
        subject = data.get('subject', '')
        body = data.get('body', '')
        html_body = data.get('html_body', '')
        
        # Import services inside the route to avoid circular imports
        from app.services.draft_service import DraftService
        
        if draft_id:
            # Update existing draft
            draft = DraftService.update_draft(
                draft_id=draft_id,
                to=to,
                cc=cc,
                bcc=bcc,
                subject=subject,
                body=body,
                html_body=html_body,
                user_id=current_user.id
            )
        else:
            # Create new draft
            draft = DraftService.create_local_draft(
                to=to,
                cc=cc,
                bcc=bcc,
                subject=subject,
                body=body,
                html_body=html_body,
                user_id=current_user.id
            )
        
        if draft:
            return jsonify({
                'success': True,
                'draft_id': draft.id,
                'message': 'Draft saved successfully'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to save draft'
            })
    except Exception as e:
        logger.exception("Error saving draft")
        return jsonify({'success': False, 'error': str(e)})

@main.route('/dashboard/auto-replies')
@login_required
def auto_replies():
    """Display the auto-replies dashboard page."""
    try:
        # Import models inside the route to avoid circular imports
        from app.models.auto_reply import AutoReplyRule, AutoReplyTemplate, AutoReplyLog
        
        # Get all auto-reply rules for the current user
        rules = AutoReplyRule.query.filter_by(user_id=current_user.id).order_by(AutoReplyRule.priority.asc()).all()
        
        # Get all templates for the current user and create a mapping
        templates = AutoReplyTemplate.query.filter_by(user_id=current_user.id).all()
        template_map = {t.id: t.name for t in templates}
        
        # Add template_name to each rule object for display
        for rule in rules:
            rule.template_name = template_map.get(rule.template_id, 'Unknown Template')
        
        # Get recent auto-reply logs
        recent_logs = AutoReplyLog.query.filter_by(user_id=current_user.id).order_by(AutoReplyLog.created_at.desc()).limit(10).all()
        
        # Calculate stats
        today = datetime.utcnow().date()
        week_ago = today - timedelta(days=7)
        
        # Get stats
        stats = {
            'active_rules': AutoReplyRule.query.filter_by(user_id=current_user.id, is_active=True).count(),
            'total_templates': len(templates), # Use the templates we already fetched
            'replies_today': AutoReplyLog.query.filter(
                AutoReplyLog.user_id == current_user.id,
                db.func.date(AutoReplyLog.created_at) == today,
                AutoReplyLog.status == 'Sent'
            ).count(),
            'rules_week': AutoReplyLog.query.filter(
                AutoReplyLog.user_id == current_user.id,
                AutoReplyLog.created_at >= week_ago,
                AutoReplyLog.status == 'Sent'
            ).count()
        }
        
        # Check if auto-replies are globally enabled
        global_enabled = current_user.auto_reply_enabled if hasattr(current_user, 'auto_reply_enabled') else True
        
        # Debug logging
        logger.info(f"Auto-replies loaded for user {current_user.id}: {len(rules)} rules, {len(templates)} templates, {len(recent_logs)} logs")
        
        # Add format_indian_time function to the template context
        def format_indian_time(dt):
            """Format datetime to Indian time string"""
            if not dt:
                return "Never"
            
            try:
                # Ensure dt is timezone-aware
                if dt.tzinfo is None:
                    # Assume UTC if no timezone info
                    import pytz
                    dt = dt.replace(tzinfo=pytz.UTC)
                
                # Convert to Indian timezone
                import pytz
                indian_tz = pytz.timezone('Asia/Kolkata')
                indian_time = dt.astimezone(indian_tz)
                
                return indian_time.strftime('%Y-%m-%d %H:%M:%S IST')
            except Exception as e:
                logger.error(f"Error formatting time: {e}")
                return str(dt)
        
        return render_template('dashboard/auto_replies.html', 
                             rules=rules, 
                             templates=templates,
                             logs=recent_logs,
                             global_enabled=global_enabled,
                             stats=stats,
                             format_indian_time=format_indian_time)  # Fixed: use snake_case
        
    except Exception as e:
        logger.exception(f"Error loading auto-replies for user {current_user.id}")
        flash(f"Error loading auto-replies: {str(e)}", "error")
        
        # Return with empty data on error
        def format_indian_time(dt):
            """Format datetime to Indian time string"""
            if not dt:
                return "Never"
            return dt.strftime('%Y-%m-%d %H:%M') if dt else "Never"
        
        return render_template('dashboard/auto_replies.html', 
                             rules=[], 
                             templates=[], 
                             logs=[],
                             global_enabled=True,
                             stats={
                                 'active_rules': 0,
                                 'total_templates': 0,
                                 'replies_today': 0,
                                 'rules_week': 0
                             },
                             format_indian_time=format_indian_time)  # Fixed: use snake_case

@main.route('/api/auto-reply/retry-failed', methods=['POST'])
@login_required
def retry_failed_auto_replies():
    """Retry failed auto-replies."""
    try:
        from app.models.auto_reply import AutoReplyLog, AutoReplyRule, AutoReplyTemplate
        from app.models.email import Email
        from app.services.auto_reply_service import AutoReplyService
        
        # Get failed auto-replies
        failed_logs = AutoReplyLog.query.filter_by(
            user_id=current_user.id,
            status='Failed'
        ).all()
        
        success_count = 0
        
        for log in failed_logs:
            try:
                # Get the original email
                email = Email.query.filter_by(id=log.email_id).first()
                if not email:
                    continue
                
                # Get the rule
                rule = None
                if log.rule_id:
                    rule = AutoReplyRule.query.filter_by(id=log.rule_id).first()
                
                # Get the template
                template = AutoReplyTemplate.query.filter_by(id=log.template_id).first()
                if not template:
                    continue
                
                # ✅ FIX: Reset processed flag before retrying
                email.processed_for_auto_reply = False
                db.session.commit()
                
                # ✅ FIX: Removed bypass parameters
                success = AutoReplyService.send_auto_reply(
                    email=email,
                    template=template,
                    user=current_user,
                    rule=rule
                )
                
                if success:
                    # Update the original log
                    log.status = 'Sent'
                    log.skip_reason = None
                    success_count += 1
                
                db.session.commit()
                
            except Exception as e:
                logger.exception(f"Error retrying auto-reply log {log.id}: {str(e)}")
                db.session.rollback()
        
        return jsonify({'success': True, 'count': success_count})
    except Exception as e:
        logger.exception("Error retrying failed auto-replies")
        return jsonify({'success': False, 'error': str(e)}), 500


@main.route('/api/auto-reply/test/<int:rule_id>', methods=['POST'])
@login_required
def test_auto_reply_rule(rule_id):
    """Test an auto-reply rule."""
    try:
        from app.models.auto_reply import AutoReplyRule, AutoReplyTemplate
        from app.services.auto_reply_service import AutoReplyService
        
        rule = AutoReplyRule.query.filter_by(id=rule_id, user_id=current_user.id).first()
        if not rule:
            return jsonify({'success': False, 'error': 'Rule not found'}), 404
        
        # Get test email data from request
        data = request.get_json()
        if not data or 'sender' not in data:
            return jsonify({'success': False, 'error': 'Sender is required'}), 400
        
        # Create a mock email object
        class MockEmail:
            def __init__(self, email_id, sender, subject, body_text, snippet, is_read=False, thread_id=None, message_id=None, gmail_id=None):
                self.id = email_id
                self.sender = sender
                self.subject = subject
                self.body_text = body_text
                self.snippet = snippet
                self.is_read = is_read
                self.received_at = datetime.utcnow()
                self.thread_id = thread_id or 'test_thread_id'
                self.message_id = message_id or f'test-message-{email_id}@example.com'
                self.gmail_id = gmail_id or f'test_gmail_id_{email_id}'
                self.folder = 'inbox'
                self.processed_for_auto_reply = False

        mock_email = MockEmail(
            email_id=99999,
            sender=data.get('sender', 'test@example.com'),
            subject=data.get('subject', 'Test Subject'),
            body_text=data.get('body_text', 'Test email body'),
            snippet=data.get('body_text', 'Test email body')[:100],
            is_read=data.get('is_read', False),
            thread_id=data.get('thread_id', 'test_thread_id'),
            message_id=data.get('message_id', f'test-message-99999@example.com'),
            gmail_id=data.get('gmail_id', f'test_gmail_id_99999')
        )
        
        # Get the template
        template = AutoReplyTemplate.query.filter_by(id=rule.template_id).first()
        if not template:
            return jsonify({'success': False, 'error': 'Template not found'}), 404
        
        # ✅ FIX: Use correct method name
        would_trigger = AutoReplyService.does_email_match_rule(mock_email, rule)
        
        if would_trigger:
            # Generate the reply content
            subject = f"Re: {mock_email.subject}"
            # ✅ FIX: Use template.content directly (adjust based on your model)
            content = template.content
            
            # If requested to actually send the test email
            if data.get('send_test', False):
                # ✅ FIX: Removed bypass parameters
                success = AutoReplyService.send_auto_reply(
                    email=mock_email,
                    template=template,
                    user=current_user,
                    rule=rule
                )
                
                return jsonify({
                    'success': success,
                    'would_trigger': True,
                    'subject': subject,
                    'content': content,
                    'sent': success
                })
            
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
                'message': 'Rule would not trigger for this email based on its conditions'
            })
    except Exception as e:
        logger.exception(f"Error testing auto-reply rule {rule_id}")
        return jsonify({'success': False, 'error': str(e)}), 500

@main.route('/api/auto-reply/rules/create', methods=['POST'])
@login_required
def create_auto_reply_rule():
    """Create a new auto-reply rule."""
    try:
        logger.info("=== CREATE RULE DEBUG START ===")
        logger.info(f"User: {current_user.id}")
        
        from app.models.auto_reply import AutoReplyRule, AutoReplyTemplate
        from app.services.auto_reply_service import AutoReplyService
        import json
        
        # Handle both JSON and form data
        if request.is_json:
            data = request.get_json()
        else:
            data = request.form.to_dict()
        
        logger.info(f"Received data: {data}")
        
        # Helper function for robust boolean parsing
        def parse_bool(value, default=False):
            if isinstance(value, bool):
                return value
            if value is None:
                return default
            if isinstance(value, (int, float)):
                return bool(value)
            return str(value).lower() in ('true', '1', 't', 'y', 'yes')
        
        # Validate required fields
        if not data.get("name"):
            logger.error("ERROR: Missing rule name")
            return jsonify({'success': False, 'error': 'Rule name is required'}), 400
        
        # Extract fields from data
        name = data.get("name").strip()
        priority = int(data.get("priority", 5))
        is_active = parse_bool(data.get("is_active"))
        
        # ✅ FIX: Get apply_to_existing_emails from form data
        apply_to_existing_emails = parse_bool(data.get("apply_to_existing_emails"), default=False)
        
        logger.info(f"Parsed: name={name}, priority={priority}, is_active={is_active}, apply_to_existing={apply_to_existing_emails}")
        
        # Parse trigger conditions
        trigger_conditions = {}
        
        # Check if apply to all is checked
        if parse_bool(data.get("apply_to_all")):
            trigger_conditions["apply_to_all"] = True
            logger.info("Apply to all emails rule")
        else:
            logger.info("Parsing specific conditions")
            
            # ✅ FIX: Combine keywords into single array
            keywords = []
            if data.get("subject_keywords"):
                keywords.extend([k.strip() for k in data.get("subject_keywords").split(",") if k.strip()])
            if data.get("body_keywords"):
                keywords.extend([k.strip() for k in data.get("body_keywords").split(",") if k.strip()])
            
            if keywords:
                trigger_conditions["keywords"] = keywords
            
            # Parse sender emails
            if data.get("sender_emails"):
                trigger_conditions["senders"] = [s.strip() for s in data.get("sender_emails").split(",") if s.strip()]
            
            # Parse sender domains
            if data.get("sender_domains"):
                trigger_conditions["domains"] = [d.strip() for d in data.get("sender_domains").split(",") if d.strip()]
            
            # Parse email category
            if data.get("email_category"):
                trigger_conditions["categories"] = [data.get("email_category")]
            
            # Parse urgency level
            if data.get("urgency_level"):
                trigger_conditions["urgency_level"] = [data.get("urgency_level")]
            
            # Parse checkboxes
            trigger_conditions["unread"] = parse_bool(data.get("unread_only"))
            trigger_conditions["business_hours_only"] = parse_bool(data.get("business_hours_only"))
            
            # Parse condition logic
            trigger_conditions["condition_logic"] = data.get("condition_logic", "AND")
        
        logger.info(f"Trigger conditions: {trigger_conditions}")
        
        # Validate that at least one condition is set
        if not trigger_conditions.get("apply_to_all") and not any(v for k, v in trigger_conditions.items() if v not in [False, [], "AND"]):
            logger.error("ERROR: No valid trigger conditions")
            return jsonify({'success': False, 'error': 'At least one trigger condition must be specified'}), 400
        
        # Check if "apply to all" rule already exists
        if trigger_conditions.get("apply_to_all"):
            existing_rule = AutoReplyRule.query.filter_by(
                user_id=current_user.id,
                is_active=True
            ).filter(AutoReplyRule.trigger_conditions.like('%"apply_to_all": true%')).first()
            
            if existing_rule:
                logger.error("ERROR: Apply to all rule already exists")
                return jsonify({'success': False, 'error': 'Only one rule with "Apply to All Incoming Emails" is allowed'}), 400
        
        # Parse template configuration
        template_id = data.get("template_id")
        
        if not template_id or template_id == "new":
            logger.info("Creating new template")
            
            template_data = data.get("template_data")
            
            if not isinstance(template_data, dict):
                logger.error("ERROR: Template data is missing or not in the correct format")
                return jsonify({'success': False, 'error': 'Template data is required to create a new template'}), 400

            template_name = template_data.get("name")
            reply_subject = template_data.get("reply_subject")
            reply_body = template_data.get("reply_body")
            
            if not template_name or not reply_body:
                logger.error("ERROR: Missing template name or reply body")
                return jsonify({'success': False, 'error': 'Template name and reply body are required'}), 400
            
            # ✅ FIX: Use 'content' field name (adjust based on your model)
            template = AutoReplyTemplate(
                user_id=current_user.id,
                name=template_name.strip(),
                reply_subject=reply_subject.strip() if reply_subject else None,
                reply_body=reply_body.strip()
            )
            
            db.session.add(template)
            db.session.flush()
            template_id = template.id
            logger.info(f"Created new template with ID: {template_id}")
        else:
            logger.info(f"Using existing template ID: {template_id}")
            template_id = int(template_id)
            template = AutoReplyTemplate.query.filter_by(id=template_id, user_id=current_user.id).first()
            if not template:
                logger.error("ERROR: Template not found")
                return jsonify({'success': False, 'error': 'Template not found'}), 400
        
        # Parse advanced settings
        delay_minutes = int(data.get("delay_minutes", 0))
        sender_email = data.get("sender_email")
        reply_once_per_thread = parse_bool(data.get("reply_once_per_thread"))
        prevent_auto_reply_to_auto = parse_bool(data.get("prevent_auto_reply_to_auto"))
        ignore_mailing_lists = parse_bool(data.get("ignore_mailing_lists"))
        stop_on_sender_reply = parse_bool(data.get("stop_on_sender_reply"))
        
        # Parse schedule settings
        schedule_start = None
        schedule_end = None
        business_hours_only = parse_bool(data.get("business_hours_only"))
        business_days_only = parse_bool(data.get("business_days_only"))
        business_hours_start = None
        business_hours_end = None
        
        # Parse business hours
        if data.get("business_hours_start"):
            try:
                business_hours_start = datetime.strptime(data.get("business_hours_start"), '%H:%M').time()
            except ValueError:
                business_hours_start = datetime.strptime('09:00', '%H:%M').time()
        
        if data.get("business_hours_end"):
            try:
                business_hours_end = datetime.strptime(data.get("business_hours_end"), '%H:%M').time()
            except ValueError:
                business_hours_end = datetime.strptime('18:00', '%H:%M').time()
        
        # Parse schedule dates
        if data.get("schedule_start"):
            try:
                schedule_start = datetime.fromisoformat(data.get("schedule_start"))
            except ValueError:
                schedule_start = None
        
        if data.get("schedule_end"):
            try:
                schedule_end = datetime.fromisoformat(data.get("schedule_end"))
            except ValueError:
                schedule_end = None
        
        logger.info(f"Advanced settings: delay={delay_minutes}, schedule={schedule_start} to {schedule_end}")
        
        # ✅ FIX: Create the rule with apply_to_existing_emails field
        rule = AutoReplyRule(
            user_id=current_user.id,
            name=name,
            priority=priority,
            is_active=is_active,
            template_id=template_id,
            trigger_conditions=json.dumps(trigger_conditions),
            delay_minutes=delay_minutes,
            sender_email=sender_email,
            reply_once_per_thread=reply_once_per_thread,
            prevent_auto_reply_to_auto=prevent_auto_reply_to_auto,
            ignore_mailing_lists=ignore_mailing_lists,
            stop_on_sender_reply=stop_on_sender_reply,
            schedule_start=schedule_start,
            schedule_end=schedule_end,
            business_hours_only=business_hours_only,
            business_days_only=business_days_only,
            business_hours_start=business_hours_start,
            business_hours_end=business_hours_end,
            apply_to_existing_emails=apply_to_existing_emails  # ✅ CRITICAL FIX
        )
        
        logger.info("About to add rule to session")
        db.session.add(rule)
        logger.info("About to commit")
        db.session.commit()
        logger.info(f"Rule created successfully with ID: {rule.id}")
        
        # If the rule is active, trigger immediate check in background (non-blocking)
        if rule.is_active:
            logger.info(f"Rule {rule.id} created and is active. Scheduling background email check.")
            try:
                import threading
                # Start background thread WITH app context - syncs emails first, then processes rule
                # IMPORTANT: Capture actual app and user instances (not proxy objects)
                from flask import current_app
                from app.services.gmail_service import GmailService
                
                # Get actual app and user instances (not proxy objects)
                app_instance = current_app._get_current_object()
                user_instance = current_user._get_current_object()
                rule_id_val = rule.id
                
                def run_with_app_context():
                    with app_instance.app_context():
                        try:
                            # Step 1: Sync new emails from Gmail first
                            logger.info(f"📥 Background sync: Fetching new emails for user {user_instance.id}")
                            try:
                                gs = GmailService(user_instance)
                                if gs and gs.service:
                                    synced = gs.sync_emails(limit=20)
                                    logger.info(f"📥 Background sync: Synced {synced} emails for user {user_instance.id}")
                                else:
                                    logger.warning(f"📥 Background sync: GmailService not initialized for user {user_instance.id}")
                            except Exception as sync_err:
                                logger.error(f"📥 Background sync failed for user {user_instance.id}: {sync_err}")
                            
                            # Step 2: Process the newly created rule
                            logger.info(f"🚀 Background processing: Processing rule {rule_id_val}")
                            AutoReplyService.immediate_check_for_new_rule(rule_id_val)
                            
                        except Exception as e:
                            logger.error(f"Background thread error for rule {rule_id_val}: {e}", exc_info=True)
                
                thread = threading.Thread(target=run_with_app_context, daemon=True)
                thread.start()
                logger.info(f"Background thread started for rule {rule.id} (will sync + process)")
            except Exception as e:
                logger.warning(f"Could not start background thread: {e}")
        
        logger.info("=== CREATE RULE DEBUG END ===")
        return jsonify({'success': True, 'rule_id': rule.id})
        
    except Exception as e:
        logger.error(f"ERROR IN CREATE RULE: {str(e)}")
        import traceback
        traceback.print_exc()
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@main.route('/api/auto-reply/rules/<int:rule_id>')
@login_required
def get_auto_reply_rule(rule_id):
    """Get a specific auto-reply rule."""
    try:
        # Import models inside the route to avoid circular imports
        from app.models.auto_reply import AutoReplyRule, AutoReplyTemplate
        
        rule = AutoReplyRule.query.filter_by(id=rule_id, user_id=current_user.id).first()
        if not rule:
            return jsonify({'success': False, 'error': 'Rule not found'}), 404
        
        # Get the template
        template = AutoReplyTemplate.query.filter_by(id=rule.template_id).first()
        template_name = template.name if template else "Unknown"
        
        # Check if rule is scheduled now
        from app.services.auto_reply_service import AutoReplyService
        is_scheduled_now = AutoReplyService.is_rule_scheduled_now(rule)
        
        return jsonify({
            'success': True,
            'rule': {
                'id': rule.id,
                'name': rule.name,
                'priority': rule.priority,
                'is_active': rule.is_active,
                'template_id': rule.template_id,
                'template_name': template_name,
                'trigger_conditions': rule.get_trigger_conditions(),
                'is_scheduled_now': is_scheduled_now,
                'schedule_start': rule.schedule_start.isoformat() if rule.schedule_start else None,
                'schedule_end': rule.schedule_end.isoformat() if rule.schedule_end else None,
                'delay_minutes': rule.delay_minutes,
                'sender_email': rule.sender_email,
                'apply_to_existing_emails': rule.apply_to_existing_emails,
                # CRITICAL FIX: Removed cooldown_hours
                'reply_once_per_thread': rule.reply_once_per_thread,
                'prevent_auto_reply_to_auto': rule.prevent_auto_reply_to_auto,
                'ignore_mailing_lists': rule.ignore_mailing_lists,
                'stop_on_sender_reply': rule.stop_on_sender_reply,
                'business_hours_only': rule.business_hours_only,
                'business_days_only': rule.business_days_only,
                'business_hours_start': rule.business_hours_start.strftime('%H:%M') if rule.business_hours_start else None,
                'business_hours_end': rule.business_hours_end.strftime('%H:%M') if rule.business_hours_end else None,
                'last_triggered': rule.last_triggered.isoformat() if rule.last_triggered else None
            }
        })
    except Exception as e:
        logger.exception(f"Error getting auto-reply rule {rule_id}")
        return jsonify({'success': False, 'error': str(e)}), 500

@main.route('/api/auto-reply/rules/update/<int:rule_id>', methods=['PUT'])
@login_required
def update_auto_reply_rule(rule_id):
    """Update an existing auto-reply rule."""
    try:
        from app.models.auto_reply import AutoReplyRule, AutoReplyTemplate
        from app.services.auto_reply_service import AutoReplyService
        
        rule = AutoReplyRule.query.filter_by(id=rule_id, user_id=current_user.id).first()
        if not rule:
            return jsonify({'success': False, 'error': 'Rule not found'}), 404
        
        # Handle both JSON and form data
        if request.is_json:
            data = request.get_json()
        else:
            data = request.form.to_dict()
        
        def parse_bool(value, default=False):
            if isinstance(value, bool):
                return value
            if value is None:
                return default
            if isinstance(value, (int, float)):
                return bool(value)
            return str(value).lower() in ('true', '1', 't', 'y', 'yes')

        # Update fields
        if "name" in data and data["name"].strip():
            rule.name = data["name"].strip()
        
        if "priority" in data:
            try:
                rule.priority = int(data["priority"])
            except (ValueError, TypeError):
                return jsonify({'success': False, 'error': 'Invalid priority value'}), 400
        
        if "is_active" in data:
            rule.is_active = parse_bool(data.get("is_active"))
        
        # ✅ FIX: Added apply_to_existing_emails field
        if "apply_to_existing_emails" in data:
            rule.apply_to_existing_emails = parse_bool(data.get("apply_to_existing_emails"))
        
        # Parse trigger conditions
        trigger_conditions = {}
        
        if parse_bool(data.get("apply_to_all")):
            trigger_conditions["apply_to_all"] = True
        else:
            # ✅ FIX: Combine keywords into single array
            keywords = []
            if data.get("subject_keywords"):
                keywords.extend([k.strip() for k in data.get("subject_keywords").split(",") if k.strip()])
            if data.get("body_keywords"):
                keywords.extend([k.strip() for k in data.get("body_keywords").split(",") if k.strip()])
            
            if keywords:
                trigger_conditions["keywords"] = keywords
            
            if data.get("sender_emails"):
                trigger_conditions["senders"] = [s.strip() for s in data.get("sender_emails").split(",") if s.strip()]
            
            if data.get("sender_domains"):
                trigger_conditions["domains"] = [d.strip() for d in data.get("sender_domains").split(",") if d.strip()]
            
            if data.get("email_category"):
                trigger_conditions["categories"] = [data.get("email_category")]
            
            if data.get("urgency_level"):
                trigger_conditions["urgency_level"] = [data.get("urgency_level")]
            
            trigger_conditions["unread"] = parse_bool(data.get("unread_only"))
            trigger_conditions["business_hours_only"] = parse_bool(data.get("business_hours_only"))
            trigger_conditions["condition_logic"] = data.get("condition_logic", "AND")

        # Validate that at least one condition is set
        if not trigger_conditions.get("apply_to_all") and not any(v for k, v in trigger_conditions.items() if v not in [False, [], "AND"]):
            return jsonify({'success': False, 'error': 'At least one trigger condition must be specified'}), 400
        
        # Check if "apply to all" rule already exists (and it's not this rule)
        if trigger_conditions.get("apply_to_all") and not json.loads(rule.trigger_conditions).get("apply_to_all"):
            existing_rule = AutoReplyRule.query.filter(
                AutoReplyRule.user_id == current_user.id,
                AutoReplyRule.is_active == True,
                AutoReplyRule.id != rule_id
            ).filter(AutoReplyRule.trigger_conditions.like('%"apply_to_all": true%')).first()
            
            if existing_rule:
                return jsonify({'success': False, 'error': 'Only one rule with "Apply to All Incoming Emails" is allowed'}), 400
        
        # Update trigger conditions
        rule.trigger_conditions = json.dumps(trigger_conditions)
        
        # Parse template configuration
        template_id = data.get("template_id")
        
        if template_id == "new":
            template_data = data.get("template_data")
            if not isinstance(template_data, dict):
                return jsonify({'success': False, 'error': 'Template data is required to create a new template'}), 400

            template_name = template_data.get("name")
            reply_subject = template_data.get("reply_subject")
            reply_body = template_data.get("reply_body")
            
            if not template_name or not reply_body:
                return jsonify({'success': False, 'error': 'Template name and reply body are required'}), 400
            
            template = AutoReplyTemplate(
                user_id=current_user.id,
                name=template_name.strip(),
                content=reply_body.strip(),
                html_content=None
            )
            
            db.session.add(template)
            db.session.flush()
            rule.template_id = template.id
        elif template_id:
            template_id = int(template_id)
            template = AutoReplyTemplate.query.filter_by(id=template_id, user_id=current_user.id).first()
            if not template:
                return jsonify({'success': False, 'error': 'Template not found'}), 400
            rule.template_id = template_id
        
        # Parse advanced settings
        if "delay_minutes" in data:
            try:
                rule.delay_minutes = int(data.get("delay_minutes", 0))
            except (ValueError, TypeError):
                return jsonify({'success': False, 'error': 'Invalid delay_minutes value'}), 400
        
        if "sender_email" in data:
            rule.sender_email = data.get("sender_email")
        
        if "reply_once_per_thread" in data:
            rule.reply_once_per_thread = parse_bool(data.get("reply_once_per_thread"))
        
        if "prevent_auto_reply_to_auto" in data:
            rule.prevent_auto_reply_to_auto = parse_bool(data.get("prevent_auto_reply_to_auto"))
        
        if "ignore_mailing_lists" in data:
            rule.ignore_mailing_lists = parse_bool(data.get("ignore_mailing_lists"))
        
        if "stop_on_sender_reply" in data:
            rule.stop_on_sender_reply = parse_bool(data.get("stop_on_sender_reply"))
        
        # Parse schedule settings
        if "business_hours_only" in data:
            rule.business_hours_only = parse_bool(data.get("business_hours_only"))
        
        if "business_days_only" in data:
            rule.business_days_only = parse_bool(data.get("business_days_only"))
        
        if data.get("business_hours_start"):
            try:
                rule.business_hours_start = datetime.strptime(data.get("business_hours_start"), '%H:%M').time()
            except ValueError:
                rule.business_hours_start = datetime.strptime('09:00', '%H:%M').time()
        
        if data.get("business_hours_end"):
            try:
                rule.business_hours_end = datetime.strptime(data.get("business_hours_end"), '%H:%M').time()
            except ValueError:
                rule.business_hours_end = datetime.strptime('18:00', '%H:%M').time()
        
        if data.get("schedule_start"):
            try:
                rule.schedule_start = datetime.fromisoformat(data.get("schedule_start"))
            except ValueError:
                rule.schedule_start = None
        
        if data.get("schedule_end"):
            try:
                rule.schedule_end = datetime.fromisoformat(data.get("schedule_end"))
            except ValueError:
                rule.schedule_end = None
        
        rule.updated_at = datetime.utcnow()
        db.session.commit()
        
        # If the rule is active, immediately check for emails that match
        if rule.is_active:
            logger.info(f"Rule {rule.id} updated and is active. Triggering immediate email check.")
            AutoReplyService.immediate_check_for_new_rule(rule.id)
        
        return jsonify({'success': True})
    except Exception as e:
        logger.exception(f"Error updating auto-reply rule {rule_id}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@main.route('/api/auto-reply/rules/delete/<int:rule_id>', methods=['DELETE'])
@login_required
def delete_auto_reply_rule(rule_id):
    """Delete an auto-reply rule."""
    try:
        # Import models inside the route to avoid circular imports
        from app.models.auto_reply import AutoReplyRule, ScheduledAutoReply
        
        rule = AutoReplyRule.query.filter_by(id=rule_id, user_id=current_user.id).first()
        if not rule:
            return jsonify({'success': False, 'error': 'Rule not found'}), 404
        
        # FIXED: First, handle any scheduled replies that reference this rule
        scheduled_replies = ScheduledAutoReply.query.filter_by(rule_id=rule_id).all()
        for scheduled_reply in scheduled_replies:
            # Update the status to indicate the rule was deleted
            scheduled_reply.status = 'Cancelled'
            scheduled_reply.failure_reason = 'Rule was deleted'
        
        # Now delete the rule
        db.session.delete(rule)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Auto-reply rule deleted successfully'})
    except Exception as e:
        logger.exception(f"Error deleting auto-reply rule {rule_id}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@main.route('/api/auto-reply/rules/toggle/<int:rule_id>', methods=['POST'])
@login_required
def toggle_auto_reply_rule(rule_id):
    """Toggle the active status of an auto-reply rule."""
    try:
        # Import models inside the route to avoid circular imports
        from app.models.auto_reply import AutoReplyRule
        from app.services.auto_reply_service import AutoReplyService
        
        rule = AutoReplyRule.query.filter_by(id=rule_id, user_id=current_user.id).first()
        if not rule:
            return jsonify({'success': False, 'error': 'Rule not found'}), 404
        
        # Toggle the status
        rule.is_active = not rule.is_active
        rule.updated_at = datetime.utcnow()
        db.session.commit()
        
        # If the rule is now active, immediately check for emails that match
        if rule.is_active:
            logger.info(f"Rule {rule.id} activated. Triggering immediate email check.")
            AutoReplyService.immediate_check_for_new_rule(rule.id)
        
        return jsonify({'success': True, 'is_active': rule.is_active})
    except Exception as e:
        logger.exception(f"Error toggling auto-reply rule {rule_id}")
        return jsonify({'success': False, 'error': str(e)}), 500

@main.route('/api/auto-reply/rules/duplicate/<int:rule_id>', methods=['POST'])
@login_required
def duplicate_auto_reply_rule(rule_id):
    """Duplicate an auto-reply rule."""
    try:
        # Import models inside the route to avoid circular imports
        from app.models.auto_reply import AutoReplyRule
        
        rule = AutoReplyRule.query.filter_by(id=rule_id, user_id=current_user.id).first()
        if not rule:
            return jsonify({'success': False, 'error': 'Rule not found'}), 404
        
        # Create a duplicate
        new_rule = AutoReplyRule(
            user_id=current_user.id,
            name=f"{rule.name} (Copy)",
            priority=rule.priority + 1,  # Slightly lower priority
            is_active=False,  # Start as inactive
            template_id=rule.template_id,
            trigger_conditions=rule.trigger_conditions,
            delay_minutes=rule.delay_minutes,
            # CRITICAL FIX: Removed cooldown_hours
            reply_once_per_thread=rule.reply_once_per_thread,
            prevent_auto_reply_to_auto=rule.prevent_auto_reply_to_auto,
            ignore_mailing_lists=rule.ignore_mailing_lists,
            stop_on_sender_reply=rule.stop_on_sender_reply,
            # CRITICAL FIX: Add schedule fields
            schedule_start=rule.schedule_start,
            schedule_end=rule.schedule_end,
            business_hours_only=rule.business_hours_only,
            business_days_only=rule.business_days_only,
            business_hours_start=rule.business_hours_start,
            business_hours_end=rule.business_hours_end
        )
        
        db.session.add(new_rule)
        db.session.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        logger.exception(f"Error duplicating auto-reply rule {rule_id}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@main.route('/api/auto-reply/rules/<int:rule_id>/triggered-emails')
@login_required
def get_rule_triggered_emails(rule_id):
    """Get emails that have triggered a specific rule."""
    try:
        # Import models inside the route to avoid circular imports
        from app.models.auto_reply import AutoReplyRule, AutoReplyLog
        from app.models.email import Email
        
        rule = AutoReplyRule.query.filter_by(id=rule_id, user_id=current_user.id).first()
        if not rule:
            return jsonify({'success': False, 'error': 'Rule not found'}), 404
        
        # Get logs for this rule
        logs = AutoReplyLog.query.filter_by(
            user_id=current_user.id,
            rule_id=rule_id
        ).order_by(AutoReplyLog.created_at.desc()).limit(50).all()
        
        # Get email details for each log
        emails = []
        for log in logs:
            email = Email.query.filter_by(id=log.email_id).first()
            if email:
                emails.append({
                    'id': email.id,
                    'subject': email.subject,
                    'sender': email.sender,
                    'received_at': email.received_at.isoformat() if email.received_at else None,
                    'snippet': email.snippet,
                    'status': log.status,
                    'skip_reason': log.skip_reason,
                    'message_id': email.message_id,  # CRITICAL FIX: Add Message-ID
                    'gmail_id': email.gmail_id  # CRITICAL FIX: Add gmail_id
                })
        
        return jsonify({
            'success': True,
            'emails': emails
        })
    except Exception as e:
        logger.exception(f"Error getting triggered emails for rule {rule_id}")
        return jsonify({'success': False, 'error': str(e)}), 500

@main.route('/api/auto-reply/logs')
@login_required
def get_auto_reply_logs():
    """Get auto-reply logs for the current user."""
    try:
        # Import models inside the route to avoid circular imports
        from app.models.auto_reply import AutoReplyLog, AutoReplyRule, AutoReplyTemplate
        
        # Get query parameters
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        status_filter = request.args.get('status', '')
        
        # Build query
        query = AutoReplyLog.query.filter_by(user_id=current_user.id)
        
        # Apply status filter if provided
        if status_filter and status_filter != 'all':
            query = query.filter(AutoReplyLog.status == status_filter)
        
        # Order by creation date (newest first)
        query = query.order_by(AutoReplyLog.created_at.desc())
        
        # Paginate
        logs = query.paginate(page=page, per_page=per_page, error_out=False)
        
        # Get additional details for each log
        log_data = []
        for log in logs.items:
            # Get rule name
            rule_name = None
            if log.rule_id:
                rule = AutoReplyRule.query.filter_by(id=log.rule_id).first()
                if rule:
                    rule_name = rule.name
            
            # Get template name
            template_name = None
            if log.template_id:
                template = AutoReplyTemplate.query.filter_by(id=log.template_id).first()
                if template:
                    template_name = template.name
            
            # Get incoming email subject
            incoming_subject = None
            if log.email_id:
                from app.models.email import Email
                email = Email.query.filter_by(id=log.email_id).first()
                if email:
                    incoming_subject = email.subject
            
            log_data.append({
                'id': log.id,
                'email_id': log.email_id,
                'incoming_subject': incoming_subject,
                'sender_email': log.recipient_email,  # CRITICAL FIX: Use recipient_email instead of sender_email
                'rule_id': log.rule_id,
                'rule_name': rule_name,
                'template_id': log.template_id,
                'template_name': template_name,
                'status': log.status,
                'skip_reason': log.skip_reason,
                'reply_content': log.reply_content,
                'message_id': log.message_id,  # CRITICAL FIX: Add Message-ID
                'gmail_id': log.gmail_id,  # CRITICAL FIX: Add gmail_id
                'created_at': log.created_at.isoformat() if log.created_at else None
            })
        
        return jsonify({
            'success': True,
            'logs': log_data,
            'pagination': {
                'page': logs.page,
                'pages': logs.pages,
                'per_page': logs.per_page,
                'total': logs.total,
                'has_next': logs.has_next,
                'has_prev': logs.has_prev
            }
        })
    except Exception as e:
        logger.exception("Error getting auto-reply logs")
        return jsonify({'success': False, 'error': str(e)}), 500

@main.route('/api/auto-reply/logs/<int:log_id>')
@login_required
def get_auto_reply_log(log_id):
    """Get a specific auto-reply log."""
    try:
        # Import models inside the route to avoid circular imports
        from app.models.auto_reply import AutoReplyLog, AutoReplyRule, AutoReplyTemplate
        
        log = AutoReplyLog.query.filter_by(id=log_id, user_id=current_user.id).first()
        if not log:
            return jsonify({'success': False, 'error': 'Log not found'}), 404
        
        # Get rule name
        rule_name = None
        if log.rule_id:
            rule = AutoReplyRule.query.filter_by(id=log.rule_id).first()
            if rule:
                rule_name = rule.name
        
        # Get template name
        template_name = None
        if log.template_id:
            template = AutoReplyTemplate.query.filter_by(id=log.template_id).first()
            if template:
                template_name = template.name
        
        # Get incoming email subject
        incoming_subject = None
        if log.email_id:
            from app.models.email import Email
            email = Email.query.filter_by(id=log.email_id).first()
            if email:
                incoming_subject = email.subject
        
        return jsonify({
            'success': True,
            'log': {
                'id': log.id,
                'email_id': log.email_id,
                'incoming_subject': incoming_subject,
                'sender_email': log.recipient_email,  # CRITICAL FIX: Use recipient_email instead of sender_email
                'rule_id': log.rule_id,
                'rule_name': rule_name,
                'template_id': log.template_id,
                'template_name': template_name,
                'status': log.status,
                'skip_reason': log.skip_reason,
                'reply_content': log.reply_content,
                'message_id': log.message_id,  # CRITICAL FIX: Add Message-ID
                'gmail_id': log.gmail_id,  # CRITICAL FIX: Add gmail_id
                'created_at': log.created_at.isoformat() if log.created_at else None
            }
        })
    except Exception as e:
        logger.exception(f"Error getting auto-reply log {log_id}")
        return jsonify({'success': False, 'error': str(e)}), 500

@main.route('/api/auto-reply/logs/<int:log_id>/retry', methods=['POST'])
@login_required
def retry_auto_reply_log(log_id):
    """Retry a failed auto-reply."""
    try:
        from app.models.auto_reply import AutoReplyLog, AutoReplyRule, AutoReplyTemplate
        from app.models.email import Email
        from app.services.auto_reply_service import AutoReplyService
        
        log = AutoReplyLog.query.filter_by(id=log_id, user_id=current_user.id).first()
        if not log:
            return jsonify({'success': False, 'error': 'Log not found'}), 404
        
        if log.status != 'Failed':
            return jsonify({'success': False, 'error': 'Only failed auto-replies can be retried'}), 400
        
        # Get the original email
        email = Email.query.filter_by(id=log.email_id).first()
        if not email:
            return jsonify({'success': False, 'error': 'Original email not found'}), 404
        
        # Get the rule
        rule = None
        if log.rule_id:
            rule = AutoReplyRule.query.filter_by(id=log.rule_id).first()
        
        if not rule:
            return jsonify({'success': False, 'error': 'Rule not found'}), 404
        
        # Get the template
        template = AutoReplyTemplate.query.filter_by(id=rule.template_id).first()
        if not template:
            return jsonify({'success': False, 'error': 'Template not found'}), 404
        
        # ✅ FIX: Reset processed flag before retrying
        email.processed_for_auto_reply = False
        db.session.commit()
        
        # ✅ FIX: Removed bypass parameters
        success = AutoReplyService.send_auto_reply(
            email=email,
            template=template,
            user=current_user,
            rule=rule
        )
        
        if success:
            # Update the original log
            log.status = 'Sent'
            log.skip_reason = None
            db.session.commit()
            
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Failed to resend auto-reply'}), 500
    except Exception as e:
        logger.exception(f"Error retrying auto-reply log {log_id}")
        return jsonify({'success': False, 'error': str(e)}), 500
    
@main.route('/api/auto-reply/logs/<int:log_id>', methods=['DELETE'])
@login_required
def delete_auto_reply_log(log_id):
    """Delete an auto-reply log."""
    try:
        # Import models inside the route to avoid circular imports
        from app.models.auto_reply import AutoReplyLog
        
        log = AutoReplyLog.query.filter_by(id=log_id, user_id=current_user.id).first()
        if not log:
            return jsonify({'success': False, 'error': 'Log not found'}), 404
        
        db.session.delete(log)
        db.session.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        logger.exception(f"Error deleting auto-reply log {log_id}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

# Template Management Routes

@main.route('/api/auto-reply/templates')
@login_required
def get_auto_reply_templates():
    """Get all auto-reply templates for the current user."""
    try:
        # Import models inside the route to avoid circular imports
        from app.models.auto_reply import AutoReplyTemplate
        
        templates = AutoReplyTemplate.query.filter_by(user_id=current_user.id).order_by(AutoReplyTemplate.created_at.desc()).all()
        
        template_data = []
        for template in templates:
            template_data.append({
                'id': template.id,
                'name': template.name,
                'reply_subject': template.reply_subject,
                'reply_body': template.reply_body,
                'created_at': template.created_at.isoformat() if template.created_at else None,
                'updated_at': template.updated_at.isoformat() if template.updated_at else None
            })
        
        return jsonify({
            'success': True,
            'templates': template_data
        })
    except Exception as e:
        logger.exception("Error getting auto-reply templates")
        return jsonify({'success': False, 'error': str(e)}), 500

@main.route('/api/auto-reply/templates/<int:template_id>')
@login_required
def get_auto_reply_template(template_id):
    """Get a specific auto-reply template."""
    try:
        # Import models inside the route to avoid circular imports
        from app.models.auto_reply import AutoReplyTemplate
        
        template = AutoReplyTemplate.query.filter_by(id=template_id, user_id=current_user.id).first()
        if not template:
            return jsonify({'success': False, 'error': 'Template not found'}), 404
        
        return jsonify({
            'success': True,
            'template': {
                'id': template.id,
                'name': template.name,
                'reply_subject': template.reply_subject,
                'reply_body': template.reply_body,
                'created_at': template.created_at.isoformat() if template.created_at else None,
                'updated_at': template.updated_at.isoformat() if template.updated_at else None
            }
        })
    except Exception as e:
        logger.exception(f"Error getting auto-reply template {template_id}")
        return jsonify({'success': False, 'error': str(e)}), 500

@main.route('/api/auto-reply/templates/create', methods=['POST'])
@login_required
def create_auto_reply_template():
    """Create a new auto-reply template."""
    try:
        # Import models inside the route to avoid circular imports
        from app.models.auto_reply import AutoReplyTemplate
        
        # Handle both JSON and form data
        if request.is_json:
            data = request.get_json()
        else:
            data = request.form.to_dict()
        
        # Extract fields from data
        name = data.get("name")
        reply_subject = data.get("reply_subject")
        reply_body = data.get("reply_body")
        
        if not name or not name.strip():
            return jsonify({'success': False, 'error': 'Template name is required'}), 400
        
        if not reply_body or not reply_body.strip():
            return jsonify({'success': False, 'error': 'Template reply body is required'}), 400
        
        # Create the template
        template = AutoReplyTemplate(
            user_id=current_user.id,
            name=name.strip(),
            reply_subject=reply_subject.strip() if reply_subject else None,
            reply_body=reply_body.strip()
        )
        
        db.session.add(template)
        db.session.commit()
        
        return jsonify({'success': True, 'template_id': template.id})
    except Exception as e:
        logger.exception("Error creating auto-reply template")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@main.route('/api/auto-reply/templates/<int:template_id>', methods=['PUT'])
@login_required
def update_auto_reply_template(template_id):
    """Update an existing auto-reply template."""
    try:
        # Import models inside the route to avoid circular imports
        from app.models.auto_reply import AutoReplyTemplate
        
        template = AutoReplyTemplate.query.filter_by(id=template_id, user_id=current_user.id).first()
        if not template:
            return jsonify({'success': False, 'error': 'Template not found'}), 404
        
        # Handle both JSON and form data
        if request.is_json:
            data = request.get_json()
        else:
            data = request.form.to_dict()
        
        # Update fields
        if "name" in data and data["name"].strip():
            template.name = data["name"].strip()
        
        if "reply_subject" in data:
            template.reply_subject = data["reply_subject"].strip() if data["reply_subject"] else None
        
        if "reply_body" in data and data["reply_body"].strip():
            template.reply_body = data["reply_body"].strip()
        
        template.updated_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        logger.exception(f"Error updating auto-reply template {template_id}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@main.route('/api/auto-reply/templates/<int:template_id>', methods=['DELETE'])
@login_required
def delete_auto_reply_template(template_id):
    """Delete an auto-reply template."""
    try:
        # Import models inside the route to avoid circular imports
        from app.models.auto_reply import AutoReplyTemplate
        
        template = AutoReplyTemplate.query.filter_by(id=template_id, user_id=current_user.id).first()
        if not template:
            return jsonify({'success': False, 'error': 'Template not found'}), 404
        
        # Check if any rules are using this template
        from app.models.auto_reply import AutoReplyRule
        rules_using_template = AutoReplyRule.query.filter_by(template_id=template_id).count()
        
        if rules_using_template > 0:
            return jsonify({
                'success': False, 
                'error': f'Cannot delete template: {rules_using_template} rule(s) are using this template'
            }), 400
        
        db.session.delete(template)
        db.session.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        logger.exception(f"Error deleting auto-reply template {template_id}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

# Utility Routes

@main.route('/api/auto-reply/refresh', methods=['POST'])
@login_required
def refresh_auto_replies():
    """Manually trigger auto-reply processing for the current user."""
    try:
        from app.services.auto_reply_service import AutoReplyService
        from app.models.auto_reply import AutoReplyRule
        
        # Check if the user has any active rules at all
        active_rules_count = AutoReplyRule.query.filter_by(
            user_id=current_user.id, 
            is_active=True
        ).count()
        
        if active_rules_count == 0:
            return jsonify({'success': False, 'error': 'No active rules found to process emails.'}), 404
        
        # ✅ FIX: Removed check_all_unread parameter
        logger.info(f"Manual refresh triggered for user {current_user.id}. Checking all unread emails.")
        result = AutoReplyService.check_and_send_auto_replies()
        
        return jsonify({
            'success': True, 
            'message': f'Processed {result.get("count", 0)} emails with {active_rules_count} active rule(s).'
        })
    except Exception as e:
        logger.exception("Error refreshing auto-replies")
        return jsonify({'success': False, 'error': str(e)}), 500

@main.route('/api/auto-reply/global-toggle', methods=['POST'])
@login_required
def global_toggle_auto_replies():
    """Globally enable or disable auto-replies for the current user."""
    try:
        data = request.get_json()
        enabled = data.get('enabled', True)
        
        # Update user preference
        if hasattr(current_user, 'auto_reply_enabled'):
            current_user.auto_reply_enabled = enabled
            db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': f'Auto-replies {"enabled" if enabled else "disabled"} globally.'
        })
    except Exception as e:
        logger.exception("Error toggling auto-replies globally")
        return jsonify({'success': False, 'error': str(e)}), 500

@main.route('/api/auto-reply/export-rules', methods=['GET'])
@login_required
def export_auto_reply_rules():
    """Export auto-reply rules as CSV."""
    try:
        # Import models inside the route to avoid circular imports
        from app.models.auto_reply import AutoReplyRule, AutoReplyTemplate
        import csv
        from io import StringIO
        from flask import Response
        
        # Get all rules for the current user
        rules = AutoReplyRule.query.filter_by(user_id=current_user.id).all()
        
        # Create CSV data
        output = StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow([
            'Name', 'Priority', 'Is Active', 'Template Name', 
            'Trigger Conditions', 'Delay Minutes',
            'Reply Once Per Thread', 'Prevent Auto Reply To Auto',
            'Ignore Mailing Lists', 'Stop On Sender Reply',
            'Schedule Start', 'Schedule End', 'Business Hours Only', 'Business Days Only',
            'Business Hours Start', 'Business Hours End',
            'Last Triggered', 'Created At'
        ])
        
        # Write rule data
        for rule in rules:
            # Get template name
            template_name = 'Unknown'
            if rule.template_id:
                template = AutoReplyTemplate.query.filter_by(id=rule.template_id).first()
                if template:
                    template_name = template.name
            
            writer.writerow([
                rule.name,
                rule.priority,
                rule.is_active,
                template_name,
                rule.trigger_conditions,
                rule.delay_minutes,
                # CRITICAL FIX: Removed cooldown_hours
                rule.reply_once_per_thread,
                rule.prevent_auto_reply_to_auto,
                rule.ignore_mailing_lists,
                rule.stop_on_sender_reply,
                rule.schedule_start.isoformat() if rule.schedule_start else '',
                rule.schedule_end.isoformat() if rule.schedule_end else '',
                rule.business_hours_only,
                rule.business_days_only,
                rule.business_hours_start.strftime('%H:%M') if rule.business_hours_start else '',
                rule.business_hours_end.strftime('%H:%M') if rule.business_hours_end else '',
                rule.last_triggered.isoformat() if rule.last_triggered else '',
                rule.created_at.isoformat() if rule.created_at else ''
            ])
        
        # Create response
        output.seek(0)
        return Response(
            output,
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=auto_reply_rules.csv"}
        )
    except Exception as e:
        logger.exception("Error exporting auto-reply rules")
        return jsonify({'success': False, 'error': str(e)}), 500

@main.route('/api/auto-reply/export-logs', methods=['GET'])
@login_required
def export_auto_reply_logs():
    """Export auto-reply logs as CSV."""
    try:
        # Import models inside the route to avoid circular imports
        from app.models.auto_reply import AutoReplyLog, AutoReplyRule, AutoReplyTemplate
        import csv
        from io import StringIO
        from flask import Response
        
        # Get all logs for the current user
        logs = AutoReplyLog.query.filter_by(user_id=current_user.id).all()
        
        # Create CSV data
        output = StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow([
            'ID', 'Incoming Subject', 'Sender Email', 'Rule Name', 
            'Template Name', 'Status', 'Skip Reason', 'Message-ID', 'Gmail ID', 'Created At'
        ])
        
        # Write log data
        for log in logs:
            # Get rule name
            rule_name = 'Unknown'
            if log.rule_id:
                rule = AutoReplyRule.query.filter_by(id=log.rule_id).first()
                if rule:
                    rule_name = rule.name
            
            # Get template name
            template_name = 'Unknown'
            if log.template_id:
                template = AutoReplyTemplate.query.filter_by(id=log.template_id).first()
                if template:
                    template_name = template.name
            
            # Get incoming email subject
            incoming_subject = 'Unknown'
            if log.email_id:
                from app.models.email import Email
                email = Email.query.filter_by(id=log.email_id).first()
                if email:
                    incoming_subject = email.subject
            
            writer.writerow([
                log.id,
                incoming_subject,
                log.recipient_email,  # CRITICAL FIX: Use recipient_email instead of sender_email
                rule_name,
                template_name,
                log.status,
                log.skip_reason,
                log.message_id,  # CRITICAL FIX: Add Message-ID
                log.gmail_id,  # CRITICAL FIX: Add gmail_id
                log.created_at.isoformat() if log.created_at else ''
            ])
        
        # Create response
        output.seek(0)
        return Response(
            output,
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=auto_reply_logs.csv"}
        )
    except Exception as e:
        logger.exception("Error exporting auto-reply logs")
        return jsonify({'success': False, 'error': str(e)}), 500

@main.route('/api/auto-reply/stats', methods=['GET'])
@login_required
def get_auto_reply_stats():
    """Get auto-reply statistics for the current user."""
    try:
        # Import models inside the route to avoid circular imports
        from app.models.auto_reply import AutoReplyRule, AutoReplyTemplate, AutoReplyLog
        
        # Get active rules count
        active_rules_count = AutoReplyRule.query.filter_by(user_id=current_user.id, is_active=True).count()
        
        # Get total templates count
        total_templates_count = AutoReplyTemplate.query.filter_by(user_id=current_user.id).count()
        
        # Get sent today count
        today = datetime.utcnow().date()
        sent_today = AutoReplyLog.query.filter(
            AutoReplyLog.user_id == current_user.id,
            db.func.date(AutoReplyLog.created_at) == today,
            AutoReplyLog.status == 'Sent'
        ).count()
        
        # Get sent this week count
        week_ago = datetime.utcnow() - timedelta(days=7)
        sent_this_week = AutoReplyLog.query.filter(
            AutoReplyLog.user_id == current_user.id,
            AutoReplyLog.created_at >= week_ago,
            AutoReplyLog.status == 'Sent'
        ).count()
        
        return jsonify({
            'success': True,
            'stats': {
                'active_rules': active_rules_count,
                'total_templates': total_templates_count,
                'replies_today': sent_today,
                'rules_week': sent_this_week
            }
        })
    except Exception as e:
        logger.exception("Error getting auto-reply stats")
        return jsonify({'success': False, 'error': str(e)}), 500

@main.route('/api/auto-reply/indian-time', methods=['GET'])
@login_required
def get_indian_time():
    """Get current time in Indian timezone."""
    try:
        from app.services.auto_reply_service import AutoReplyService
        
        indian_time = AutoReplyService.get_indian_time()
        
        return jsonify({
            'success': True,
            'indian_time': indian_time.isoformat(),
            'formatted': indian_time.strftime('%Y-%m-%d %H:%M:%S %Z')
        })
    except Exception as e:
        logger.exception("Error getting Indian time")
        return jsonify({'success': False, 'error': str(e)}), 500
@main.route('/classifications')
@login_required
def classifications():
    try:
        # Import models and services inside the route to avoid circular imports
        from app.models.email import Email, EmailClassification, EmailCategory
        from app.services.email_classifier import get_classification_stats, ensure_default_categories_exist, batch_classify_emails
        
        # Ensure default categories exist for this user
        ensure_default_categories_exist(current_user.id)
        
        # Get all emails for the user
        all_emails = Email.query.filter_by(user_id=current_user.id).all()
        logger.info(f"Found {len(all_emails)} emails for user {current_user.id}")
        
        # Check if there are unclassified emails
        unclassified_count = 0
        for email in all_emails:
            classification = EmailClassification.query.filter_by(email_id=email.id).first()
            if not classification:
                unclassified_count += 1
        
        # If there are unclassified emails, classify them
        if unclassified_count > 0:
            logger.info(f"Found {unclassified_count} unclassified emails, starting batch classification")
            batch_result = batch_classify_emails(current_user.id, limit=1000)
            if batch_result['success']:
                logger.info(f"Batch classification result: {batch_result}")
        
        # Get classification stats after classification
        stats = get_classification_stats(current_user.id)
        
        # Ensure all default categories have counts
        default_categories = ['Urgent', 'Important', 'Work', 'Personal', 'Spam']
        for category in default_categories:
            if category not in stats:
                stats[category] = 0
        
        # Get all emails with their classifications (increased limit or removed)
        emails_with_classifications = db.session.query(
            Email, EmailClassification, EmailCategory
        ).outerjoin(
            EmailClassification, Email.id == EmailClassification.email_id
        ).outerjoin(
            EmailCategory, EmailClassification.category_id == EmailCategory.id
        ).filter(
            Email.user_id == current_user.id
        ).order_by(
            Email.received_at.desc()
        ).limit(200).all()  # Increased from 50 to 200
        
        # Format the data for the template
        classifications = []
        for email, classification, category in emails_with_classifications:
            classifications.append({
                'email': email,
                'classification': classification,
                'category': category
            })
        
        # Get total email count
        total_emails = Email.query.filter_by(user_id=current_user.id).count()
        
        logger.info(f"Classification stats: {stats}")
        logger.info(f"Total emails: {total_emails}")
        logger.info(f"Displaying {len(classifications)} emails")
        
        return render_template('dashboard/classifications.html', 
                             classifications=classifications,
                             stats=stats,
                             total_emails=total_emails)
        
    except Exception as e:
        logger.exception("Error loading classifications")
        flash(f"Error loading classifications: {str(e)}", "error")
        return render_template('dashboard/classifications.html', 
                             classifications=[],
                             stats={},
                             total_emails=0)

# Email classification routes
@main.route('/api/classify-email/<int:email_id>', methods=['POST'])
@login_required
def classify_single_email(email_id):
    try:
        # Import models and services inside the route to avoid circular imports
        from app.models.email import Email, EmailClassification, EmailCategory
        from app.services.email_classifier import classify_email, get_classification_stats
        
        # Get the request data
        data = request.get_json()
        category_name = data.get('category', '').lower()
        manual_override = data.get('manual_override', False)
        
        # Get the email
        email = Email.query.get_or_404(email_id)
        
        # Check if email belongs to current user
        if email.user_id != current_user.id:
            return jsonify({'success': False, 'error': 'Unauthorized'}), 403
        
        # If this is a manual classification request
        if manual_override and category_name:
            # Get the category - handle both lowercase and title case
            category = EmailCategory.query.filter_by(user_id=current_user.id, name=category_name.title()).first()
            if not category:
                # Try lowercase
                category = EmailCategory.query.filter_by(user_id=current_user.id, name=category_name).first()
            
            if not category:
                # Create the category if it doesn't exist
                logger.info(f"Creating new category: {category_name}")
                category = EmailCategory(
                    user_id=current_user.id,
                    name=category_name.title(),
                    color="#6B7280",  # Default gray color
                    description=f"User created category: {category_name.title()}"
                )
                db.session.add(category)
                db.session.commit()
            
            # Check if classification already exists
            existing_classification = EmailClassification.query.filter_by(email_id=email_id).first()
            
            if existing_classification:
                # Update existing classification
                existing_classification.category_id = category.id
                existing_classification.confidence_score = 1.0  # Manual classification gets full confidence
                existing_classification.manual_override = True
                existing_classification.updated_at = datetime.utcnow()
                classification = existing_classification
            else:
                # Create new classification
                classification = EmailClassification(
                    email_id=email_id,
                    category_id=category.id,
                    confidence_score=1.0,  # Manual classification gets full confidence
                    manual_override=True,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                db.session.add(classification)
            
            db.session.commit()
            
            # Get updated stats
            stats = get_classification_stats(current_user.id)
            return jsonify({
                'success': True,
                'classification': category.name,
                'confidence': classification.confidence_score,
                'counts': stats,
                'message': f'Email classified as: {category.name}'
            })
        else:
            # Classify the email using the automatic classification function
            classification = classify_email(email_id, current_user.id)
            
            if classification:
                # Get the category name for the response
                category = EmailCategory.query.get(classification.category_id)
                
                return jsonify({
                    'success': True,
                    'classification': category.name if category else 'Unknown',
                    'confidence': classification.confidence_score,
                    'message': f'Email classified as: {category.name if category else "Unknown"}'
                })
            else:
                return jsonify({'success': False, 'error': 'Failed to classify email'})
            
    except Exception as e:
        logger.exception("Error classifying email")
        return jsonify({'success': False, 'error': str(e)})

@main.route('/api/classify-batch', methods=['POST'])
@login_required
def classify_batch_emails():
    try:
        # Import models and services inside the route to avoid circular imports
        from app.models.email import Email, EmailClassification
        from app.services.email_classifier import batch_classify_emails, get_classification_stats, fetch_and_classify_all_gmail_emails, auto_classify_new_emails
        
        # Safely get the request data
        try:
            data = request.get_json() or {}
        except Exception as e:
            logger.warning(f"Failed to parse JSON from request: {e}")
            data = {}
        
        # Check if data was sent as form data instead
        if not data and request.form:
            # Convert form data to dictionary
            data = {key: value for key, value in request.form.items()}
            # Convert string booleans to actual booleans
            for key in ['fetch_from_gmail', 'fetch_new']:
                if key in data:
                    data[key] = data[key].lower() in ['true', '1', 'yes', 'on']
        
        fetch_from_gmail = data.get('fetch_from_gmail', False)
        fetch_new = data.get('fetch_new', False)
        
        if fetch_from_gmail:
            # Fetch and classify all emails from Gmail
            result = fetch_and_classify_all_gmail_emails(current_user.id)
            logger.info(f"Gmail fetch and classification result: {result}")
        elif fetch_new:
            # Auto-classify new emails
            result = auto_classify_new_emails(current_user.id)
            logger.info(f"Auto-classify new emails result: {result}")
        else:
            # Call the batch classification function from email_classifier.py
            result = batch_classify_emails(current_user.id, limit=1000)
            logger.info(f"Batch classification result: {result}")
        
        # If successful, get updated stats
        if result.get('success'):
            stats = get_classification_stats(current_user.id)
            result['counts'] = stats
        
        return jsonify(result)
        
    except Exception as e:
        logger.exception("Error in batch classification")
        return jsonify({'success': False, 'error': str(e)})

@main.route('/api/classification/update/<int:email_id>', methods=['PUT'])
@login_required
def update_classification(email_id):
    try:
        data = request.get_json()
        category_name = data.get('category', '')
        
        if not category_name:
            return jsonify({'success': False, 'error': 'Category is required'})
        
        # Import models and services inside the route to avoid circular imports
        from app.models.email import Email, EmailClassification, EmailCategory
        from app.services.email_classifier import update_classification_from_user_correction, get_classification_stats
        
        # Get the email
        email = Email.query.get_or_404(email_id)
        
        # Check if email belongs to current user
        if email.user_id != current_user.id:
            return jsonify({'success': False, 'error': 'Unauthorized'}), 403
        
        # Get the category - handle both lowercase and title case
        category = EmailCategory.query.filter_by(user_id=current_user.id, name=category_name.title()).first()
        if not category:
            # Try lowercase
            category = EmailCategory.query.filter_by(user_id=current_user.id, name=category_name).first()
        
        if not category:
            # Create the category if it doesn't exist
            logger.info(f"Creating new category: {category_name}")
            category = EmailCategory(
                user_id=current_user.id,
                name=category_name.title(),
                color="#6B7280",  # Default gray color
                description=f"User created category: {category_name.title()}"
            )
            db.session.add(category)
            db.session.commit()
        
        # Update the classification
        classification = update_classification_from_user_correction(email_id, category.id, current_user.id)
        
        if classification:
            # Get updated stats
            stats = get_classification_stats(current_user.id)
            return jsonify({
                'success': True,
                'classification': category.name,
                'counts': stats,
                'message': 'Classification updated successfully'
            })
        else:
            return jsonify({'success': False, 'error': 'Failed to update classification'})
            
    except Exception as e:
        logger.exception("Error updating classification")
        return jsonify({'success': False, 'error': str(e)})

@main.route('/api/classification/delete/<int:email_id>', methods=['DELETE'])
@login_required
def delete_classification(email_id):
    try:
        # Import models inside the route to avoid circular imports
        from app.models.email import Email, EmailClassification
        from app.services.email_classifier import get_classification_stats
        
        # Get the email
        email = Email.query.get_or_404(email_id)
        
        # Check if email belongs to current user
        if email.user_id != current_user.id:
            return jsonify({'success': False, 'error': 'Unauthorized'}), 403
        
        # Get the classification record
        classification_record = EmailClassification.query.filter_by(email_id=email_id).first()
        
        if classification_record:
            # Delete the classification
            db.session.delete(classification_record)
            db.session.commit()
            
            # Get updated stats
            stats = get_classification_stats(current_user.id)
            
            return jsonify({
                'success': True, 
                'counts': stats,
                'message': 'Classification deleted successfully'
            })
        else:
            return jsonify({'success': False, 'error': 'No classification found for this email'})
            
    except Exception as e:
        logger.exception("Error deleting classification")
        return jsonify({'success': False, 'error': str(e)})

# New route to mark an email as spam
@main.route('/api/email/<int:email_id>/mark-spam', methods=['POST'])
@login_required
def mark_email_as_spam(email_id):
    try:
        # Import models inside the route to avoid circular imports
        from app.models.email import Email, EmailClassification, EmailCategory
        from app.services.email_classifier import get_classification_stats
        
        # Get the email
        email = Email.query.get_or_404(email_id)
        
        # Check if email belongs to current user
        if email.user_id != current_user.id:
            return jsonify({'success': False, 'error': 'Unauthorized'}), 403
        
        # Get or create the spam category
        spam_category = EmailCategory.query.filter_by(user_id=current_user.id, name='Spam').first()
        if not spam_category:
            spam_category = EmailCategory(
                user_id=current_user.id,
                name='Spam',
                color="#9333EA",  # Purple color for spam
                description="Spam emails"
            )
            db.session.add(spam_category)
            db.session.commit()
        
        # Check if classification already exists
        existing_classification = EmailClassification.query.filter_by(email_id=email_id).first()
        
        if existing_classification:
            # Update existing classification
            existing_classification.category_id = spam_category.id
            existing_classification.confidence_score = 1.0  # Manual classification gets full confidence
            existing_classification.manual_override = True
            existing_classification.updated_at = datetime.utcnow()
            classification = existing_classification
        else:
            # Create new classification
            classification = EmailClassification(
                email_id=email_id,
                category_id=spam_category.id,
                confidence_score=1.0,  # Manual classification gets full confidence
                manual_override=True,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db.session.add(classification)
        
        db.session.commit()
        
        # Get updated stats
        stats = get_classification_stats(current_user.id)
        return jsonify({
            'success': True,
            'counts': stats,
            'message': 'Email marked as spam'
        })
            
    except Exception as e:
        logger.exception("Error marking email as spam")
        return jsonify({'success': False, 'error': str(e)})
    

# Debug route to check classification status
@main.route('/debug/classifications')
@login_required
def debug_classifications():
    try:
        from app.models.email import Email, EmailClassification, EmailCategory
        from app.services.email_classifier import ensure_default_categories_exist
        
        # Ensure categories exist
        ensure_default_categories_exist(current_user.id)
        
        # Get all data
        emails = Email.query.filter_by(user_id=current_user.id).all()
        classifications = EmailClassification.query.all()
        categories = EmailCategory.query.filter_by(user_id=current_user.id).all()
        
        debug_info = {
            'total_emails': len(emails),
            'total_classifications': len(classifications),
            'total_categories': len(categories),
            'categories': [{'id': c.id, 'name': c.name} for c in categories],
            'unclassified_emails': []
        }
        
        # Find unclassified emails
        for email in emails:
            classification = EmailClassification.query.filter_by(email_id=email.id).first()
            if not classification:
                debug_info['unclassified_emails'].append({
                    'id': email.id,
                    'subject': email.subject,
                    'sender': email.sender
                })
        
        return jsonify(debug_info)
        
    except Exception as e:
        return jsonify({'error': str(e)})
@main.route('/followups')
@login_required
def followups():
    """Display follow-ups page with India timezone support"""
    try:
        # Import models inside the route to avoid circular imports
        from app.models.follow_up import FollowUp
        from app.models.email import Email
        from app.services.follow_up_service import FollowUpService
        
        # Get follow-up statistics
        stats = FollowUpService.get_follow_up_stats(current_user.id)
        
        # Query for follow-ups for the current user
        follow_ups = FollowUp.query.filter_by(user_id=current_user.id).order_by(FollowUp.scheduled_at.desc()).limit(50).all()
        
        # Convert times to India timezone for display
        india_tz = pytz.timezone('Asia/Kolkata')
        for fu in follow_ups:
            if fu.scheduled_at:
                # Convert UTC to India time
                if fu.scheduled_at.tzinfo is None:
                    fu.scheduled_at = pytz.utc.localize(fu.scheduled_at)
                fu.scheduled_at_local = fu.scheduled_at.astimezone(india_tz)
            
            if fu.sent_at:
                # Convert UTC to India time
                if fu.sent_at.tzinfo is None:
                    fu.sent_at = pytz.utc.localize(fu.sent_at)
                fu.sent_at_local = fu.sent_at.astimezone(india_tz)
        
        # Get follow-up rules for the current user
        rules = FollowUpService.get_rules_for_user(current_user.id)
        
        # Get follow-up logs for the current user with proper error handling
        try:
            logs = FollowUpService.get_follow_up_logs(current_user.id, limit=20)
        except Exception as e:
            logger.error(f"Error getting follow-up logs: {str(e)}")
            logs = []
        
        # Get recent emails for the dropdown
        recent_emails = Email.query.filter_by(user_id=current_user.id).order_by(Email.received_at.desc()).limit(20).all()
        
        # Get current time in India for display
        now_india = datetime.now(pytz.utc).astimezone(india_tz)

        return render_template(
            'dashboard/followups.html',
            followups=follow_ups,
            rules=rules,
            logs=logs,
            stats=stats,
            recent_emails=recent_emails,
            now=now_india,
            timezone='Asia/Kolkata'
        )

    except Exception as e:
        logger.exception("Error loading follow-ups")
        flash(f"Error loading follow-ups: {str(e)}", "error")

        # Default stats for error case
        stats = {
            "active_rules": 0,
            "pending_follow_ups": 0,
            "sent_follow_ups": 0,
            "responses_received": 0,
            "total_sent": 0,
            "upcoming": 0
        }

        return render_template(
            'dashboard/followups.html',
            followups=[],
            rules=[],
            logs=[],
            stats=stats,
            recent_emails=[],
            now=datetime.now(pytz.utc).astimezone(pytz.timezone('Asia/Kolkata')),
            timezone='Asia/Kolkata'
        )

@main.route('/follow-up-rules')
@login_required
def follow_up_rules():
    """Display the follow-up rules management page."""
    try:
        # Import models inside the route to avoid circular imports
        from app.services.follow_up_service import FollowUpService
        
        # Get follow-up rules for the current user
        rules = FollowUpService.get_rules_for_user(current_user.id)
        
        # Get follow-up statistics
        stats = FollowUpService.get_follow_up_stats(current_user.id)
        
        return render_template(
            'dashboard/followups.html',
            rules=rules,
            stats=stats
        )

    except Exception as e:
        logger.exception("Error loading follow-up rules")
        flash(f"Error loading follow-up rules: {str(e)}", "error")
        return render_template(
            'dashboard/followups.html',
            rules=[],
            stats={}
        )

@main.route('/api/follow-up/create-rule', methods=['POST'])
@login_required
def create_follow_up_rule():
    """API endpoint to create a new follow-up rule."""
    try:
        # Get form data
        rule_data = request.get_json()
        
        logger.info(f"Received rule data: {rule_data}")
        
        # Validate required fields
        if not rule_data.get('name'):
            return jsonify({'success': False, 'error': 'Rule name is required'})
        
        if not rule_data.get('user_id'):
            rule_data['user_id'] = current_user.id
        
        # Import the FollowUpService
        from app.services.follow_up_service import FollowUpService
        
        # Create the rule
        rule = FollowUpService.create_rule(rule_data)
        
        if not rule:
            return jsonify({'success': False, 'error': 'Failed to create rule - service returned None'})
        
        return jsonify({
            'success': True, 
            'rule': rule.to_dict()
        })
            
    except Exception as e:
        logger.exception("Error creating follow-up rule")
        return jsonify({'success': False, 'error': f'Internal server error: {str(e)}'})

@main.route('/api/follow-up/update-rule/<int:rule_id>', methods=['PUT'])
@login_required
def update_follow_up_rule(rule_id):
    """API endpoint to update an existing follow-up rule."""
    try:
        # Get form data
        rule_data = request.get_json()
        
        # Import the FollowUpService
        from app.services.follow_up_service import FollowUpService
        
        # Update the rule
        rule = FollowUpService.update_rule(rule_id, rule_data)
        
        if not rule:
            return jsonify({'success': False, 'error': 'Failed to update rule'})
        
        return jsonify({
            'success': True, 
            'rule': rule.to_dict()
        })
            
    except Exception as e:
        logger.exception("Error updating follow-up rule")
        return jsonify({'success': False, 'error': str(e)})

@main.route('/api/follow-up/delete-rule/<int:rule_id>', methods=['DELETE'])
@login_required
def delete_follow_up_rule(rule_id):
    """API endpoint to delete a follow-up rule."""
    try:
        # Import the FollowUpService
        from app.services.follow_up_service import FollowUpService
        
        # Delete the rule
        success = FollowUpService.delete_rule(rule_id, current_user.id)
        
        if not success:
            return jsonify({'success': False, 'error': 'Failed to delete rule'})
        
        return jsonify({
            'success': True, 
            'message': 'Rule deleted successfully'
        })
            
    except Exception as e:
        logger.exception("Error deleting follow-up rule")
        return jsonify({'success': False, 'error': str(e)})

@main.route('/api/follow-up/toggle-rule/<int:rule_id>', methods=['POST'])
@login_required
def toggle_follow_up_rule(rule_id):
    """API endpoint to toggle a follow-up rule's active status."""
    try:
        # Import the FollowUpService
        from app.services.follow_up_service import FollowUpService
        
        # Toggle the rule
        rule = FollowUpService.toggle_rule(rule_id, current_user.id)
        
        if not rule:
            return jsonify({'success': False, 'error': 'Failed to toggle rule'})
        
        return jsonify({
            'success': True, 
            'rule': rule.to_dict()
        })
            
    except Exception as e:
        logger.exception("Error toggling follow-up rule")
        return jsonify({'success': False, 'error': str(e)})

@main.route('/api/follow-up/duplicate-rule/<int:rule_id>', methods=['POST'])
@login_required
def duplicate_follow_up_rule(rule_id):
    """API endpoint to duplicate a follow-up rule."""
    try:
        # Import the FollowUpService
        from app.services.follow_up_service import FollowUpService
        
        # Duplicate the rule
        rule = FollowUpService.duplicate_rule(rule_id, current_user.id)
        
        if not rule:
            return jsonify({'success': False, 'error': 'Failed to duplicate rule'})
        
        return jsonify({
            'success': True, 
            'rule': rule.to_dict()
        })
            
    except Exception as e:
        logger.exception("Error duplicating follow-up rule")
        return jsonify({'success': False, 'error': str(e)})

@main.route('/api/follow-up/rule/<int:rule_id>', methods=['GET'])
@login_required
def get_follow_up_rule(rule_id):
    """API endpoint to get a specific follow-up rule."""
    try:
        # Import the FollowUpService
        from app.services.follow_up_service import FollowUpService
        
        # Get the rule
        rule = FollowUpService.get_rule_by_id(rule_id, current_user.id)
        
        if not rule:
            return jsonify({'success': False, 'error': 'Rule not found'})
        
        return jsonify({
            'success': True, 
            'rule': rule.to_dict()
        })
            
    except Exception as e:
        logger.exception("Error getting follow-up rule")
        return jsonify({'success': False, 'error': str(e)})

@main.route('/api/follow-up/logs', methods=['GET'])
@login_required
def get_follow_up_logs():
    """API endpoint to get follow-up logs."""
    try:
        # Get query parameters
        rule_id = request.args.get('rule_id', type=int)
        limit = request.args.get('limit', 50, type=int)
        
        # Import the FollowUpService
        from app.services.follow_up_service import FollowUpService
        
        # Get the logs
        logs = FollowUpService.get_follow_up_logs(current_user.id, rule_id, limit)
        
        return jsonify({
            'success': True, 
            'logs': [log.to_dict() for log in logs]
        })
            
    except Exception as e:
        logger.exception("Error getting follow-up logs")
        return jsonify({'success': False, 'error': str(e)})

@main.route('/api/follow-up/test/<int:rule_id>', methods=['POST'])
@login_required
def test_follow_up_rule(rule_id):
    """API endpoint to test a follow-up rule."""
    try:
        # Get form data
        test_email = request.get_json().get('test_email')
        
        if not test_email:
            return jsonify({'success': False, 'error': 'Test email is required'})
        
        # Import the FollowUpService
        from app.services.follow_up_service import FollowUpService
        
        # Test the rule
        success = FollowUpService.test_rule(rule_id, current_user.id, test_email)
        
        if not success:
            return jsonify({'success': False, 'error': 'Failed to send test email'})
        
        return jsonify({
            'success': True, 
            'message': 'Test email sent successfully'
        })
            
    except Exception as e:
        logger.exception("Error testing follow-up rule")
        return jsonify({'success': False, 'error': str(e)})

@main.route('/api/follow-up/cancel/<int:email_id>', methods=['POST'])
@login_required
def cancel_follow_ups_for_email(email_id):
    """API endpoint to cancel all future follow-ups for an email."""
    try:
        # Import the FollowUpService
        from app.services.follow_up_service import FollowUpService
        
        # Cancel the follow-ups
        count = FollowUpService.cancel_future_follow_ups(email_id, current_user.id)
        
        return jsonify({
            'success': True, 
            'message': f'Cancelled {count} follow-up(s)'
        })
            
    except Exception as e:
        logger.exception("Error cancelling follow-ups")
        return jsonify({'success': False, 'error': str(e)})

@main.route('/api/follow-up/export-rules', methods=['GET'])
@login_required
def export_follow_up_rules():
    """API endpoint to export follow-up rules as CSV."""
    try:
        # Import the FollowUpService
        from app.services.follow_up_service import FollowUpService
        
        # Export the rules
        csv_content = FollowUpService.export_rules(current_user.id)
        
        if not csv_content:
            return jsonify({'success': False, 'error': 'Failed to export rules'})
        
        # Create a response with the CSV content
        response = make_response(csv_content)
        response.headers['Content-Disposition'] = 'attachment; filename=follow_up_rules.csv'
        response.headers['Content-type'] = 'text/csv'
        
        return response
            
    except Exception as e:
        logger.exception("Error exporting follow-up rules")
        return jsonify({'success': False, 'error': str(e)})

@main.route('/api/follow-up/export-logs', methods=['GET'])
@login_required
def export_follow_up_logs():
    """API endpoint to export follow-up logs as CSV."""
    try:
        # Import the FollowUpService
        from app.services.follow_up_service import FollowUpService
        
        # Export the logs
        csv_content = FollowUpService.export_logs(current_user.id)
        
        if not csv_content:
            return jsonify({'success': False, 'error': 'Failed to export logs'})
        
        # Create a response with the CSV content
        response = make_response(csv_content)
        response.headers['Content-Disposition'] = 'attachment; filename=follow_up_logs.csv'
        response.headers['Content-type'] = 'text/csv'
        
        return response
            
    except Exception as e:
        logger.exception("Error exporting follow-up logs")
        return jsonify({'success': False, 'error': str(e)})

@main.route('/api/follow-up/pause-all', methods=['POST'])
@login_required
def pause_all_follow_ups():
    """API endpoint to pause all follow-up rules."""
    try:
        # Import the FollowUpService
        from app.services.follow_up_service import FollowUpService
        
        # Pause all follow-ups
        count = FollowUpService.pause_all_follow_ups(current_user.id)
        
        return jsonify({
            'success': True, 
            'message': f'Paused {count} rule(s)'
        })
            
    except Exception as e:
        logger.exception("Error pausing all follow-ups")
        return jsonify({'success': False, 'error': str(e)})

@main.route('/api/follow-up/resume-all', methods=['POST'])
@login_required
def resume_all_follow_ups():
    """API endpoint to resume all follow-up rules."""
    try:
        # Import the FollowUpService
        from app.services.follow_up_service import FollowUpService
        
        # Resume all follow-ups
        count = FollowUpService.resume_all_follow_ups(current_user.id)
        
        return jsonify({
            'success': True, 
            'message': f'Resumed {count} rule(s)'
        })
            
    except Exception as e:
        logger.exception("Error resuming all follow-ups")
        return jsonify({'success': False, 'error': str(e)})

# CRITICAL FIX: Updated schedule_followup with India timezone support
@main.route('/email/schedule-followup', methods=['POST'])
@login_required
def schedule_followup():
    """Schedule follow-up with India timezone support"""
    try:
        # Get form data
        recipient_emails = request.form.get('recipient_emails')
        content = request.form.get('content')
        scheduled_date_str = request.form.get('scheduled_date')
        
        logger.info(f"Schedule follow-up request - User: {current_user.id}")
        logger.info(f"Received data: recipient_emails={recipient_emails}, content_length={len(content) if content else 0}, scheduled_date={scheduled_date_str}")
        
        # Validate inputs
        if not recipient_emails or not recipient_emails.strip():
            logger.error("Recipient emails is null or empty")
            return jsonify({'success': False, 'error': 'Recipient emails are required'})
        
        if not all([recipient_emails, content, scheduled_date_str]):
            logger.error("Missing required fields")
            return jsonify({'success': False, 'error': 'Missing required fields'})
        
        # FIXED: Proper India timezone handling
        try:
            # Parse the datetime from the form (assumes it's in India time)
            scheduled_date = datetime.fromisoformat(scheduled_date_str)
            
            # CRITICAL FIX: Always assume India timezone for input
            india_tz = pytz.timezone('Asia/Kolkata')
            
            # Localize to India timezone if naive
            if scheduled_date.tzinfo is None:
                scheduled_date = india_tz.localize(scheduled_date)
            else:
                # Convert to India timezone if it has a different timezone
                scheduled_date = scheduled_date.astimezone(india_tz)
            
            # Convert to UTC for storage
            scheduled_date_utc = scheduled_date.astimezone(pytz.UTC)
            
            # Log both times for debugging
            logger.info(f"India time: {scheduled_date.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            logger.info(f"UTC time: {scheduled_date_utc.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            
        except ValueError as e:
            logger.error(f"Invalid date format: {str(e)}")
            return jsonify({'success': False, 'error': 'Invalid date format. Please use YYYY-MM-DD HH:MM:SS format'})
        
        # Import the FollowUpService
        from app.services.follow_up_service import FollowUpService
        
        # Create the follow-up in the database
        followup = FollowUpService.schedule_follow_up_for_recipients(
            recipient_emails=recipient_emails,
            scheduled_at=scheduled_date_utc,
            content=content,
            user_id=current_user.id
        )
        
        if not followup:
            logger.error("Failed to create follow-up")
            return jsonify({'success': False, 'error': 'Failed to create follow-up'})
        
        logger.info(f"Successfully created follow-up {followup.id} scheduled for {scheduled_date_utc}")
        
        # CRITICAL FIX: Create a one-time job in the scheduler
        from app.utils.scheduler import automation_scheduler
        
        # Create a unique job ID
        job_id = f"follow_up_direct_{followup.id}"
        
        # Schedule the job using the scheduler's method
        automation_scheduler.scheduler.add_job(
            func=send_scheduled_followup,
            trigger='date',
            run_date=scheduled_date_utc,
            args=[followup.id],
            id=job_id,
            replace_existing=True,
            misfire_grace_time=300  # 5 minutes grace period
        )
        
        logger.info(f"Scheduled one-time job {job_id} for {scheduled_date_utc}")
        
        # Return the follow-up info with local time for display
        return jsonify({
            'success': True, 
            'followup': {
                'id': followup.id,
                'email_id': followup.email_id,
                'content': followup.content,
                'thread_id': followup.thread_id,
                'recipient_email': followup.recipient_email,
                'scheduled_date': scheduled_date.strftime('%Y-%m-%d %H:%M:%S'),  # India time for display
                'scheduled_date_utc': followup.scheduled_at.isoformat(),  # UTC time for storage
                'status': followup.status
            }
        })
            
    except Exception as e:
        logger.exception("Unexpected error scheduling follow-up")
        return jsonify({'success': False, 'error': 'Internal server error'})

# CRITICAL FIX: Function to handle scheduled jobs
def send_scheduled_followup(followup_id):
    """Function to be called by the scheduler to send a specific follow-up"""
    try:
        from app import create_app
        from app.models.follow_up import FollowUp
        from app.services.follow_up_service import FollowUpService
        
        app = create_app()
        with app.app_context():
            # Get the follow-up
            followup = FollowUp.query.get(followup_id)
            if not followup:
                logger.error(f"Follow-up {followup_id} not found")
                return
            
            # Check if it's still pending
            if followup.status != 'pending':
                logger.info(f"Follow-up {followup_id} is no longer pending (status: {followup.status})")
                return
            
            logger.info(f"🚀 Sending scheduled follow-up {followup_id} to {followup.recipient_email}")
            
            # Send the follow-up
            success = FollowUpService.send_follow_up(followup)
            
            if success:
                followup.status = 'sent'
                followup.sent_at = datetime.now(pytz.UTC)
                db.session.commit()
                
                # Convert to India time for logging
                india_tz = pytz.timezone('Asia/Kolkata')
                sent_time_india = followup.sent_at.astimezone(india_tz)
                
                logger.info(f"✅ Successfully sent scheduled follow-up {followup_id} at {sent_time_india.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            else:
                followup.status = 'failed'
                db.session.commit()
                logger.error(f"❌ Failed to send scheduled follow-up {followup_id}")
                
    except Exception as e:
        logger.exception(f"❌ Error sending scheduled follow-up {followup_id}")

@main.route('/email/send-followup/<int:followup_id>', methods=['POST'])
@login_required
def send_followup(followup_id):
    """Manually send a follow-up"""
    try:
        # Import models and services inside the route to avoid circular imports
        from app.models.follow_up import FollowUp
        from app.services.follow_up_service import FollowUpService
        
        # Get the follow-up
        followup = FollowUp.query.get_or_404(followup_id)
        
        # Check if follow-up belongs to current user
        if followup.user_id != current_user.id:
            return jsonify({'success': False, 'error': 'Unauthorized'}), 403
        
        # Check if already sent
        if followup.status in ['sent', 'completed']:
            return jsonify({'success': False, 'error': 'Follow-up already sent'})
        
        logger.info(f"Manually sending follow-up {followup_id} to {followup.recipient_email}")
        
        # Use the service to send the follow-up
        success = FollowUpService.send_follow_up(followup)
        
        if success:
            # Update follow-up status with proper commit
            followup.status = 'sent'
            followup.sent_at = datetime.utcnow()
            db.session.commit()
            
            # Convert to India time for response
            india_tz = pytz.timezone('Asia/Kolkata')
            sent_time_india = followup.sent_at.astimezone(india_tz)
            
            logger.info(f"✅ Manually sent follow-up {followup_id} at {sent_time_india.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            
            return jsonify({
                'success': True, 
                'message': 'Follow-up sent successfully',
                'sent_at': sent_time_india.strftime('%Y-%m-%d %H:%M:%S')
            })
        else:
            # Update status to failed
            followup.status = 'failed'
            db.session.commit()
            
            logger.error(f"❌ Failed to send follow-up {followup_id}")
            
            return jsonify({'success': False, 'error': 'Failed to send follow-up'})
            
    except Exception as e:
        logger.exception("Error sending follow-up")
        return jsonify({'success': False, 'error': str(e)})

@main.route('/email/followup/<int:followup_id>', methods=['GET'])
@login_required
def get_followup(followup_id):
    """Get follow-up details with India timezone support"""
    try:
        # Import models inside the route to avoid circular imports
        from app.models.follow_up import FollowUp
        from app.models.email import Email
        
        # Get the follow-up
        followup = FollowUp.query.get_or_404(followup_id)
        
        # Check if follow-up belongs to current user
        if followup.user_id != current_user.id:
            return jsonify({'success': False, 'error': 'Unauthorized'}), 403
        
        # Get email details if available
        email = None
        email_subject = 'Unknown'
        email_sender = 'Unknown'
        
        if followup.email_id:
            email = Email.query.get(followup.email_id)
            if email:
                email_subject = email.subject
                email_sender = email.sender
        
        # Convert times to India timezone
        india_tz = pytz.timezone('Asia/Kolkata')
        
        scheduled_at_local = None
        if followup.scheduled_at:
            if followup.scheduled_at.tzinfo is None:
                followup.scheduled_at = pytz.utc.localize(followup.scheduled_at)
            scheduled_at_local = followup.scheduled_at.astimezone(india_tz)
        
        return jsonify({
            'success': True,
            'followup': {
                'id': followup.id,
                'email_id': followup.email_id,
                'email_subject': email_subject,
                'email_sender': email_sender,
                'recipient_email': followup.recipient_email,
                'content': followup.content,
                'scheduled_date': scheduled_at_local.strftime('%Y-%m-%d %H:%M:%S') if scheduled_at_local else None,
                'scheduled_at': followup.scheduled_at.isoformat(),
                'status': followup.status,
                'thread_id': followup.thread_id
            }
        })
    except Exception as e:
        logger.exception("Error getting follow-up")
        return jsonify({'success': False, 'error': str(e)})

@main.route('/email/delete-followup/<int:followup_id>', methods=['DELETE'])
@login_required
def delete_followup(followup_id):
    """Delete a follow-up"""
    try:
        # Import models inside the route to avoid circular imports
        from app.models.follow_up import FollowUp
        
        # Get the follow-up
        followup = FollowUp.query.get_or_404(followup_id)
        
        # Check if follow-up belongs to current user
        if followup.user_id != current_user.id:
            return jsonify({'success': False, 'error': 'Unauthorized'}), 403
        
        # Delete the follow-up
        db.session.delete(followup)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Follow-up deleted successfully'})
    except Exception as e:
        logger.exception("Error deleting follow-up")
        return jsonify({'success': False, 'error': str(e)})

@main.route('/email/check-followups', methods=['POST'])
@login_required
def check_followups():
    """Manual endpoint to check and send pending follow-ups."""
    try:
        from app.services.follow_up_service import FollowUpService
        
        logger.info(f"🔄 Manual follow-up check triggered by user {current_user.id}")
        
        # Check and send follow-ups
        result = FollowUpService.check_and_send_follow_ups()
        
        logger.info(f"✅ Manual follow-up check completed with result: {result}")
        
        return jsonify({
            'success': True, 
            'message': 'Follow-ups checked and sent if due',
            'result': result
        })
    except Exception as e:
        logger.exception("Error checking follow-ups")
        return jsonify({'success': False, 'error': str(e)})

@main.route('/email/test-send-followup/<int:followup_id>', methods=['POST'])
@login_required
def test_send_followup(followup_id):
    """Test endpoint to force send a specific follow-up regardless of scheduled time."""
    try:
        from app.models.follow_up import FollowUp
        from app.services.follow_up_service import FollowUpService
        
        # Get the follow-up
        followup = FollowUp.query.get_or_404(followup_id)
        
        # Check if follow-up belongs to current user
        if followup.user_id != current_user.id:
            return jsonify({'success': False, 'error': 'Unauthorized'}), 403
        
        logger.info(f"🧪 Test sending follow-up {followup_id} to {followup.recipient_email}")
        
        # Force send the follow-up
        success = FollowUpService.send_follow_up(followup)
        
        if success:
            # Update follow-up status with proper commit
            followup.status = 'sent'
            followup.sent_at = datetime.utcnow()
            db.session.commit()
            
            # Convert to India time for response
            india_tz = pytz.timezone('Asia/Kolkata')
            sent_time_india = followup.sent_at.astimezone(india_tz)
            
            logger.info(f"✅ Test sent follow-up {followup_id} at {sent_time_india.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            
            return jsonify({
                'success': True, 
                'message': 'Follow-up sent successfully',
                'sent_at': sent_time_india.strftime('%Y-%m-%d %H:%M:%S')
            })
        else:
            # Update status to failed
            followup.status = 'failed'
            db.session.commit()
            
            logger.error(f"❌ Failed to test send follow-up {followup_id}")
            
            return jsonify({'success': False, 'error': 'Failed to send follow-up'})
            
    except Exception as e:
        logger.exception("Error sending test follow-up")
        return jsonify({'success': False, 'error': str(e)})

@main.route('/email/followup-stats', methods=['GET'])
@login_required
def get_followup_stats():
    """Get follow-up statistics for the current user."""
    try:
        from app.services.follow_up_service import FollowUpService
        
        stats = FollowUpService.get_follow_up_stats(current_user.id)
        
        return jsonify({
            'success': True,
            'stats': stats
        })
    except Exception as e:
        logger.exception("Error getting follow-up stats")
        return jsonify({'success': False, 'error': str(e)})

# CRITICAL FIX: Debug endpoints for troubleshooting
@main.route('/debug/scheduler')
@login_required
def debug_scheduler():
    """Debug endpoint to check scheduler status and jobs"""
    try:
        from app.utils.scheduler import automation_scheduler
        from datetime import datetime, timezone
        
        jobs = automation_scheduler.get_jobs()
        job_info = []
        
        for job in jobs:
            job_info.append({
                'id': job.id,
                'name': job.name,
                'next_run_time': job.next_run_time.isoformat() if job.next_run_time else None,
                'trigger': str(job.trigger),
                'pending': job.pending
            })
        
        # Get current time in India
        india_tz = pytz.timezone('Asia/Kolkata')
        current_time_india = datetime.now(timezone.utc).astimezone(india_tz)
        
        return {
            'scheduler_running': automation_scheduler.scheduler.running,
            'jobs': job_info,
            'last_follow_up_count': automation_scheduler.last_follow_up_count,
            'last_run_times': automation_scheduler.last_run_times,
            'current_time_utc': datetime.now(timezone.utc).isoformat(),
            'current_time_india': current_time_india.strftime('%Y-%m-%d %H:%M:%S %Z')
        }
    except Exception as e:
        logger.exception("Error getting scheduler debug info")
        return {'error': str(e)}

@main.route('/debug/followups')
@login_required
def debug_followups():
    """Debug endpoint to check follow-up status with India timezone"""
    try:
        from app.models.follow_up import FollowUp
        from datetime import datetime, timezone
        
        followups = FollowUp.query.filter_by(user_id=current_user.id).all()
        result = []
        
        india_tz = pytz.timezone('Asia/Kolkata')
        now = datetime.now(timezone.utc)
        now_india = now.astimezone(india_tz)
        
        for fu in followups:
            scheduled_at_india = None
            if fu.scheduled_at:
                if fu.scheduled_at.tzinfo is None:
                    fu.scheduled_at = pytz.utc.localize(fu.scheduled_at)
                scheduled_at_india = fu.scheduled_at.astimezone(india_tz)
            
            sent_at_india = None
            if fu.sent_at:
                if fu.sent_at.tzinfo is None:
                    fu.sent_at = pytz.utc.localize(fu.sent_at)
                sent_at_india = fu.sent_at.astimezone(india_tz)
            
            result.append({
                'id': fu.id,
                'status': fu.status,
                'scheduled_at_utc': fu.scheduled_at.isoformat() if fu.scheduled_at else None,
                'scheduled_at_india': scheduled_at_india.strftime('%Y-%m-%d %H:%M:%S %Z') if scheduled_at_india else None,
                'sent_at_utc': fu.sent_at.isoformat() if fu.sent_at else None,
                'sent_at_india': sent_at_india.strftime('%Y-%m-%d %H:%M:%S %Z') if sent_at_india else None,
                'recipient_email': fu.recipient_email,
                'is_past_due': fu.scheduled_at < now if fu.scheduled_at else False,
                'minutes_overdue': (now - fu.scheduled_at).total_seconds() / 60 if fu.scheduled_at and fu.scheduled_at < now else None,
                'minutes_until_due': (fu.scheduled_at - now).total_seconds() / 60 if fu.scheduled_at and fu.scheduled_at > now else None
            })
        
        return {
            'followups': result,
            'current_time_utc': now.isoformat(),
            'current_time_india': now_india.strftime('%Y-%m-%d %H:%M:%S %Z')
        }
    except Exception as e:
        logger.exception("Error getting follow-up debug info")
        return {'error': str(e)}

@main.route('/debug/run-followup-check')
@login_required
def debug_run_followup_check():
    """Debug endpoint to manually trigger follow-up check"""
    try:
        from app.utils.scheduler import automation_scheduler
        from app import create_app
        
        app = create_app()
        try:
            logger.info("🔄 Manually triggering follow-up check via debug endpoint")
            automation_scheduler.run_follow_up_check(app)
            return {'status': 'success', 'message': 'Follow-up check executed'}
        except Exception as e:
            logger.error(f"Error in manual follow-up check: {str(e)}")
            return {'status': 'error', 'message': str(e)}
    except Exception as e:
        logger.exception("Error running debug follow-up check")
        return {'status': 'error', 'message': str(e)}

@main.route('/debug/followup-comprehensive')
@login_required
def debug_followup_comprehensive():
    """Comprehensive debug endpoint for follow-up issues"""
    try:
        from app.models.follow_up import FollowUp
        from app.utils.scheduler import automation_scheduler
        from datetime import datetime, timezone, timedelta
        
        # Check scheduler status
        scheduler_running = automation_scheduler.scheduler.running
        jobs = automation_scheduler.get_jobs()
        
        # Get follow-up jobs
        followup_jobs = [job for job in jobs if 'follow_up' in job.id]
        
        # Get pending follow-ups
        now = datetime.now(timezone.utc)
        pending_followups = FollowUp.query.filter_by(user_id=current_user.id, status='pending').all()
        
        # Get past-due follow-ups
        past_due_followups = FollowUp.query.filter(
            FollowUp.user_id == current_user.id,
            FollowUp.status == 'pending',
            FollowUp.scheduled_at <= now
        ).all()
        
        # Convert times to India timezone
        india_tz = pytz.timezone('Asia/Kolkata')
        now_india = now.astimezone(india_tz)
        
        result = {
            'scheduler_running': scheduler_running,
            'total_jobs': len(jobs),
            'followup_jobs': len(followup_jobs),
            'current_time_utc': now.isoformat(),
            'current_time_india': now_india.strftime('%Y-%m-%d %H:%M:%S %Z'),
            'pending_followups': len(pending_followups),
            'past_due_followups': len(past_due_followups),
            'followup_job_details': []
        }
        
        # Add details for each follow-up job
        for job in followup_jobs:
            next_run_india = None
            if job.next_run_time:
                next_run_india = job.next_run_time.astimezone(india_tz).strftime('%Y-%m-%d %H:%M:%S %Z')
            
            result['followup_job_details'].append({
                'id': job.id,
                'name': job.name,
                'next_run_time_utc': job.next_run_time.isoformat() if job.next_run_time else None,
                'next_run_time_india': next_run_india,
                'trigger': str(job.trigger)
            })
        
        # Add details for past-due follow-ups
        result['past_due_details'] = []
        for fu in past_due_followups:
            scheduled_at_india = None
            if fu.scheduled_at:
                if fu.scheduled_at.tzinfo is None:
                    fu.scheduled_at = pytz.utc.localize(fu.scheduled_at)
                scheduled_at_india = fu.scheduled_at.astimezone(india_tz)
            
            result['past_due_details'].append({
                'id': fu.id,
                'recipient_email': fu.recipient_email,
                'scheduled_at_utc': fu.scheduled_at.isoformat(),
                'scheduled_at_india': scheduled_at_india.strftime('%Y-%m-%d %H:%M:%S %Z') if scheduled_at_india else None,
                'minutes_overdue': (now - fu.scheduled_at).total_seconds() / 60
            })
        
        return jsonify(result)
    except Exception as e:
        logger.exception("Error in comprehensive follow-up debug")
        return jsonify({'error': str(e)})

# In main.py, keep these routes

@main.route('/api/reset-email-sync', methods=['POST'])
@login_required
def reset_email_sync():
    """Reset the email sync time for the current user."""
    try:
        current_user.last_email_sync_time = None
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@main.route('/api/update-preferences', methods=['POST'])
@login_required
def update_preferences():
    """Update user preferences."""
    try:
        data = request.get_json()
        current_user.theme_preference = data.get('theme', 'light')
        
        # You can add more preference fields here as needed
        if 'language' in data:
            current_user.language = data.get('language')
        if 'timezone' in data:
            current_user.timezone = data.get('timezone')
            
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@main.route('/api/process-classifications', methods=['POST'])
@login_required
def process_classifications():
    """Manually trigger email classification for all unclassified emails."""
    try:
        count = process_new_emails_for_classification()
        return jsonify({'success': True, 'count': count, 'message': f'Processed {count} emails for classification'})
    except Exception as e:
        logger.exception("Error processing classifications")
        return jsonify({'success': False, 'error': str(e)})

@main.route('/api/process-auto-replies', methods=['POST'])
@login_required
def process_auto_replies_endpoint():
    """Manually trigger auto-reply processing."""
    try:
        # Import services inside the route to avoid circular imports
        from app.services.auto_reply_service import AutoReplyService
        
        AutoReplyService.process_auto_replies()
        return jsonify({'success': True, 'message': 'Auto-reply processing completed'})
    except Exception as e:
        logger.exception("Error processing auto-replies")
        return jsonify({'success': False, 'error': str(e)})

@main.route('/api/process-follow-ups', methods=['POST'])
@login_required
def process_follow_ups_endpoint():
    """Manually trigger follow-up processing."""
    try:
        # Import services inside the route to avoid circular imports
        from app.services.follow_up_service import FollowUpService
        
        FollowUpService.check_and_send_follow_ups()
        return jsonify({'success': True, 'message': 'Follow-up processing completed'})
    except Exception as e:
        logger.exception("Error processing follow-ups")
        return jsonify({'success': False, 'error': str(e)})

# Helper function
def process_new_emails_for_classification():
    """Process new emails and classify them."""
    try:
        # Import models and services inside the function to avoid circular imports
        from app.models.email import Email, EmailClassification
        from app.services.email_classifier import classify_email, store_email_classification
        
        # Get unclassified emails
        unclassified_emails = Email.query.outerjoin(EmailClassification).filter(
            EmailClassification.id.is_(None),
            Email.user_id == current_user.id
        ).all()
        
        for email in unclassified_emails:
            # Classify the email
            classification = classify_email(email.subject, email.snippet)
            
            # Store the classification
            store_email_classification(email.id, classification)
            
            # Update the email with classification
            email.category = classification
            db.session.commit()
            
        return len(unclassified_emails)
    except Exception as e:
        logger.exception("Error in email classification")
        return 0