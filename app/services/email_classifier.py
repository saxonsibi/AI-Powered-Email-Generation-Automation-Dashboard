# app/services/email_classifier.py
from app import db, logging
from datetime import datetime
import json

logger = logging.getLogger(__name__)

def ensure_default_categories_exist(user_id):
    """
    Ensure default email categories exist for a user.
    
    Args:
        user_id: ID of the user
        
    Returns:
        Boolean indicating success
    """
    try:
        # Import models inside function to avoid circular imports
        from app.models.email import EmailCategory
        
        # Define default categories with colors
        default_categories = [
            {'name': 'Urgent', 'color': '#ff5252', 'is_default': False},
            {'name': 'Important', 'color': '#ff9800', 'is_default': False},
            {'name': 'Work', 'color': '#448aff', 'is_default': False},
            {'name': 'Personal', 'color': '#69f0ae', 'is_default': True},
            {'name': 'Spam', 'color': '#9c27b0', 'is_default': False}
        ]
        
        # Check if user already has categories
        existing_categories = EmailCategory.query.filter_by(user_id=user_id).all()
        existing_category_names = [cat.name for cat in existing_categories]
        
        # Create only the categories that don't exist
        new_categories_created = False
        for cat_data in default_categories:
            if cat_data['name'] not in existing_category_names:
                category = EmailCategory(
                    user_id=user_id,
                    name=cat_data['name'],
                    color=cat_data['color'],
                    is_default=cat_data['is_default']
                )
                db.session.add(category)
                new_categories_created = True
                logger.info(f"Creating category: {cat_data['name']} for user {user_id}")
        
        if new_categories_created:
            db.session.commit()
            logger.info(f"Created default categories for user {user_id}")
        
        return True
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error initializing categories: {str(e)}")
        return False

def classify_email(email_id, user_id):
    """
    Classify an email and store the classification.
    
    Args:
        email_id: ID of the email to classify
        user_id: ID of the user who owns the email
        
    Returns:
        EmailClassification object or None if classification failed
    """
    try:
        # Import models inside function to avoid circular imports
        from app.models.email import Email, EmailCategory, EmailClassification
        from app.models.automation import ClassificationRule
        
        # CRITICAL FIX: Check if email_id is valid
        if not email_id or not isinstance(email_id, int):
            logger.warning(f"Cannot classify email: Invalid email ID provided: {email_id}")
            return None
            
        # Verify email exists in database
        email = Email.query.get(email_id)
        if not email:
            logger.warning(f"Cannot classify email: Email with ID {email_id} not found in database")
            return None
            
        # Ensure default categories exist
        ensure_default_categories_exist(user_id)
            
        # Check if already classified
        existing = EmailClassification.query.filter_by(email_id=email_id).first()
        if existing:
            logger.info(f"Email {email_id} already classified")
            return existing
            
        # Get user's classification rules
        rules = ClassificationRule.query.filter_by(user_id=user_id, is_active=True).order_by(ClassificationRule.priority.desc()).all()
        
        # Apply rule-based classification
        category_id, confidence = apply_rules(email, rules)
        
        # If no rules matched, try keyword-based classification
        if not category_id:
            category_name, confidence = keyword_classify(email.subject, email.body_text or email.snippet or '')
            # Find category ID for the keyword-based classification
            category = EmailCategory.query.filter_by(user_id=user_id, name=category_name).first()
            if category:
                category_id = category.id
                logger.info(f"Keyword classification matched: {category_name} for email {email_id}")
            else:
                # Create the category if it doesn't exist
                category = EmailCategory(
                    user_id=user_id,
                    name=category_name,
                    color="#999999"  # Default color
                )
                db.session.add(category)
                db.session.commit()
                category_id = category.id
                logger.info(f"Created new category: {category_name} for email {email_id}")
        
        # If still no classification, use default category
        if not category_id:
            default_category = EmailCategory.query.filter_by(user_id=user_id, is_default=True).first()
            if default_category:
                category_id = default_category.id
                confidence = 0.1  # Low confidence for default
                logger.info(f"Using default category: {default_category.name} for email {email_id}")
            else:
                # If no default category, use Personal category
                personal_category = EmailCategory.query.filter_by(user_id=user_id, name='Personal').first()
                if personal_category:
                    category_id = personal_category.id
                    confidence = 0.1  # Low confidence for default
                    logger.info(f"Using Personal category for email {email_id}")
                else:
                    # Create Personal category as last resort
                    personal_category = EmailCategory(
                        user_id=user_id,
                        name='Personal',
                        color="#69f0ae",
                        is_default=True
                    )
                    db.session.add(personal_category)
                    db.session.commit()
                    category_id = personal_category.id
                    confidence = 0.1  # Low confidence for default
                    logger.info(f"Created Personal category for email {email_id}")
                
        # Create and store classification
        classification = EmailClassification(
            email_id=email_id,
            category_id=category_id,
            confidence_score=confidence,
            is_manual=False
        )
        
        db.session.add(classification)
        db.session.commit()
        
        # Get the category name for logging
        category = EmailCategory.query.get(category_id)
        logger.info(f"Classified email {email_id} with category {category.name if category else 'Unknown'} (confidence: {confidence})")
        return classification
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error in email classification: {str(e)}")
        return None

