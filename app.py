import os
import streamlit as st
from streamlit import config
import time
import datetime as dt
import pandas as pd
import sys
import io
import matplotlib.pyplot as plt
from auth import (
    authenticate_user, 
    create_user, 
    logout, 
    get_current_user, 
    require_role, 
    hash_password,
    show_login_form
)

# =============================================
# Early session state initialization
# =============================================
if 'db' not in st.session_state:
    st.session_state.db = None
    st.session_state.get_check_data = lambda *args, **kwargs: pd.DataFrame()

required_keys = {
    'authenticated': False,
    'username': None,
    'role': None,
    'form_type': None,
    'start_time': None,
    'check_id': None,
    'page_loaded': False,
    'last_tab': 'Dashboard',
    'init_phase': 'starting',
    'needs_rerun': False
}

for key, default_value in required_keys.items():
    if key not in st.session_state:
        st.session_state[key] = default_value

# Rerun handling at the top level
if st.session_state.needs_rerun:
    st.session_state.needs_rerun = False
    st.rerun()

# =============================================
# Environment Configuration
# =============================================
os.environ.update({
    'STREAMLIT_SERVER_PORT': '5000',
    'STREAMLIT_SERVER_ADDRESS': '0.0.0.0',
    'STREAMLIT_BROWSER_GATHER_USAGE_STATS': 'false',
    'BROWSER': 'true',
})

config.set_option('server.fileWatcherType', 'none')

# =============================================
# Fallback Classes
# =============================================
class FallbackDatabase:
    def get_recent_checks(self, limit):
        st.warning("Using fallback database - no real data available")
        return pd.DataFrame(columns=['check_id', 'check_type', 'timestamp', 'username', 'trade_name', 'product'])
    
    def get_user_checks(self, username, limit):
        return self.get_recent_checks(limit)
    
    def get_public_checks(self, limit):
        return self.get_recent_checks(limit)
    
    def update_user_last_tab(self, username, tab):
        pass
    
    def get_all_users_data(self):
        return pd.DataFrame(columns=['username', 'role', 'created_at', 'last_login'])
    
    def get_check_data(self, *args, **kwargs):
        return pd.DataFrame()
    
    def execute_query(self, query, params=None):
        """Fallback implementation of execute_query"""
        st.warning("Using fallback database - query execution not available")
        return pd.DataFrame()

# =============================================
# RBAC Configuration
# =============================================
ROLE_PERMISSIONS = {
    'admin': {
        'pages': [
            "Dashboard", "Data Entry", "Visualizations", "SPC Analysis", 
            "Process Capability", "Trend Prediction", "Anomaly Detection",
            "Shift Handover", "Lab Inventory", "Reports", "Compliance Reports",
            "User Management"
        ],
        'permissions': {
            'view_all_data': True,
            'edit_all_data': True,
            'manage_users': True,
            'add_comments': True,
            'export_data': True
        }
    },
    'supervisor': {
        'pages': [
            "Dashboard", "Data Entry", "Visualizations", "SPC Analysis", 
            "Process Capability", "Trend Prediction", "Anomaly Detection",
            "Shift Handover", "Lab Inventory", "Reports", "Compliance Reports"
        ],
        'permissions': {
            'view_all_data': True,
            'edit_all_data': True,
            'manage_users': False,
            'add_comments': True,
            'export_data': True
        }
    },
    'operator': {
        'pages': [
            "Dashboard", "Data Entry", "Visualizations", "SPC Analysis",
            "Process Capability", "Trend Prediction", "Anomaly Detection",
            "Shift Handover", "Lab Inventory", "Reports", "Compliance Reports"
        ],
        'permissions': {
            'view_all_data': True,
            'edit_own_data': True,
            'manage_users': False,
            'add_comments': True,
            'export_data': True
        }
    },
    'viewer': {
        'pages': [
            "Dashboard", "Visualizations", "SPC Analysis",
            "Process Capability", "Trend Prediction", "Anomaly Detection",
            "Lab Inventory", "Compliance Reports"
        ],
        'permissions': {
            'view_public_data': True,
            'edit_data': False,
            'manage_users': False,
            'add_comments': False,
            'export_data': False
        }
    },
    'guest': {
        'pages': ["Dashboard"],
        'permissions': {
            'view_public_data': True,
            'edit_data': False,
            'manage_users': False,
            'add_comments': False,
            'export_data': False
        }
    }
}

