# app/services/sent_emails_service.py

from app import db
import base64
from datetime import datetime
import logging
import re
from email.utils import parsedate_to_datetime
from sqlalchemy import or_
from flask import current_app

logger = logging.getLogger(__name__)

def sync_sent_emails(user_id=None, limit=50, min_sync_interval=3600):
    """
    Sync the last 'limit' sent emails from Gmail using the logged-in user
    Only sync if the last sync was more than min_sync_interval seconds ago
    """
    try:
        # Import models inside function to avoid circular imports
        from app.models.email import SentEmail
        from app.models.user import User
        from app.services.gmail_service import GmailService
        from flask_login import current_user
        
        # Get the current user if user_id is not provided
        if user_id is None:
            if not current_user.is_authenticated:
                logger.error("User not authenticated")
                return False
            user = current_user
        else:
            user = User.query.get(user_id)
            if not user:
                logger.error(f"User with ID {user_id} not found")
                return False
        
        # Check if we need to sync (rate limiting)
        last_sync = user.last_sent_email_sync or 0
        now = datetime.utcnow().timestamp()
        if now - last_sync < min_sync_interval:
            logger.info(f"Skipping sync, last sync was {int(now - last_sync)} seconds ago")
            return True
        
        # Initialize Gmail service
        gmail_service = GmailService(user)
        if not gmail_service.service:
            logger.error("Gmail service not available")
            return False
        
        # Query for sent messages
        results = gmail_service.service.users().messages().list(
            userId='me',
            labelIds=['SENT'],
            maxResults=limit
        ).execute()
        
        messages = results.get('messages', [])
        
        if not messages:
            logger.info("No sent messages found.")
            # Update last sync time even if no messages
            user.last_sent_email_sync = now
            db.session.commit()
            return True
        
        synced_count = 0
        
        # Get all existing gmail_ids in a single query
        existing_ids = set(
            email.gmail_id for email in SentEmail.query.filter_by(user_id=user.id)
            .filter(SentEmail.gmail_id.in_([msg['id'] for msg in messages]))
            .all()
        )
        
        # Batch process messages
        for message in messages:
            try:
                # Skip if we already have this email
                if message['id'] in existing_ids:
                    continue
                
                # Get only the metadata, not the full content
                msg = gmail_service.service.users().messages().get(
                    userId='me',
                    id=message['id'],
                    format='metadata',
                    metadataHeaders=['Date', 'To', 'Cc', 'Bcc', 'Subject']
                ).execute()
                
                # Extract headers
                headers = {}
                for header in msg['payload'].get('headers', []):
                    headers[header['name']] = header['value']
                
                # Parse the date safely
                date_str = headers.get('Date', '')
                try:
                    date = parsedate_to_datetime(date_str) if date_str else datetime.utcnow()
                except Exception as e:
                    logger.warning(f"Error parsing date '{date_str}': {str(e)}")
                    date = datetime.utcnow()
                
                # Extract recipients
                to_header = headers.get('To', '')
                cc_header = headers.get('Cc', '')
                bcc_header = headers.get('Bcc', '')
                
                # Combine all recipients
                all_recipients = []
                for recipient_header in [to_header, cc_header, bcc_header]:
                    if recipient_header:
                        # Parse email addresses from header
                        recipients = re.findall(r'[\w\.-]+@[\w\.-]+\.\w+', recipient_header)
                        all_recipients.extend(recipients)
                
                recipients_str = ', '.join(all_recipients) if all_recipients else to_header
                
                # Get snippet from message
                snippet = msg.get('snippet', '')
                
                # Create a new sent email record with minimal data
                sent_email = SentEmail(
                    user_id=user.id,
                    gmail_id=message['id'],
                    to=recipients_str,
                    subject=headers.get('Subject', '(No Subject)'),
                    snippet=snippet,
                    thread_id=msg.get('threadId', ''),
                    sent_at=date,
                    status='Sent'
                    # Note: We're not fetching body_text and body_html initially
                )
                db.session.add(sent_email)
                synced_count += 1
                
                # Commit in batches to avoid large transactions
                if synced_count % 10 == 0:
                    db.session.commit()
                    
            except Exception as e:
                logger.error(f"Error syncing sent email {message['id']}: {str(e)}")
                continue
        
        # Final commit
        db.session.commit()
        
        # Update last sync time
        user.last_sent_email_sync = now
        db.session.commit()
        
        logger.info(f"Synced {synced_count} new sent emails for user {user.id}")
        return True
        
    except Exception as e:
        logger.error(f"Error syncing sent emails: {str(e)}")
        db.session.rollback()
        return False

