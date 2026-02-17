# app/routes/auth.py
from flask import Blueprint, render_template, redirect, url_for, request, flash, session, current_app
from flask_login import login_user, logout_user, login_required, current_user
from app import db, login_manager
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

auth = Blueprint('auth', __name__)

@auth.route('/login', methods=['GET', 'POST'])
def login():
    """Handle user login."""
    # Debug information
    current_app.logger.info(f"Login route accessed. Method: {request.method}")
    current_app.logger.info(f"Current user authenticated: {current_user.is_authenticated}")
    
    if current_user.is_authenticated:
        current_app.logger.info(f"User {current_user.email} already authenticated, redirecting to dashboard")
        return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        remember = True if request.form.get('remember') else False
        
        current_app.logger.info(f"Login attempt for email: {email}")
        
        # Import User model inside the route to avoid circular imports
        from app.models.user import User
        
        # Authenticate user
        success, user, error = User.authenticate_user(email, password)
        
        if success:
            # Set session permanent if remember is checked
            session.permanent = remember
            
            # Set session lifetime to 30 days if remember is True
            if remember:
                current_app.permanent_session_lifetime = timedelta(days=30)
            
            login_user(user, remember=remember)
            
            # Log the login
            current_app.logger.info(f"User {email} logged in successfully")
            
            next_page = request.args.get('next')
            # Validate the next URL to prevent open redirects
            if next_page and not next_page.startswith('/'):
                next_page = None
                
            return redirect(next_page) if next_page else redirect(url_for('main.dashboard'))
        else:
            current_app.logger.warning(f"Failed login attempt for email: {email}, error: {error}")
            flash(error or 'Invalid login credentials', 'danger')
    
    return render_template('auth/login.html')

@auth.route('/signup', methods=['GET', 'POST'])
def signup():
    """Handle user registration."""
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        # Basic validation
        if not username or not email or not password:
            flash('All fields are required.', 'danger')
            return render_template('auth/signup.html')
        
        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return render_template('auth/signup.html')
        
        if len(password) < 6:
            flash('Password must be at least 6 characters long.', 'danger')
            return render_template('auth/signup.html')
        
        # Import User model inside the route to avoid circular imports
        from app.models.user import User
        
        # Create user
        success, user, error = User.create_user(username, email, password)
        
        if success:
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('auth.login'))
        else:
            flash(error or 'Registration failed', 'danger')
    
    return render_template('auth/signup.html')

@auth.route('/logout')
@login_required
def logout():
    """Handle user logout."""
    user_email = current_user.email
    logout_user()
    flash('You have been logged out.', 'info')
    current_app.logger.info(f"User {user_email} logged out")
    return redirect(url_for('auth.login'))

@auth.route('/gmail/authorize')
@login_required
def gmail_authorize():
    """Initiate Gmail OAuth authorization."""
    redirect_uri = url_for('auth.gmail_callback', _external=True)
    
    try:
        # Import GmailService inside the route to avoid circular imports
        from app.services.gmail_service import GmailService
        
        auth_url, state = GmailService.get_auth_url(redirect_uri)
        session['oauth_state'] = state
        return redirect(auth_url)
    except FileNotFoundError as e:
        flash(str(e), 'danger')
        return redirect(url_for('main.settings'))
    except Exception as e:
        logger.error(f"Error initiating Gmail authorization: {str(e)}")
        flash(f'Error initiating Gmail authorization: {str(e)}', 'danger')
        return redirect(url_for('main.settings'))

@auth.route('/gmail/callback')
@login_required
def gmail_callback():
    """Handle Gmail OAuth callback."""
    # Verify state to prevent CSRF attacks
    state = session.pop('oauth_state', None)
    if state is None or state != request.args.get('state'):
        flash('Invalid OAuth state.', 'danger')
        return redirect(url_for('main.settings'))
    
    # Exchange authorization code for credentials
    code = request.args.get('code')
    redirect_uri = url_for('auth.gmail_callback', _external=True)
    
    try:
        # Import GmailService inside the route to avoid circular imports
        from app.services.gmail_service import GmailService
        
        gmail_service = GmailService.handle_callback(code, redirect_uri, current_user)
        flash('Gmail account successfully connected!', 'success')
    except FileNotFoundError as e:
        flash(str(e), 'danger')
    except Exception as e:
        logger.error(f"Error connecting Gmail account: {str(e)}")
        flash(f'Error connecting Gmail account: {str(e)}', 'danger')
    
    return redirect(url_for('main.settings'))

@auth.route('/gmail/disconnect')
@login_required
def gmail_disconnect():
    """Disconnect Gmail account."""
    try:
        current_user.gmail_credentials = None
        db.session.commit()
        flash('Gmail account disconnected.', 'info')
    except Exception as e:
        logger.error(f"Error disconnecting Gmail account: {str(e)}")
        flash(f'Error disconnecting Gmail account: {str(e)}', 'danger')
    
    return redirect(url_for('main.settings'))