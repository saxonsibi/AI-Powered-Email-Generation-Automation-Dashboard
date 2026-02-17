# config.py
import os
import secrets
from datetime import timedelta

class Config:
    # Generate a secure random key if not provided
    SECRET_KEY = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
    SECURITY_PASSWORD_SALT = os.environ.get('SECURITY_PASSWORD_SALT') or secrets.token_hex(16)
    
    # Database settings
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///app.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
        'pool_size': 10,
        'max_overflow': 20
    }
    
    # Gmail OAuth settings
    GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID')
    GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET')
    GMAIL_CLIENT_SECRETS_FILE = os.environ.get('GMAIL_CLIENT_SECRETS_FILE') or 'client_secrets.json'
    
    # Email settings
    MAIL_SERVER = os.environ.get('MAIL_SERVER')
    MAIL_PORT = int(os.environ.get('MAIL_PORT') or 587)
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() in ['true', 'on', '1']
    MAIL_USE_SSL = os.environ.get('MAIL_USE_SSL', 'false').lower() in ['true', 'on', '1']
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER')
    
    # Upload settings
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB
    ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'csv', 'xlsx', 'doc', 'docx'}
    
    # Session settings
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    SESSION_COOKIE_SECURE = os.environ.get('FLASK_ENV') == 'production'
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    
    # App settings
    APP_NAME = 'AI Email Dashboard'
    VERSION = '1.0.0'
    
    # CRITICAL FIX: Scheduler configuration
    SCHEDULER_API_ENABLED = True
    # CRITICAL FIX: Set timezone to Asia/Kolkata for India time
    SCHEDULER_TIMEZONE = os.environ.get('SCHEDULER_TIMEZONE', 'Asia/Kolkata')
    JOBS = []
    
    # CRITICAL FIX: Email check intervals in seconds
    EMAIL_CHECK_INTERVAL_MINUTES = int(os.environ.get('EMAIL_CHECK_INTERVAL_MINUTES', 10))  # Check for new emails every 10 minutes
    FOLLOW_UP_CHECK_INTERVAL_MINUTES = int(os.environ.get('FOLLOW_UP_CHECK_INTERVAL_MINUTES', 1))  # Check for follow-ups every 1 minute
    AUTO_REPLY_CHECK_INTERVAL_MINUTES = int(os.environ.get('AUTO_REPLY_CHECK_INTERVAL_MINUTES', 1))  # Check for auto-replies every 1 minute
    
    # CRITICAL FIX: Legacy interval settings for backward compatibility
    EMAIL_CHECK_INTERVAL = EMAIL_CHECK_INTERVAL_MINUTES * 60
    FOLLOW_UP_CHECK_INTERVAL = FOLLOW_UP_CHECK_INTERVAL_MINUTES * 60
    AUTO_REPLY_CHECK_INTERVAL = AUTO_REPLY_CHECK_INTERVAL_MINUTES * 60
    
    # Automation settings
    MAX_FOLLOW_UPS = int(os.environ.get('MAX_FOLLOW_UPS', 3))  # Maximum number of follow-ups per email
    DEFAULT_FOLLOW_UP_DELAY = int(os.environ.get('DEFAULT_FOLLOW_UP_DELAY', 24))  # Default delay in hours
    AUTO_REPLY_COOLDOWN = int(os.environ.get('AUTO_REPLY_COOLDOWN', 300))  # Cooldown period in seconds
    
    # Business hours settings
    BUSINESS_HOURS_START = int(os.environ.get('BUSINESS_HOURS_START', 9))  # 9 AM
    BUSINESS_HOURS_END = int(os.environ.get('BUSINESS_HOURS_END', 18))  # 6 PM
    BUSINESS_DAYS_ONLY = os.environ.get('BUSINESS_DAYS_ONLY', 'true').lower() in ['true', 'on', '1']
    
    # Logging configuration
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
    LOG_FILE = os.environ.get('LOG_FILE') or 'app.log'
    LOG_MAX_BYTES = int(os.environ.get('LOG_MAX_BYTES', 10485760))  # 10MB
    LOG_BACKUP_COUNT = int(os.environ.get('LOG_BACKUP_COUNT', 5))
    LOG_FORMAT = '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    
    # AI service settings
    AI_SERVICE_URL = os.environ.get('AI_SERVICE_URL')
    AI_SERVICE_API_KEY = os.environ.get('AI_SERVICE_API_KEY')
    AI_SERVICE_MODEL = os.environ.get('AI_SERVICE_MODEL', 'gpt-3.5-turbo')
    AI_SERVICE_MAX_TOKENS = int(os.environ.get('AI_SERVICE_MAX_TOKENS', 1000))
    AI_SERVICE_TEMPERATURE = float(os.environ.get('AI_SERVICE_TEMPERATURE', 0.7))
    
    # Rate limiting
    RATELIMIT_STORAGE_URL = os.environ.get('RATELIMIT_STORAGE_URL') or 'memory://'
    RATELIMIT_DEFAULT = os.environ.get('RATELIMIT_DEFAULT') or '200 per day, 50 per hour'
    
    # Security settings
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = int(os.environ.get('WTF_CSRF_TIME_LIMIT', 3600))
    
    # Cache settings
    CACHE_TYPE = os.environ.get('CACHE_TYPE', 'simple')
    CACHE_DEFAULT_TIMEOUT = int(os.environ.get('CACHE_DEFAULT_TIMEOUT', 300))
    
    # Pagination settings
    ITEMS_PER_PAGE = int(os.environ.get('ITEMS_PER_PAGE', 20))
    MAX_SEARCH_RESULTS = int(os.environ.get('MAX_SEARCH_RESULTS', 50))

