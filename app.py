import os
# =============================================
# Environment Configuration
# =============================================
os.environ.update({
    'STREAMLIT_SERVER_PORT': '8501',
    'STREAMLIT_SERVER_ADDRESS': '0.0.0.0',
    'STREAMLIT_BROWSER_GATHER_USAGE_STATS': 'false',
    'BROWSER': 'true',
})

import streamlit as st
from streamlit import config

config.set_option('server.fileWatcherType', 'none')

# =============================================
# Initial Setup & Performance Optimizations
# =============================================
st.set_page_config(
    page_title="Beverage QA Tracker",
    page_icon="🧪",
    layout="wide",
    initial_sidebar_state="expanded"
)

import time
import datetime as dt
from typing import Optional, Tuple
from streamlit.runtime.scriptrunner import get_script_run_ctx
import pandas as pd
import time
import sys

APP_START_TIME = time.time()

# Show loading spinner immediately
loading_placeholder = st.empty()
with loading_placeholder:
    st.spinner("Initializing application...")

# =============================================
# Lazy Loaded Modules (Cached Resources)
# =============================================
@st.cache_resource
def load_database():
    from database import BeverageQADatabase, get_check_data
    return BeverageQADatabase(), get_check_data

@st.cache_resource
def load_auth_module():
    from auth import authenticate_user, create_user_if_not_exists, logout
    return authenticate_user, create_user_if_not_exists, logout

@st.cache_resource
def load_form_modules():
    from forms import (
        display_torque_tamper_form, 
        display_net_content_form, 
        display_quality_check_form
    )
    return display_torque_tamper_form, display_net_content_form, display_quality_check_form

@st.cache_resource
def load_visualization_modules():
    from visualization import (
        display_brix_visualization,
        display_torque_visualization,
        display_quality_metrics_visualization
    )
    return display_brix_visualization, display_torque_visualization, display_quality_metrics_visualization

@st.cache_resource
def load_report_modules():
    from reports import generate_report, download_report
    return generate_report, download_report

@st.cache_resource
def load_other_modules():
    from utils import format_timestamp
    from spc import display_spc_page
    from capability import display_capability_page
    from compliance import display_compliance_report_page
    from prediction import display_prediction_page
    from anomaly import display_anomaly_detection_page
    from handover import display_shift_handover_page
    from lab_inventory import display_lab_inventory_page
    return locals()

# =============================================
# Initialization Phase
# =============================================
# Initialize critical components and session state in one place
if 'init_phase' not in st.session_state:
    st.session_state.init_phase = 'starting'
    
    try:
        from auth import authenticate_user, create_user_if_not_exists, logout
        from database import BeverageQADatabase, get_check_data
        
        db_instance = BeverageQADatabase()
        
        # Store auth functions in multiple ways for compatibility
        auth_functions = {
            'authenticate': authenticate_user,
            'create_user': create_user_if_not_exists,
            'logout': logout
        }
        
        st.session_state.update({
            'db': db_instance,
            'get_check_data': get_check_data,
            'auth_functions': auth_functions,  # Organized version
            # Individual functions for direct access
            'authenticate_user': authenticate_user,
            'create_user_if_not_exists': create_user_if_not_exists,
            'logout': logout,
            # Core authentication state
            'authenticated': False,
            'username': None,
            # Other state variables
            'form_type': None,
            'start_time': None,
            'check_id': None,
            'page_loaded': False,
            'last_tab': 'Dashboard',
            'init_phase': 'ready'
        })
        
    except ImportError as e:
        st.error(f"Failed to load critical components: {str(e)}")
        st.session_state.init_phase = 'failed'
        raise
    except Exception as e:
        st.error(f"Initialization error: {str(e)}")
        st.session_state.init_phase = 'failed'
        raise
    finally:
        if 'loading_placeholder' in locals():
            loading_placeholder.empty()