# =============================================
# Initial Setup
# =============================================
st.set_page_config(
    page_title="Beverage QA Tracker",
    page_icon="🧪",
    layout="wide",
    initial_sidebar_state="expanded"
)

APP_START_TIME = time.time()

# Show loading spinner immediately
loading_placeholder = st.empty()
with loading_placeholder:
    st.spinner("Initializing application...")

# =============================================
# Lazy Loaded Modules (Cached Resources)
# =============================================
@st.cache_resource(ttl=3600)
def load_database():
    try:
        from database import BeverageQADatabase, get_check_data
        from hybrid_db import HybridDatabase
        
        online_db = BeverageQADatabase()
        if not hasattr(online_db, 'test_connection') or not online_db.test_connection():
            raise ConnectionError("Online database connection failed")
            
        return HybridDatabase(online_db), get_check_data
        
    except Exception as e:
        st.error(f"Database initialization failed: {str(e)}")
        st.warning("Using fallback database")
        return FallbackDatabase(), lambda *args, **kwargs: pd.DataFrame()

@st.cache_resource
def load_form_modules():
    """Load form modules with proper error handling and fallbacks"""
    modules = {
        'torque_tamper': lambda: st.error("Torque form module not loaded"),
        'net_content': lambda: st.error("Net content form module not loaded"),
        'quality_check': lambda: st.error("Quality check form module not loaded")
    }
    
    try:
        from forms import display_torque_tamper_form
        modules['torque_tamper'] = display_torque_tamper_form
    except ImportError as e:
        st.warning(f"Could not load torque form module: {str(e)}")
    
    try:
        from forms import display_net_content_form
        modules['net_content'] = display_net_content_form
    except ImportError as e:
        st.warning(f"Could not load net content form module: {str(e)}")
    
    try:
        from forms import display_quality_check_form
        modules['quality_check'] = display_quality_check_form
    except ImportError as e:
        st.warning(f"Could not load quality check form module: {str(e)}")
    
    return (
        modules['torque_tamper'],
        modules['net_content'],
        modules['quality_check']
    )

@st.cache_resource
def load_visualization_modules():
    """Load visualization modules with proper error handling and fallbacks"""
    modules = {
        'brix': lambda: st.error("Brix visualization module not loaded"),
        'torque': lambda: st.error("Torque visualization module not loaded"),
        'quality': lambda: st.error("Quality visualization module not loaded")
    }
    
    try:
        from visualization import display_brix_visualization
        modules['brix'] = display_brix_visualization
    except ImportError as e:
        st.warning(f"Could not load brix visualization module: {str(e)}")
    
    try:
        from visualization import display_torque_visualization
        modules['torque'] = display_torque_visualization
    except ImportError as e:
        st.warning(f"Could not load torque visualization module: {str(e)}")
    
    try:
        from visualization import display_quality_metrics_visualization
        modules['quality'] = display_quality_metrics_visualization
    except ImportError as e:
        st.warning(f"Could not load quality visualization module: {str(e)}")
    
    return (
        modules['brix'],
        modules['torque'],
        modules['quality']
    )

@st.cache_resource
def load_report_modules():
    """Load report modules with proper error handling and fallbacks"""
    modules = {
        'generate': lambda *args, **kwargs: st.error("Report generation module not loaded"),
        'download': lambda *args, **kwargs: st.error("Report download module not loaded")
    }
    
    try:
        from reports import generate_report
        modules['generate'] = generate_report
    except ImportError as e:
        st.warning(f"Could not load report generation module: {str(e)}")
    
    try:
        from reports import download_report
        modules['download'] = download_report
    except ImportError as e:
        st.warning(f"Could not load report download module: {str(e)}")
    
    return (
        modules['generate'],
        modules['download']
    )