def get_sent_emails(user_id=None, limit=20, offset=0, status=None):
    """
    Get sent emails for the user, ordered by sent date (newest first)
    """
    try:
        # Import models inside function to avoid circular imports
        from app.models.email import SentEmail
        from flask_login import current_user
        
        # Get the current user if user_id is not provided
        if user_id is None:
            if not current_user.is_authenticated:
                return []
            user_id = current_user.id
        
        query = SentEmail.query.filter_by(user_id=user_id)
        
        # Filter by status if provided
        if status:
            query = query.filter_by(status=status)
        
        sent_emails = query.order_by(
            SentEmail.sent_at.desc()
        ).offset(offset).limit(limit).all()
        
        return sent_emails
    except Exception as e:
        logger.error(f"Error getting sent emails: {str(e)}")
        return []

def search_sent_emails(user_id=None, query="", limit=20, offset=0, status=None):
    """
    Search sent emails by query string
    """
    try:
        # Import models inside function to avoid circular imports
        from app.models.email import SentEmail
        from flask_login import current_user
        
        # Get the current user if user_id is not provided
        if user_id is None:
            if not current_user.is_authenticated:
                return []
            user_id = current_user.id
        
        db_query = SentEmail.query.filter_by(user_id=user_id)
        
        # Filter by status if provided
        if status:
            db_query = db_query.filter_by(status=status)
        
        if query:
            search_filter = or_(
                SentEmail.subject.contains(query), 
                SentEmail.to.contains(query),
                SentEmail.snippet.contains(query)
                # Note: Removed body_text from search for performance
            )
            db_query = db_query.filter(search_filter)
        
        sent_emails = db_query.order_by(SentEmail.sent_at.desc()).offset(offset).limit(limit).all()
        
        return sent_emails
    except Exception as e:
        logger.error(f"Error searching sent emails: {str(e)}")
        return []

def get_sent_email_by_id(email_id, user_id=None, fetch_body=False):
    """
    Get a specific sent email by ID
    Optionally fetch the body content if fetch_body is True
    """
    try:
        # Import models inside function to avoid circular imports
        from app.models.email import SentEmail
        from flask_login import current_user
        from app.services.gmail_service import GmailService
        
        # Get the current user if user_id is not provided
        if user_id is None:
            if not current_user.is_authenticated:
                return None
            user_id = current_user.id
            user = current_user
        else:
            from app.models.user import User
            user = User.query.get(user_id)
            if not user:
                return None
        
        sent_email = SentEmail.query.filter_by(id=email_id, user_id=user_id).first()
        
        if not sent_email:
            return None
            
        # If body content is requested and not available, fetch it from Gmail
        if fetch_body and not sent_email.body_text and not sent_email.body_html and sent_email.gmail_id:
            try:
                gmail_service = GmailService(user)
                if gmail_service.service:
                    msg = gmail_service.service.users().messages().get(
                        userId='me',
                        id=sent_email.gmail_id,
                        format='full'
                    ).execute()
                    
                    # Extract body content
                    body_text = ''
                    body_html = ''
                    
                    # Helper function to extract body from message parts
                    def extract_body(payload):
                        nonlocal body_text, body_html
                        
                        if 'parts' in payload:
                            # Multipart message
                            for part in payload['parts']:
                                if 'parts' in part:
                                    # Recursively handle nested parts
                                    extract_body(part)
                                else:
                                    mime_type = part.get('mimeType', '')
                                    data = part.get('body', {}).get('data', '')
                                    
                                    if data:
                                        try:
                                            content = base64.urlsafe_b64decode(data).decode('utf-8')
                                            
                                            if 'text/plain' in mime_type and not body_text:
                                                body_text = content
                                            elif 'text/html' in mime_type and not body_html:
                                                body_html = content
                                        except Exception as e:
                                            logger.error(f"Error decoding body part: {e}")
                        else:
                            # Single part message
                            mime_type = payload.get('mimeType', '')
                            data = payload.get('body', {}).get('data', '')
                            
                            if data:
                                try:
                                    content = base64.urlsafe_b64decode(data).decode('utf-8')
                                    
                                    if 'text/html' in mime_type:
                                        body_html = content
                                    else:
                                        body_text = content
                                except Exception as e:
                                    logger.error(f"Error decoding body: {e}")
                    
                    # Extract body content
                    extract_body(msg.get('payload', {}))
                    
                    # Update the email with body content
                    sent_email.body_text = body_text
                    sent_email.body_html = body_html
                    db.session.commit()
                    
            except Exception as e:
                logger.error(f"Error fetching email body: {str(e)}")
        
        return sent_email
    except Exception as e:
        logger.error(f"Error getting sent email by ID: {str(e)}")
        return None

