import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import datetime as dt
import uuid
import json
from database import get_conn, get_check_data
from sqlalchemy import text
import base64
from utils import format_timestamp

# Initialize handover tables
def initialize_handover():
    """Initialize database tables for shift handover reports"""
    conn = get_conn()
    if conn:
        try:
            # Create shift handover table
            conn.execute(text('''
            CREATE TABLE IF NOT EXISTS shift_handover (
                handover_id TEXT PRIMARY KEY,
                shift_date DATE,
                shift_type TEXT,
                outgoing_shift_lead TEXT,
                incoming_shift_lead TEXT,
                production_summary TEXT,
                quality_issues TEXT,
                equipment_issues TEXT,
                pending_tasks TEXT,
                comments TEXT,
                created_at TIMESTAMP,
                status TEXT
            )
            '''))
            
            # Create handover acknowledgment table
            conn.execute(text('''
            CREATE TABLE IF NOT EXISTS handover_acknowledgment (
                acknowledgment_id TEXT PRIMARY KEY,
                handover_id TEXT,
                acknowledged_by TEXT,
                acknowledged_at TIMESTAMP,
                comments TEXT,
                FOREIGN KEY (handover_id) REFERENCES shift_handover (handover_id)
            )
            '''))
            
            # Create shift configuration table
            conn.execute(text('''
            CREATE TABLE IF NOT EXISTS shift_config (
                config_id SERIAL PRIMARY KEY,
                shift_name TEXT,
                start_time TEXT,
                end_time TEXT,
                is_active BOOLEAN
            )
            '''))
            
            # Insert default shift configurations if not exist
            result = conn.execute(text('SELECT COUNT(*) FROM shift_config'))
            count = result.scalar()
            
            if count == 0:
                # Insert default shifts
                conn.execute(text('''
                INSERT INTO shift_config (shift_name, start_time, end_time, is_active)
                VALUES 
                ('Morning', '06:00', '14:00', TRUE),
                ('Afternoon', '14:00', '22:00', TRUE),
                ('Night', '22:00', '06:00', TRUE)
                '''))
            
            conn.commit()
        except Exception as e:
            st.error(f"Error initializing handover tables: {e}")
        finally:
            conn.close()

# Save shift handover report
def save_handover_report(
    shift_date, shift_type, outgoing_lead, incoming_lead,
    production_summary, quality_issues, equipment_issues,
    pending_tasks, comments
):
    """
    Save a shift handover report to the database
    
    Args:
        shift_date: Date of the shift
        shift_type: Type of shift (Morning, Afternoon, Night)
        outgoing_lead: Name of outgoing shift lead
        incoming_lead: Name of incoming shift lead
        production_summary: Summary of production during the shift
        quality_issues: Description of quality issues encountered
        equipment_issues: Description of equipment issues encountered
        pending_tasks: List of pending tasks for next shift
        comments: Additional comments
        
    Returns:
        handover_id: ID of the saved handover report
    """
    conn = get_conn()
    if conn:
        try:
            handover_id = str(uuid.uuid4())
            current_time = dt.datetime.now()
            
            query = text('''
            INSERT INTO shift_handover (
                handover_id, shift_date, shift_type, outgoing_shift_lead,
                incoming_shift_lead, production_summary, quality_issues,
                equipment_issues, pending_tasks, comments, created_at, status
            )
            VALUES (
                :handover_id, :shift_date, :shift_type, :outgoing_lead,
                :incoming_lead, :production_summary, :quality_issues,
                :equipment_issues, :pending_tasks, :comments, :created_at, :status
            )
            ''')
            
            conn.execute(query, {
                'handover_id': handover_id,
                'shift_date': shift_date,
                'shift_type': shift_type,
                'outgoing_lead': outgoing_lead,
                'incoming_lead': incoming_lead,
                'production_summary': production_summary,
                'quality_issues': quality_issues,
                'equipment_issues': equipment_issues,
                'pending_tasks': pending_tasks,
                'comments': comments,
                'created_at': current_time,
                'status': 'pending'
            })
            
            conn.commit()
            return handover_id
        except Exception as e:
            st.error(f"Error saving handover report: {e}")
            return None
        finally:
            conn.close()
    
    return None