@st.cache_resource
def load_other_modules():
    """Load miscellaneous utility modules with proper error handling"""
    modules = {
        'format_timestamp': lambda x: str(x),
        'display_spc_page': lambda: st.error("SPC module not loaded"),
        'display_capability_page': lambda: st.error("Capability module not loaded"),
        'display_compliance_report_page': lambda: st.error("Compliance module not loaded"),
        'display_prediction_page': lambda: st.error("Prediction module not loaded"),
        'display_anomaly_detection_page': lambda: st.error("Anomaly module not loaded"),
        'display_shift_handover_page': lambda: st.error("Handover module not loaded"),
        'display_lab_inventory_page': lambda: st.error("Inventory module not loaded")
    }
    
    try:
        from utils import format_timestamp
        modules['format_timestamp'] = format_timestamp
    except ImportError as e:
        st.warning(f"Could not load utils module: {str(e)}")
    
    try:
        from spc import display_spc_page
        modules['display_spc_page'] = display_spc_page
    except ImportError as e:
        st.warning(f"Could not load SPC module: {str(e)}")
    
    try:
        from capability import display_capability_page
        modules['display_capability_page'] = display_capability_page
    except ImportError as e:
        st.warning(f"Could not load capability module: {str(e)}")
    
    try:
        from compliance import display_compliance_report_page
        modules['display_compliance_report_page'] = display_compliance_report_page
    except ImportError as e:
        st.warning(f"Could not load compliance module: {str(e)}")
    
    try:
        from prediction import display_prediction_page
        modules['display_prediction_page'] = display_prediction_page
    except ImportError as e:
        st.warning(f"Could not load prediction module: {str(e)}")
    
    try:
        from anomaly import display_anomaly_detection_page
        modules['display_anomaly_detection_page'] = display_anomaly_detection_page
    except ImportError as e:
        st.warning(f"Could not load anomaly module: {str(e)}")
    
    try:
        from handover import display_shift_handover_page
        modules['display_shift_handover_page'] = display_shift_handover_page
    except ImportError as e:
        st.warning(f"Could not load handover module: {str(e)}")
    
    try:
        from lab_inventory import display_lab_inventory_page
        modules['display_lab_inventory_page'] = display_lab_inventory_page
    except ImportError as e:
        st.warning(f"Could not load inventory module: {str(e)}")
    
    return modules

# =============================================
# Modified initialization phase
# =============================================
if st.session_state.init_phase == 'starting':
    try:
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        def update_status(step, total, message):
            progress = min(step/total, 1.0)
            progress_bar.progress(progress)
            status_text.text(f"Initializing... ({int(progress*100)}%) {message}")
        
        # Load modules
        update_status(1, 5, "Loading core modules...")
        st.session_state.app_modules = load_other_modules()
        
        update_status(2, 5, "Connecting to database...")
        try:
            from database import BeverageQADatabase
            online_db = BeverageQADatabase()
            if hasattr(online_db, 'test_connection') and online_db.test_connection():
                try:
                    from hybrid_db import HybridDatabase
                    st.session_state.db = HybridDatabase(online_db)
                    st.session_state.get_check_data = online_db.get_check_data
                except ImportError:
                    st.warning("Using direct database connection")
                    st.session_state.db = online_db
                    st.session_state.get_check_data = online_db.get_check_data
            else:
                raise ConnectionError("Online database failed")
        except Exception as e:
            st.warning(f"Using fallback database: {str(e)}")
            st.session_state.db = FallbackDatabase()
            st.session_state.get_check_data = lambda *args, **kwargs: pd.DataFrame()
        
        update_status(3, 5, "Loading forms...")
        st.session_state.form_modules = load_form_modules()
        
        update_status(4, 5, "Loading visualizations...")
        st.session_state.viz_modules = load_visualization_modules()
        
        update_status(5, 5, "Loading reports...")
        st.session_state.report_modules = load_report_modules()
        
        st.session_state.init_phase = 'ready'
        
    except Exception as e:
        st.session_state.init_phase = 'failed'
        st.error(f"Initialization error: {str(e)}")
    finally:
        if 'progress_bar' in locals():
            progress_bar.empty()
        if 'status_text' in locals():
            status_text.empty()

if st.session_state.init_phase == 'failed':
    if st.button("Retry Initialization"):
        st.cache_resource.clear()
        st.session_state.clear()
        st.session_state.needs_rerun = True
    st.stop()

# =============================================
# Helper Functions
# =============================================
def export_as_png(fig, filename):
    """Helper function to export graphs as PNG"""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=300)
    buf.seek(0)
    plt.close(fig)
    
    st.download_button(
        label="Download as PNG",
        data=buf,
        file_name=filename,
        mime="image/png",
        key=f"export_{filename}"
    )

