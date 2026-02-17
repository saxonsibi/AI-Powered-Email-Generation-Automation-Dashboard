import os
import sys
import logging
from datetime import datetime
from app import create_app

# Fix Unicode encoding issues on Windows
if sys.platform == 'win32':
    # Set console to UTF-8 encoding
    os.system('chcp 65001 >nul')
    # Change stdout encoding to UTF-8
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

# Configure logging
def setup_logging():
    # Create logs directory if it doesn't exist
    if not os.path.exists('logs'):
        os.makedirs('logs')
    
    # Configure logging format
    log_format = '[%(asctime)s] [%(levelname)s] %(message)s'
    date_format = '%Y-%m-%d %H:%M:%S'
    
    # Configure file logging with UTF-8 encoding
    file_handler = logging.FileHandler('logs/system.log', encoding='utf-8')
    file_handler.setFormatter(logging.Formatter(log_format, date_format))
    file_handler.setLevel(logging.INFO)
    
    # Configure console logging with UTF-8 encoding
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter(log_format, date_format))
    console_handler.setLevel(logging.INFO)
    
    # Set up root logger
    logging.basicConfig(
        level=logging.INFO,
        handlers=[file_handler, console_handler]
    )
    
    return logging.getLogger('auto_reply_system')

# Set environment variables for Flask
os.environ['FLASK_APP'] = 'run.py:create_app_with_config'
os.environ['FLASK_ENV'] = 'development'

if __name__ == '__main__':
    logger = setup_logging()
    logger.info("Starting Auto-Reply System")
    
    try:
        app = create_app('development')
        logger.info("Flask app initialized successfully")
        
        # Add a before_request handler to log all requests
        @app.before_request
        def log_request_info():
            from flask import request
            logger.info(f"Request: {request.method} {request.path}")
        
        # Add an after_request handler to log responses
        @app.after_request
        def log_response_info(response):
            logger.info(f"Response: {response.status_code}")
            return response
        
        logger.info("Server starting on 127.0.0.1:5000")
        app.run(debug=True, host='127.0.0.1', port=5000, use_reloader=False)
    except Exception as e:
        logger.error(f"Failed to start server: {str(e)}")
        raise