# Ensure critical keys exist (defensive programming)
required_keys = {
    'authenticated': False,
    'username': None,
    'form_type': None,
    'start_time': None,
    'check_id': None,
    'page_loaded': False,
    'last_tab': 'Dashboard'
}

for key, default_value in required_keys.items():
    if key not in st.session_state:
        st.session_state[key] = default_value

# =============================================
# Authentication System
# =============================================
def show_login_ui():
    """Complete login/registration UI with all original functionality"""
    st.markdown("""
    <style>
    .main > div { padding-top: 2rem; }
    .login-container {
        max-width: 450px;
        margin: 0 auto;
        padding: 2rem;
        border-radius: 10px;
        background-color: #f8f9fa;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    }
    .login-header {
        text-align: center;
        margin-bottom: 2rem;
    }
    .stButton>button {
        width: 100%;
        margin-top: 1rem;
        background-color: #0066cc;
        color: white;
        font-weight: 500;
    }
    </style>
    <div class="login-container">
        <div class="login-header">
            <h1>Beverage Quality Assurance Tracker</h1>
            <p>Please sign in to continue</p>
        </div>
    """, unsafe_allow_html=True)
    
    login_tab, register_tab = st.tabs(["Login", "Create Account"])
    
    with login_tab:
        username = st.text_input("📱 Username", key="login_username", placeholder="Enter your username")
        password = st.text_input("🔒 Password", type="password", key="login_password", placeholder="Enter your password")
        
        col1, col2 = st.columns([1, 1])
        with col1:
            remember_me = st.checkbox("Remember me")
        
        login_button = st.button("Sign In", type="primary", use_container_width=True)
        
        if login_button:
            if not username or not password:
                st.error("Please enter both username and password")
            else:
                try:
                    # Try to authenticate using the auth tuple first
                    if 'auth' in st.session_state and len(st.session_state.auth) > 0:
                        authenticate_func = st.session_state.auth[0]  # First element is authenticate_user
                    else:
                        # Fallback to direct authentication
                        authenticate_func = st.session_state.get('authenticate_user')
                        
                    if authenticate_func and authenticate_func(username, password):
                        # Get the last visited tab from database
                        last_tab = st.session_state.db.get_user_last_tab(username)
                        st.session_state.update({
                            'authenticated': True,
                            'username': username,
                            'last_tab': last_tab if last_tab else 'Dashboard'
                        })
                        st.success("Login successful! Redirecting...")
                        st.rerun()
                    else:
                        st.error("Invalid username or password")
                except Exception as e:
                    st.error(f"Authentication error: {str(e)}")
    
    with register_tab:
        new_username = st.text_input("👤 Choose Username", key="reg_username", placeholder="Create a username")
        new_password = st.text_input("🔒 Create Password", type="password", key="reg_password", 
                                  placeholder="Minimum 6 characters")
        confirm_password = st.text_input("🔒 Confirm Password", type="password", key="confirm_password", 
                                      placeholder="Re-enter your password")
        
        st.markdown("##### Password Requirements")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("✅ At least 6 characters")
        with col2:
            st.markdown("✅ Alphanumeric recommended")
            
        register_button = st.button("Create Account", type="primary", use_container_width=True)
        
        if register_button:
            if not new_username or not new_password or not confirm_password:
                st.error("Please fill in all fields")
            elif new_password != confirm_password:
                st.error("Passwords do not match")
            elif len(new_password) < 6:
                st.error("Password should be at least 6 characters long")
            else:
                # Use the properly stored function
                create_func = (
                    st.session_state.create_user_if_not_exists  # Direct access
                    if hasattr(st.session_state, 'create_user_if_not_exists')
                    else st.session_state.auth_functions['create_user']  # Fallback
                )
                
                if create_func(new_username, new_password):
                    st.success("Account created successfully! You can now log in.")
                else:
                    st.error("Username already exists. Please choose a different one.")
    
    st.markdown("</div>", unsafe_allow_html=True)