def apply_rules(email, rules):
    """
    Apply classification rules to an email.
    
    Args:
        email: Email object
        rules: List of ClassificationRule objects
        
    Returns:
        Tuple of (category_id, confidence_score)
    """
    if not rules:
        return None, 0.0
        
    sender = email.sender.lower() if email.sender else ""
    subject = email.subject.lower() if email.subject else ""
    body = email.body_text.lower() if email.body_text else email.snippet.lower() if email.snippet else ""
    
    for rule in rules:
        try:
            conditions = json.loads(rule.conditions) if rule.conditions else {}
            
            # Check sender conditions
            if 'senders' in conditions and conditions['senders']:
                if not any(s.lower() in sender for s in conditions['senders']):
                    continue
                    
            # Check keyword conditions
            if 'keywords' in conditions and conditions['keywords']:
                if not any(kw.lower() in subject or kw.lower() in body for kw in conditions['keywords']):
                    continue
                    
            # Check domain conditions
            if 'domains' in conditions and conditions['domains']:
                sender_domain = sender.split('@')[-1] if '@' in sender else ''
                if not any(domain.lower() in sender_domain for domain in conditions['domains']):
                    continue
                    
            # If all conditions passed, return this rule's category
            return rule.category_id, 0.8  # High confidence for rule-based matching
            
        except Exception as e:
            logger.error(f"Error applying rule {rule.id}: {str(e)}")
            continue
            
    return None, 0.0

def keyword_classify(email_subject, email_body):
    """
    Rule-based email classification using keyword matching
    Returns classification label and confidence based on content
    
    Args:
        email_subject: Subject of the email
        email_body: Body of the email
        
    Returns:
        Tuple of (classification_label, confidence_score)
    """
    # Define classification rules with keywords
    classification_rules = {
        'Urgent': ['urgent', 'asap', 'critical', 'emergency', 'immediate', 'last chance', 'ends soon', 'expires'],
        'Important': ['important', 'priority', 'attention', 'review', 'update'],
        'Work': ['meeting', 'project', 'deadline', 'report', 'task', 'work', 'developer', 'engineer', 'intern', 'coursera', 'indeed'],
        'Personal': ['family', 'personal', 'friend', 'vacation', 'weekend', 'canva', 'adobe'],
        'Spam': ['lottery', 'winner', 'congratulations', 'free money', 'claim now', 'limited offer', 'act now', 
                 'guaranteed', 'risk free', 'no cost', 'special promotion', 'exclusive deal', 'click here',
                 'unsubscribe', 'viagra', 'cialis', 'casino', 'weight loss', 'make money', 'work from home',
                 'prize', 'award', 'congrats', 'you have won', 'selected', 'guarantee', 'investment opportunity',
                 'congratulations you have won', 'you have been selected', 'limited time offer', 'special discount',
                 'click below', 'act immediately', 'exclusive access', 'free gift', 'no purchase necessary'],
        'Promotional': ['sale', 'discount', 'offer', 'promotion', 'deal', 'buy', 'off', 'price'],
        'Newsletter': ['newsletter', 'subscription', 'update', 'weekly', 'digest'],
        'Finance': ['invoice', 'payment', 'bill', 'transaction', 'account'],
        'Travel': ['booking', 'reservation', 'flight', 'hotel', 'trip'],
        'Default': []  # Fallback classification
    }
    
    # Combine subject and body for analysis
    content = f"{email_subject or ''} {email_body or ''}".lower()
    
    # Score each classification based on keyword matches
    scores = {}
    for classification, keywords in classification_rules.items():
        score = sum(1 for keyword in keywords if keyword in content)
        scores[classification] = score
    
    # Find the classification with the highest score
    best_classification = max(scores.items(), key=lambda x: x[1])
    
    # Calculate confidence based on the score
    max_possible_score = max(len(keywords) for keywords in classification_rules.values())
    confidence = best_classification[1] / max_possible_score if max_possible_score > 0 else 0.0
    
    # Return 'Personal' if no keywords matched (since it's a default category)
    if best_classification[1] == 0:
        return 'Personal', 0.1  # Low confidence for default
    
    return best_classification[0], confidence

