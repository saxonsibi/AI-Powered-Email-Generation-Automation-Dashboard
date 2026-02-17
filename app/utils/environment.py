# app/utils/environment.py
import os
import sys
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

def get_project_root():
    """Get the project root directory."""
    # Start from the current file and go up until we find a marker
    current = Path(__file__).parent
    
    while current.parent != current:  # Stop at filesystem root
        if (current / 'run.py').exists() or (current / 'app').is_dir():
            return current
        current = current.parent
    
    # Fallback to parent of utils directory
    return Path(__file__).parent.parent

def get_client_secrets_path():
    """Get the path to client_secrets.json file."""
    # Try environment variable first
    env_path = os.environ.get('GMAIL_CLIENT_SECRETS_FILE')
    if env_path and os.path.exists(env_path):
        logger.info(f"Found client_secrets.json from environment variable: {env_path}")
        return env_path
    
    # Try project root
    project_root = get_project_root()
    root_path = project_root / 'client_secrets.json'
    if root_path.exists():
        logger.info(f"Found client_secrets.json in project root: {root_path}")
        return str(root_path)
    
    # Try app directory
    app_path = project_root / 'app' / 'client_secrets.json'
    if app_path.exists():
        logger.info(f"Found client_secrets.json in app directory: {app_path}")
        return str(app_path)
    
    # Try current working directory
    cwd_path = Path.cwd() / 'client_secrets.json'
    if cwd_path.exists():
        logger.info(f"Found client_secrets.json in current working directory: {cwd_path}")
        return str(cwd_path)
    
    # Try parent of current working directory
    parent_cwd_path = Path.cwd().parent / 'client_secrets.json'
    if parent_cwd_path.exists():
        logger.info(f"Found client_secrets.json in parent of current working directory: {parent_cwd_path}")
        return str(parent_cwd_path)
    
    # Return default path (will raise FileNotFoundError)
    default_path = str(project_root / 'client_secrets.json')
    logger.warning(f"client_secrets.json not found, defaulting to: {default_path}")
    return default_path

def get_env_var(key, default=None, required=False):
    """
    Get an environment variable with optional default and requirement validation.
    
    Args:
        key (str): The environment variable key
        default: Default value if the variable is not found
        required (bool): Whether the variable is required
        
    Returns:
        The environment variable value or default
        
    Raises:
        ValueError: If required=True and the variable is not found
    """
    value = os.environ.get(key, default)
    
    if required and value is None:
        raise ValueError(f"Required environment variable '{key}' is not set")
    
    return value

def get_database_url():
    """
    Get the database URL from environment variables.
    
    Returns:
        str: The database URL
    """
    # Check for explicit DATABASE_URL
    database_url = os.environ.get('DATABASE_URL')
    if database_url:
        logger.info("Using DATABASE_URL from environment")
        return database_url
    
    # Build from individual components
    db_host = get_env_var('DB_HOST', 'localhost')
    db_port = get_env_var('DB_PORT', '5432')
    db_name = get_env_var('DB_NAME', 'email_automation')
    db_user = get_env_var('DB_USER', 'postgres')
    db_password = get_env_var('DB_PASSWORD', required=True)
    
    database_url = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    logger.info(f"Built database URL from components: postgresql://{db_user}:****@{db_host}:{db_port}/{db_name}")
    return database_url

def get_redis_url():
    """
    Get the Redis URL from environment variables.
    
    Returns:
        str: The Redis URL
    """
    # Check for explicit REDIS_URL
    redis_url = os.environ.get('REDIS_URL')
    if redis_url:
        logger.info("Using REDIS_URL from environment")
        return redis_url
    
    # Build from individual components
    redis_host = get_env_var('REDIS_HOST', 'localhost')
    redis_port = get_env_var('REDIS_PORT', '6379')
    redis_password = get_env_var('REDIS_PASSWORD', '')
    
    if redis_password:
        redis_url = f"redis://:{redis_password}@{redis_host}:{redis_port}/0"
    else:
        redis_url = f"redis://{redis_host}:{redis_port}/0"
    
    logger.info(f"Built Redis URL: redis://{'****@' if redis_password else ''}{redis_host}:{redis_port}/0")
    return redis_url