def check_system_health():
    """Check if all required components are initialized"""
    required = ['db', 'app_modules', 'viz_modules', 'report_modules', 'form_modules']
    return all(comp in st.session_state for comp in required)

def get_allowed_pages():
    """Determine which pages the current user can access based on role"""
    role = st.session_state.get('role', 'guest')
    return ROLE_PERMISSIONS.get(role, ROLE_PERMISSIONS['guest'])['pages']

def check_permission(action, resource=None):
    """Check if current user has permission for an action on a resource"""
    role = st.session_state.get('role', 'guest')
    permissions = ROLE_PERMISSIONS.get(role, ROLE_PERMISSIONS['guest'])['permissions']
    
    if action == 'view':
        if resource == 'all_data':
            return permissions.get('view_all_data', False)
        elif resource == 'own_data':
            return permissions.get('edit_own_data', False)  # If can edit own, can view own
        return permissions.get('view_public_data', False)
    elif action == 'edit':
        if resource == 'all_data':
            return permissions.get('edit_all_data', False)
        elif resource == 'own_data':
            return permissions.get('edit_own_data', False)
        return permissions.get('edit_data', False)
    elif action == 'manage':
        return permissions.get('manage_users', False)
    elif action == 'comment':
        return permissions.get('add_comments', False)
    elif action == 'export':
        return permissions.get('export_data', False)
    return False

def generate_check_id():
    """Generate a unique check ID for new quality checks"""
    return f"CHK-{dt.datetime.now().strftime('%Y%m%d%H%M%S')}-{st.session_state.username[:3].upper()}"

# =============================================
# Page Components with RBAC
# =============================================
@require_role("admin", "supervisor", "operator", "viewer", "guest")
def show_dashboard():
    """Dashboard with role-based content"""
    if not check_system_health():
        st.error("System not properly initialized")
        st.button("Retry Initialization", on_click=lambda: st.cache_resource.clear() or st.session_state.clear() or st.session_state.needs_rerun)
        st.stop()
    
    st.title("Quality Assurance Dashboard")
    
    @st.cache_data(ttl=300)
    def get_recent_checks():
        try:
            if check_permission('view', 'all_data'):
                return st.session_state.db.get_recent_checks(10)
            elif check_permission('edit', 'own_data'):
                return st.session_state.db.get_user_checks(st.session_state.username, 10)
            else:
                return st.session_state.db.get_public_checks(5)
        except Exception as e:
            st.error(f"Failed to load checks: {str(e)}")
            return pd.DataFrame()
    
    recent_checks = get_recent_checks()
    
    if recent_checks.empty:
        st.info("No recent checks found.")
    else:
        display_df = recent_checks.copy()
        if 'timestamp' in display_df.columns:
            display_df['timestamp'] = display_df['timestamp'].apply(st.session_state.app_modules.get('format_timestamp', str))
        
        base_columns = ['check_type', 'timestamp', 'trade_name', 'product']
        if check_permission('view', 'all_data'):
            display_df = display_df[['check_id'] + base_columns + ['username']]
            display_df.columns = ['Check ID'] + [col.title() for col in base_columns] + ['Inspector']
        else:
            display_df = display_df[base_columns]
            display_df.columns = [col.title() for col in base_columns]
        
        st.dataframe(display_df, use_container_width=True)
        
        col1, col2, col3 = st.columns(3)
        with col1:
            today_checks = len(recent_checks[recent_checks['timestamp'].dt.date == dt.datetime.now().date()]) if 'timestamp' in recent_checks.columns else 0
            st.metric("Total Checks Today", today_checks)
        
        with col2:
            st.metric("Active Inspectors", recent_checks['username'].nunique() if 'username' in recent_checks.columns else 0)
        
        with col3:
            pass_rate = 100
            if 'tamper_evidence' in recent_checks.columns:
                pass_rate = int(100 * recent_checks['tamper_evidence'].str.contains('PASS').sum() / len(recent_checks))
            st.metric("Tamper Evidence Pass Rate", f"{pass_rate}%")
        
        if st.session_state.viz_modules[0] and check_permission('view', 'all_data'):
            st.subheader("Quick Insights")
            tab1, tab2 = st.tabs(["BRIX Trends", "Torque Performance"])
            
            with tab1:
                fig = st.session_state.viz_modules[0](recent_checks, height=400)
                if fig and check_permission('export'):
                    export_as_png(fig, "brix_trends.png")
            
            with tab2:
                fig = st.session_state.viz_modules[1](recent_checks, height=400)
                if fig and check_permission('export'):
                    export_as_png(fig, "torque_performance.png")