def ml_classify(email_data, user_id):
    """
    ML-based classification (placeholder for now).
    
    Args:
        email_data: Dictionary containing email data
        user_id: ID of the user who owns the email
        
    Returns:
        Tuple of (category_id, confidence_score)
    """
    # This is a placeholder for ML-based classification
    # Implement your ML model here
    return None, 0.0

def train_model(training_data, user_id):
    """
    Train ML model with user corrections (placeholder).
    
    Args:
        training_data: Training data
        user_id: ID of the user who owns the data
        
    Returns:
        Boolean indicating success
    """
    # This is a placeholder for model training
    # Implement your model training here
    return True

def store_email_classification(email_id, category_id, confidence_score=0.0):
    """
    Store email classification in the database.
    
    Args:
        email_id: ID of the email
        category_id: ID of the category
        confidence_score: Confidence score of the classification
        
    Returns:
        EmailClassification object or None if failed
    """
    try:
        # Import models inside function to avoid circular imports
        from app.models.email import EmailClassification
        
        # CRITICAL FIX: Check if email_id is valid
        if not email_id or not isinstance(email_id, int):
            logger.warning(f"Cannot store classification: Invalid email ID provided: {email_id}")
            return None
            
        # Check if classification already exists for this email
        existing = EmailClassification.query.filter_by(email_id=email_id).first()
        
        if existing:
            # Update existing classification
            existing.category_id = category_id
            existing.confidence_score = confidence_score
            existing.is_manual = False
            existing.updated_at = datetime.utcnow()
        else:
            # Create new classification record
            new_classification = EmailClassification(
                email_id=email_id,
                category_id=category_id,
                confidence_score=confidence_score,
                is_manual=False
            )
            db.session.add(new_classification)
        
        db.session.commit()
        return existing if existing else new_classification
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error storing email classification: {str(e)}")
        return None

def update_classification_from_user_correction(email_id, category_id, user_id):
    """
    Update classification based on user correction.
    
    Args:
        email_id: ID of the email
        category_id: ID of the new category
        user_id: ID of the user
        
    Returns:
        EmailClassification object or None if failed
    """
    try:
        # Import models inside function to avoid circular imports
        from app.models.email import EmailClassification
        
        # Check if classification already exists for this email
        existing = EmailClassification.query.filter_by(email_id=email_id).first()
        
        if existing:
            # Update existing classification
            existing.category_id = category_id
            existing.is_manual = True
            existing.updated_at = datetime.utcnow()
        else:
            # Create new classification record
            new_classification = EmailClassification(
                email_id=email_id,
                category_id=category_id,
                confidence_score=1.0,  # High confidence for manual classification
                is_manual=True
            )
            db.session.add(new_classification)
        
        db.session.commit()
        
        # Use this as training data for the ML model
        train_model({
            'email_id': email_id,
            'category_id': category_id,
            'user_id': user_id
        }, user_id)
        
        return existing if existing else new_classification
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating email classification: {str(e)}")
        return None

def batch_classify_emails(user_id, limit=50):
    """
    Classify a batch of unclassified emails for a user.
    
    Args:
        user_id: ID of the user
        limit: Maximum number of emails to classify
        
    Returns:
        Dictionary with success status and count of classified emails
    """
    try:
        # Import models inside function to avoid circular imports
        from app.models.email import Email, EmailClassification
        
        # Ensure default categories exist
        ensure_default_categories_exist(user_id)
        
        # Get all unclassified emails for the user
        unclassified_emails = Email.query.outerjoin(EmailClassification).filter(
            EmailClassification.id.is_(None),
            Email.user_id == user_id
        ).limit(limit).all()
        
        logger.info(f"Found {len(unclassified_emails)} unclassified emails for user {user_id}")
        
        classified_count = 0
        for email in unclassified_emails:
            # Classify the email
            classification = classify_email(email.id, user_id)
            if classification:
                classified_count += 1
                logger.info(f"Successfully classified email {email.id}")
            else:
                logger.warning(f"Failed to classify email {email.id}")
        
        logger.info(f"Classified {classified_count} out of {len(unclassified_emails)} emails for user {user_id}")
        
        return {
            'success': True,
            'count': classified_count,
            'message': f'Classified {classified_count} emails'
        }
        
    except Exception as e:
        logger.error(f"Error in batch email classification: {str(e)}")
        return {
            'success': False,
            'count': 0,
            'message': f'Error: {str(e)}'
        }

