# app/services/user_service.py
from flask import flash
from app import db, logger
from datetime import datetime, time
import json
import logging

logger = logging.getLogger(__name__)

def create_user(username, email, password):
    """
    Create a new user safely, checking for duplicates.
    
    Args:
        username (str): The username for the new user
        email (str): The email for the new user
        password (str): The password for the new user
        
    Returns:
        tuple: (success: bool, user: User or None, error: str or None)
    """
    try:
        # Import models inside function to avoid circular imports
        from app.models.user import User
        from app.utils.database import safe_db_commit
        
        # Check if username already exists
        if User.username_exists(username):
            return False, None, 'username_exists'
        
        # Check if email already exists
        if User.email_exists(email):
            return False, None, 'email_exists'
        
        # Create new user
        new_user = User(username=username, email=email)
        new_user.set_password(password)
        
        # Add to database session
        db.session.add(new_user)
        
        # Try to commit with error handling
        success, error_type = safe_db_commit("user creation")
        
        if success:
            flash('Account created successfully! You can now log in.', 'success')
            logger.info(f"Created new user: {username}")
            return True, new_user, None
        else:
            return False, None, error_type
            
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creating user: {str(e)}")
        return False, None, 'database_error'

def get_user(user_id):
    """
    Get a user by ID.
    
    Args:
        user_id (int): The ID of the user to retrieve
        
    Returns:
        User object or None if not found
    """
    try:
        # Import models inside function to avoid circular imports
        from app.models.user import User
        
        user = User.query.get(user_id)
        return user
        
    except Exception as e:
        logger.error(f"Error getting user {user_id}: {str(e)}")
        return None

def get_user_by_email(email):
    """
    Get a user by email.
    
    Args:
        email (str): The email of the user to retrieve
        
    Returns:
        User object or None if not found
    """
    try:
        # Import models inside function to avoid circular imports
        from app.models.user import User
        
        user = User.query.filter_by(email=email).first()
        return user
        
    except Exception as e:
        logger.error(f"Error getting user by email {email}: {str(e)}")
        return None

def update_user_profile(user_id, data):
    """
    Update a user's profile information.
    
    Args:
        user_id (int): The ID of the user to update
        data (dict): Dictionary containing the fields to update
        
    Returns:
        tuple: (success: bool, user: User or None, error: str or None)
    """
    try:
        # Import models inside function to avoid circular imports
        from app.models.user import User
        
        user = User.query.get(user_id)
        if not user:
            return False, None, 'user_not_found'
        
        # Update allowed fields
        if 'username' in data and data['username'] != user.username:
            # Check if username already exists
            if User.username_exists(data['username']):
                return False, None, 'username_exists'
            user.username = data['username']
        
        if 'email' in data and data['email'] != user.email:
            # Check if email already exists
            if User.email_exists(data['email']):
                return False, None, 'email_exists'
            user.email = data['email']
        
        if 'first_name' in data:
            user.first_name = data['first_name']
            
        if 'last_name' in data:
            user.last_name = data['last_name']
        
        # Update the database
        db.session.commit()
        
        logger.info(f"Updated profile for user {user_id}")
        return True, user, None
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating user profile: {str(e)}")
        return False, None, 'database_error'

def update_user_password(user_id, new_password):
    """
    Update a user's password.
    
    Args:
        user_id (int): The ID of the user to update
        new_password (str): The new password
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Import models inside function to avoid circular imports
        from app.models.user import User
        
        user = User.query.get(user_id)
        if not user:
            logger.warning(f"Attempted to update password for non-existent user {user_id}")
            return False
        
        user.set_password(new_password)
        db.session.commit()
        
        logger.info(f"Updated password for user {user_id}")
        return True
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating user password: {str(e)}")
        return False

def update_user_preferences(user_id, preferences):
    """
    Update a user's preferences.
    
    Args:
        user_id (int): The ID of the user to update
        preferences (dict): Dictionary containing the preferences
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Import models inside function to avoid circular imports
        from app.models.user import User
        
        user = User.query.get(user_id)
        if not user:
            logger.warning(f"Attempted to update preferences for non-existent user {user_id}")
            return False
        
        # Serialize preferences to JSON
        user.preferences = json.dumps(preferences)
        db.session.commit()
        
        logger.info(f"Updated preferences for user {user_id}")
        return True
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating user preferences: {str(e)}")
        return False

def get_user_preferences(user_id):
    """
    Get a user's preferences.
    
    Args:
        user_id (int): The ID of the user
        
    Returns:
        dict: User preferences or empty dict if not found
    """
    try:
        # Import models inside function to avoid circular imports
        from app.models.user import User
        
        user = User.query.get(user_id)
        if not user or not user.preferences:
            return {}
        
        # Deserialize preferences from JSON
        return json.loads(user.preferences)
        
    except Exception as e:
        logger.error(f"Error getting user preferences: {str(e)}")
        return {}