@require_role("admin", "supervisor", "operator")
def show_data_entry():
    """Data entry forms for quality checks"""
    if not check_system_health():
        st.error("System not properly initialized")
        return
    
    st.title("Quality Data Entry")
    
    # Generate a new check ID if one doesn't exist
    if 'check_id' not in st.session_state or not st.session_state.check_id:
        st.session_state.check_id = generate_check_id()
    
    # Ensure start_time is set
    if 'start_time' not in st.session_state or not st.session_state.start_time:
        st.session_state.start_time = dt.datetime.now()
    
    form_type = st.radio(
        "Select Form Type",
        ["Torque & Tamper", "Net Content", "30-Min Quality Check"],
        horizontal=True
    )
    
    # Get required parameters from session state
    username = st.session_state.get('username')
    start_time = st.session_state.get('start_time')
    check_id = st.session_state.get('check_id')
    
    # Debug output to verify values
    st.write(f"Debug - Username: {username}, Start Time: {start_time}, Check ID: {check_id}")
    
    if form_type == "Torque & Tamper" and st.session_state.form_modules[0]:
        try:
            st.session_state.form_modules[0](
                username=username,
                start_time=start_time,
                check_id=check_id
            )
        except Exception as e:
            st.error(f"Error displaying torque form: {str(e)}")
    elif form_type == "Net Content" and st.session_state.form_modules[1]:
        try:
            st.session_state.form_modules[1](
                username=username,
                start_time=start_time,
                check_id=check_id
            )
        except Exception as e:
            st.error(f"Error displaying net content form: {str(e)}")
    elif form_type == "30-Min Quality Check" and st.session_state.form_modules[2]:
        try:
            st.session_state.form_modules[2](
                username=username,
                start_time=start_time,
                check_id=check_id
            )
        except Exception as e:
            st.error(f"Error displaying quality check form: {str(e)}")
    else:
        st.error("Form modules not loaded properly")

@require_role("admin", "supervisor", "operator", "viewer")
def show_visualizations():
    """Interactive visualizations of quality data"""
    if not check_system_health():
        st.error("System not properly initialized")
        return
    
    st.title("Quality Data Visualizations")
    
    # Date range selector
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("Start Date", dt.date.today() - dt.timedelta(days=7))
    with col2:
        end_date = st.date_input("End Date", dt.date.today())
    
    if start_date > end_date:
        st.error("End date must be after start date")
        return
    
    # Product filter
    product_options = ["All"] + list(st.session_state.db.get_check_data(
        start_date, end_date
    )['product'].dropna().unique())
    
    selected_products = st.multiselect(
        "Filter by Product (optional)",
        product_options,
        default="All"
    )
    
    # Load data with appropriate permissions
    with st.spinner("Loading data..."):
        if check_permission('view', 'all_data'):
            data = st.session_state.get_check_data(
                start_date,
                end_date,
                selected_products if "All" not in selected_products else None
            )
        elif check_permission('edit', 'own_data'):
            data = st.session_state.db.get_user_checks(
                st.session_state.username,
                start_date=start_date,
                end_date=end_date,
                products=selected_products if "All" not in selected_products else None
            )
        else:
            data = st.session_state.db.get_public_checks(
                start_date=start_date,
                end_date=end_date,
                products=selected_products if "All" not in selected_products else None
            )
    
    if data.empty:
        st.info("No data found for selected filters")
        return
    
    # Visualization tabs
    tab1, tab2, tab3 = st.tabs(["BRIX Analysis", "Torque Analysis", "Quality Metrics"])
    
    with tab1:
        if st.session_state.viz_modules[0]:
            fig = st.session_state.viz_modules[0](data, height=500)
            if fig and check_permission('export'):
                export_as_png(fig, "brix_analysis.png")
    
    with tab2:
        if st.session_state.viz_modules[1]:
            fig = st.session_state.viz_modules[1](data, height=500)
            if fig and check_permission('export'):
                export_as_png(fig, "torque_analysis.png")
    
    with tab3:
        if st.session_state.viz_modules[2]:
            fig = st.session_state.viz_modules[2](data, height=500)
            if fig and check_permission('export'):
                export_as_png(fig, "quality_metrics.png")