# NEW: Function to safely classify an email after storing it
def classify_email_after_storing(email_data, user_id):
    """
    Safely classify an email after it has been stored in the database.
    
    Args:
        email_data: Dictionary containing email data
        user_id: ID of the user who owns the email
        
    Returns:
        EmailClassification object or None if classification failed
    """
    try:
        # Import models inside function to avoid circular imports
        from app.models.email import Email
        
        # Check if email_data has an ID
        if not email_data or not hasattr(email_data, 'id') or not email_data.id:
            logger.warning("Cannot classify email: Invalid email data or missing ID")
            return None
        
        # Ensure default categories exist
        ensure_default_categories_exist(user_id)
        
        # Classify the email
        return classify_email(email_data.id, user_id)
        
    except Exception as e:
        logger.error(f"Error in classify_email_after_storing: {str(e)}")
        return None

# NEW: Function to initialize and classify all emails for a user
def initialize_and_classify_all_emails(user_id):
    """
    Initialize default categories and classify all emails for a user.
    
    Args:
        user_id: ID of the user
        
    Returns:
        Dictionary with success status and count of classified emails
    """
    try:
        # Ensure default categories exist
        ensure_default_categories_exist(user_id)
        
        # Classify all emails
        return batch_classify_emails(user_id, limit=1000)  # Use a high limit to classify all emails
        
    except Exception as e:
        logger.error(f"Error initializing and classifying emails: {str(e)}")
        return {
            'success': False,
            'count': 0,
            'message': f'Error: {str(e)}'
        }

# NEW: Function to check if an email is spam
def is_spam(email_id, user_id):
    """
    Check if an email is classified as spam.
    
    Args:
        email_id: ID of the email
        user_id: ID of the user
        
    Returns:
        Boolean indicating if the email is spam
    """
    try:
        # Import models inside function to avoid circular imports
        from app.models.email import Email, EmailClassification, EmailCategory
        
        # Get the email classification
        classification = EmailClassification.query.filter_by(email_id=email_id).first()
        if not classification:
            return False
            
        # Get the category
        category = EmailCategory.query.filter_by(id=classification.category_id, user_id=user_id).first()
        if not category:
            return False
            
        # Check if the category is Spam
        return category.name == 'Spam'
        
    except Exception as e:
        logger.error(f"Error checking if email is spam: {str(e)}")
        return False

# NEW: Function to mark an email as spam
def mark_as_spam(email_id, user_id):
    """
    Mark an email as spam.
    
    Args:
        email_id: ID of the email
        user_id: ID of the user
        
    Returns:
        EmailClassification object or None if failed
    """
    try:
        # Import models inside function to avoid circular imports
        from app.models.email import EmailCategory
        
        # Get the Spam category
        spam_category = EmailCategory.query.filter_by(user_id=user_id, name='Spam').first()
        if not spam_category:
            # Create the Spam category if it doesn't exist
            spam_category = EmailCategory(
                user_id=user_id,
                name='Spam',
                color='#9c27b0',
                is_default=False
            )
            db.session.add(spam_category)
            db.session.commit()
        
        # Update the classification
        return update_classification_from_user_correction(email_id, spam_category.id, user_id)
        
    except Exception as e:
        logger.error(f"Error marking email as spam: {str(e)}")
        return None

# NEW: Function to get classification statistics
def get_classification_stats(user_id):
    """
    Get statistics for email classifications.
    
    Args:
        user_id: ID of the user
        
    Returns:
        Dictionary with classification counts
    """
    try:
        # Import models inside function to avoid circular imports
        from app.models.email import Email, EmailClassification, EmailCategory
        
        # Ensure default categories exist
        ensure_default_categories_exist(user_id)
        
        # Get all categories for the user
        categories = EmailCategory.query.filter_by(user_id=user_id).all()
        
        # Initialize stats with all categories
        stats = {cat.name: 0 for cat in categories}
        
        # Get all emails for the user
        emails = Email.query.filter_by(user_id=user_id).all()
        
        # Count unclassified emails
        unclassified_count = 0
        
        for email in emails:
            # Get classification for this email
            classification = EmailClassification.query.filter_by(email_id=email.id).first()
            
            if classification:
                # Get category name
                category = EmailCategory.query.filter_by(id=classification.category_id).first()
                if category and category.name in stats:
                    stats[category.name] += 1
                    logger.debug(f"Email {email.id} counted as {category.name}")
            else:
                unclassified_count += 1
                logger.debug(f"Email {email.id} is unclassified")
        
        # Add unclassified count
        stats['unclassified'] = unclassified_count
        
        logger.info(f"Classification stats for user {user_id}: {stats}")
        
        return stats
        
    except Exception as e:
        logger.error(f"Error getting classification stats: {str(e)}")
        return {}

