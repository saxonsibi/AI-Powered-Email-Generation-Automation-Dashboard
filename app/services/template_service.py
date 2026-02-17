# app/services/template_service.py

from app import logging
import re
from datetime import datetime

logger = logging.getLogger(__name__)

def generate_auto_reply(email, classification=None):
    """
    Generate an auto-reply based on the email and classification.
    
    Args:
        email: Email object
        classification: EmailClassification object or None
        
    Returns:
        String containing the auto-reply
    """
    try:
        # Import models inside function to avoid circular imports
        from app.models.email import Email
        from app.models.automation import EmailClassification
        
        # Extract context from email
        sender = email.sender
        subject = email.subject
        category = classification.category.name if classification and classification.category else "Unclassified"
        is_urgent = "Urgent" if classification and classification.confidence_score > 0.7 else "Normal"
        
        # Create the prompt with context
        prompt = f"""You are an automated email reply assistant.

Rules:
- This is an auto-reply, NOT a conversation.
- Do NOT answer questions.
- Do NOT promise actions.
- Do NOT ask follow-up questions.
- Be polite, short, and professional.
- Maximum 2-3 sentences.

Context:
Sender email: {sender}
Email subject: {subject}
Email category: {category}
Urgency: {is_urgent}

Auto-reply:"""
        
        # For now, return a simple template
        # In a real implementation, you would send this to an AI service
        return generate_simple_reply(category, is_urgent)
        
    except Exception as e:
        logger.error(f"Error in generate_auto_reply: {str(e)}")
        return "Thank you for your email. I'll get back to you as soon as possible."

def generate_simple_reply(category, is_urgent):
    """
    Generate a simple reply based on category and urgency.
    
    Args:
        category: String containing the email category
        is_urgent: String indicating urgency
        
    Returns:
        String containing the reply
    """
    try:
        # Define templates for different categories
        templates = {
            "Work": "Thank you for your work-related email. I'll review it and get back to you soon.",
            "Personal": "Thank you for your message. I appreciate you reaching out and will respond when I'm able.",
            "Newsletter": "Thank you for the newsletter. I appreciate being kept in the loop.",
            "Promotion": "Thank you for the information. I'll review it at my earliest convenience.",
            "Unclassified": "Thank you for your email. I'll get back to you as soon as possible."
        }
        
        # Get the appropriate template
        template = templates.get(category, templates["Unclassified"])
        
        # Adjust for urgency if needed
        if is_urgent == "Urgent" and category != "Newsletter":
            template = "Thank you for your urgent message. I'll prioritize my response and get back to you shortly."
            
        return template
        
    except Exception as e:
        logger.error(f"Error in generate_simple_reply: {str(e)}")
        return "Thank you for your email. I'll get back to you as soon as possible."

def generate_follow_up_template(original_email, follow_up_number):
    """
    Generate a follow-up template based on the original email and follow-up number.
    
    Args:
        original_email: The original sent email
        follow_up_number: The follow-up sequence number (1, 2, 3, etc.)
        
    Returns:
        String containing the follow-up message
    """
    try:
        # Import models inside function to avoid circular imports
        from app.models.email import SentEmail
        
        # Define follow-up templates based on sequence number
        if follow_up_number == 1:
            return f"Hi, just following up on my previous email regarding '{original_email.subject}'. I wanted to make sure you received it."
        elif follow_up_number == 2:
            return f"Hi, I'm following up again about '{original_email.subject}'. I'd appreciate your response when you have a moment."
        elif follow_up_number == 3:
            return f"Hi, I've sent a couple of emails about '{original_email.subject}' without response. Is this still a priority for you?"
        else:
            return f"Hi, this is my {follow_up_number}th follow-up regarding '{original_email.subject}'. I'll assume you're not interested at this point and won't send further messages."
            
    except Exception as e:
        logger.error(f"Error in generate_follow_up_template: {str(e)}")
        return f"Hi, just following up on my previous email regarding '{original_email.subject}'."

def extract_email_context(email):
    """
    Extract relevant context from an email for template generation.
    
    Args:
        email: Email object
        
    Returns:
        Dictionary containing email context
    """
    try:
        # Import models inside function to avoid circular imports
        from app.models.email import Email
        
        # Extract key information
        sender_name = extract_name_from_email(email.sender)
        is_first_time = check_if_first_time_sender(email.sender, email.user_id)
        
        # Determine if email is a reply
        is_reply = email.subject.lower().startswith('re:')
        
        # Extract key entities from email body
        entities = extract_entities(email.body_text if hasattr(email, 'body_text') else email.body)
        
        return {
            'sender_name': sender_name,
            'sender_email': email.sender,
            'is_first_time': is_first_time,
            'is_reply': is_reply,
            'subject': email.subject,
            'entities': entities,
            'has_attachments': hasattr(email, 'has_attachments') and email.has_attachments
        }
        
    except Exception as e:
        logger.error(f"Error in extract_email_context: {str(e)}")
        return {}