@require_role("admin", "supervisor", "operator")
def show_reports():
    """Generate and download quality reports"""
    if not check_system_health():
        st.error("System not properly initialized")
        return
    
    st.title("Quality Reports")
    
    # Date range selector
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("Report Start Date", dt.date.today() - dt.timedelta(days=7))
    with col2:
        end_date = st.date_input("Report End Date", dt.date.today())
    
    if start_date > end_date:
        st.error("End date must be after start date")
        return
    
    # Report type selector
    report_type = st.selectbox(
        "Report Type",
        ["Daily Summary", "Shift Summary", "Product Analysis", "Full Quality Report"]
    )
    
    # Comment field for reports
    report_comment = ""
    if check_permission('comment'):
        report_comment = st.text_area("Add comments to report")
    
    # Generate report
    if st.button("Generate Report"):
        with st.spinner(f"Generating {report_type} report..."):
            try:
                if check_permission('view', 'all_data'):
                    report_data = st.session_state.get_check_data(start_date, end_date)
                elif check_permission('edit', 'own_data'):
                    report_data = st.session_state.db.get_user_checks(
                        st.session_state.username,
                        start_date=start_date,
                        end_date=end_date
                    )
                else:
                    report_data = st.session_state.db.get_public_checks(
                        start_date=start_date,
                        end_date=end_date
                    )
                
                if report_data.empty:
                    st.warning("No data found for selected date range")
                    return
                
                report = st.session_state.report_modules[0](
                    report_data, 
                    report_type,
                    start_date=start_date,
                    end_date=end_date,
                    comments=report_comment
                )
                
                if report:
                    st.success("Report generated successfully")
                    st.session_state.report_modules[1](report, f"{report_type}_{start_date}_to_{end_date}.pdf")
            except Exception as e:
                st.error(f"Error generating report: {str(e)}")

@require_role("admin")
def show_user_management():
    """User management interface for admins"""
    if not check_system_health():
        st.error("System not properly initialized")
        return
    
    st.title("User Management")
    
    # Display current users
    users_df = st.session_state.db.get_all_users_data()
    if not users_df.empty:
        st.subheader("Current Users")
        
        # Add a delete checkbox column
        users_df['delete'] = False
        edited_df = st.data_editor(
            users_df,
            column_config={
                "password_hash": None,
                "created_at": st.column_config.DatetimeColumn(
                    "Created At",
                    format="YYYY-MM-DD HH:mm"
                ),
                "last_login": st.column_config.DatetimeColumn(
                    "Last Login",
                    format="YYYY-MM-DD HH:mm"
                ),
                "role": st.column_config.SelectboxColumn(
                    "Role",
                    options=["admin", "supervisor", "operator", "viewer"],
                    required=True
                ),
                "delete": st.column_config.CheckboxColumn(
                    "Delete?",
                    help="Check to delete user",
                    default=False
                )
            },
            disabled=["username", "created_at"],
            hide_index=True,
            use_container_width=True,
            key="user_management_editor"
        )
        
        # Create columns for action buttons
        col1, col2 = st.columns(2)
        
        with col1:
            # Save changes button
            if st.button("Save Role Changes"):
                try:
                    for _, row in edited_df.iterrows():
                        if not row['delete']:  # Only update roles for non-deleted users
                            st.session_state.db.update_user_role(row['username'], row['role'])
                    st.success("User roles updated successfully")
                    st.session_state.needs_rerun = True
                except Exception as e:
                    st.error(f"Error updating users: {str(e)}")
        
        with col2:
            # Delete users button
            if st.button("Delete Selected Users", type="primary"):
                try:
                    users_to_delete = edited_df[edited_df['delete']]['username'].tolist()
                    
                    if not users_to_delete:
                        st.warning("No users selected for deletion")
                    else:
                        # Confirm deletion
                        with st.expander("⚠️ Confirm User Deletion", expanded=True):
                            st.warning(f"You are about to delete {len(users_to_delete)} user(s)")
                            st.write("Users to be deleted:", ", ".join(users_to_delete))
                            
                            if st.button("Permanently Delete Users", type="primary"):
                                # First check if current user is trying to delete themselves
                                current_user = st.session_state.username
                                if current_user in users_to_delete:
                                    st.error("You cannot delete your own account while logged in")
                                    return
                                
                                # Perform deletion
                                for username in users_to_delete:
                                    st.session_state.db.delete_user(username)
                                
                                st.success(f"Deleted {len(users_to_delete)} user(s) successfully")
                                st.session_state.needs_rerun = True
                except Exception as e:
                    st.error(f"Error deleting users: {str(e)}")
    else:
        st.warning("No users found in database")
    
    # Add new user
    st.subheader("Add New User")
    with st.form("add_user_form"):
        new_username = st.text_input("Username")
        new_password = st.text_input("Password", type="password")
        confirm_password = st.text_input("Confirm Password", type="password")
        new_role = st.selectbox(
            "Role",
            ["admin", "supervisor", "operator", "viewer"]
        )
        
        if st.form_submit_button("Add User"):
            if not new_username or not new_password:
                st.error("Username and password are required")
            elif new_password != confirm_password:
                st.error("Passwords do not match")
            else:
                try:
                    success, message = create_user(new_username, new_password, new_role)
                    if success:
                        st.success(message)
                        st.session_state.needs_rerun = True
                    else:
                        st.error(message)
                except Exception as e:
                    st.error(f"Error creating user: {str(e)}")

