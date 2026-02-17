# app/services/draft_service.py

from app import db
from datetime import datetime
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
import logging
import re

logger = logging.getLogger(__name__)

class DraftService:
    """Service for managing email drafts."""

    @staticmethod
    def create_local_draft(to, subject, body, cc=None, bcc=None, html_body=None, user_id=None, attachments=None):
        """
        Create a draft locally in our database first
        
        Args:
            to: Recipient email address or list of addresses
            subject: Email subject
            body: Email body content (plain text)
            cc: CC recipients (optional)
            bcc: BCC recipients (optional)
            html_body: HTML body content (optional)
            user_id: User ID
            attachments: List of attachment files (optional)
            
        Returns:
            DraftEmail object or None if creation failed
        """
        try:
            # Import models inside the method to avoid circular imports
            from app.models.email import DraftEmail
            from flask_login import current_user
            
            # Get the user ID from current_user if not provided
            if user_id is None:
                if not current_user.is_authenticated:
                    logger.error("User not authenticated")
                    return None
                user_id = current_user.id
            
            # Convert to string if it's a list
            if isinstance(to, list):
                to = ', '.join(to)
            if isinstance(cc, list):
                cc = ', '.join(cc)
            if isinstance(bcc, list):
                bcc = ', '.join(bcc)
            
            # Store the draft in our database
            draft_email = DraftEmail(
                user_id=user_id,
                to=to,
                cc=cc,
                bcc=bcc,
                subject=subject,
                body=body,
                html_body=html_body,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            
            db.session.add(draft_email)
            db.session.commit()
            
            # Process attachments if provided
            if attachments:
                DraftService._process_attachments(draft_email.id, attachments)
            
            logger.info(f"Created local draft with ID: {draft_email.id}")
            return draft_email
            
        except Exception as e:
            logger.error(f"Error creating local draft: {str(e)}")
            db.session.rollback()
            return None
    
    @staticmethod
    def _process_attachments(draft_id, attachments):
        """Process and save attachments for a draft."""
        try:
            # Import models inside the method to avoid circular imports
            from app.models.email import DraftAttachment
            
            for attachment in attachments:
                # Create a new attachment record
                draft_attachment = DraftAttachment(
                    draft_id=draft_id,
                    filename=attachment.get('filename', 'attachment'),
                    content_type=attachment.get('content_type', 'application/octet-stream'),
                    size=attachment.get('size', 0),
                    data=attachment.get('data', b'')
                )
                db.session.add(draft_attachment)
            
            db.session.commit()
            logger.info(f"Processed {len(attachments)} attachments for draft {draft_id}")
            return True
        except Exception as e:
            logger.error(f"Error processing attachments: {str(e)}")
            db.session.rollback()
            return False
    
    @staticmethod
    def save_draft_to_gmail(draft_id, user_id=None):
        """
        Save a local draft to Gmail and update our database.
        
        Args:
            draft_id: DraftEmail ID
            user_id: User ID (optional, will use current_user if not provided)
            
        Returns:
            Updated DraftEmail object or None if failed
        """
        try:
            # Import models and services inside the method to avoid circular imports
            from app.models.email import DraftEmail, DraftAttachment
            from app.models.user import User
            from app.services.gmail_service import GmailService
            from flask_login import current_user
            
            # Get the user ID from current_user if not provided
            if user_id is None:
                if not current_user.is_authenticated:
                    logger.error("User not authenticated")
                    return None
                user_id = current_user.id
                user = current_user
            else:
                user = User.query.get(user_id)
                if not user:
                    logger.error(f"User not found with ID: {user_id}")
                    return None
            
            # Get the draft from database
            draft = DraftEmail.query.filter_by(id=draft_id, user_id=user_id).first()
            if not draft:
                logger.error(f"Draft not found with ID: {draft_id}")
                return None
            
            # Initialize Gmail service
            gmail_service = GmailService(user)
            if not gmail_service.service:
                logger.error("Gmail service not available")
                return draft
            
            # Create message from draft data
            if draft.html_body:
                # Create a multipart message for HTML content
                message = MIMEMultipart('alternative')
                message.attach(MIMEText(draft.body, 'plain'))
                message.attach(MIMEText(draft.html_body, 'html'))
            else:
                # Create a simple text message
                message = MIMEText(draft.body)
            
            # Set headers
            message['to'] = draft.to
            if draft.cc:
                message['cc'] = draft.cc
            if draft.bcc:
                message['bcc'] = draft.bcc
            message['subject'] = draft.subject
            
            # Add attachments if any
            attachments = DraftAttachment.query.filter_by(draft_id=draft_id).all()
            if attachments:
                # Convert to multipart/mixed if there are attachments
                if draft.html_body:
                    mixed_message = MIMEMultipart('mixed')
                    mixed_message.attach(message)
                    message = mixed_message
                else:
                    message = MIMEMultipart('mixed')
                    message.attach(MIMEText(draft.body, 'plain'))
                
                for attachment in attachments:
                    part = MIMEApplication(attachment.data)
                    part.add_header('Content-Disposition', 'attachment', filename=attachment.filename)
                    message.attach(part)
            
            # Convert message to base64url encoded string
            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
            
            # Create or update the draft in Gmail
            if draft.gmail_id:
                # Update existing draft
                draft_request = {
                    'id': draft.gmail_id,
                    'message': {
                        'raw': raw_message
                    }
                }
                
                gmail_draft = gmail_service.service.users().drafts().update(
                    userId='me',
                    id=draft.gmail_id,
                    body=draft_request
                ).execute()
            else:
                # Create new draft
                draft_request = {
                    'message': {
                        'raw': raw_message
                    }
                }
                
                gmail_draft = gmail_service.service.users().drafts().create(
                    userId='me',
                    body=draft_request
                ).execute()
                
                # Update our database with the Gmail ID
                draft.gmail_id = gmail_draft['id']
            
            # Update the draft in our database
            draft.updated_at = datetime.utcnow()
            draft.synced_at = datetime.utcnow()
            db.session.commit()
            
            logger.info(f"Saved draft to Gmail with ID: {draft.gmail_id}")
            return draft
            
        except Exception as e:
            logger.error(f"Error saving draft to Gmail: {str(e)}")
            db.session.rollback()
            return None
    
    @staticmethod
    def update_draft(draft_id, to=None, subject=None, body=None, cc=None, bcc=None, html_body=None, user_id=None):
        """
        Update an existing draft in our database
        
        Args:
            draft_id: Draft ID
            to: Updated recipient email
            subject: Updated subject
            body: Updated body content
            cc: Updated CC recipients
            bcc: Updated BCC recipients
            html_body: Updated HTML body content
            user_id: User ID
            
        Returns:
            Updated DraftEmail object or None if update failed
        """
        try:
            # Import models inside the method to avoid circular imports
            from app.models.email import DraftEmail
            from flask_login import current_user
            
            # Get the user ID from current_user if not provided
            if user_id is None:
                if not current_user.is_authenticated:
                    logger.error("User not authenticated")
                    return None
                user_id = current_user.id
            
            # Get the draft from database
            draft = DraftEmail.query.filter_by(id=draft_id, user_id=user_id).first()
            if not draft:
                logger.error(f"Draft not found with ID: {draft_id}")
                return None
            
            # Update fields if provided
            if to is not None:
                draft.to = to if isinstance(to, str) else ', '.join(to)
            if subject is not None:
                draft.subject = subject
            if body is not None:
                draft.body = body
            if cc is not None:
                draft.cc = cc if isinstance(cc, str) else ', '.join(cc)
            if bcc is not None:
                draft.bcc = bcc if isinstance(bcc, str) else ', '.join(bcc)
            if html_body is not None:
                draft.html_body = html_body
            
            draft.updated_at = datetime.utcnow()
            db.session.commit()
            
            logger.info(f"Updated draft with ID: {draft_id}")
            return draft
            
        except Exception as e:
            logger.error(f"Error updating draft: {str(e)}")
            db.session.rollback()
            return None
    
    @staticmethod
    def delete_draft(draft_id, user_id=None, delete_from_gmail=True):
        """
        Delete a draft from Gmail and our database
        
        Args:
            draft_id: Draft ID
            user_id: User ID
            delete_from_gmail: Whether to delete from Gmail as well
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Import models and services inside the method to avoid circular imports
            from app.models.email import DraftEmail
            from app.models.user import User
            from app.services.gmail_service import GmailService
            from flask_login import current_user
            
            # Get the user ID from current_user if not provided
            if user_id is None:
                if not current_user.is_authenticated:
                    logger.error("User not authenticated")
                    return False
                user_id = current_user.id
                user = current_user
            else:
                user = User.query.get(user_id)
                if not user:
                    logger.error(f"User not found with ID: {user_id}")
                    return False
            
            # Get the draft from database
            draft = DraftEmail.query.filter_by(id=draft_id, user_id=user_id).first()
            if not draft:
                logger.error(f"Draft not found with ID: {draft_id}")
                return False
            
            # Delete from Gmail if requested and if we have a Gmail ID
            if delete_from_gmail and draft.gmail_id:
                gmail_service = GmailService(user)
                if gmail_service.service:
                    try:
                        gmail_service.service.users().drafts().delete(
                            userId='me',
                            id=draft.gmail_id
                        ).execute()
                        logger.info(f"Deleted draft from Gmail with ID: {draft.gmail_id}")
                    except Exception as e:
                        logger.error(f"Error deleting draft from Gmail: {str(e)}")
                        # Continue with database deletion even if Gmail deletion fails
            
            # Remove the draft from our database
            db.session.delete(draft)
            db.session.commit()
            
            logger.info(f"Deleted draft with ID: {draft_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error deleting draft: {str(e)}")
            db.session.rollback()
            return False
    
    @staticmethod
    def get_draft_by_id(draft_id, user_id=None):
        """
        Get a draft by ID for a specific user.
        
        Args:
            draft_id: Draft ID
            user_id: User ID
            
        Returns:
            DraftEmail object or None if not found
        """
        try:
            # Import models inside the method to avoid circular imports
            from app.models.email import DraftEmail
            from flask_login import current_user
            
            # Get the user ID from current_user if not provided
            if user_id is None:
                if not current_user.is_authenticated:
                    return None
                user_id = current_user.id
            
            return DraftEmail.query.filter_by(id=draft_id, user_id=user_id).first()
            
        except Exception as e:
            logger.error(f"Error getting draft by ID: {str(e)}")
            return None
    
    @staticmethod
    def get_user_drafts(user_id=None, limit=20, offset=0, include_gmail_drafts=False):
        """
        Get all drafts for a user.
        
        Args:
            user_id: User ID
            limit: Maximum number of drafts to retrieve
            offset: Number of drafts to skip (for pagination)
            include_gmail_drafts: Whether to sync with Gmail for latest drafts
            
        Returns:
            List of DraftEmail objects
        """
        try:
            # Import models and services inside the method to avoid circular imports
            from app.models.email import DraftEmail
            from app.models.user import User
            from app.services.gmail_service import GmailService
            from flask_login import current_user
            
            # Get the user ID from current_user if not provided
            if user_id is None:
                if not current_user.is_authenticated:
                    return []
                user_id = current_user.id
                user = current_user
            else:
                user = User.query.get(user_id)
                if not user:
                    logger.error(f"User not found with ID: {user_id}")
                    return []
            
            # Sync with Gmail if requested
            if include_gmail_drafts:
                DraftService._sync_drafts_from_gmail(user, limit)
            
            # Get drafts from our database
            drafts = DraftEmail.query.filter_by(user_id=user_id).order_by(
                DraftEmail.updated_at.desc()
            ).offset(offset).limit(limit).all()
            
            return drafts
            
        except Exception as e:
            logger.error(f"Error getting user drafts: {str(e)}")
            return []
    
    @staticmethod
    def _sync_drafts_from_gmail(user, limit=20):
        """
        Sync drafts from Gmail to our database
        
        Args:
            user: User object
            limit: Maximum number of drafts to sync
            
        Returns:
            Number of drafts synced
        """
        try:
            # Import models inside the method to avoid circular imports
            from app.models.email import DraftEmail
            from app.services.gmail_service import GmailService
            
            # Initialize Gmail service
            gmail_service = GmailService(user)
            if not gmail_service.service:
                logger.error("Gmail service not available")
                return 0
            
            # Query for drafts
            results = gmail_service.service.users().drafts().list(
                userId='me',
                maxResults=limit
            ).execute()
            
            gmail_drafts = results.get('drafts', [])
            synced_count = 0
            
            # Get existing Gmail IDs to avoid unnecessary queries
            existing_gmail_ids = set(
                draft.gmail_id for draft in DraftEmail.query.filter_by(user_id=user.id).all()
                if draft.gmail_id
            )
            
            for gmail_draft in gmail_drafts:
                # Skip if we already have this draft
                if gmail_draft['id'] in existing_gmail_ids:
                    continue
                
                # Get the full draft details
                draft_detail = gmail_service.service.users().drafts().get(
                    userId='me',
                    id=gmail_draft['id']
                ).execute()
                
                # Extract message details
                message = draft_detail['message']
                headers = {h['name']: h['value'] for h in message['payload'].get('headers', [])}
                
                # Extract body content
                body_text, body_html = DraftService._extract_body_content(message['payload'])
                
                # Create new draft record
                db_draft = DraftEmail(
                    user_id=user.id,
                    gmail_id=gmail_draft['id'],
                    to=headers.get('To', ''),
                    cc=headers.get('Cc', ''),
                    bcc=headers.get('Bcc', ''),
                    subject=headers.get('Subject', ''),
                    body=body_text,
                    html_body=body_html,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                    synced_at=datetime.utcnow()
                )
                
                db.session.add(db_draft)
                synced_count += 1
            
            if synced_count > 0:
                db.session.commit()
                logger.info(f"Synced {synced_count} new drafts from Gmail for user {user.id}")
            
            return synced_count
            
        except Exception as e:
            logger.error(f"Error syncing drafts from Gmail: {str(e)}")
            try:
                db.session.rollback()
            except Exception:
                pass
            return 0
    
    @staticmethod
    def _extract_body_content(payload):
        """
        Extract text and HTML body content from a Gmail message payload
        
        Args:
            payload: Gmail message payload
            
        Returns:
            Tuple of (body_text, body_html)
        """
        body_text = ""
        body_html = ""
        
        def extract_parts(parts):
            nonlocal body_text, body_html
            
            for part in parts:
                mime_type = part.get('mimeType', '')
                
                if 'parts' in part:
                    # Recursively handle nested parts
                    extract_parts(part['parts'])
                elif mime_type == 'text/plain' and not body_text:
                    # Extract plain text body
                    data = part.get('body', {}).get('data', '')
                    if data:
                        try:
                            body_text = base64.urlsafe_b64decode(data).decode('utf-8')
                        except Exception as e:
                            logger.error(f"Error decoding plain text body: {e}")
                elif mime_type == 'text/html' and not body_html:
                    # Extract HTML body
                    data = part.get('body', {}).get('data', '')
                    if data:
                        try:
                            body_html = base64.urlsafe_b64decode(data).decode('utf-8')
                        except Exception as e:
                            logger.error(f"Error decoding HTML body: {e}")
        
        # Check if the payload has parts
        if 'parts' in payload:
            extract_parts(payload['parts'])
        else:
            # Single part message
            mime_type = payload.get('mimeType', '')
            data = payload.get('body', {}).get('data', '')
            
            if data:
                try:
                    content = base64.urlsafe_b64decode(data).decode('utf-8')
                    
                    if mime_type == 'text/html':
                        body_html = content
                    else:
                        body_text = content
                except Exception as e:
                    logger.error(f"Error decoding body: {e}")
        
        return body_text, body_html
    
    @staticmethod
    def get_drafts_count(user_id=None):
        """
        Get the total count of drafts for a user
        
        Args:
            user_id: User ID
            
        Returns:
            Number of drafts
        """
        try:
            # Import models inside the method to avoid circular imports
            from app.models.email import DraftEmail
            from flask_login import current_user
            
            # Get the user ID from current_user if not provided
            if user_id is None:
                if not current_user.is_authenticated:
                    return 0
                user_id = current_user.id
            
            return DraftEmail.query.filter_by(user_id=user_id).count()
            
        except Exception as e:
            logger.error(f"Error getting drafts count: {str(e)}")
            return 0

# Legacy functions for backward compatibility
def create_draft(to, subject, body, user_id=1):
    """Legacy function for backward compatibility."""
    return DraftService.create_local_draft(to, subject, body, user_id=user_id)

def update_draft(draft_id, to=None, subject=None, body=None, user_id=1):
    """Legacy function for backward compatibility."""
    return DraftService.update_draft(draft_id, to, subject, body, user_id=user_id)

def delete_draft(draft_id, user_id=1):
    """Legacy function for backward compatibility."""
    return DraftService.delete_draft(draft_id, user_id=user_id)

def get_drafts(user_id=1, limit=20):
    """Legacy function for backward compatibility."""
    return DraftService.get_user_drafts(user_id, limit)

def get_draft_by_id(draft_id, user_id=1):
    """Legacy function for backward compatibility."""
    return DraftService.get_draft_by_id(draft_id, user_id)

def save_draft_to_gmail(draft_id, user_id=1):
    """Legacy function for backward compatibility."""
    return DraftService.save_draft_to_gmail(draft_id, user_id)