# Get shift handover reports
def get_handover_reports(days=7, status=None, shift_type=None):
    """
    Get shift handover reports
    
    Args:
        days: Number of days to look back
        status: Optional filter by status (pending, acknowledged)
        shift_type: Optional filter by shift type (Morning, Afternoon, Night)
        
    Returns:
        DataFrame with handover reports
    """
    conn = get_conn()
    if conn:
        try:
            # Base query with parameters
            params = {'days_ago': dt.datetime.now().date() - dt.timedelta(days=days)}
            
            query_str = '''
            SELECT h.*, 
                a.acknowledged_by, a.acknowledged_at, a.comments as acknowledgment_comments
            FROM shift_handover h
            LEFT JOIN handover_acknowledgment a ON h.handover_id = a.handover_id
            WHERE h.shift_date >= :days_ago
            '''
            
            # Add optional filters
            if status:
                query_str += " AND h.status = :status"
                params['status'] = status
            
            if shift_type:
                query_str += " AND h.shift_type = :shift_type"
                params['shift_type'] = shift_type
            
            # Add ordering
            query_str += " ORDER BY h.shift_date DESC, h.shift_type"
            
            # Execute query with SQLAlchemy text
            query = text(query_str)
            result = conn.execute(query, params)
            
            # Convert result to DataFrame
            df = pd.DataFrame(result.fetchall())
            
            if not df.empty:
                df.columns = result.keys()
                
            return df
        except Exception as e:
            st.error(f"Error getting handover reports: {e}")
            return pd.DataFrame()
        finally:
            conn.close()
    
    return pd.DataFrame()

# Acknowledge handover report
def acknowledge_handover(handover_id, acknowledged_by, comments=None):
    """
    Acknowledge a shift handover report
    
    Args:
        handover_id: ID of the handover report
        acknowledged_by: Name of the person acknowledging
        comments: Optional comments
        
    Returns:
        success: Boolean indicating if acknowledgment was successful
    """
    conn = get_conn()
    if conn:
        try:
            acknowledgment_id = str(uuid.uuid4())
            current_time = dt.datetime.now()
            
            # Insert acknowledgment
            insert_query = text('''
            INSERT INTO handover_acknowledgment (
                acknowledgment_id, handover_id, acknowledged_by,
                acknowledged_at, comments
            )
            VALUES (:acknowledgment_id, :handover_id, :acknowledged_by, :acknowledged_at, :comments)
            ''')
            
            conn.execute(insert_query, {
                'acknowledgment_id': acknowledgment_id,
                'handover_id': handover_id,
                'acknowledged_by': acknowledged_by,
                'acknowledged_at': current_time,
                'comments': comments
            })
            
            # Update handover status
            update_query = text('''
            UPDATE shift_handover
            SET status = 'acknowledged'
            WHERE handover_id = :handover_id
            ''')
            
            conn.execute(update_query, {'handover_id': handover_id})
            
            conn.commit()
            return True
        except Exception as e:
            st.error(f"Error acknowledging handover: {e}")
            return False
        finally:
            conn.close()
    
    return False

# Get active shifts
def get_active_shifts():
    """
    Get active shift configurations
    
    Returns:
        DataFrame with shift configurations
    """
    conn = get_conn()
    if conn:
        try:
            query = text('SELECT * FROM shift_config WHERE is_active = TRUE')
            result = conn.execute(query)
            
            # Convert result to DataFrame
            df = pd.DataFrame(result.fetchall())
            
            if not df.empty:
                df.columns = result.keys()
                
            return df
        except Exception as e:
            st.error(f"Error getting shift configurations: {e}")
            return pd.DataFrame()
        finally:
            conn.close()
    
    return pd.DataFrame()

# Get current shift based on time
def get_current_shift():
    """
    Determine the current shift based on time
    
    Returns:
        Current shift name or None if no matching shift
    """
    shifts = get_active_shifts()
    
    if shifts.empty:
        return None
    
    current_time = dt.datetime.now().time()
    current_time_str = current_time.strftime('%H:%M')
    
    for _, shift in shifts.iterrows():
        start_time = shift['start_time']
        end_time = shift['end_time']
        
        # Handle shifts that span midnight
        if end_time < start_time:
            if current_time_str >= start_time or current_time_str < end_time:
                return shift['shift_name']
        else:
            if start_time <= current_time_str < end_time:
                return shift['shift_name']
    
    return None