# =============================================
# Main Application Flow
# =============================================
# Check authentication with proper fallbacks
def is_authenticated():
    return st.session_state.get('authenticated', False)

if not is_authenticated():
    show_login_ui()
    st.stop()

if not st.session_state.authenticated:
    show_login_ui()
    st.stop()

# Load remaining modules after authentication
if not st.session_state.page_loaded:
    with st.spinner("Loading application modules..."):
        app_modules = load_other_modules()
        viz_modules = load_visualization_modules()
        report_modules = load_report_modules()
        form_modules = load_form_modules()
        
        st.session_state.update({
            'app_modules': app_modules,
            'viz_modules': viz_modules,
            'report_modules': report_modules,
            'form_modules': form_modules,
            'page_loaded': True
        })

# =============================================
# Page Components (All Original Functionality)
# =============================================
def show_dashboard():
    """Complete dashboard with all original features"""
    st.title("Quality Assurance Dashboard")
    
    # Display recent checks
    @st.cache_data(ttl=300)
    def get_recent_checks():
        return st.session_state.db.get_recent_checks(10)
    
    recent_checks = get_recent_checks()
    
    if recent_checks.empty:
        st.info("No recent checks found. Start by entering data in the Data Entry section.")
    else:
        # Format the dataframe for display
        display_df = recent_checks.copy()
        display_df['timestamp'] = display_df['timestamp'].apply(st.session_state.app_modules['format_timestamp'])
        display_df = display_df[['check_id', 'check_type', 'username', 'timestamp', 'trade_name', 'product']]
        display_df.columns = ['Check ID', 'Check Type', 'Inspector', 'Timestamp', 'Trade Name', 'Product']
        st.dataframe(display_df, use_container_width=True)
        
        # Display summary metrics
        col1, col2, col3 = st.columns(3)
        
        with col1:
            today_date = dt.datetime.now().date()
            today_checks = 0
            if not recent_checks.empty:
                if not pd.api.types.is_datetime64_any_dtype(recent_checks['timestamp']):
                    recent_checks['timestamp'] = pd.to_datetime(recent_checks['timestamp'])
                today_checks = len(recent_checks[recent_checks['timestamp'].dt.date == today_date])
            st.metric("Total Checks Today", today_checks)
        
        with col2:
            st.metric("Active Inspectors", recent_checks['username'].nunique())
        
        with col3:
            pass_rate = 100
            if not recent_checks.empty and 'tamper_evidence' in recent_checks.columns:
                pass_rate = int(100 * recent_checks['tamper_evidence'].str.contains('PASS').sum() / 
                            len(recent_checks))
            st.metric("Tamper Evidence Pass Rate", f"{pass_rate}%")
        
        # Show quick visualizations
        st.subheader("Quick Insights")
        tab1, tab2 = st.tabs(["BRIX Trends", "Torque Performance"])
        
        with tab1:
            st.session_state.viz_modules[0](recent_checks, height=400)
            
        with tab2:
            st.session_state.viz_modules[1](recent_checks, height=400)

def show_data_entry():
    """Complete data entry forms with all original functionality"""
    st.title("Quality Assurance Data Entry")
    
    # Form selection
    form_options = [
        "Torque and Tamper Evidence",
        "NET CONTENT Check",
        "30-Minute Quality Check"
    ]
    
    form_type = st.radio("Select check type:", form_options)
    
    # Set start time when form is selected
    if st.session_state.form_type != form_type:
        st.session_state.update({
            'start_time': dt.datetime.now(),
            'form_type': form_type,
            'check_id': f"CK-{dt.datetime.now().strftime('%Y%m%d%H%M%S')}"
        })
    
    # Display the appropriate form
    if form_type == "Torque and Tamper Evidence":
        st.session_state.form_modules[0](
            st.session_state.username, 
            st.session_state.start_time,
            st.session_state.check_id
        )
    elif form_type == "NET CONTENT Check":
        st.session_state.form_modules[1](
            st.session_state.username,
            st.session_state.start_time,
            st.session_state.check_id
        )
    elif form_type == "30-Minute Quality Check":
        st.session_state.form_modules[2](
            st.session_state.username,
            st.session_state.start_time,
            st.session_state.check_id
        )