# =============================================
# Navigation & Main Layout
# =============================================
with st.sidebar:
    if not st.session_state.get('authenticated'):
        st.title("Welcome, Guest")
        if show_login_form():
            st.session_state.needs_rerun = True
    else:
        st.title(f"Welcome, {st.session_state.username}")
        st.caption(f"Role: {st.session_state.role.capitalize()}")
        
        if st.button("Logout"):
            logout()
            st.session_state.needs_rerun = True
    
    # System status indicator
    if not check_system_health():
        st.error("⚠️ System initialization incomplete")
    elif isinstance(st.session_state.get('db'), FallbackDatabase):
        st.warning("⚠️ Using fallback database")
    
    # Get allowed pages based on role
    allowed_pages = get_allowed_pages()
    tab_options = [
        "Dashboard", "Data Entry", "Visualizations", "SPC Analysis", 
        "Process Capability", "Trend Prediction", "Anomaly Detection",
        "Shift Handover", "Lab Inventory", "Reports", "Compliance Reports",
        "User Management"
    ]
    filtered_tabs = [tab for tab in tab_options if tab in allowed_pages]
    
    if filtered_tabs:
        app_mode = st.selectbox(
            "Navigation",
            filtered_tabs,
            index=filtered_tabs.index(st.session_state.last_tab) if st.session_state.last_tab in filtered_tabs else 0
        )
        
        if app_mode != st.session_state.last_tab:
            st.session_state.last_tab = app_mode
            if st.session_state.authenticated and st.session_state.username:
                try:
                    # First try the dedicated update method if available
                    if hasattr(st.session_state.db, 'update_user_last_tab'):
                        st.session_state.db.update_user_last_tab(st.session_state.username, app_mode)
                    # Fallback to direct query execution if method not available
                    elif hasattr(st.session_state.db, 'execute_query'):
                        query = """
                            UPDATE users 
                            SET last_tab = %s 
                            WHERE username = %s
                        """
                        result = st.session_state.db.execute_query(query, (app_mode, st.session_state.username))
                        if result.empty:
                            st.warning("Could not update last tab in database")
                    else:
                        st.warning("Database doesn't support tab tracking updates")
                except Exception as e:
                    st.warning(f"Could not update last tab: {str(e)}")
                    # Ensure we don't show this warning for fallback database
                    if not isinstance(st.session_state.db, FallbackDatabase):
                        st.warning("Tab preference won't be saved between sessions")

    # Performance debug (only for admins/supervisors)
    if st.session_state.get('role') in ['admin', 'supervisor'] and st.checkbox("Show Performance", False):
        current_time = time.time()
        load_time = current_time - APP_START_TIME
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("App Load Time", f"{load_time:.2f}s")
        with col2:
            st.metric("Current Time", dt.datetime.now().strftime("%H:%M:%S"))
        
        st.caption(f"Python: {sys.version.split()[0]}")
        st.caption(f"Streamlit: {st.__version__}")

