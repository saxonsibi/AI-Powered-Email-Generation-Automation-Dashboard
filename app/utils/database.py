# app/utils/database.py
from pydoc import text
from flask import flash, current_app
from sqlalchemy.exc import IntegrityError, OperationalError, ProgrammingError
from app import db, logger
import logging

# Configure logger
db_logger = logging.getLogger(__name__)

def handle_db_integrity_error(error, operation="operation"):
    """Handle database integrity errors gracefully."""
    if isinstance(error, IntegrityError):
        # Extract the specific constraint that failed
        error_message = str(error.orig)
        db_logger.error(f"Database integrity error during {operation}: {error_message}")
        
        # Handle user-related constraints
        if 'users.username' in error_message:
            flash('Username already exists. Please choose a different username.', 'error')
            return 'username_exists'
        elif 'users.email' in error_message:
            flash('Email address already exists. Please use a different email.', 'error')
            return 'email_exists'
        
        # Handle email-related constraints
        elif 'email_categories' in error_message and 'name' in error_message:
            flash('Category name already exists. Please choose a different name.', 'error')
            return 'category_name_exists'
        elif 'auto_reply_templates' in error_message and 'name' in error_message:
            flash('Template name already exists. Please choose a different name.', 'error')
            return 'template_name_exists'
        
        # Handle automation rule constraints
        elif 'automation_rules' in error_message and 'name' in error_message:
            flash('Rule name already exists. Please choose a different name.', 'error')
            return 'rule_name_exists'
        
        # Handle foreign key constraints
        elif 'foreign key constraint' in error_message.lower():
            flash('Referenced record does not exist. Please check your selection.', 'error')
            return 'foreign_key_violation'
        
        # Handle unique constraints
        elif 'unique constraint' in error_message.lower():
            flash('A record with these values already exists. Please use different values.', 'error')
            return 'unique_constraint_violation'
        
        # Handle other constraint violations
        else:
            flash(f'Database constraint violation during {operation}.', 'error')
            return 'unknown_constraint'
    
    # Re-raise if it's not an IntegrityError
    raise error

def safe_db_commit(operation="operation", log_success=True):
    """Safely commit to database with error handling."""
    try:
        db.session.commit()
        if log_success:
            db_logger.info(f"Successfully committed database changes for {operation}")
        return True, None
    except IntegrityError as e:
        db.session.rollback()
        error_type = handle_db_integrity_error(e, operation)
        return False, error_type
    except OperationalError as e:
        db.session.rollback()
        db_logger.error(f"Database operational error during {operation}: {str(e)}")
        flash('A database error occurred. Please try again later.', 'error')
        return False, 'operational_error'
    except ProgrammingError as e:
        db.session.rollback()
        db_logger.error(f"Database programming error during {operation}: {str(e)}")
        flash('A database error occurred. Please contact support.', 'error')
        return False, 'programming_error'
    except Exception as e:
        db.session.rollback()
        db_logger.error(f"Unexpected database error during {operation}: {str(e)}")
        flash(f'An error occurred during {operation}: {str(e)}', 'error')
        return False, 'unknown_error'

def safe_db_rollback(operation="operation"):
    """Safely rollback database changes with error handling."""
    try:
        db.session.rollback()
        db_logger.info(f"Successfully rolled back database changes for {operation}")
        return True
    except Exception as e:
        db_logger.error(f"Error rolling back database changes for {operation}: {str(e)}")
        return False

def check_db_connection():
    """Check if the database connection is healthy."""
    try:
        # Import text to properly declare SQL expressions
        from sqlalchemy import text
        
        # Execute a simple query to check connection
        db.session.execute(text('SELECT 1'))
        return True
    except Exception as e:
        db_logger.error(f"Database connection check failed: {str(e)}")
        return False