# NEW: Function to fetch and classify all Gmail emails for a user
def fetch_and_classify_all_gmail_emails(user_id):
    """
    Fetch all Gmail emails for a user and classify them.
    
    Args:
        user_id: ID of the user
        
    Returns:
        Dictionary with success status and count of classified emails
    """
    try:
        # Import models inside function to avoid circular imports
        from app.models.email import Email, EmailClassification
        
        # Ensure default categories exist
        ensure_default_categories_exist(user_id)
        
        # Try to import gmail_service, but handle the case where it doesn't exist
        try:
            from app.services.gmail_service import fetch_all_emails
            
            # Fetch all emails from Gmail
            result = fetch_all_emails(user_id)
            
            if not result.get('success', False):
                logger.error(f"Failed to fetch emails from Gmail: {result.get('message', 'Unknown error')}")
                return {
                    'success': False,
                    'count': 0,
                    'message': f'Failed to fetch emails: {result.get("message", "Unknown error")}'
                }
        except ImportError:
            logger.warning("Gmail service not available, proceeding with existing emails")
        
        # Get all emails for the user
        emails = Email.query.filter_by(user_id=user_id).all()
        
        logger.info(f"Found {len(emails)} emails for user {user_id}")
        
        # Classify all emails
        classified_count = 0
        for email in emails:
            # Check if already classified
            existing = EmailClassification.query.filter_by(email_id=email.id).first()
            if existing:
                logger.info(f"Email {email.id} already classified")
                continue
                
            # Classify the email
            classification = classify_email(email.id, user_id)
            if classification:
                classified_count += 1
                logger.info(f"Successfully classified email {email.id}")
            else:
                logger.warning(f"Failed to classify email {email.id}")
        
        logger.info(f"Classified {classified_count} out of {len(emails)} emails for user {user_id}")
        
        return {
            'success': True,
            'count': classified_count,
            'message': f'Fetched and classified {classified_count} emails'
        }
        
    except Exception as e:
        logger.error(f"Error fetching and classifying Gmail emails: {str(e)}")
        return {
            'success': False,
            'count': 0,
            'message': f'Error: {str(e)}'
        }

# NEW: Function to automatically classify new emails as they arrive
def auto_classify_new_emails(user_id):
    """
    Automatically classify new emails that haven't been classified yet.
    
    Args:
        user_id: ID of the user
        
    Returns:
        Dictionary with success status and count of classified emails
    """
    try:
        # Import models inside function to avoid circular imports
        from app.models.email import Email, EmailClassification
        
        # Ensure default categories exist
        ensure_default_categories_exist(user_id)
        
        # Try to import gmail_service, but handle the case where it doesn't exist
        try:
            from app.services.gmail_service import fetch_new_emails
            
            # Fetch new emails from Gmail
            result = fetch_new_emails(user_id)
            
            if not result.get('success', False):
                logger.error(f"Failed to fetch new emails from Gmail: {result.get('message', 'Unknown error')}")
                return {
                    'success': False,
                    'count': 0,
                    'message': f'Failed to fetch new emails: {result.get("message", "Unknown error")}'
                }
        except ImportError:
            logger.warning("Gmail service not available, proceeding with existing emails")
        
        # Get unclassified emails for the user
        unclassified_emails = Email.query.outerjoin(EmailClassification).filter(
            EmailClassification.id.is_(None),
            Email.user_id == user_id
        ).all()
        
        logger.info(f"Found {len(unclassified_emails)} unclassified emails for user {user_id}")
        
        # Classify all unclassified emails
        classified_count = 0
        for email in unclassified_emails:
            # Classify the email
            classification = classify_email(email.id, user_id)
            if classification:
                classified_count += 1
                logger.info(f"Successfully classified email {email.id}")
            else:
                logger.warning(f"Failed to classify email {email.id}")
        
        logger.info(f"Classified {classified_count} out of {len(unclassified_emails)} emails for user {user_id}")
        
        return {
            'success': True,
            'count': classified_count,
            'message': f'Classified {classified_count} new emails'
        }
        
    except Exception as e:
        logger.error(f"Error auto-classifying new emails: {str(e)}")
        return {
            'success': False,
            'count': 0,
            'message': f'Error: {str(e)}'
        }