# =============================================
# Main Application Router
# =============================================
if not check_system_health():
    st.error("Critical system components failed to initialize")
    st.button("Retry Initialization", on_click=lambda: st.cache_resource.clear() or st.session_state.clear() or st.session_state.needs_rerun)
    st.stop()

if not st.session_state.get('authenticated'):
    # Show login page or dashboard for guests
    if 'app_mode' not in locals() or app_mode == "Dashboard":
        show_dashboard()
    else:
        st.warning("Please log in to access this page")
elif app_mode == "Dashboard":
    show_dashboard()
elif app_mode == "Data Entry":
    show_data_entry()
elif app_mode == "Visualizations":
    show_visualizations()
elif app_mode == "SPC Analysis":
    if 'display_spc_page' in st.session_state.app_modules:
        st.session_state.app_modules['display_spc_page']()
    else:
        st.error("SPC Analysis module not available")
elif app_mode == "Process Capability":
    if 'display_capability_page' in st.session_state.app_modules:
        # Date range selector for capability analysis
        st.sidebar.subheader("Date Range for Analysis")
        today = dt.date.today()
        start_date = st.sidebar.date_input(
            "Start Date", 
            today - dt.timedelta(days=30),
            max_value=today
        )
        end_date = st.sidebar.date_input(
            "End Date", 
            today,
            min_value=start_date,
            max_value=today
        )
        
        # Load data with appropriate permissions
        with st.spinner(f"Loading data from {start_date} to {end_date}..."):
            try:
                if check_permission('view', 'all_data'):
                    data = st.session_state.get_check_data(start_date, end_date)
                elif check_permission('edit', 'own_data'):
                    data = st.session_state.db.get_user_checks(
                        st.session_state.username,
                        start_date=start_date,
                        end_date=end_date
                    )
                else:
                    data = st.session_state.db.get_public_checks(
                        start_date=start_date,
                        end_date=end_date
                    )
                
                if data.empty:
                    st.warning(f"No data available between {start_date} and {end_date}")
                    st.stop()
                
                # Determine edit mode based on permissions
                edit_mode = check_permission('edit', 'all_data') or check_permission('edit', 'own_data')
                st.session_state.app_modules['display_capability_page'](
                    data=data,
                    edit_mode=edit_mode
                )
            except Exception as e:
                st.error(f"Error loading data: {str(e)}")
                st.stop()
    else:
        st.error("Process Capability module not available")
elif app_mode == "Trend Prediction":
    if 'display_prediction_page' in st.session_state.app_modules:
        st.session_state.app_modules['display_prediction_page']()
    else:
        st.error("Trend Prediction module not available")
elif app_mode == "Anomaly Detection":
    if 'display_anomaly_detection_page' in st.session_state.app_modules:
        st.session_state.app_modules['display_anomaly_detection_page']()
    else:
        st.error("Anomaly Detection module not available")
elif app_mode == "Shift Handover":
    if 'display_shift_handover_page' in st.session_state.app_modules:
        edit_mode = check_permission('edit', 'all_data') or check_permission('edit', 'own_data')
        st.session_state.app_modules['display_shift_handover_page'](edit_mode=edit_mode)
    else:
        st.error("Shift Handover module not available")
elif app_mode == "Lab Inventory":
    if 'display_lab_inventory_page' in st.session_state.app_modules:
        edit_mode = check_permission('edit', 'all_data') or check_permission('edit', 'own_data')
        comment_mode = check_permission('comment')
        st.session_state.app_modules['display_lab_inventory_page'](
            edit_mode=edit_mode,
            comment_mode=comment_mode
        )
    else:
        st.error("Lab Inventory module not available")
elif app_mode == "Reports":
    show_reports()
elif app_mode == "Compliance Reports":
    if 'display_compliance_report_page' in st.session_state.app_modules:
        edit_mode = check_permission('edit', 'all_data') or check_permission('edit', 'own_data')
        st.session_state.app_modules['display_compliance_report_page'](edit_mode=edit_mode)
    else:
        st.error("Compliance Reports module not available")
elif app_mode == "User Management":
    show_user_management()