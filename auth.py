import streamlit as st
import hashlib
import datetime as dt
import time
from database import BeverageQADatabase
from sqlalchemy import text
import re

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
    if role not in ['operator', 'supervisor', 'admin', 'viewer']:
        return False, "Invalid role specified"
        
    try:
         # Use the existing database instance from session state
        if 'db' not in st.session_state or st.session_state.db is None:
            return False, "Database not initialized"
            
        db = st.session_state.db  # ← Use the existing instance!
        # db = BeverageQADatabase()
        
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
    """Completely clear session state and reset authentication"""
    # Clear all session state except initialization flags
    keys_to_keep = ['init_phase', 'db', 'app_modules', 'viz_modules', 'report_modules', 'form_modules']
    current_state = st.session_state.copy()
    
    st.session_state.clear()
    
    # Restore only the necessary initialization keys
    for key in keys_to_keep:
        if key in current_state:
            st.session_state[key] = current_state[key]
            
    """Clear authentication state and redirect to login"""
    st.session_state.authenticated = False
    st.session_state.username = None
    st.session_state.role = None
    st.session_state.show_login_page = True
    st.session_state.form_type = None
    st.session_state.start_time = None
    st.session_state.check_id = None
    
    # Clear any query parameters
    if hasattr(st, 'query_params'):
        st.query_params.clear()

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
    """Display login form with registration option and emergency admin creation"""

    import uuid
    form_id = str(uuid.uuid4())[:8]  # Use first 8 chars for readability

    # Remove counter increment and use stable keys
    login_form_key = "login_form"
    register_form_key = "register_form"

    # Temporary admin creation (remove after first admin exists)
    try:
        # Check if any admin exists using get_all_users_data()
        users_df = st.session_state.db.get_all_users_data()
        admin_exists = not users_df.empty and 'admin' in users_df['role'].values
    except Exception as e:
        st.error(f"Error checking admin status: {str(e)}")
        admin_exists = False

    if not admin_exists:  # If no admin exists
        with st.expander("⚠️ INITIAL ADMIN SETUP", expanded=True):
            st.warning("No admin account detected. Create your first admin account:")
            
            admin_username = st.text_input("Admin Username", key="admin_username")
            admin_password = st.text_input("Admin Password", type="password", key="admin_password")
            confirm_password = st.text_input("Confirm Password", type="password", key="admin_confirm")
            
            if st.button("Create Admin Account"):
                # Validation
                if not re.match(r'^[a-zA-Z0-9_]{3,20}$', admin_username):
                    st.error("Username must be 3-20 characters (letters, numbers, underscores)")
                    return False
                
                if admin_password != confirm_password:
                    st.error("Passwords don't match!")
                    return False
                
                if len(admin_password) < 12:
                    st.error("Admin password must be at least 12 characters")
                    return False
                
                hashed = hash_password(admin_password)
                try:
                    # Use create_user function instead of direct database access
                    success, message = create_user(
                        username=admin_username,
                        password=admin_password,
                        role='admin'
                    )
                    if success:
                        st.success("Admin account created successfully! Please login")
                        st.rerun()  # Refresh to show normal login
                    else:
                        st.error(f"Failed to create admin account: {message}")
                except Exception as e:
                    st.error(f"Error creating admin: {str(e)}")
                return False

    # Regular login/register tabs
    tab1, tab2 = st.tabs(["Login", "Register"])
    
    with tab1:
        with st.form(login_form_key):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            
            if st.form_submit_button("Login"):
                return authenticate_user(username, password)
    
    with tab2:
        with st.form(register_form_key):
            st.subheader("New User Registration")
            new_username = st.text_input("New Username", help="Must be 3-20 characters, letters and numbers only")
            new_password = st.text_input("New Password", type="password", 
                                       help="Minimum 8 characters with at least 1 number")
            confirm_password = st.text_input("Confirm Password", type="password")
            
            # Get current user role if logged in (for admin registration)
            current_role = st.session_state.get('role', 'guest')
            
            # Role selection with permissions
            if current_role == 'admin':
                role_options = ["admin", "supervisor", "operator", "viewer"]
                default_role = "operator"
            else:  # For guests or non-admin users
                role_options = ["operator", "viewer"]
                default_role = "operator"
            
            role = st.selectbox("Account Type", role_options, 
                               index=role_options.index(default_role),
                               help="Select your role in the system")
            
            if st.form_submit_button("Register"):
                # Validation
                if not re.match(r'^[a-zA-Z0-9_]{3,20}$', new_username):
                    st.error("Username must be 3-20 characters (letters, numbers, underscores)")
                    return False
                
                if new_password != confirm_password:
                    st.error("Passwords don't match!")
                    return False
                
                if len(new_password) < 8 or not any(c.isdigit() for c in new_password):
                    st.error("Password must be at least 8 characters with 1 number")
                    return False
                
                # Additional security check for non-admin users
                if current_role != 'admin' and role in ['admin', 'supervisor']:
                    st.error("You cannot register with this role")
                    return False
                
                try:
                    success, message = create_user(new_username, new_password, role)
                    if success:
                        st.success(message)
                        # Auto-login unless admin creating another account
                        if current_role != 'admin':
                            return authenticate_user(new_username, new_password)
                        return False
                    else:
                        st.error(message)
                        return False
                except Exception as e:
                    st.error(f"Registration failed: {str(e)}")
                    return False
    
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