def with_db_transaction(func):
    """
    Decorator to wrap a function in a database transaction.
    
    Usage:
    @with_db_transaction
    def my_function():
        # Database operations here
        pass
    """
    def wrapper(*args, **kwargs):
        try:
            result = func(*args, **kwargs)
            db.session.commit()
            return result
        except Exception as e:
            db.session.rollback()
            db_logger.error(f"Transaction error in {func.__name__}: {str(e)}")
            raise
    return wrapper

def bulk_insert(model_class, data_list, batch_size=1000):
    """
    Bulk insert data into a table with error handling.
    
    Args:
        model_class: SQLAlchemy model class
        data_list: List of dictionaries with data to insert
        batch_size: Number of records to insert in each batch
        
    Returns:
        tuple: (success: bool, count: int, error: str or None)
    """
    try:
        count = 0
        for i in range(0, len(data_list), batch_size):
            batch = data_list[i:i + batch_size]
            db.session.bulk_insert_mappings(model_class, batch)
            db.session.commit()
            count += len(batch)
        
        db_logger.info(f"Successfully bulk inserted {count} records into {model_class.__name__}")
        return True, count, None
    except Exception as e:
        db.session.rollback()
        error_msg = f"Error bulk inserting into {model_class.__name__}: {str(e)}"
        db_logger.error(error_msg)
        return False, 0, error_msg

def bulk_update(model_class, data_list, batch_size=1000):
    """
    Bulk update data in a table with error handling.
    
    Args:
        model_class: SQLAlchemy model class
        data_list: List of dictionaries with data to update
        batch_size: Number of records to update in each batch
        
    Returns:
        tuple: (success: bool, count: int, error: str or None)
    """
    try:
        count = 0
        for i in range(0, len(data_list), batch_size):
            batch = data_list[i:i + batch_size]
            db.session.bulk_update_mappings(model_class, batch)
            db.session.commit()
            count += len(batch)
        
        db_logger.info(f"Successfully bulk updated {count} records in {model_class.__name__}")
        return True, count, None
    except Exception as e:
        db.session.rollback()
        error_msg = f"Error bulk updating {model_class.__name__}: {str(e)}"
        db_logger.error(error_msg)
        return False, 0, error_msg

def execute_raw_query(query, params=None, fetch_all=True):
    """
    Execute a raw SQL query with error handling.
    
    Args:
        query: SQL query string
        params: Parameters for the query
        fetch_all: Whether to fetch all results or just one
        
    Returns:
        tuple: (success: bool, result: list/dict/None, error: str or None)
    """
    try:
        # Import text for raw SQL queries
        from sqlalchemy import text
        
        # Convert string query to text object if needed
        if isinstance(query, str):
            query = text(query)
        
        result = db.session.execute(query, params or {})
        
        if fetch_all:
            data = result.fetchall()
        else:
            data = result.fetchone()
        
        db_logger.info(f"Successfully executed raw query: {str(query)[:100]}...")
        return True, data, None
    except Exception as e:
        error_msg = f"Error executing raw query: {str(e)}"
        db_logger.error(error_msg)
        return False, None, error_msg

def get_table_row_count(table_name):
    """
    Get the number of rows in a table.
    
    Args:
        table_name: Name of the table
        
    Returns:
        int: Number of rows in the table or 0 if error
    """
    try:
        # Import text for raw SQL queries
        from sqlalchemy import text
        
        result = db.session.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
        count = result.scalar()
        return count
    except Exception as e:
        db_logger.error(f"Error getting row count for {table_name}: {str(e)}")
        return 0

def init_db(app):
    """Initialize the database with all models."""
    with app.app_context():
        try:
            # Import all models to ensure they are registered with SQLAlchemy
            from app.models.user import User
            from app.models.email import Email, EmailCategory, EmailClassification, SentEmail, DraftEmail, EmailAttachment
            from app.models.auto_reply import AutoReplyTemplate, AutoReplyLog, ScheduledAutoReply
            from app.models.automation import AutomationRule, ClassificationRule, FollowUpRule, FollowUpTemplate
            from app.models.follow_up import FollowUp, FollowUpSequence, FollowUpLog
            
            # Create all tables
            db.create_all()
            db_logger.info("Database tables created successfully")
            
            # Check if there's an admin user, if not create one
            if User.query.filter_by(username='admin').first() is None:
                admin = User(
                    username='admin',
                    email='admin@example.com',
                    name='Administrator'
                )
                admin.set_password('admin123')
                
                db.session.add(admin)
                db.session.commit()
                print("Created default admin user (username: admin, password: admin123)")
                db_logger.info("Created default admin user")
            
            return True
        except Exception as e:
            db_logger.error(f"Error initializing database: {str(e)}")
            db.session.rollback()
            return False