def extract_name_from_email(email_address):
    """
    Extract name from email address.
    
    Args:
        email_address: Email address string
        
    Returns:
        String containing the extracted name or the email address if name not found
    """
    try:
        # Pattern to match "Name <email@domain.com>" format
        match = re.match(r'^(.+?)\s*<([^>]+)>$', email_address)
        if match:
            return match.group(1).strip()
        
        # If no name in the format, return the part before @
        if '@' in email_address:
            return email_address.split('@')[0]
        
        return email_address
        
    except Exception as e:
        logger.error(f"Error in extract_name_from_email: {str(e)}")
        return email_address

def check_if_first_time_sender(email_address, user_id):
    """
    Check if this is the first time receiving an email from this sender.
    
    Args:
        email_address: Email address string
        user_id: ID of the user
        
    Returns:
        Boolean indicating if this is the first time sender
    """
    try:
        # Import models inside function to avoid circular imports
        from app.models.email import Email
        
        # Check if we have received emails from this sender before
        previous_emails = Email.query.filter_by(
            sender=email_address, 
            user_id=user_id
        ).count()
        
        return previous_emails <= 1  # Current email is the first or second one
        
    except Exception as e:
        logger.error(f"Error in check_if_first_time_sender: {str(e)}")
        return False

def extract_entities(text):
    """
    Extract key entities from email text.
    
    Args:
        text: Email body text
        
    Returns:
        Dictionary containing extracted entities
    """
    try:
        if not text:
            return {}
        
        entities = {}
        
        # Extract dates
        date_pattern = r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b|\b\d{4}[/-]\d{1,2}[/-]\d{1,2}\b'
        dates = re.findall(date_pattern, text)
        if dates:
            entities['dates'] = dates
        
        # Extract phone numbers
        phone_pattern = r'\b(?:\+?(\d{1,3}))?[-. (]*(\d{3})[-. )]*(\d{3})[-. ]*(\d{4})\b'
        phones = re.findall(phone_pattern, text)
        if phones:
            entities['phone_numbers'] = [''.join(phone) for phone in phones]
        
        # Extract URLs
        url_pattern = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
        urls = re.findall(url_pattern, text)
        if urls:
            entities['urls'] = urls
        
        # Extract money amounts
        money_pattern = r'\$\d+(?:,\d{3})*(?:\.\d{2})?'
        money = re.findall(money_pattern, text)
        if money:
            entities['money'] = money
        
        return entities
        
    except Exception as e:
        logger.error(f"Error in extract_entities: {str(e)}")
        return {}

def personalize_template(template, context):
    """
    Personalize a template with context information.
    
    Args:
        template: Template string with placeholders
        context: Dictionary containing context information
        
    Returns:
        Personalized template string
    """
    try:
        if not template or not context:
            return template
        
        # Replace common placeholders
        personalized = template.replace('{sender_name}', context.get('sender_name', 'there'))
        personalized = personalized.replace('{current_date}', datetime.now().strftime('%B %d, %Y'))
        personalized = personalized.replace('{current_time}', datetime.now().strftime('%I:%M %p'))
        
        # Replace custom placeholders if they exist
        for key, value in context.items():
            if isinstance(value, str):
                placeholder = '{' + key + '}'
                personalized = personalized.replace(placeholder, value)
        
        return personalized
        
    except Exception as e:
        logger.error(f"Error in personalize_template: {str(e)}")
        return template

def generate_template_from_rule(rule, email_context):
    """
    Generate a template based on an automation rule and email context.
    
    Args:
        rule: AutomationRule object
        email_context: Dictionary containing email context
        
    Returns:
        Generated template string
    """
    try:
        # Import models inside function to avoid circular imports
        from app.models.automation import AutomationRule
        
        # Get the template text from the rule
        template = rule.template_text
        
        # Personalize the template with context
        personalized_template = personalize_template(template, email_context)
        
        return personalized_template
        
    except Exception as e:
        logger.error(f"Error in generate_template_from_rule: {str(e)}")
        return rule.template_text if rule else "Thank you for your email. I'll get back to you as soon as possible."