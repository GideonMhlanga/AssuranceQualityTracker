import streamlit as st
import hashlib
import datetime as dt
import time
from database import BeverageQADatabase
from sqlalchemy import text

# Initialize database connection
db = BeverageQADatabase()

def hash_password(password):
    """
    Create a secure hash of the password using SHA-256 with salt.
    
    Args:
        password (str): Plain text password
        
    Returns:
        str: Hashed password
    """
    # Add a pepper to the password before hashing (store this in environment variables in production)
    pepper = st.secrets.get("PEPPER", "default-pepper-value")
    return hashlib.sha256((password + pepper).encode()).hexdigest()

def authenticate_user(username, password):
    """
    Authenticate a user with username and password.
    
    Args:
        username (str): The username to authenticate
        password (str): The plain text password to verify
        
    Returns:
        bool: True if authentication successful, False otherwise
    """
    if not username or not password:
        st.error("Username and password are required")
        return False
        
    with db.get_engine().connect() as conn:
        try:
            # Get user with matching credentials
            query = text("""
                SELECT username, role, password_hash 
                FROM users 
                WHERE username = :username
            """)
            result = conn.execute(query, {'username': username})
            user = result.fetchone()
            
            if not user:
                st.error("Invalid username or password")
                return False
                
            # Verify password
            hashed_input = hash_password(password)
            if hashed_input != user.password_hash:
                st.error("Invalid username or password")
                return False
                
            # Update last login time
            update_query = text("""
                UPDATE users 
                SET last_login = NOW() 
                WHERE username = :username
            """)
            conn.execute(update_query, {'username': username})
            conn.commit()
            
            # Store user info in session
            st.session_state.update({
                'authenticated': True,
                'username': user.username,
                'role': user.role,
                'login_time': dt.datetime.now()
            })
            
            return True
            
        except Exception as e:
            st.error(f"Authentication error: {e}")
            return False

def create_user(username, password, role='operator'):
    """
    Create a new user account with enhanced Neon database handling
    
    Args:
        username (str): The username for the new account
        password (str): The plain text password
        role (str): User role (default: 'operator')
        
    Returns:
        tuple: (success: bool, message: str)
    """
    # Input validation
    if not username or not password:
        return False, "Username and password are required"
    if len(username) < 4:
        return False, "Username must be at least 4 characters"
    if len(password) < 8:
        return False, "Password must be at least 8 characters"
    if role not in ['operator', 'supervisor', 'admin']:
        return False, "Invalid role specified"
        
    try:
        db = BeverageQADatabase()
        
        # 1. Verify database connection
        if not db.test_connection():
            return False, "Database connection failed"
            
        # 2. Check if user exists (with retry for eventual consistency)
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # 3. Create user with immediate verification
                success = db.create_user(
                    username=username,
                    password_hash=hash_password(password),
                    role=role
                )
                
                if not success:
                    return False, f"Username {username} already exists"
                
                # 4. Verify creation (with delay for Neon propagation)
                time.sleep(0.5)  # Brief delay for serverless consistency
                verified_user = db.get_user(username)
                
                if verified_user:
                    return True, f"User {username} created and verified"
                elif attempt == max_retries - 1:
                    return False, "User created but verification failed"
                    
            except Exception as e:
                if attempt == max_retries - 1:
                    return False, f"Failed after {max_retries} attempts: {str(e)}"
                time.sleep(1)  # Wait before retry
                continue
                
    except Exception as e:
        st.error(f"System error: {str(e)}")
        return False, f"System error: {str(e)}"
    
# Backward compatibility alias
def create_user_if_not_exists(username, password, role='operator'):
    """Deprecated - use create_user() instead"""
    return create_user(username, password, role)

def logout():
    """
    Clear the user session and reset authentication state.
    Also triggers a rerun to refresh the page.
    """
    st.session_state.clear()
    st.rerun()

def get_current_user():
    """
    Get information about the currently authenticated user.
    
    Returns:
        dict: {
            'authenticated': bool,
            'username': str or None,
            'role': str or None,
            'login_time': datetime or None
        }
    """
    return {
        'authenticated': st.session_state.get('authenticated', False),
        'username': st.session_state.get('username'),
        'role': st.session_state.get('role'),
        'login_time': st.session_state.get('login_time')
    }

def require_login():
    """
    Decorator function to protect routes that require authentication.
    Redirects to login page if not authenticated.
    """
    if not st.session_state.get('authenticated', False):
        st.warning("Please log in to access this page")
        st.stop()

def require_role(*required_roles):
    """
    Decorator function to protect routes that require specific roles.
    
    Args:
        *required_roles: One or more role strings that are allowed
        
    Example:
        @require_role('admin', 'supervisor')
        def admin_page():
            # Your admin code here
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            require_login()
            current_role = st.session_state.get('role')
            if current_role not in required_roles:
                st.error("You don't have permission to access this page")
                st.stop()
            return func(*args, **kwargs)
        return wrapper
    return decorator

def show_login_form():
    """
    Display a login form and handle authentication.
    
    Returns:
        bool: True if login successful, False otherwise
    """
    with st.form("login_form"):
        st.subheader("Login")
        username = st.text_input("Username", key="login_username")
        password = st.text_input("Password", type="password", key="login_password")
        submit = st.form_submit_button("Login")
        
        if submit:
            if authenticate_user(username, password):
                st.success("Login successful!")
                st.rerun()
                return True
    return False

def show_create_account_form(allowed_roles=None):
    """
    Display an account creation form.
    
    Args:
        allowed_roles: List of roles that can be assigned (None for default)
        
    Returns:
        bool: True if account created successfully
    """
    if allowed_roles is None:
        allowed_roles = ['operator', 'supervisor']
        
    with st.form("create_account_form"):
        st.subheader("Create New Account")
        new_username = st.text_input("New Username")
        new_password = st.text_input("New Password", type="password")
        confirm_password = st.text_input("Confirm Password", type="password")
        role = st.selectbox("Role", allowed_roles)
        submit = st.form_submit_button("Create Account")
        
        if submit:
            if new_password != confirm_password:
                st.error("Passwords do not match")
                return False
                
            success, message = create_user(new_username, new_password, role)
            if success:
                st.success(message)
                return True
            else:
                st.error(message)
    return False

def initialize_session():
    """
    Initialize session state variables if they don't exist.
    """
    if 'authenticated' not in st.session_state:
        st.session_state.update({
            'authenticated': False,
            'username': None,
            'role': None,
            'login_time': None
        })