def init_app(app):
    """Initialize database utilities with the Flask app."""
    with app.app_context():
        try:
            # Check database connection on startup
            if not check_db_connection():
                db_logger.error("Database connection failed during app initialization")
                return False
            else:
                db_logger.info("Database connection verified during app initialization")
                
            # Initialize database if needed
            if not init_db(app):
                db_logger.error("Database initialization failed")
                return False
                
            return True
        except Exception as e:
            db_logger.error(f"Error initializing database utilities: {str(e)}")
            return False

def get_database_info():
    """Get information about the database."""
    try:
        from sqlalchemy import text
        
        # Get database version
        version_result = db.session.execute(text("SELECT version()"))
        db_version = version_result.scalar()
        
        # Get table list
        tables_result = db.session.execute(text("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            ORDER BY table_name
        """))
        tables = [row[0] for row in tables_result.fetchall()]
        
        # Get row counts for each table
        table_info = {}
        for table in tables:
            count_result = db.session.execute(text(f"SELECT COUNT(*) FROM {table}"))
            table_info[table] = count_result.scalar()
        
        return {
            'version': db_version,
            'tables': table_info
        }
    except Exception as e:
        db_logger.error(f"Error getting database info: {str(e)}")
        return None

def backup_table(table_name, backup_path=None):
    """
    Backup a table to a CSV file.
    
    Args:
        table_name: Name of the table to backup
        backup_path: Path to save the backup file (optional)
        
    Returns:
        tuple: (success: bool, file_path: str or None, error: str or None)
    """
    try:
        import csv
        from datetime import datetime
        import os
        
        if not backup_path:
            backup_path = f"backups/{table_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        # Create backup directory if it doesn't exist
        os.makedirs(os.path.dirname(backup_path), exist_ok=True)
        
        # Get table data
        result = db.session.execute(text(f"SELECT * FROM {table_name}"))
        rows = result.fetchall()
        columns = result.keys()
        
        # Write to CSV
        with open(backup_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(columns)
            writer.writerows(rows)
        
        db_logger.info(f"Successfully backed up table {table_name} to {backup_path}")
        return True, backup_path, None
    except Exception as e:
        error_msg = f"Error backing up table {table_name}: {str(e)}"
        db_logger.error(error_msg)
        return False, None, error_msg

def optimize_database():
    """Run database optimization commands."""
    try:
        from sqlalchemy import text
        
        # Analyze tables to update statistics
        db.session.execute(text("ANALYZE"))
        
        # Vacuum to reclaim space
        db.session.execute(text("VACUUM ANALYZE"))
        
        db.session.commit()
        db_logger.info("Database optimization completed")
        return True
    except Exception as e:
        db_logger.error(f"Error optimizing database: {str(e)}")
        db.session.rollback()
        return False

def clear_table(table_name, confirm=False):
    """
    Clear all data from a table.
    
    Args:
        table_name: Name of the table to clear
        confirm: Confirmation flag to prevent accidental data loss
        
    Returns:
        bool: Success status
    """
    if not confirm:
        db_logger.warning("Table clear operation not confirmed")
        return False
    
    try:
        from sqlalchemy import text
        
        db.session.execute(text(f"DELETE FROM {table_name}"))
        db.session.commit()
        db_logger.info(f"Cleared all data from table {table_name}")
        return True
    except Exception as e:
        db_logger.error(f"Error clearing table {table_name}: {str(e)}")
        db.session.rollback()
        return False