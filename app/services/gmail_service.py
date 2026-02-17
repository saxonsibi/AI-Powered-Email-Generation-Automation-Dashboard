# app/services/gmail_service.py
import os
import json
import base64
import logging
import email
from app import db
import pytz  # Added for timezone handling
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.application import MIMEApplication
from email import encoders
from pathlib import Path
from googleapiclient.discovery import build, HttpError
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional, Union
import time
import random  # CRITICAL FIX: Added for rate limiting
import re  # CRITICAL FIX: Added for email validation

# Configure logging
logger = logging.getLogger(__name__)

class GmailService:
    """Service for interacting with Gmail API.
    
    IMPORTANT: This service should ONLY be used in background jobs (scheduler/worker).
    NEVER import or call this service directly in UI routes.
    All Gmail API interactions must run in background jobs with app.app_context().
    """
    
    # Define OAuth scopes as class constants
    SCOPE_MODIFY = 'https://www.googleapis.com/auth/gmail.modify'
    SCOPE_READONLY = 'https://www.googleapis.com/auth/gmail.readonly'
    SCOPE_SEND = 'https://www.googleapis.com/auth/gmail.send'
    
    # Rate limiting constants
    MAX_RETRIES = 3  # CRITICAL FIX: Reduced from 5 to 3
    BASE_DELAY = 1  # Base delay in seconds
    MAX_DELAY = 30  # Maximum delay in seconds (reduced from 60)
    JITTER_FACTOR = 0.1  # Random jitter to avoid thundering herd
    BATCH_SIZE = 10  # CRITICAL FIX: Reduced batch size to prevent rate limiting
    BATCH_DELAY = 0.3  # CRITICAL FIX: Added delay between batches
    
    # CRITICAL FIX: Safety check patterns
    NO_REPLY_PATTERNS = [
        r'noreply@',
        r'no-reply@',
        r'do-not-reply@',
        r'donotreply@',
        r'notifications@',
        r'automated@',
        r'auto@'
    ]
    
    MAILING_LIST_HEADERS = [
        'List-Id',
        'List-Unsubscribe',
        'List-Post',
        'Mailing-List',
        'X-Mailing-List'
    ]
    
    AUTO_GENERATED_HEADERS = [
        ('Auto-Submitted', 'auto-generated'),
        ('Auto-Submitted', 'auto-replied'),
        ('X-Auto-Response-Suppress', 'All'),
        ('X-Auto-Response-Suppress', 'OOF'),
        ('Precedence', 'bulk'),
        ('Precedence', 'list'),
        ('Precedence', 'junk')
    ]
    
    def __init__(self, user, sender_email=None):
        """Initialize Gmail service for a user.
        
        Args:
            user: User object
            sender_email: Optional custom sender email for this service instance
        """
        self.user = user
        self.sender_email = sender_email  # Store custom sender email
        self.credentials = self._get_credentials()
        # CRITICAL FIX 3: Ensure service is properly initialized
        self.service = build('gmail', 'v1', credentials=self.credentials) if self.credentials else None
    
    def _get_credentials(self) -> Optional[Credentials]:
        """Get OAuth credentials for user.
        """
        if not self.user.gmail_credentials:
            logger.warning(f"No Gmail credentials found for user {self.user.id}")
            return None
        
        try:
            creds_data = json.loads(self.user.gmail_credentials)
            credentials = Credentials(
                token=creds_data.get('token'),
                refresh_token=creds_data.get('refresh_token'),
                token_uri=creds_data.get('token_uri'),
                client_id=creds_data.get('client_id'),
                client_secret=creds_data.get('client_secret'),
                scopes=creds_data.get('scopes')
            )
            
            # CRITICAL FIX 9: Token refresh safety
            if credentials.expired and credentials.refresh_token:
                logger.info(f"Refreshing Gmail credentials for user {self.user.id}")
                credentials.refresh(Request())
                # Update stored credentials
                self.user.gmail_credentials = credentials.to_json()
                db.session.commit()
            
            return credentials
        except Exception as e:
            logger.error(f"Error loading Gmail credentials: {str(e)}")
            return None
    
    def safe_execute(self, request, retries=None):
        """
        Safely execute a Gmail API request with exponential backoff and jitter.
        
        Args:
            request: The Gmail API request to execute
            retries: Number of retries (defaults to MAX_RETRIES)
            
        Returns:
            Response from the API or None if all retries fail
        """
        if retries is None:
            retries = self.MAX_RETRIES
            
        for attempt in range(retries + 1):
            try:
                # Add small random delay to avoid thundering herd
                if attempt > 0:
                    delay = min(
                        self.BASE_DELAY * (2 ** (attempt - 1)) + random.uniform(0, self.JITTER_FACTOR),
                        self.MAX_DELAY
                    )
                    logger.info(f"Retrying Gmail API request (attempt {attempt + 1}/{retries + 1}) after {delay:.2f}s")
                    time.sleep(delay)
                
                return request.execute()
            except HttpError as e:
                # CRITICAL FIX 4: Handle revoked or expired tokens
                if e.resp.status in [401, 403]:
                    logger.error(f"Gmail token expired or revoked: {str(e)}")
                    return None
                elif e.resp.status == 429:  # Rate limit exceeded
                    if attempt < retries:
                        # Calculate exponential backoff with jitter
                        delay = min(
                            self.BASE_DELAY * (2 ** attempt) + random.uniform(0, self.JITTER_FACTOR),
                            self.MAX_DELAY
                        )
                        logger.warning(f"Rate limit exceeded, retrying in {delay:.2f}s (attempt {attempt + 1}/{retries + 1})")
                        time.sleep(delay)
                        continue
                    else:
                        logger.error(f"Rate limit exceeded after {retries} retries")
                        return None
                elif e.resp.status == 403:  # Forbidden
                    logger.error(f"Access forbidden: {str(e)}")
                    return None
                else:
                    logger.error(f"Gmail API error: {str(e)}")
                    if attempt == retries:
                        return None
            except Exception as e:
                logger.error(f"Unexpected error executing Gmail API request: {str(e)}")
                if attempt == retries:
                    return None
        
        return None
    
    # CRITICAL FIX: Add comprehensive safety check method
    def is_safe_to_reply(self, email_address: str, headers: Dict[str, str]) -> Tuple[bool, Optional[str]]:
        """
        Check if it's safe to auto-reply to an email.
        
        Args:
            email_address: The sender's email address
            headers: Dictionary of email headers
            
        Returns:
            Tuple of (is_safe, skip_reason)
        """
        # Check for no-reply addresses
        for pattern in self.NO_REPLY_PATTERNS:
            if re.search(pattern, email_address, re.IGNORECASE):
                return False, f"No-reply address detected: {email_address}"
        
        # Check for mailing list headers
        for header_name in self.MAILING_LIST_HEADERS:
            if header_name in headers:
                return False, f"Mailing list detected: {header_name} header present"
        
        # Check for auto-generated headers
        for header_name, header_value in self.AUTO_GENERATED_HEADERS:
            if header_name in headers:
                actual_value = headers.get(header_name, '')
                if header_value.lower() in actual_value.lower():
                    return False, f"Auto-generated email detected: {header_name}={actual_value}"
        
        return True, None
    
    def fetch_emails(self, query=None, label_ids=None, max_results=20, page_token=None, max_retries=3, metadata_only=True):
        """
        Fetch emails from Gmail API with query, label filtering, and pagination support.
        BACKGROUND JOB ONLY: This method should NEVER be called in UI routes.
        
        Args:
            query: Gmail search query string (e.g., 'in:sent')
            label_ids: List of label IDs to filter by (e.g., ['SENT'])
            max_results: Maximum number of results to return
            page_token: Token for pagination (nextPageToken from previous request)
            max_retries: Maximum number of retries for SSL errors
            metadata_only: If True, only fetch metadata (faster) - DEFAULTED TO True
            
        Returns:
            Tuple of (emails_list, next_page_token)
        """
        if not self.service:
            logger.warning("Gmail service not initialized")
            return [], None
        
        try:
            # CRITICAL FIX: Limit max_results to prevent rate limiting
            max_results = min(max_results, 10)  # ⛔ NEVER >10
            
            # Build request parameters
            params = {
                'userId': 'me',
                'maxResults': max_results  # CRITICAL FIX: Limit batch size
            }
            
            # Add query if provided
            if query:
                params['q'] = query
                
            # Add label IDs if provided
            if label_ids:
                params['labelIds'] = label_ids
                
            # Add page token if provided
            if page_token:
                params['pageToken'] = page_token
            
            # Get message list with safe execution
            list_request = self.service.users().messages().list(**params)
            response = self.safe_execute(list_request)
            
            if not response:
                logger.error("Failed to get message list from Gmail API")
                return [], None
                
            messages = response.get('messages', [])
            next_page_token = response.get('nextPageToken')
            
            # Get message details - Always use metadata format for better performance
            email_dicts = []
            # CRITICAL FIX: Include Message-ID in metadata headers
            metadata_headers = ['From', 'To', 'Subject', 'Date', 'Message-ID', 'In-Reply-To', 'References']
            
            # CRITICAL FIX: Process in smaller batches with delays
            for i in range(0, len(messages), self.BATCH_SIZE):
                batch_messages = messages[i:i + self.BATCH_SIZE]
                
                # CRITICAL FIX: Fetch messages sequentially with backoff
                for message in batch_messages:
                    try:
                        # CRITICAL FIX: Implement sequential fetching with exponential backoff
                        msg = None
                        for attempt in range(5):
                            try:
                                msg = self.service.users().messages().get(
                                    userId="me",
                                    id=message['id'],
                                    format="metadata",  # Use metadata format for efficiency
                                    metadataHeaders=metadata_headers
                                ).execute()
                                break
                            except HttpError as e:
                                if e.resp.status == 429:
                                    sleep_time = (2 ** attempt) + random.random()
                                    logger.warning(f"Rate limit exceeded for message {message['id']}, retrying in {sleep_time:.2f}s")
                                    time.sleep(sleep_time)
                                else:
                                    raise
                        
                        if not msg:
                            logger.error(f"Failed to fetch message {message['id']}")
                            continue
                            
                        # Parse the message
                        email_dict = self._parse_message(msg, metadata_only=True)
                        email_dicts.append(email_dict)
                        
                        # CRITICAL FIX: Add small delay between messages to avoid rate limiting
                        time.sleep(0.1)
                        
                    except Exception as e:
                        logger.error(f"Error processing message {message['id']}: {str(e)}")
                        continue
                
                # CRITICAL FIX: Add delay between batches
                if i + self.BATCH_SIZE < len(messages):
                    time.sleep(self.BATCH_DELAY)
            
            # Return emails and next page token
            return email_dicts, next_page_token
            
        except Exception as e:
            logger.error(f"Error fetching emails: {str(e)}")
            return [], None
    
    def fetch_full_message(self, message_id):
        """
        Fetch the full message content including body.
        Only use this when absolutely necessary (e.g., for keyword matching).
        
        Args:
            message_id: Gmail message ID
            
        Returns:
            Full message object or None if failed
        """
        if not self.service:
            logger.warning("Gmail service not initialized")
            return None
        
        try:
            # CRITICAL FIX: Implement sequential fetching with exponential backoff
            msg = None
            for attempt in range(5):
                try:
                    msg = self.service.users().messages().get(
                        userId="me",
                        id=message_id,
                        format="full"
                    ).execute()
                    break
                except HttpError as e:
                    if e.resp.status == 429:
                        sleep_time = (2 ** attempt) + random.random()
                        logger.warning(f"Rate limit exceeded for message {message_id}, retrying in {sleep_time:.2f}s")
                        time.sleep(sleep_time)
                    else:
                        raise
            
            return msg
            
        except Exception as e:
            logger.error(f"Error fetching full message: {str(e)}")
            return None
    
    def check_keywords_in_email(self, message_id, keywords):
        """
        Check if an email contains any of the specified keywords in subject or body.
        This method fetches the full message only when needed.
        
        Args:
            message_id: Gmail message ID
            keywords: List of keywords to search for
            
        Returns:
            Tuple of (found, matched_keywords, locations)
        """
        if not self.service or not keywords:
            return False, [], []
        
        try:
            # First, get metadata to check subject
            metadata = None
            for attempt in range(5):
                try:
                    metadata = self.service.users().messages().get(
                        userId="me",
                        id=message_id,
                        format="metadata",
                        metadataHeaders=['Subject']
                    ).execute()
                    break
                except HttpError as e:
                    if e.resp.status == 429:
                        sleep_time = (2 ** attempt) + random.random()
                        logger.warning(f"Rate limit exceeded for message {message_id}, retrying in {sleep_time:.2f}s")
                        time.sleep(sleep_time)
                    else:
                        raise
            
            if not metadata:
                return False, [], []
            
            # Extract subject
            headers = metadata.get('payload', {}).get('headers', [])
            subject = ''
            
            for header in headers:
                if header['name'].lower() == 'subject':
                    subject = header['value']
                    break
            
            # Check if keywords are in subject
            matched_keywords = []
            locations = []
            
            for keyword in keywords:
                keyword_lower = keyword.lower()
                if keyword_lower in subject.lower():
                    matched_keywords.append(keyword)
                    locations.append('subject')
            
            # If we already found keywords in subject, no need to fetch body
            if matched_keywords:
                return True, matched_keywords, locations
            
            # If no keywords in subject, fetch full message to check body
            full_message = self.fetch_full_message(message_id)
            if not full_message:
                return False, [], []
            
            # Extract body content
            body = self._extract_body(full_message.get('payload', {}))
            body_text = body.get('text', '')
            body_html = body.get('html', '')
            
            # Convert HTML to text for searching if needed
            if not body_text and body_html:
                body_text = self._html_to_text(body_html)
            
            # Check for keywords in body
            for keyword in keywords:
                keyword_lower = keyword.lower()
                if keyword_lower in body_text.lower():
                    if keyword not in matched_keywords:  # Avoid duplicates
                        matched_keywords.append(keyword)
                    if 'body' not in locations:  # Avoid duplicates
                        locations.append('body')
            
            return len(matched_keywords) > 0, matched_keywords, locations
            
        except Exception as e:
            logger.error(f"Error checking keywords: {str(e)}")
            return False, [], []
    
    def sync_emails(self, limit=100):
        """
        Sync emails from Gmail to the local database.
        Uses metadata-only approach for efficiency.
        
        Args:
            limit: Maximum number of emails to sync
            
        Returns:
            int: Number of emails synced
        """
        try:
            # Import models inside method to avoid circular imports
            from app.models.email import Email
            
            # Fetch from INBOX and SENT (to catch self-sent emails)
            all_emails = []
            
            # Get inbox emails
            inbox_emails, _ = self.fetch_emails(
                label_ids=['INBOX'],
                max_results=limit,
                metadata_only=True
            )
            all_emails.extend(inbox_emails)
            
            # Get sent emails (for self-sent)
            sent_emails, _ = self.fetch_emails(
                label_ids=['SENT'],
                max_results=limit,
                metadata_only=True
            )
            all_emails.extend(sent_emails)
            
            logger.info(f"🔍 Sync: Found {len(all_emails)} total emails (inbox: {len(inbox_emails)}, sent: {len(sent_emails)})")
            
            synced_count = 0
            seen_gmail_ids = set()
            
            for email_data in all_emails:
                gmail_id = email_data.get('id')
                if gmail_id in seen_gmail_ids:
                    continue
                seen_gmail_ids.add(gmail_id)
                
                # Store in local database
                email = self.store_email_in_db(email_data, self.user.id)
                if email:
                    synced_count += 1
            
            logger.info(f"Synced {synced_count} NEW emails for user {self.user.id}")
            return synced_count
            
        except Exception as e:
            logger.error(f"Error syncing emails: {str(e)}")
            return 0
    
    def _parse_message(self, message, metadata_only=True):
        """Parse Gmail message into a dictionary.
        
        Args:
            message: Gmail message object
            metadata_only: If True, only parse metadata fields
    
        Returns:
            Dictionary with email data
        """
        headers = message.get('payload', {}).get('headers', [])
        
        # CRITICAL FIX: Extract headers properly - convert list to dict
        header_map = {h['name']: h['value'] for h in headers}
        
        # Extract headers with CRITICAL FIX: Include all threading headers
        subject = header_map.get('Subject', '')
        sender = header_map.get('From', '')
        date = header_map.get('Date', '')
        to = header_map.get('To', '')
        cc = header_map.get('Cc', '')
        bcc = header_map.get('Bcc', '')
        message_id = header_map.get('Message-ID', '')  # CRITICAL FIX: RFC Message-ID for threading
        in_reply_to = header_map.get('In-Reply-To', '')  # CRITICAL FIX: Threading header
        references = header_map.get('References', '')  # CRITICAL FIX: Threading header
        
        # Parse date using the improved method
        try:
            if date:
                # Convert to datetime object with proper timezone handling
                date_obj = self._parse_gmail_date(date)
                formatted_date = date_obj.strftime('%b %d, %Y')
            else:
                formatted_date = ''
        except Exception as e:
            logger.error(f"Error parsing date in _parse_message: {str(e)}")
            formatted_date = ''
        
        # Check if message is read
        is_read = 'UNREAD' not in message.get('labelIds', [])
        
        # Check if message is starred
        is_starred = 'STARRED' in message.get('labelIds', [])
        
        # Base result dictionary
        result = {
            'id': message.get('id'),  # CRITICAL FIX: This is the gmail_id
            'threadId': message.get('threadId'),
            'subject': subject,
            'sender': sender,
            'date': date,  # Raw date string
            'formatted_date': formatted_date,  # Formatted date
            'to': to,
            'cc': cc,
            'bcc': bcc,
            'message_id': message_id,  # CRITICAL FIX: RFC Message-ID for threading
            'in_reply_to': in_reply_to,  # CRITICAL FIX: Threading header
            'references': references,  # CRITICAL FIX: Threading header
            'snippet': message.get('snippet', ''),  # Get snippet from message
            'is_read': is_read,
            'is_starred': is_starred,
            'headers': header_map  # CRITICAL FIX: Include full header map for safety checks
        }
        
        # If not metadata only, extract body content
        if not metadata_only:
            body = self._extract_body(message.get('payload', {}))
            result['body'] = body
        
        return result
    
    def _extract_body(self, payload):
        """Extract email body from payload."""
        body = {'text': '', 'html': ''}
        
        if 'parts' in payload:
            # Multipart message
            for part in payload['parts']:
                # Recursively handle nested parts
                if 'parts' in part:
                    nested_body = self._extract_body(part)
                    # Merge text content
                    if nested_body.get('text'):
                        body['text'] += nested_body.get('text', '')
                    # Merge HTML content
                    if nested_body.get('html'):
                        body['html'] += nested_body.get('html', '')
                else:
                    mime_type = part.get('mimeType', '')
                    data = part.get('body', {}).get('data', '')
                    
                    if data:
                        try:
                            content = base64.urlsafe_b64decode(data).decode('utf-8')
                            
                            if 'text/plain' in mime_type:
                                body['text'] = content
                            elif 'text/html' in mime_type:
                                body['html'] = content
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
                        body['html'] = content
                    else:
                        body['text'] = content
                except Exception as e:
                    logger.error(f"Error decoding body: {e}")
        
        return body
    
    def _parse_gmail_date(self, date_str):
        """
        Parse Gmail date string to UTC datetime object.
        Handles various date formats from Gmail API.
        
        Args:
            date_str: Date string from Gmail API
            
        Returns:
            UTC datetime object
        """
        if not date_str:
            return datetime.utcnow()
        
        try:
            # First try with email.utils.parsedate_to_datetime
            dt = email.utils.parsedate_to_datetime(date_str)
            
            # Convert to UTC if it has timezone info
            if dt.tzinfo is not None:
                dt = dt.astimezone(pytz.UTC)
            else:
                # Assume UTC if no timezone info
                dt = dt.replace(tzinfo=pytz.UTC)
                
            return dt
        except Exception as e:
            logger.warning(f"Error parsing date with email.utils: {str(e)}")
            
            try:
                # Fallback to manual parsing
                # Example format: "Tue, 15 Jun 2021 14:30:00 +0000"
                import re
                from datetime import datetime
                
                # Try to extract date components
                match = re.match(r'.*?(\d{1,2})\s+(\w{3})\s+(\d{4})\s+(\d{1,2}):(\d{2}):(\d{2})\s+([+-]\d{4})', date_str)
                if match:
                    day, month, year, hour, minute, second, tz_offset = match.groups()
                    
                    # Convert month name to number
                    month_num = {
                        'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
                        'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
                    }.get(month, 1)
                    
                    # Create datetime without timezone
                    dt = datetime(int(year), month_num, int(day), 
                                 int(hour), int(minute), int(second))
                    
                    # Handle timezone offset
                    tz_hours = int(tz_offset[1:3])
                    tz_minutes = int(tz_offset[3:5])
                    tz_delta = timedelta(hours=tz_hours, minutes=tz_minutes)
                    
                    if tz_offset[0] == '+':
                        dt = dt - tz_delta
                    else:
                        dt = dt + tz_delta
                    
                    # Return as UTC
                    return dt.replace(tzinfo=pytz.UTC)
                    
            except Exception as e2:
                logger.warning(f"Error parsing date with fallback method: {str(e2)}")
            
            # Last resort: return current time
            return datetime.utcnow().replace(tzinfo=pytz.UTC)
    
    def send_email(self, to: str, subject: str, body_text: Optional[str] = None, 
               body_html: Optional[str] = None, cc: Optional[str] = None, 
               bcc: Optional[str] = None, attachments: Optional[List[Dict]] = None,
               thread_id: Optional[str] = None, in_reply_to: Optional[str] = None,
               references: Optional[str] = None) -> Tuple[bool, str, str]:
        """
        CRITICAL FIX 1: Send an email through Gmail API with proper return signature.
        
        Args:
            to: Recipient email address
            subject: Email subject
            body_text: Plain text body
            body_html: HTML body
            cc: CC recipients
            bcc: BCC recipients
            attachments: List of attachment dictionaries
            thread_id: Gmail thread ID for replies (optional)
            in_reply_to: RFC Message-ID this email is replying to (optional) - CRITICAL FOR THREADING
            references: References header for threading (optional) - CRITICAL FOR THREADING
            
        Returns:
            Tuple of (success, message, message_id)  # CRITICAL FIX: Return message_id
        """
        if not self.service:
            logger.warning("Gmail service not initialized")
            return False, "Gmail service not authenticated", None

        # CRITICAL: Ensure we always have valid body content
        if not body_text and not body_html:
            body_text = "Hello, this is a generated email."
        
        # If only HTML is provided, create a plain text version
        if not body_text and body_html:
            body_text = self._html_to_text(body_html)
        
        # FINAL SAFEGUARD: Ensure body_text is never None or empty
        if not body_text or body_text.strip() == "":
            body_text = "Hello, this is a generated email."
        
        # Ensure body_html is a string if provided
        if body_html is None:
            body_html = ""
        
        try:
            # Create message with thread_id if provided
            message = self._create_message(to, subject, body_text, body_html, cc, bcc, attachments, 
                                         thread_id, in_reply_to, references)
            
            # CRITICAL FIX 6: Use threadId when replying
            request_body = {
                'raw': message['raw']
            }
            
            # Add threadId if provided
            if thread_id:
                request_body['threadId'] = thread_id
            
            # CRITICAL FIX: Implement sequential sending with exponential backoff
            response = None
            for attempt in range(5):
                try:
                    response = self.service.users().messages().send(
                        userId='me',
                        body=request_body
                    ).execute()
                    break
                except HttpError as e:
                    # CRITICAL FIX 4: Handle revoked or expired tokens
                    if e.resp.status in [401, 403]:
                        logger.error(f"Gmail token expired or revoked: {str(e)}")
                        return False, f"Gmail authentication error: {str(e)}", None
                    elif e.resp.status == 429:
                        sleep_time = (2 ** attempt) + random.random()
                        logger.warning(f"Rate limit exceeded when sending email, retrying in {sleep_time:.2f}s")
                        time.sleep(sleep_time)
                    else:
                        raise
            
            if not response:
                return False, "Failed to send email due to rate limiting", None
                
            # CRITICAL FIX: Check for message ID in response to confirm success
            message_id = response.get('id')  # CRITICAL FIX: Get the message ID (gmail_id)
            response_thread_id = response.get('threadId')  # CRITICAL FIX: Get the thread ID
            
            # CRITICAL FIX: Treat Gmail send() success as source of truth
            # If we get a message_id from Gmail, the email was sent successfully
            if message_id:
                logger.info(f"Email sent successfully with ID: {message_id}, thread_id: {response_thread_id}")
                
                # Store the sent email in database immediately after sending
                # CRITICAL: Don't call Gmail API again, just store what we know
                self._store_sent_email_immediately(message_id, to, subject, body_text, body_html, 
                                                  cc, bcc, thread_id, response_thread_id, 
                                                  in_reply_to, references)
                
                return True, "Email sent successfully", message_id  # CRITICAL FIX: Return message_id
            else:
                logger.error("Failed to send email: No message ID in response")
                return False, "Failed to send email: No message ID in response", None
                
        except Exception as e:
            error_msg = f"Error sending email: {str(e)}"
            logger.error(error_msg)
            return False, error_msg, None  # CRITICAL FIX: Return None for message_id on error
    
    def _store_sent_email_immediately(self, gmail_message_id, to, subject, body_text, body_html, 
                                    cc, bcc, thread_id=None, response_thread_id=None,
                                    in_reply_to=None, references=None):
        """
        Store a sent email in the database immediately after sending without additional API calls.
        CRITICAL FIX: Now stores RFC Message-ID for threading.
        """
        try:
            from app.models.email import Email
            
            # Use the thread ID from the response if available, otherwise use the one provided
            effective_thread_id = response_thread_id or thread_id
            
            # CRITICAL FIX: Generate or extract RFC Message-ID
            # When we send via Gmail API, we don't immediately get the RFC Message-ID
            # We'll mark it for background enrichment
            rfc_message_id = None  # Will be enriched later
            
            # Create new email record with what we know immediately
            new_email = Email(
                user_id=self.user.id,
                gmail_id=gmail_message_id,  # CRITICAL FIX: Use gmail_id as primary identifier
                message_id=rfc_message_id,  # CRITICAL FIX: RFC Message-ID (will be enriched)
                thread_id=effective_thread_id,  # Use the thread ID from the response
                sender=self.user.email,  # Current user is the sender
                to=to,
                subject=subject,
                body_text=body_text,
                body_html=body_html,
                snippet=body_text[:100] + "..." if len(body_text) > 100 else body_text,  # Create snippet from body
                is_read=True,  # Sent emails are always read
                is_starred=False,
                sent_at=datetime.utcnow(),  # Use UTC timestamp
                folder='sent',  # Explicitly mark as sent
                sync_status='pending'  # Mark for background sync to enrich metadata (including RFC Message-ID)
            )
            
            db.session.add(new_email)
            db.session.commit()
            
            logger.info(f"Stored sent email {gmail_message_id} in database immediately (RFC Message-ID will be enriched)")
            return new_email
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error storing sent email in database: {str(e)}")
            return None
    
    def _create_message(self, to, subject, body_text, body_html=None, cc=None, bcc=None, 
                       attachments=None, thread_id=None, in_reply_to=None, references=None):
        """
        CRITICAL FIX 2: Create a message for sending with proper thread headers.
        CRITICAL: in_reply_to and references should be RFC Message-ID, NOT Gmail thread_id
        """
        # CRITICAL: Ensure body_text is never None
        if not body_text or body_text.strip() == "":
            body_text = "Hello, this is a generated email."
        
        # Process HTML content to ensure links are clickable
        if body_html:
            body_html = self._process_html_links(body_html)
        
        # CRITICAL FIX 2: Thread-safe reply headers
        headers = [
            {"name": "To", "value": to},
            {"name": "Subject", "value": subject},
            # CRITICAL: Add headers to prevent auto-reply loops
            {"name": "Auto-Submitted", "value": "auto-replied"},
            {"name": "X-Auto-Response-Suppress", "value": "All"},
        ]
        
        # CRITICAL FIX: Use RFC Message-ID for threading, NOT Gmail thread_id
        # Gmail thread_id is internal to Gmail, RFC Message-ID is the standard
        if in_reply_to:
            headers.append({"name": "In-Reply-To", "value": in_reply_to})
        
        if references:
            headers.append({"name": "References", "value": references})
        
        if attachments:
            # Create multipart/mixed message for attachments
            message = MIMEMultipart()
            
            # Add headers
            for header in headers:
                message[header["name"]] = header["value"]
            
            # Add anti-loop headers
            message['Auto-Submitted'] = 'auto-replied'
            message['X-Auto-Response-Suppress'] = 'All'
            
            # Add custom sender if specified
            if self.sender_email:
                message['from'] = self.sender_email
                logger.info(f"Using custom sender email: {self.sender_email}")
            
            # Add recipients
            if cc:
                message['cc'] = cc
            if bcc:
                message['bcc'] = bcc
            
            # CRITICAL FIX: Add threading headers correctly
            if in_reply_to:
                message['In-Reply-To'] = in_reply_to
            if references:
                message['References'] = references
            
            # Create alternative part for text and HTML
            if body_html:
                # Create multipart/alternative for text and HTML
                alt_part = MIMEMultipart('alternative')
                alt_part.attach(MIMEText(body_text, 'plain'))
                alt_part.attach(MIMEText(body_html, 'html'))
                message.attach(alt_part)
            else:
                # Just plain text
                message.attach(MIMEText(body_text, 'plain'))
            
            # Add attachments
            for attachment in attachments:
                if 'data' in attachment and 'filename' in attachment:
                    # Determine MIME type based on file extension
                    filename = attachment['filename']
                    mime_type = attachment.get('mimeType', 'application/octet-stream')
                    
                    # Create appropriate MIME part
                    if mime_type.startswith('image/'):
                        part = MIMEApplication(attachment['data'], _subtype=mime_type.split('/')[1])
                    else:
                        part = MIMEBase(mime_type.split('/')[0], mime_type.split('/')[1] if '/' in mime_type else 'octet-stream')
                        part.set_payload(attachment['data'])
                        encoders.encode_base64(part)
                    
                    part.add_header(
                        'Content-Disposition',
                        f'attachment; filename="{filename}"'
                    )
                    message.attach(part)
        else:
            # No attachments
            if body_html:
                # Create multipart/alternative for text and HTML
                message = MIMEMultipart('alternative')
                
                # Add headers
                for header in headers:
                    message[header["name"]] = header["value"]
                
                # Add anti-loop headers
                message['Auto-Submitted'] = 'auto-replied'
                message['X-Auto-Response-Suppress'] = 'All'
                
                # Add custom sender if specified
                if self.sender_email:
                    message['from'] = self.sender_email
                    logger.info(f"Using custom sender email: {self.sender_email}")
                
                if cc:
                    message['cc'] = cc
                if bcc:
                    message['bcc'] = bcc
                
                # CRITICAL FIX: Add threading headers correctly
                if in_reply_to:
                    message['In-Reply-To'] = in_reply_to
                if references:
                    message['References'] = references
                
                # Add both text and HTML parts
                message.attach(MIMEText(body_text, 'plain'))
                message.attach(MIMEText(body_html, 'html'))
            else:
                # Just plain text
                message = MIMEText(body_text, 'plain')
                
                # Add headers
                for header in headers:
                    message[header["name"]] = header["value"]
                
                # Add anti-loop headers
                message['Auto-Submitted'] = 'auto-replied'
                message['X-Auto-Response-Suppress'] = 'All'
                
                # Add custom sender if specified
                if self.sender_email:
                    message['from'] = self.sender_email
                    logger.info(f"Using custom sender email: {self.sender_email}")
                
                if cc:
                    message['cc'] = cc
                if bcc:
                    message['bcc'] = bcc
                
                # CRITICAL FIX: Add threading headers correctly
                if in_reply_to:
                    message['In-Reply-To'] = in_reply_to
                if references:
                    message['References'] = references
        
        return {'raw': base64.urlsafe_b64encode(message.as_bytes()).decode()}
    
    def send_reply(self, message_id: str, body_text: Optional[str] = None, 
               body_html: Optional[str] = None, cc: Optional[str] = None, 
               bcc: Optional[str] = None, attachments: Optional[List[Dict]] = None) -> Tuple[bool, str, Optional[str]]:
        """Send a reply to an email in the same thread.
        
        Args:
            message_id: Gmail message ID to reply to
            body_text: Plain text body
            body_html: HTML body
            cc: CC recipients
            bcc: BCC recipients
            attachments: List of attachment dictionaries
            
        Returns:
            Tuple of (success, message, reply_message_id)  # CRITICAL FIX: Return reply_message_id
        """
        if not self.service:
            logger.warning("Gmail service not initialized")
            return False, "Gmail service not authenticated", None
        
        try:
            # CRITICAL FIX: Get message with ALL safety check headers
            message = None
            safety_headers = ['From', 'Subject', 'Thread-Id', 'Message-Id', 'References', 
                            'Auto-Submitted', 'X-Auto-Response-Suppress', 'Precedence',
                            'List-Id', 'List-Unsubscribe']
            
            for attempt in range(5):
                try:
                    message = self.service.users().messages().get(
                        userId="me",
                        id=message_id,
                        format="metadata",
                        metadataHeaders=safety_headers
                    ).execute()
                    break
                except HttpError as e:
                    if e.resp.status == 429:
                        sleep_time = (2 ** attempt) + random.random()
                        logger.warning(f"Rate limit exceeded for message {message_id}, retrying in {sleep_time:.2f}s")
                        time.sleep(sleep_time)
                    else:
                        raise
            
            if not message:
                return False, "Failed to get original message", None
            
            # CRITICAL FIX: Extract headers properly
            headers = message.get('payload', {}).get('headers', [])
            header_map = {h['name']: h['value'] for h in headers}
            
            # Extract sender
            sender = header_map.get('From', '')
            if not sender:
                return False, "Could not determine sender from original message", None
            
            # CRITICAL FIX: Comprehensive safety check
            is_safe, skip_reason = self.is_safe_to_reply(sender, header_map)
            if not is_safe:
                logger.info(f"Skipping reply to message {message_id}: {skip_reason}")
                return False, skip_reason, None
            
            # Extract thread ID
            thread_id = message.get('threadId')
            
            # Extract other headers
            subject = header_map.get('Subject', '')
            message_id_header = header_map.get('Message-Id', '')  # CRITICAL: RFC Message-ID
            references = header_map.get('References', '')
            
            # Create reply subject
            reply_subject = f"Re: {subject}" if subject and not subject.lower().startswith('re:') else subject
            
            # CRITICAL FIX: Update references header for proper threading
            # References should be: <original references> <message-id of email we're replying to>
            if message_id_header:
                if references:
                    new_references = f"{references} {message_id_header}"
                else:
                    new_references = message_id_header
            else:
                new_references = references
            
            # CRITICAL FIX 7: Add In-Reply-To & References with RFC Message-ID
            # Send the reply with proper threading headers
            success, message, reply_message_id = self.send_email(
                to=sender,
                subject=reply_subject,
                body_text=body_text,
                body_html=body_html,
                cc=cc,
                bcc=bcc,
                attachments=attachments,
                thread_id=thread_id,  # Gmail thread ID
                in_reply_to=message_id_header,  # CRITICAL: RFC Message-ID for In-Reply-To
                references=new_references  # CRITICAL: RFC Message-IDs for References
            )
            
            return success, message, reply_message_id  # CRITICAL FIX: Return reply_message_id
            
        except Exception as e:
            error_msg = f"Error sending reply: {str(e)}"
            logger.error(error_msg)
            return False, error_msg, None  # CRITICAL FIX: Return None for reply_message_id on error
    
    def _process_html_links(self, html_content):
        """Process HTML content to ensure links are clickable."""
        import re
        
        # Handle None input
        if not html_content:
            return ""
        
        # Pattern to find links without target attribute
        pattern = r'<a\s+(?:[^>]*?\s)?href=["\']([^"\']+)["\'][^>]*>'
        
        def add_target(match):
            link = match.group(0)
            if 'target=' not in link:
                # Add target="_blank" and rel="noopener noreferrer" for security
                if 'rel=' not in link:
                    return link.replace('>', ' target="_blank" rel="noopener noreferrer">')
                else:
                    return link.replace('>', ' target="_blank">')
            return link
        
        # Process all links
        processed_html = re.sub(pattern, add_target, html_content, flags=re.IGNORECASE)
        return processed_html
    
    def _html_to_text(self, html_content):
        """Convert HTML to plain text."""
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html_content, 'html.parser')
            return soup.get_text()
        except ImportError:
            # Fallback if BeautifulSoup is not available
            import re
            # Remove HTML tags
            text = re.sub(r'<[^>]+>', '', html_content)
            return text.strip()
        except Exception as e:
            logger.error(f"Error converting HTML to text: {str(e)}")
            return html_content or ""
    
    @staticmethod
    def get_client_secrets_path() -> str:
        """Get path to client_secrets.json file."""
        # Try multiple possible locations in order of preference
        possible_paths = [
            # Environment variable override (for production)
            os.environ.get('GMAIL_CLIENT_SECRETS_FILE'),
            
            # Current working directory
            os.path.join(os.getcwd(), 'client_secrets.json'),
            
            # Project root using os.path
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'client_secrets.json'),
            
            # Project root using pathlib
            str(Path(__file__).parent.parent / 'client_secrets.json')
        ]
        
        # Return first path that exists
        for path in possible_paths:
            if path and os.path.exists(path):
                logger.info(f"Found client_secrets.json at: {path}")
                return path
        
        # If none found, return default path (will raise FileNotFoundError when used)
        default_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'client_secrets.json')
        logger.warning(f"client_secrets.json not found, defaulting to: {default_path}")
        return default_path
    
    @classmethod
    def get_auth_url(cls, redirect_uri: str) -> Tuple[str, str]:
        """Get authorization URL for OAuth flow."""
        client_secrets_path = cls.get_client_secrets_path()
        
        if not os.path.exists(client_secrets_path):
            raise FileNotFoundError(
                f"client_secrets.json not found. Please download it from Google Cloud Console "
                f"and place it in the project root directory. Expected path: {client_secrets_path}"
            )
        
        # Use consistent scopes across OAuth flow
        scopes = [cls.SCOPE_MODIFY, cls.SCOPE_READONLY, cls.SCOPE_SEND]
        
        flow = Flow.from_client_secrets_file(
            client_secrets_path,
            scopes=scopes,
            redirect_uri=redirect_uri
        )
        
        auth_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent'
        )
        
        logger.info(f"Generated Gmail authorization URL with state: {state}")
        return auth_url, state
    
    @classmethod
    def handle_callback(cls, code: str, redirect_uri: str, user) -> 'GmailService':
        """Handle OAuth callback and store credentials."""
        client_secrets_path = cls.get_client_secrets_path()
        
        # Use same scopes as in get_auth_url
        scopes = [cls.SCOPE_MODIFY, cls.SCOPE_READONLY, cls.SCOPE_SEND]
        
        flow = Flow.from_client_secrets_file(
            client_secrets_path,
            scopes=scopes,
            redirect_uri=redirect_uri
        )
        
        flow.fetch_token(code=code)
        
        # Store credentials
        credentials = flow.credentials
        user.gmail_credentials = credentials.to_json()
        db.session.commit()
        
        logger.info(f"Successfully stored Gmail credentials for user {user.id}")
        return cls(user)
    
    def store_email_in_db(self, email_data, user_id):
        """
        Store an email from Gmail API in the local database.
        
        Args:
            email_data: Dictionary with email data from Gmail API
            user_id: ID of the user who owns the email
            
        Returns:
            Email object or None if failed
        """
        try:
            from app.models.email import Email
            
            # Check if email already exists
            existing_email = Email.query.filter_by(
                user_id=user_id,
                gmail_id=email_data['id']
            ).first()
            
            if existing_email:
                # Update existing email with new data
                existing_email.subject = email_data.get('subject', '')
                existing_email.snippet = email_data.get('snippet', '')
                existing_email.is_read = not email_data.get('is_read', False)
                existing_email.is_starred = email_data.get('is_starred', False)
                # Note: headers field does not exist in Email model
                
                # Only update body if we have it and the email doesn't
                if 'body' in email_data and not existing_email.body_text:
                    body = email_data['body']
                    existing_email.body_text = body.get('text', '')
                    existing_email.body_html = body.get('html', '')
                
                db.session.commit()
                return existing_email
            
            # Create new email record
            email = Email(
                user_id=user_id,
                gmail_id=email_data['id'],
                message_id=email_data.get('message_id', ''),  # RFC Message-ID
                thread_id=email_data.get('threadId', ''),
                sender=email_data.get('sender', ''),
                to=email_data.get('to', ''),
                subject=email_data.get('subject', ''),
                snippet=email_data.get('snippet', ''),
                is_read=not email_data.get('is_read', False),
                is_starred=email_data.get('is_starred', False),
                received_at=datetime.now(pytz.UTC),  # Use sync time, not email Date header
                folder='inbox'  # Default to inbox
            )
            
            # Add body if available
            if 'body' in email_data:
                body = email_data['body']
                email.body_text = body.get('text', '')
                email.body_html = body.get('html', '')
            
            db.session.add(email)
            db.session.commit()
            
            return email
            
        except Exception as e:
            logger.error(f"Error storing email in database: {str(e)}")
            db.session.rollback()
            return None