def show_visualizations():
    """Complete visualization page with all original functionality"""
    st.title("Quality Metrics Visualization")
    
    # Filters
    col1, col2, col3 = st.columns(3)
    
    with col1:
        metric_type = st.selectbox(
            "Select Metric", 
            ["BRIX", "Torque", "Net Content", "All Parameters"]
        )
    
    with col2:
        date_range = st.date_input(
            "Date Range",
            [dt.datetime.now() - dt.timedelta(days=7), dt.datetime.now()],
            max_value=dt.datetime.now()
        )
    
    with col3:
        product_filter = st.multiselect(
            "Filter by Product",
            ["All", "Blackberry", "Raspberry", "Cream Soda", "Mazoe Orange Crush", 
             "Bonaqua Water", "Schweppes Still Water"],
            default=["All"]
        )
    
    # Get filtered data
    start_date, end_date = date_range
    end_date = dt.datetime.combine(end_date, dt.time(23, 59, 59))
    
    # Get data based on selected metric
    data = st.session_state.get_check_data(start_date, end_date, product_filter)
    
    if data.empty:
        st.info("No data available for the selected filters.")
    else:
        # Display visualizations based on selected metric
        if metric_type == "BRIX":
            st.session_state.viz_modules[0](data)
        elif metric_type == "Torque":
            st.session_state.viz_modules[1](data)
        elif metric_type == "Net Content":
            st.subheader("Net Content Analysis")
            # Placeholder for net content visualization
        else:  # All Parameters
            st.session_state.viz_modules[2](data)

def show_reports():
    """Complete reports page with all original functionality"""
    st.title("Quality Assurance Reports")
    
    report_type = st.selectbox(
        "Report Type",
        ["Daily Summary", "Weekly Summary", "Monthly Summary", "Custom Period"]
    )
    
    if report_type == "Custom Period":
        date_range = st.date_input(
            "Select Date Range",
            [dt.datetime.now() - dt.timedelta(days=7), dt.datetime.now()],
            max_value=dt.datetime.now()
        )
        start_date, end_date = date_range
    else:
        # Calculate date range based on report type
        end_date = dt.datetime.now().date()
        if report_type == "Daily Summary":
            start_date = end_date
        elif report_type == "Weekly Summary":
            start_date = end_date - dt.timedelta(days=7)
        else:  # Monthly Summary
            start_date = end_date.replace(day=1)
    
    # Generate report
    report_data = st.session_state.report_modules[0](start_date, end_date)
    
    if report_data:
        st.subheader(f"Report for {start_date} to {end_date}")
        st.dataframe(report_data, use_container_width=True)
        
        # Download report
        st.session_state.report_modules[1](
            report_data, 
            f"{report_type.replace(' ', '_')}_{start_date}_to_{end_date}"
        )
    else:
        st.info("No data available for the selected period.")

def show_user_management():
    """Complete user management page with all original functionality"""
    st.title("User Management")
    
    # Get all users
    users_data = st.session_state.db.get_all_users_data()
    
    if users_data.empty:
        st.info("No users found.")
    else:
        st.subheader("Users")
        # Display user data (exclude password hash)
        display_df = users_data[['username', 'created_at', 'last_login']]
        display_df['created_at'] = display_df['created_at'].apply(
            st.session_state.app_modules['format_timestamp']
        )
        display_df['last_login'] = display_df['last_login'].apply(
            lambda x: st.session_state.app_modules['format_timestamp'](x) if x else "Never"
        )
        display_df.columns = ['Username', 'Created At', 'Last Login']
        st.dataframe(display_df, use_container_width=True)