# Generate production summary
def generate_production_summary(shift_date, shift_type):
    """
    Generate production summary for a shift
    
    Args:
        shift_date: Date of the shift
        shift_type: Type of shift (Morning, Afternoon, Night)
        
    Returns:
        Dictionary with production summary
    """
    # Get shift times
    shifts = get_active_shifts()
    if shifts.empty:
        return None
    
    shift_row = shifts[shifts['shift_name'] == shift_type]
    if shift_row.empty:
        return None
    
    start_time = shift_row['start_time'].iloc[0]
    end_time = shift_row['end_time'].iloc[0]
    
    # Create datetime objects for shift start and end
    shift_date_dt = pd.to_datetime(shift_date).date()
    
    if end_time < start_time:  # Shift spans midnight
        start_datetime = dt.datetime.combine(shift_date_dt, dt.datetime.strptime(start_time, '%H:%M').time())
        end_datetime = dt.datetime.combine(shift_date_dt + dt.timedelta(days=1), dt.datetime.strptime(end_time, '%H:%M').time())
    else:
        start_datetime = dt.datetime.combine(shift_date_dt, dt.datetime.strptime(start_time, '%H:%M').time())
        end_datetime = dt.datetime.combine(shift_date_dt, dt.datetime.strptime(end_time, '%H:%M').time())
    
    # Get data for the shift
    shift_data = get_check_data(start_datetime, end_datetime)
    
    # Initialize summary
    summary = {
        'total_checks': 0,
        'products_produced': [],
        'quality_issues': 0,
        'avg_brix': None,
        'avg_torque': None,
        'inspectors': []
    }
    
    if not shift_data.empty:
        # Count total checks
        summary['total_checks'] = len(shift_data)
        
        # Get unique products
        if 'product' in shift_data.columns:
            summary['products_produced'] = shift_data['product'].dropna().unique().tolist()
        
        # Count quality issues (example implementation)
        quality_issues = 0
        
        # Check torque values (should be between 5-12)
        for head in ['head1_torque', 'head2_torque', 'head3_torque', 'head4_torque', 'head5_torque']:
            if head in shift_data.columns:
                quality_issues += ((shift_data[head] < 5) | (shift_data[head] > 12)).sum()
        
        # Check tamper evidence
        if 'tamper_evidence' in shift_data.columns:
            quality_issues += shift_data['tamper_evidence'].str.contains('FAIL').sum()
        
        summary['quality_issues'] = quality_issues
        
        # Calculate average metrics
        if 'brix' in shift_data.columns:
            summary['avg_brix'] = shift_data['brix'].mean()
        
        # Average torque across all heads
        torque_cols = [col for col in shift_data.columns if 'torque' in col]
        if torque_cols:
            summary['avg_torque'] = shift_data[torque_cols].mean().mean()
        
        # Get unique inspectors
        if 'username' in shift_data.columns:
            summary['inspectors'] = shift_data['username'].unique().tolist()
    
    return summary