def delete_sent_email(email_id, user_id=None):
    """
    Delete a sent email from the database
    """
    try:
        # Import models inside function to avoid circular imports
        from app.models.email import SentEmail
        from flask_login import current_user
        
        # Get the current user if user_id is not provided
        if user_id is None:
            if not current_user.is_authenticated:
                return False
            user_id = current_user.id
        
        sent_email = SentEmail.query.filter_by(id=email_id, user_id=user_id).first()
        if not sent_email:
            logger.warning(f"Sent email with ID {email_id} not found for user {user_id}")
            return False
        
        db.session.delete(sent_email)
        db.session.commit()
        
        logger.info(f"Deleted sent email with ID {email_id}")
        return True
    except Exception as e:
        logger.error(f"Error deleting sent email: {str(e)}")
        db.session.rollback()
        return False

def update_sent_email_status(email_id, status, user_id=None):
    """
    Update the status of a sent email
    """
    try:
        # Import models inside function to avoid circular imports
        from app.models.email import SentEmail
        from flask_login import current_user
        
        # Get the current user if user_id is not provided
        if user_id is None:
            if not current_user.is_authenticated:
                return False
            user_id = current_user.id
        
        sent_email = SentEmail.query.filter_by(id=email_id, user_id=user_id).first()
        if not sent_email:
            logger.warning(f"Sent email with ID {email_id} not found for user {user_id}")
            return False
        
        sent_email.status = status
        db.session.commit()
        
        logger.info(f"Updated status of sent email {email_id} to {status}")
        return True
    except Exception as e:
        logger.error(f"Error updating sent email status: {str(e)}")
        db.session.rollback()
        return False

def get_sent_emails_by_thread(thread_id, user_id=None):
    """
    Get all sent emails in a specific thread
    """
    try:
        # Import models inside function to avoid circular imports
        from app.models.email import SentEmail
        from flask_login import current_user
        
        # Get the current user if user_id is not provided
        if user_id is None:
            if not current_user.is_authenticated:
                return []
            user_id = current_user.id
        
        sent_emails = SentEmail.query.filter_by(
            thread_id=thread_id, 
            user_id=user_id
        ).order_by(SentEmail.sent_at.asc()).all()
        
        return sent_emails
    except Exception as e:
        logger.error(f"Error getting sent emails by thread: {str(e)}")
        return []

def get_sent_emails_count(user_id=None, status=None):
    """
    Get the total count of sent emails for a user
    """
    try:
        # Import models inside function to avoid circular imports
        from app.models.email import SentEmail
        from flask_login import current_user
        
        # Get the current user if user_id is not provided
        if user_id is None:
            if not current_user.is_authenticated:
                return 0
            user_id = current_user.id
        
        query = SentEmail.query.filter_by(user_id=user_id)
        
        # Filter by status if provided
        if status:
            query = query.filter_by(status=status)
        
        return query.count()
    except Exception as e:
        logger.error(f"Error getting sent emails count: {str(e)}")
        return 0