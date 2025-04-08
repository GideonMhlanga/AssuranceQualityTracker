import streamlit as st
import pandas as pd
import datetime as dt
from auth import authenticate_user, create_user_if_not_exists, logout
from forms import (
    display_torque_tamper_form, 
    display_net_content_form, 
    display_quality_check_form
)
from visualization import (
    display_brix_visualization,
    display_torque_visualization,
    display_quality_metrics_visualization
)
from reports import generate_report, download_report
from database import (
    initialize_database,
    get_check_data,
    get_all_users_data,
    get_recent_checks
)
from utils import format_timestamp
from spc import display_spc_page
from capability import display_capability_page
from compliance import display_compliance_report_page
from prediction import display_prediction_page
from anomaly import display_anomaly_detection_page
from handover import display_shift_handover_page

# Page configuration
st.set_page_config(
    page_title="Beverage QA Tracker",
    page_icon="🧪",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize database
initialize_database()

# Initialize session state variables if they don't exist
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'username' not in st.session_state:
    st.session_state.username = None
if 'form_type' not in st.session_state:
    st.session_state.form_type = None
if 'start_time' not in st.session_state:
    st.session_state.start_time = None
if 'check_id' not in st.session_state:
    st.session_state.check_id = None

# Authentication
if not st.session_state.authenticated:
    # Center the login form with CSS
    st.markdown("""
    <style>
    .main > div {
        padding-top: 2rem;
    }
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
    .stButton > button {
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
    </div>
    """, unsafe_allow_html=True)
    
    # Create login form
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
            elif authenticate_user(username, password):
                st.session_state.authenticated = True
                st.session_state.username = username
                st.success("Login successful! Redirecting...")
                st.rerun()
            else:
                st.error("Invalid username or password")
    
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
                if create_user_if_not_exists(new_username, new_password):
                    st.success("Account created successfully! You can now log in.")
                else:
                    st.error("Username already exists. Please choose a different one.")

else:
    # Main application after authentication
    # Sidebar navigation
    st.sidebar.title(f"Welcome, {st.session_state.username}")
    
    app_mode = st.sidebar.selectbox(
        "Navigation",
        ["Dashboard", "Data Entry", "Visualizations", "SPC Analysis", "Process Capability", "Trend Prediction", 
         "Anomaly Detection", "Shift Handover", "Reports", "Compliance Reports", "User Management"]
    )
    
    if st.sidebar.button("Logout"):
        logout()
        st.rerun()
    
    # Dashboard page
    if app_mode == "Dashboard":
        st.title("Quality Assurance Dashboard")
        
        # Display recent checks
        st.subheader("Recent Quality Checks")
        recent_checks = get_recent_checks(10)  # Get last 10 checks
        
        if recent_checks.empty:
            st.info("No recent checks found. Start by entering data in the Data Entry section.")
        else:
            # Format the dataframe for display
            display_df = recent_checks.copy()
            display_df['timestamp'] = display_df['timestamp'].apply(format_timestamp)
            display_df = display_df[['check_id', 'check_type', 'username', 'timestamp', 'trade_name', 'product']]
            display_df.columns = ['Check ID', 'Check Type', 'Inspector', 'Timestamp', 'Trade Name', 'Product']
            st.dataframe(display_df, use_container_width=True)
            
        # Display summary metrics
        col1, col2, col3 = st.columns(3)
        
        with col1:
            # Make sure timestamp is properly converted to datetime
            today_date = dt.datetime.now().date()
            today_checks = 0
            if not recent_checks.empty:
                # Convert timestamp to datetime if it's not already
                if not pd.api.types.is_datetime64_any_dtype(recent_checks['timestamp']):
                    recent_checks['timestamp'] = pd.to_datetime(recent_checks['timestamp'])
                today_checks = len(recent_checks[recent_checks['timestamp'].dt.date == today_date])
            st.metric("Total Checks Today", today_checks)
        
        with col2:
            st.metric("Active Inspectors", 
                     recent_checks['username'].nunique())
        
        with col3:
            # Calculate percentage of passing checks (just an example)
            pass_rate = 100
            if not recent_checks.empty and 'tamper_evidence' in recent_checks.columns:
                pass_rate = int(100 * recent_checks['tamper_evidence'].str.contains('PASS').sum() / 
                            len(recent_checks))
            st.metric("Tamper Evidence Pass Rate", f"{pass_rate}%")
        
        # Show quick visualizations
        st.subheader("Quick Insights")
        
        # Display mini-visualizations if data exists
        if not recent_checks.empty:
            tab1, tab2 = st.tabs(["BRIX Trends", "Torque Performance"])
            
            with tab1:
                display_brix_visualization(recent_checks, height=400)
                
            with tab2:
                display_torque_visualization(recent_checks, height=400)
    
    # Data Entry page
    elif app_mode == "Data Entry":
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
            st.session_state.start_time = dt.datetime.now()
            st.session_state.form_type = form_type
            # Generate a unique check ID
            st.session_state.check_id = f"CK-{dt.datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        # Display the appropriate form
        if form_type == "Torque and Tamper Evidence":
            display_torque_tamper_form(st.session_state.username, 
                                      st.session_state.start_time,
                                      st.session_state.check_id)
        
        elif form_type == "NET CONTENT Check":
            display_net_content_form(st.session_state.username,
                                    st.session_state.start_time,
                                    st.session_state.check_id)
        
        elif form_type == "30-Minute Quality Check":
            display_quality_check_form(st.session_state.username,
                                      st.session_state.start_time,
                                      st.session_state.check_id)
    
    # Visualizations page
    elif app_mode == "Visualizations":
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
                ["All", "Blackberry", "Raspberry", "Cream Soda", "Mazoe Orange Crush", "Bonaqua Water", "Schweppes Still Water"],
                default=["All"]
            )
        
        # Get filtered data
        start_date, end_date = date_range
        end_date = dt.datetime.combine(end_date, dt.time(23, 59, 59))
        
        # Get data based on selected metric
        data = get_check_data(start_date, end_date, product_filter)
        
        if data.empty:
            st.info("No data available for the selected filters.")
        else:
            # Display visualizations based on selected metric
            if metric_type == "BRIX":
                display_brix_visualization(data)
            elif metric_type == "Torque":
                display_torque_visualization(data)
            elif metric_type == "Net Content":
                st.subheader("Net Content Analysis")
                # Implement specific visualization for net content
                # This would be implemented in visualization.py
            else:  # All Parameters
                display_quality_metrics_visualization(data)
    
    # SPC Analysis page
    elif app_mode == "SPC Analysis":
        display_spc_page()
    
    # Process Capability page
    elif app_mode == "Process Capability":
        # Get filtered data for capability analysis
        col1, col2 = st.columns(2)
        
        with col1:
            date_range = st.date_input(
                "Date Range",
                [dt.datetime.now() - dt.timedelta(days=30), dt.datetime.now()],
                max_value=dt.datetime.now()
            )
        
        with col2:
            product_filter = st.multiselect(
                "Filter by Product",
                ["All", "Blackberry", "Raspberry", "Cream Soda", "Mazoe Orange Crush", "Bonaqua Water", "Schweppes Still Water"],
                default=["All"]
            )
        
        # Get filtered data
        start_date, end_date = date_range
        end_date = dt.datetime.combine(end_date, dt.time(23, 59, 59))
        
        # Get data for capability analysis
        capability_data = get_check_data(start_date, end_date, product_filter)
        
        # Display capability analysis page
        display_capability_page(capability_data, product_filter)
    
    # Trend Prediction page
    elif app_mode == "Trend Prediction":
        display_prediction_page()
    
    # Anomaly Detection page
    elif app_mode == "Anomaly Detection":
        display_anomaly_detection_page()
    
    # Shift Handover page
    elif app_mode == "Shift Handover":
        display_shift_handover_page()
    
    # Reports page
    elif app_mode == "Reports":
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
        report_data = generate_report(start_date, end_date)
        
        if report_data:
            st.subheader(f"Report for {start_date} to {end_date}")
            st.dataframe(report_data, use_container_width=True)
            
            # Download report
            download_report(report_data, f"{report_type.replace(' ', '_')}_{start_date}_to_{end_date}")
        else:
            st.info("No data available for the selected period.")
    
    # Compliance Reports page
    elif app_mode == "Compliance Reports":
        display_compliance_report_page()
    
    # User Management page
    elif app_mode == "User Management":
        st.title("User Management")
        
        # Get all users
        users_data = get_all_users_data()
        
        if users_data.empty:
            st.info("No users found.")
        else:
            st.subheader("Users")
            # Display user data (exclude password hash)
            display_df = users_data[['username', 'created_at', 'last_login']]
            display_df['created_at'] = display_df['created_at'].apply(format_timestamp)
            display_df['last_login'] = display_df['last_login'].apply(format_timestamp)
            display_df.columns = ['Username', 'Created At', 'Last Login']
            st.dataframe(display_df, use_container_width=True)