# =============================================
# Navigation & Main Layout
# =============================================
with st.sidebar:
    st.title(f"Welcome, {st.session_state.username}")

     # Define the tab options
    tab_options = [
        "Dashboard", "Data Entry", "Visualizations", "SPC Analysis", 
        "Process Capability", "Trend Prediction", "Anomaly Detection",
        "Shift Handover", "Lab Inventory", "Reports", "Compliance Reports",
        "User Management"
    ]

    app_mode = st.selectbox(
        "Navigation",
        tab_options,
        index=tab_options.index(st.session_state.last_tab) if st.session_state.last_tab in tab_options else 0
    )
    
     # Update the last_tab in session state when user selects a new tab
    if app_mode != st.session_state.last_tab:
        st.session_state.last_tab = app_mode
        # Store the current tab in database
        if st.session_state.authenticated and st.session_state.username:
            st.session_state.db.update_user_last_tab(st.session_state.username, app_mode)

    if st.button("Logout"):
        try:
            # Store the current tab before logging out if user is authenticated
            if st.session_state.get('authenticated', False) and st.session_state.get('username'):
                st.session_state.db.update_user_last_tab(
                    st.session_state.username, 
                    st.session_state.get('last_tab', 'Dashboard')
                )

            # Determine which logout function to use (with fallbacks)
            logout_func = None
            
            # Check for auth tuple first (your original approach)
            if 'auth' in st.session_state and len(st.session_state.auth) > 2:
                logout_func = st.session_state.auth[2]
            # Check for direct logout function
            elif hasattr(st.session_state, 'logout'):
                logout_func = st.session_state.logout
            # Check for auth_functions dictionary
            elif 'auth_functions' in st.session_state and 'logout' in st.session_state.auth_functions:
                logout_func = st.session_state.auth_functions['logout']
            
            # Execute logout if we found a function
            if logout_func:
                logout_func()
            else:
                st.warning("No logout function found - performing basic cleanup")

            # Clear session state (regardless of logout method)
            st.session_state.update({
                'authenticated': False,
                'username': None,
                'form_type': None,
                'start_time': None,
                'check_id': None
            })
            
            st.rerun()
            
        except Exception as e:
            st.error(f"Logout failed: {str(e)}")
            # Fallback to minimal cleanup if something went wrong
            st.session_state.authenticated = False
            st.session_state.username = None
            st.rerun()
    
    # Performance debug
    if st.checkbox("Show Performance", False):
        current_time = time.time()
        load_time = current_time - APP_START_TIME
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("App Load Time", f"{load_time:.2f}s")
        with col2:
            st.metric("Current Time", dt.datetime.now().strftime("%H:%M:%S"))
        
        # Additional performance info
        st.caption(f"Python version: {sys.version.split()[0]}")
        st.caption(f"Streamlit version: {st.__version__}")

# Route to the selected page
if app_mode == "Dashboard":
    show_dashboard()
elif app_mode == "Data Entry":
    show_data_entry()
elif app_mode == "Visualizations":
    show_visualizations()
elif app_mode == "SPC Analysis":
    st.session_state.app_modules['display_spc_page']()
elif app_mode == "Process Capability":
    st.session_state.app_modules['display_capability_page']()
elif app_mode == "Trend Prediction":
    st.session_state.app_modules['display_prediction_page']()
elif app_mode == "Anomaly Detection":
    st.session_state.app_modules['display_anomaly_detection_page']()
elif app_mode == "Shift Handover":
    st.session_state.app_modules['display_shift_handover_page']()
elif app_mode == "Lab Inventory":
    st.session_state.app_modules['display_lab_inventory_page']()
elif app_mode == "Reports":
    show_reports()
elif app_mode == "Compliance Reports":
    st.session_state.app_modules['display_compliance_report_page']()
elif app_mode == "User Management":
    show_user_management()

