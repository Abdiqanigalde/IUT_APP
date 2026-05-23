"""
Security Service for IUT Appointment System
Handles password hashing, session management, CSRF protection, and input sanitization
"""

from flask_bcrypt import Bcrypt
from functools import wraps
from flask import session, redirect, url_for, abort, request
from datetime import datetime, timedelta, timezone
import re
import html

bcrypt = Bcrypt()

class SecurityService:
    """Service for managing security-related operations"""

    # Session timeout in minutes
    SESSION_TIMEOUT = 30
    
    # Maximum login attempts before lockout
    MAX_LOGIN_ATTEMPTS = 5
    
    # Lockout duration in minutes
    LOCKOUT_DURATION = 15

    @staticmethod
    def hash_password(password):
        """
        Hash a password using bcrypt
        
        Args:
            password (str): Plain text password
        
        Returns:
            str: Hashed password
        """
        return bcrypt.generate_password_hash(password).decode('utf-8')

    @staticmethod
    def verify_password(password, hashed_password):
        """
        Verify a password against its hash
        
        Args:
            password (str): Plain text password
            hashed_password (str): Hashed password
        
        Returns:
            bool: True if password matches, False otherwise
        """
        return bcrypt.check_password_hash(hashed_password, password)

    @staticmethod
    def sanitize_input(user_input):
        """
        Sanitize user input to prevent XSS attacks
        
        Args:
            user_input (str): User input to sanitize
        
        Returns:
            str: Sanitized input
        """
        if not isinstance(user_input, str):
            return user_input
        
        # Remove HTML tags and escape special characters
        sanitized = html.escape(user_input)
        
        # Remove potentially dangerous characters
        sanitized = re.sub(r'[<>\"\'`]', '', sanitized)
        
        return sanitized

    @staticmethod
    def validate_email(email):
        """
        Validate email format
        
        Args:
            email (str): Email address to validate
        
        Returns:
            bool: True if email is valid, False otherwise
        """
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(email_pattern, email) is not None

    @staticmethod
    def validate_password_strength(password):
        """
        Validate password strength
        
        Args:
            password (str): Password to validate
        
        Returns:
            tuple: (bool, str) - (is_valid, message)
        """
        if len(password) < 8:
            return False, "Password must be at least 8 characters long"
        
        if not re.search(r'[A-Z]', password):
            return False, "Password must contain at least one uppercase letter"
        
        if not re.search(r'[a-z]', password):
            return False, "Password must contain at least one lowercase letter"
        
        if not re.search(r'[0-9]', password):
            return False, "Password must contain at least one digit"
        
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            return False, "Password must contain at least one special character"
        
        return True, "Password is strong"

    @staticmethod
    def check_session_timeout():
        """
        Check if the current session has timed out
        
        Returns:
            bool: True if session is valid, False if timed out
        """
        if 'last_activity' in session:
            last_activity = session['last_activity']
            if isinstance(last_activity, str):
                last_activity = datetime.fromisoformat(last_activity)
            
            timeout_duration = timedelta(minutes=SecurityService.SESSION_TIMEOUT)
            if datetime.now(timezone.utc) - last_activity > timeout_duration:
                return False
        
        session['last_activity'] = datetime.now(timezone.utc).isoformat()
        return True

    @staticmethod
    def require_role(*roles):
        """
        Decorator to require specific roles for a route
        
        Args:
            *roles: Allowed roles
        
        Returns:
            function: Decorated function
        """
        def decorator(f):
            @wraps(f)
            def decorated_function(*args, **kwargs):
                from flask_login import current_user
                
                if not current_user.is_authenticated:
                    return redirect(url_for('login'))
                
                if current_user.role not in roles:
                    abort(403)
                
                if not SecurityService.check_session_timeout():
                    session.clear()
                    return redirect(url_for('login'))
                
                return f(*args, **kwargs)
            
            return decorated_function
        return decorator

    @staticmethod
    def require_permission(permission):
        """
        Decorator to require specific permission for a route
        
        Args:
            permission (str): Required permission
        
        Returns:
            function: Decorated function
        """
        def decorator(f):
            @wraps(f)
            def decorated_function(*args, **kwargs):
                from flask_login import current_user
                
                if not current_user.is_authenticated:
                    return redirect(url_for('login'))
                
                # Permission mapping based on role
                permissions = {
                    'super_admin': ['view_all', 'edit_all', 'delete_all', 'manage_users', 'manage_officers'],
                    'admin': ['view_all', 'edit_all', 'manage_officers'],
                    'officer': ['view_own', 'edit_own'],
                    'receptionist': ['view_all', 'edit_all'],
                    'student': ['view_own', 'edit_own']
                }
                
                user_permissions = permissions.get(current_user.role, [])
                
                if permission not in user_permissions:
                    abort(403)
                
                if not SecurityService.check_session_timeout():
                    session.clear()
                    return redirect(url_for('login'))
                
                return f(*args, **kwargs)
            
            return decorated_function
        return decorator

    @staticmethod
    def prevent_sql_injection(user_input):
        """
        Prevent SQL injection by escaping dangerous characters
        
        Args:
            user_input (str): User input to escape
        
        Returns:
            str: Escaped input
        """
        if not isinstance(user_input, str):
            return user_input
        
        # Escape single quotes
        escaped = user_input.replace("'", "''")
        
        # Remove or escape dangerous SQL keywords
        dangerous_keywords = ['DROP', 'DELETE', 'INSERT', 'UPDATE', 'UNION', 'SELECT']
        for keyword in dangerous_keywords:
            escaped = re.sub(rf'\b{keyword}\b', '', escaped, flags=re.IGNORECASE)
        
        return escaped

    @staticmethod
    def generate_csrf_token():
        """
        Generate a CSRF token for the session
        
        Returns:
            str: CSRF token
        """
        import secrets
        token = secrets.token_hex(32)
        session['csrf_token'] = token
        return token

    @staticmethod
    def verify_csrf_token(token):
        """
        Verify a CSRF token
        
        Args:
            token (str): Token to verify
        
        Returns:
            bool: True if token is valid, False otherwise
        """
        if 'csrf_token' not in session:
            return False
        
        return session['csrf_token'] == token

    @staticmethod
    def rate_limit_login_attempts(user_email, max_attempts=MAX_LOGIN_ATTEMPTS, lockout_duration=LOCKOUT_DURATION):
        """
        Rate limit login attempts to prevent brute force attacks
        
        Args:
            user_email (str): Email of the user attempting to login
            max_attempts (int): Maximum allowed attempts
            lockout_duration (int): Lockout duration in minutes
        
        Returns:
            tuple: (bool, str) - (is_allowed, message)
        """
        # This would typically use Redis or a similar cache
        # For now, we'll use a simple in-memory approach
        if not hasattr(SecurityService, '_login_attempts'):
            SecurityService._login_attempts = {}
        
        if user_email not in SecurityService._login_attempts:
            SecurityService._login_attempts[user_email] = {'attempts': 0, 'locked_until': None}
        
        user_attempts = SecurityService._login_attempts[user_email]
        
        # Check if user is locked out
        if user_attempts['locked_until']:
            if datetime.now(timezone.utc) < user_attempts['locked_until']:
                return False, f"Account locked. Try again after {user_attempts['locked_until']}"
            else:
                user_attempts['locked_until'] = None
                user_attempts['attempts'] = 0
        
        # Increment attempts
        user_attempts['attempts'] += 1
        
        if user_attempts['attempts'] > max_attempts:
            user_attempts['locked_until'] = datetime.now(timezone.utc) + timedelta(minutes=lockout_duration)
            return False, f"Too many login attempts. Account locked for {lockout_duration} minutes"
        
        return True, f"Login attempt {user_attempts['attempts']}/{max_attempts}"

    @staticmethod
    def reset_login_attempts(user_email):
        """
        Reset login attempts for a user
        
        Args:
            user_email (str): Email of the user
        """
        if hasattr(SecurityService, '_login_attempts') and user_email in SecurityService._login_attempts:
            SecurityService._login_attempts[user_email] = {'attempts': 0, 'locked_until': None}