# Generate HTML report for handover
def generate_handover_html(handover_id):
    """
    Generate HTML report for a handover
    
    Args:
        handover_id: ID of the handover
        
    Returns:
        HTML string
    """
    handover = None
    acknowledgment = None
    
    conn = get_conn()
    if conn:
        try:
            # Get handover data
            handover_query = text('SELECT * FROM shift_handover WHERE handover_id = :handover_id')
            handover_result = conn.execute(handover_query, {'handover_id': handover_id})
            handover_data = handover_result.fetchone()
            
            if not handover_data:
                return None
            
            # Convert to dictionary
            handover = dict(zip(handover_result.keys(), handover_data))
            
            # Get acknowledgment data
            ack_query = text('SELECT * FROM handover_acknowledgment WHERE handover_id = :handover_id')
            ack_result = conn.execute(ack_query, {'handover_id': handover_id})
            ack_data = ack_result.fetchone()
            
            if ack_data:
                acknowledgment = dict(zip(ack_result.keys(), ack_data))
        except Exception as e:
            st.error(f"Error generating handover HTML: {e}")
            return None
        finally:
            conn.close()
    
    if not handover:
        return None
        
    # Format dates
    shift_date = handover['shift_date'].strftime('%Y-%m-%d') if isinstance(handover['shift_date'], dt.date) else handover['shift_date']
    created_at = format_timestamp(handover['created_at'])
    
    acknowledged_at = "Not acknowledged yet"
    if acknowledgment:
        acknowledged_at = format_timestamp(acknowledgment['acknowledged_at'])
    
    # Create HTML
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Shift Handover Report - {shift_date} {handover['shift_type']} Shift</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                line-height: 1.6;
                color: #333;
                max-width: 800px;
                margin: 0 auto;
                padding: 20px;
            }}
            .header {{
                text-align: center;
                margin-bottom: 20px;
                padding-bottom: 10px;
                border-bottom: 1px solid #ddd;
            }}
            .section {{
                margin-bottom: 20px;
                padding: 15px;
                background-color: #f9f9f9;
                border-radius: 5px;
            }}
            .section h2 {{
                margin-top: 0;
                color: #0066cc;
                border-bottom: 1px solid #ddd;
                padding-bottom: 5px;
            }}
            .footer {{
                margin-top: 30px;
                text-align: center;
                font-size: 12px;
                color: #666;
            }}
            .meta-info {{
                display: flex;
                justify-content: space-between;
                background-color: #eee;
                padding: 10px;
                border-radius: 5px;
                margin-bottom: 20px;
            }}
            .status {{
                padding: 5px 10px;
                border-radius: 3px;
                font-weight: bold;
            }}
            .pending {{
                background-color: #fff3cd;
                color: #856404;
            }}
            .acknowledged {{
                background-color: #d4edda;
                color: #155724;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
            }}
            table, th, td {{
                border: 1px solid #ddd;
            }}
            th, td {{
                padding: 10px;
                text-align: left;
            }}
            th {{
                background-color: #f2f2f2;
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>Shift Handover Report</h1>
            <h3>{shift_date} - {handover['shift_type']} Shift</h3>
        </div>
        
        <div class="meta-info">
            <div>
                <strong>Handover ID:</strong> {handover_id}<br>
                <strong>Created:</strong> {created_at}
            </div>
            <div>
                <strong>Status:</strong> 
                <span class="status {handover['status']}">{handover['status'].upper()}</span>
            </div>
        </div>
        
        <div class="section">
            <h2>Shift Information</h2>
            <table>
                <tr>
                    <th>Outgoing Shift Lead</th>
                    <td>{handover['outgoing_shift_lead']}</td>
                </tr>
                <tr>
                    <th>Incoming Shift Lead</th>
                    <td>{handover['incoming_shift_lead']}</td>
                </tr>
            </table>
        </div>
        
        <div class="section">
            <h2>Production Summary</h2>
            <p>{handover['production_summary']}</p>
        </div>
        
        <div class="section">
            <h2>Quality Issues</h2>
            <p>{handover['quality_issues'] or "No quality issues reported."}</p>
        </div>
        
        <div class="section">
            <h2>Equipment Issues</h2>
            <p>{handover['equipment_issues'] or "No equipment issues reported."}</p>
        </div>
        
        <div class="section">
            <h2>Pending Tasks</h2>
            <p>{handover['pending_tasks'] or "No pending tasks."}</p>
        </div>
        
        <div class="section">
            <h2>Additional Comments</h2>
            <p>{handover['comments'] or "No additional comments."}</p>
        </div>
    """
    
    if acknowledgment:
        html += f"""
        <div class="section">
            <h2>Acknowledgment</h2>
            <table>
                <tr>
                    <th>Acknowledged By</th>
                    <td>{acknowledgment['acknowledged_by']}</td>
                </tr>
                <tr>
                    <th>Acknowledged At</th>
                    <td>{acknowledged_at}</td>
                </tr>
                <tr>
                    <th>Comments</th>
                    <td>{acknowledgment['comments'] or "No comments."}</td>
                </tr>
            </table>
        </div>
        """
    
    html += f"""
        <div class="footer">
            <p>This report was generated by the Beverage Quality Assurance Tracker System.</p>
            <p>© {dt.datetime.now().year} Beverage Quality Assurance Department</p>
        </div>
    </body>
    </html>
    """
    
    return html

# Get download link for HTML report
def get_html_download_link(html_content, filename="handover_report.html"):
    """
    Generate a download link for HTML content
    
    Args:
        html_content: HTML content to download
        filename: Name of the file to download
    
    Returns:
        HTML link for downloading the content
    """
    # Convert to string if it's not already
    if not isinstance(html_content, str):
        html_content = str(html_content)
    
    # Encode as bytes
    b64 = base64.b64encode(html_content.encode()).decode()
    
    # Create download link
    href = f'<a href="data:text/html;base64,{b64}" download="{filename}" class="download-button">Download Report</a>'
    
    return href

# Display handover creation form
def display_handover_creation_form():
    """Display the form for creating a shift handover report"""
    st.subheader("Create Shift Handover Report")
    
    # Get active shifts
    shifts = get_active_shifts()
    shift_names = shifts['shift_name'].tolist() if not shifts.empty else ["Morning", "Afternoon", "Night"]
    
    # Get current shift
    current_shift = get_current_shift()
    
    # Set default date to today
    default_date = dt.datetime.now().date()
    
    # Get username for default outgoing lead
    default_outgoing_lead = st.session_state.username if 'username' in st.session_state else ""
    
    with st.form("handover_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            shift_date = st.date_input("Shift Date", default_date, max_value=default_date)
        
        with col2:
            shift_type = st.selectbox(
                "Shift", 
                shift_names,
                index=shift_names.index(current_shift) if current_shift in shift_names else 0
            )
        
        # Generate production summary automatically
        auto_summary = generate_production_summary(shift_date, shift_type)
        
        if auto_summary:
            with st.expander("Production Statistics (Auto-Generated)"):
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.metric("Total Checks", auto_summary['total_checks'])
                
                with col2:
                    st.metric("Quality Issues", auto_summary['quality_issues'])
                
                with col3:
                    inspector_count = len(auto_summary['inspectors'])
                    st.metric("Inspectors", inspector_count)
                
                if auto_summary['products_produced']:
                    st.write("**Products Produced:**", ", ".join(auto_summary['products_produced']))
                
                if auto_summary['avg_brix'] is not None:
                    st.write(f"**Average BRIX:** {auto_summary['avg_brix']:.2f}")
                
                if auto_summary['avg_torque'] is not None:
                    st.write(f"**Average Torque:** {auto_summary['avg_torque']:.2f}")
        
        col1, col2 = st.columns(2)
        
        with col1:
            outgoing_lead = st.text_input("Outgoing Shift Lead", default_outgoing_lead)
        
        with col2:
            incoming_lead = st.text_input("Incoming Shift Lead")
        
        # Production summary
        production_summary = st.text_area(
            "Production Summary", 
            height=100,
            help="Summarize production activities, quantities produced, etc."
        )
        
        col1, col2 = st.columns(2)
        
        with col1:
            # Quality issues
            quality_issues = st.text_area(
                "Quality Issues", 
                height=100,
                help="Describe any quality issues encountered during the shift"
            )
        
        with col2:
            # Equipment issues
            equipment_issues = st.text_area(
                "Equipment Issues", 
                height=100,
                help="Describe any equipment issues encountered during the shift"
            )
        
        # Pending tasks
        pending_tasks = st.text_area(
            "Pending Tasks", 
            height=100,
            help="List any tasks that need to be completed by the incoming shift"
        )
        
        # Additional comments
        comments = st.text_area(
            "Additional Comments", 
            height=100,
            help="Add any additional information not covered above"
        )
        
        # Submit button
        submitted = st.form_submit_button("Submit Handover Report", type="primary")
        
        if submitted:
            if not outgoing_lead or not incoming_lead:
                st.error("Outgoing and incoming shift leads are required.")
            else:
                handover_id = save_handover_report(
                    shift_date, shift_type, outgoing_lead, incoming_lead,
                    production_summary, quality_issues, equipment_issues,
                    pending_tasks, comments
                )
                
                st.success(f"Shift handover report submitted successfully!")
                
                # Show download link
                html_report = generate_handover_html(handover_id)
                if html_report:
                    report_filename = f"handover_{shift_date}_{shift_type}.html"
                    download_link = get_html_download_link(html_report, report_filename)
                    st.markdown(
                        f"""
                        <style>
                        .download-button {{
                            display: inline-block;
                            padding: 0.5em 1em;
                            background-color: #4CAF50;
                            color: white;
                            text-decoration: none;
                            border-radius: 4px;
                            margin-top: 10px;
                        }}
                        </style>
                        {download_link}
                        """, 
                        unsafe_allow_html=True
                    )
                
                # Clear form (by rerunning the app)
                st.rerun()

# Display handover review page
def display_handover_review_page():
    """Display the page for reviewing and acknowledging handover reports"""
    st.subheader("Review Handover Reports")
    
    # Filter options
    col1, col2, col3 = st.columns(3)
    
    with col1:
        days_back = st.number_input("Days to Look Back", min_value=1, max_value=30, value=7)
    
    with col2:
        status_filter = st.selectbox(
            "Status Filter",
            ["All", "Pending", "Acknowledged"]
        )
    
    with col3:
        shifts = get_active_shifts()
        shift_names = shifts['shift_name'].tolist() if not shifts.empty else ["Morning", "Afternoon", "Night"]
        shift_names = ["All"] + shift_names
        
        shift_filter = st.selectbox("Shift Filter", shift_names)
    
    # Apply filters
    status = status_filter.lower() if status_filter != "All" else None
    shift = shift_filter if shift_filter != "All" else None
    
    # Get filtered reports
    reports = get_handover_reports(days=days_back, status=status, shift_type=shift)
    
    if reports.empty:
        st.info("No handover reports found with the current filters.")
    else:
        # Format for display
        display_reports = reports.copy()
        
        # Format dates
        display_reports['shift_date'] = pd.to_datetime(display_reports['shift_date']).dt.strftime('%Y-%m-%d')
        display_reports['created_at'] = pd.to_datetime(display_reports['created_at']).dt.strftime('%Y-%m-%d %H:%M')
        
        if 'acknowledged_at' in display_reports.columns:
            display_reports['acknowledged_at'] = pd.to_datetime(display_reports['acknowledged_at']).fillna(pd.NaT).dt.strftime('%Y-%m-%d %H:%M')
        
        # Limit text length for display
        for col in ['production_summary', 'quality_issues', 'equipment_issues', 'pending_tasks', 'comments']:
            if col in display_reports.columns:
                display_reports[col] = display_reports[col].apply(lambda x: x[:50] + '...' if x and len(x) > 50 else x)
        
        # Rename columns for display
        display_reports = display_reports.rename(columns={
            'handover_id': 'ID',
            'shift_date': 'Date',
            'shift_type': 'Shift',
            'outgoing_shift_lead': 'Outgoing Lead',
            'incoming_shift_lead': 'Incoming Lead',
            'status': 'Status',
            'acknowledged_by': 'Acknowledged By',
            'acknowledged_at': 'Acknowledged At'
        })
        
        # Select columns to display
        display_cols = ['ID', 'Date', 'Shift', 'Outgoing Lead', 'Incoming Lead', 'Status']
        
        if 'Acknowledged By' in display_reports.columns:
            display_cols += ['Acknowledged By', 'Acknowledged At']
        
        # Show the reports
        st.dataframe(display_reports[display_cols], use_container_width=True)
        
        # View detailed report and acknowledge
        st.markdown("---")
        
        col1, col2 = st.columns([1, 3])
        
        with col1:
            selected_id = st.selectbox("Select Handover ID", reports['handover_id'].tolist())
        
        with col2:
            if selected_id:
                selected_report = reports[reports['handover_id'] == selected_id].iloc[0]
                
                if 'status' in selected_report and selected_report['status'] == 'acknowledged':
                    st.info(f"This report has already been acknowledged by {selected_report['acknowledged_by']}.")
                else:
                    acknowledgment_tab, view_tab = st.tabs(["Acknowledge", "View Report"])
                    
                    with acknowledgment_tab:
                        with st.form("acknowledgment_form"):
                            st.write(f"Acknowledging handover report from {selected_report['shift_date']} ({selected_report['shift_type']} shift)")
                            
                            if 'username' not in st.session_state:
                                st.warning("You must be logged in to acknowledge a handover report.")
                                acknowledged_by = st.text_input("Your Name")
                            else:
                                acknowledged_by = st.session_state.username
                            
                            comments = st.text_area("Acknowledgment Comments", height=100)
                            
                            ack_submitted = st.form_submit_button("Acknowledge Handover", type="primary")
                            
                            if ack_submitted:
                                if not acknowledged_by:
                                    st.error("Your name is required to acknowledge the handover.")
                                else:
                                    success = acknowledge_handover(selected_id, acknowledged_by, comments)
                                    
                                    if success:
                                        st.success("Handover report acknowledged successfully!")
                                        st.rerun()
                                    else:
                                        st.error("Failed to acknowledge handover report. Please try again.")
                    
                    with view_tab:
                        html_report = generate_handover_html(selected_id)
                        if html_report:
                            # Show download link
                            report_filename = f"handover_{selected_report['shift_date']}_{selected_report['shift_type']}.html"
                            download_link = get_html_download_link(html_report, report_filename)
                            
                            st.markdown(
                                f"""
                                <style>
                                .download-button {{
                                    display: inline-block;
                                    padding: 0.5em 1em;
                                    background-color: #4CAF50;
                                    color: white;
                                    text-decoration: none;
                                    border-radius: 4px;
                                    margin-top: 10px;
                                }}
                                </style>
                                {download_link}
                                """, 
                                unsafe_allow_html=True
                            )
                            
                            # Show embedded report
                            st.components.v1.html(html_report, height=600, scrolling=True)

# Display shift configuration page
def display_shift_config_page():
    """Display the page for configuring shifts"""
    st.subheader("Shift Configuration")
    
    # Get existing configurations
    shifts = get_active_shifts()
    
    # Display current shifts
    if not shifts.empty:
        st.write("Current Shift Configuration")
        
        # Format for display
        display_shifts = shifts.copy()
        
        # Rename columns for display
        display_shifts = display_shifts.rename(columns={
            'config_id': 'ID',
            'shift_name': 'Shift Name',
            'start_time': 'Start Time',
            'end_time': 'End Time',
            'is_active': 'Active'
        })
        
        st.dataframe(display_shifts[['ID', 'Shift Name', 'Start Time', 'End Time', 'Active']], use_container_width=True)
    
    # Form to add/update shifts
    with st.form("shift_config_form"):
        st.write("Add or Update Shift")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            shift_name = st.text_input("Shift Name", help="e.g., Morning, Afternoon, Night")
        
        with col2:
            start_time = st.time_input("Start Time", dt.time(6, 0))
        
        with col3:
            end_time = st.time_input("End Time", dt.time(14, 0))
        
        is_active = st.checkbox("Active", value=True)
        
        # Format times
        start_time_str = start_time.strftime('%H:%M')
        end_time_str = end_time.strftime('%H:%M')
        
        submitted = st.form_submit_button("Save Shift Configuration", type="primary")
        
        if submitted:
            if not shift_name:
                st.error("Shift name is required.")
            else:
                conn = get_conn()
                if conn:
                    try:
                        # Check if shift already exists
                        check_query = text('SELECT config_id FROM shift_config WHERE shift_name = :shift_name')
                        result = conn.execute(check_query, {'shift_name': shift_name})
                        existing = result.fetchone()
                        
                        if existing:
                            # Update existing shift
                            update_query = text('''
                            UPDATE shift_config
                            SET start_time = :start_time, end_time = :end_time, is_active = :is_active
                            WHERE shift_name = :shift_name
                            ''')
                            
                            conn.execute(update_query, {
                                'start_time': start_time_str,
                                'end_time': end_time_str,
                                'is_active': is_active,
                                'shift_name': shift_name
                            })
                            
                            message = f"Shift '{shift_name}' updated successfully!"
                        else:
                            # Add new shift
                            insert_query = text('''
                            INSERT INTO shift_config (shift_name, start_time, end_time, is_active)
                            VALUES (:shift_name, :start_time, :end_time, :is_active)
                            ''')
                            
                            conn.execute(insert_query, {
                                'shift_name': shift_name,
                                'start_time': start_time_str,
                                'end_time': end_time_str,
                                'is_active': is_active
                            })
                            
                            message = f"Shift '{shift_name}' added successfully!"
                        
                        conn.commit()
                    except Exception as e:
                        st.error(f"Error saving shift configuration: {e}")
                        message = "An error occurred while saving the shift configuration."
                    finally:
                        conn.close()
                
                st.success(message)
                st.rerun()

# Main function to display shift handover page
def display_shift_handover_page():
    """Display the shift handover page with tabs"""
    # Initialize handover tables
    initialize_handover()
    
    st.title("Shift Handover Management")
    
    st.markdown("""
    Shift handover reports facilitate smooth transitions between shifts by documenting important 
    information about production, quality issues, equipment status, and pending tasks.
    """)
    
    # Create tabs
    tab1, tab2, tab3 = st.tabs(["Create Handover", "Review Handovers", "Shift Configuration"])
    
    with tab1:
        display_handover_creation_form()
    
    with tab2:
        display_handover_review_page()
    
    with tab3:
        display_shift_config_page()