def update_business_hours(user_id, business_hours):
    """
    Update a user's business hours.
    
    Args:
        user_id (int): The ID of the user to update
        business_hours (dict): Dictionary containing business hours with timezone
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Import models inside function to avoid circular imports
        from app.models.user import User
        
        user = User.query.get(user_id)
        if not user:
            logger.warning(f"Attempted to update business hours for non-existent user {user_id}")
            return False
        
        # Serialize business hours to JSON
        user.business_hours = json.dumps(business_hours)
        db.session.commit()
        
        logger.info(f"Updated business hours for user {user_id}")
        return True
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating business hours: {str(e)}")
        return False

def get_business_hours(user_id):
    """
    Get a user's business hours.
    
    Args:
        user_id (int): The ID of the user
        
    Returns:
        dict: Business hours or default hours if not found
    """
    try:
        # Import models inside function to avoid circular imports
        from app.models.user import User
        
        user = User.query.get(user_id)
        if not user or not user.business_hours:
            # Return default business hours
            return {
                'timezone': 'UTC',
                'days': {
                    'monday': {'start': '09:00', 'end': '17:00', 'enabled': True},
                    'tuesday': {'start': '09:00', 'end': '17:00', 'enabled': True},
                    'wednesday': {'start': '09:00', 'end': '17:00', 'enabled': True},
                    'thursday': {'start': '09:00', 'end': '17:00', 'enabled': True},
                    'friday': {'start': '09:00', 'end': '17:00', 'enabled': True},
                    'saturday': {'start': '09:00', 'end': '17:00', 'enabled': False},
                    'sunday': {'start': '09:00', 'end': '17:00', 'enabled': False}
                }
            }
        
        # Deserialize business hours from JSON
        return json.loads(user.business_hours)
        
    except Exception as e:
        logger.error(f"Error getting business hours: {str(e)}")
        return {}

def is_within_business_hours(user_id):
    """
    Check if the current time is within a user's business hours.
    
    Args:
        user_id (int): The ID of the user
        
    Returns:
        bool: True if within business hours, False otherwise
    """
    try:
        # Import models inside function to avoid circular imports
        from app.models.user import User
        
        business_hours = get_business_hours(user_id)
        
        # Get current time in user's timezone
        import pytz
        timezone = pytz.timezone(business_hours.get('timezone', 'UTC'))
        now = datetime.now(timezone)
        
        # Get current day of week (lowercase)
        current_day = now.strftime('%A').lower()
        
        # Check if today is enabled
        day_config = business_hours.get('days', {}).get(current_day, {})
        if not day_config.get('enabled', False):
            return False
        
        # Parse start and end times
        start_time_str = day_config.get('start', '09:00')
        end_time_str = day_config.get('end', '17:00')
        
        start_hour, start_minute = map(int, start_time_str.split(':'))
        end_hour, end_minute = map(int, end_time_str.split(':'))
        
        start_time = time(start_hour, start_minute)
        end_time = time(end_hour, end_minute)
        current_time = now.time()
        
        # Check if current time is within business hours
        return start_time <= current_time <= end_time
        
    except Exception as e:
        logger.error(f"Error checking business hours: {str(e)}")
        # Default to True if there's an error (to avoid missing important emails)
        return True

def store_gmail_credentials(user_id, credentials):
    """
    Store Gmail OAuth credentials for a user.
    
    Args:
        user_id (int): The ID of the user
        credentials (Credentials): Google OAuth credentials object
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Import models inside function to avoid circular imports
        from app.models.user import User
        
        user = User.query.get(user_id)
        if not user:
            logger.warning(f"Attempted to store Gmail credentials for non-existent user {user_id}")
            return False
        
        # Store credentials as JSON
        user.gmail_credentials = credentials.to_json()
        db.session.commit()
        
        logger.info(f"Stored Gmail credentials for user {user_id}")
        return True
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error storing Gmail credentials: {str(e)}")
        return False

def delete_user(user_id):
    """
    Delete a user and all associated data.
    
    Args:
        user_id (int): The ID of the user to delete
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Import models inside function to avoid circular imports
        from app.models.user import User
        
        user = User.query.get(user_id)
        if not user:
            logger.warning(f"Attempted to delete non-existent user {user_id}")
            return False
        
        # Delete the user (this will cascade delete related records)
        db.session.delete(user)
        db.session.commit()
        
        logger.info(f"Deleted user {user_id}")
        return True
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting user: {str(e)}")
        return False