def get_secret_key():
    """
    Get the Flask secret key from environment variables.
    
    Returns:
        str: The secret key
    """
    # For development, provide a default if not set
    if is_development():
        return get_env_var('SECRET_KEY', 'dev-secret-key-change-in-production')
    
    return get_env_var('SECRET_KEY', default='dev-secret-key', required=False)


def is_development():
    """
    Check if the application is running in development mode.
    
    Returns:
        bool: True if in development mode, False otherwise
    """
    env = get_env_var('FLASK_ENV', 'production')
    return env.lower() == 'development'

def is_production():
    """
    Check if the application is running in production mode.
    
    Returns:
        bool: True if in production mode, False otherwise
    """
    env = get_env_var('FLASK_ENV', 'production')
    return env.lower() == 'production'

def is_testing():
    """
    Check if the application is running in testing mode.
    
    Returns:
        bool: True if in testing mode, False otherwise
    """
    env = get_env_var('FLASK_ENV', 'production')
    return env.lower() == 'testing'

def get_log_level():
    """
    Get the logging level from environment variables.
    
    Returns:
        str: The logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    level = get_env_var('LOG_LEVEL', 'INFO').upper()
    valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
    
    if level not in valid_levels:
        logger.warning(f"Invalid log level '{level}', defaulting to INFO")
        return 'INFO'
    
    return level

def get_email_config():
    """
    Get email configuration from environment variables.
    
    Returns:
        dict: Email configuration
    """
    return {
        'mail_server': get_env_var('MAIL_SERVER', 'smtp.gmail.com'),
        'mail_port': int(get_env_var('MAIL_PORT', '587')),
        'mail_use_tls': get_env_var('MAIL_USE_TLS', 'True').lower() == 'true',
        'mail_use_ssl': get_env_var('MAIL_USE_SSL', 'False').lower() == 'true',
        'mail_username': get_env_var('MAIL_USERNAME', ''),
        'mail_password': get_env_var('MAIL_PASSWORD', ''),
        'mail_default_sender': get_env_var('MAIL_DEFAULT_SENDER', '')
    }

def get_gmail_config():
    """
    Get Gmail API configuration from environment variables.
    
    Returns:
        dict: Gmail API configuration
    """
    return {
        'client_secrets_path': get_client_secrets_path(),
        'scopes': [
            'https://www.googleapis.com/auth/gmail.modify',
            'https://www.googleapis.com/auth/gmail.readonly',
            'https://www.googleapis.com/auth/gmail.send'
        ]
    }

def get_scheduler_config():
    """
    Get scheduler configuration from environment variables.
    
    Returns:
        dict: Scheduler configuration
    """
    return {
        'enabled': get_env_var('SCHEDULER_ENABLED', 'True').lower() == 'true',
        'timezone': get_env_var('SCHEDULER_TIMEZONE', 'UTC'),
        'email_check_interval': int(get_env_var('EMAIL_CHECK_INTERVAL', '60')),  # seconds
        'follow_up_check_interval': int(get_env_var('FOLLOW_UP_CHECK_INTERVAL', '300')),  # seconds
        'auto_reply_check_interval': int(get_env_var('AUTO_REPLY_CHECK_INTERVAL', '60'))  # seconds
    }

def init_app(app):
    """
    Initialize the app with environment variables.
    
    Args:
        app: Flask app instance
    """
    # Set secret key
    app.config['SECRET_KEY'] = get_secret_key()
    
    # Set database URL
    app.config['SQLALCHEMY_DATABASE_URI'] = get_database_url()
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Set Redis URL
    app.config['REDIS_URL'] = get_redis_url()
    
    # Set email configuration
    email_config = get_email_config()
    for key, value in email_config.items():
        app.config[key.upper()] = value
    
    # Set scheduler configuration
    scheduler_config = get_scheduler_config()
    for key, value in scheduler_config.items():
        app.config[key.upper()] = value
    
    # Set log level
    app.config['LOG_LEVEL'] = get_log_level()
    
    logger.info("Initialized app with environment variables")