class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get('DEV_DATABASE_URL') or 'sqlite:///dev.db'
    
    # Development-specific settings
    SCHEDULER_API_ENABLED = True
    
    # CRITICAL FIX: Longer intervals in development to avoid overwhelming the system
    EMAIL_CHECK_INTERVAL_MINUTES = int(os.environ.get('EMAIL_CHECK_INTERVAL_MINUTES', 10))  # 10 minutes in development
    FOLLOW_UP_CHECK_INTERVAL_MINUTES = int(os.environ.get('FOLLOW_UP_CHECK_INTERVAL_MINUTES', 1))  # 1 minute in development
    AUTO_REPLY_CHECK_INTERVAL_MINUTES = int(os.environ.get('AUTO_REPLY_CHECK_INTERVAL_MINUTES', 5))  # 5 minutes in development
    
    # Update legacy interval settings
    EMAIL_CHECK_INTERVAL = EMAIL_CHECK_INTERVAL_MINUTES * 60
    FOLLOW_UP_CHECK_INTERVAL = FOLLOW_UP_CHECK_INTERVAL_MINUTES * 60
    AUTO_REPLY_CHECK_INTERVAL = AUTO_REPLY_CHECK_INTERVAL_MINUTES * 60
    
    # Development logging
    LOG_LEVEL = 'DEBUG'
    
    # Development cache
    CACHE_TYPE = 'null'  # Disable cache in development for easier debugging

class ProductionConfig(Config):
    DEBUG = False
    
    # Production-specific settings
    SESSION_COOKIE_SECURE = True
    
    # Production database configuration
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'postgresql://user:password@localhost/email_automation'
    
    # Production logging
    LOG_LEVEL = 'WARNING'
    
    # Production security
    SECURITY_PASSWORD_SALT = os.environ.get('SECURITY_PASSWORD_SALT') or secrets.token_hex(16)
    
    # Production cache
    CACHE_TYPE = 'redis'
    CACHE_REDIS_URL = os.environ.get('CACHE_REDIS_URL', 'redis://localhost:6379/0')
    
    # Production rate limiting
    RATELIMIT_STORAGE_URL = 'redis://localhost:6379/1'
    
    # Production performance
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
        'pool_size': 20,
        'max_overflow': 30
    }

class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    
    # Testing-specific settings
    SCHEDULER_API_ENABLED = False  # Disable scheduler in tests
    WTF_CSRF_ENABLED = False  # Disable CSRF in tests
    
    # CRITICAL FIX: Short intervals for testing
    EMAIL_CHECK_INTERVAL_MINUTES = 0  # Disabled in tests
    FOLLOW_UP_CHECK_INTERVAL_MINUTES = 0  # Disabled in tests
    AUTO_REPLY_CHECK_INTERVAL_MINUTES = 0  # Disabled in tests
    
    # Update legacy interval settings
    EMAIL_CHECK_INTERVAL = 0
    FOLLOW_UP_CHECK_INTERVAL = 0
    AUTO_REPLY_CHECK_INTERVAL = 0
    
    # Testing cache
    CACHE_TYPE = 'null'

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}