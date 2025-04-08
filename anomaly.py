import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import datetime as dt
from scipy import stats
from database import get_check_data, get_conn
import json
from statsmodels.tsa.seasonal import seasonal_decompose
import uuid
from sqlalchemy import text

# Initialize anomaly alert tables
def initialize_anomaly_detection():
    """Initialize tables for anomaly detection and alerts"""
    conn = get_conn()
    if conn:
        try:
            # Create anomaly configuration table
            conn.execute(text('''
            CREATE TABLE IF NOT EXISTS anomaly_config (
                parameter_name TEXT PRIMARY KEY,
                enabled BOOLEAN,
                sensitivity REAL,
                method TEXT,
                alert_threshold REAL,
                last_updated TIMESTAMP,
                updated_by TEXT
            )
            '''))
            
            # Create anomaly alerts table
            conn.execute(text('''
            CREATE TABLE IF NOT EXISTS anomaly_alerts (
                alert_id TEXT PRIMARY KEY,
                parameter_name TEXT,
                timestamp TIMESTAMP,
                observed_value REAL,
                expected_value REAL,
                deviation_score REAL,
                status TEXT,
                acknowledged_by TEXT,
                acknowledged_time TIMESTAMP,
                notes TEXT
            )
            '''))
            
            conn.commit()
        except Exception as e:
            st.error(f"Error initializing anomaly detection tables: {e}")
        finally:
            conn.close()

# Function to save anomaly configuration
def save_anomaly_config(parameter_name, enabled, sensitivity, method, alert_threshold):
    """
    Save anomaly detection configuration for a parameter
    
    Args:
        parameter_name: Name of the parameter to monitor
        enabled: Boolean indicating if anomaly detection is enabled
        sensitivity: Sensitivity level (0-1) for detection
        method: Detection method (statistical, isolation_forest, etc)
        alert_threshold: Threshold for alerting
    """
    conn = get_conn()
    if conn:
        try:
            now = dt.datetime.now()
            username = st.session_state.username if 'username' in st.session_state else "System"
            
            query = text('''
            INSERT INTO anomaly_config 
                (parameter_name, enabled, sensitivity, method, alert_threshold, last_updated, updated_by)
            VALUES 
                (:param_name, :enabled, :sensitivity, :method, :threshold, :timestamp, :username)
            ON CONFLICT (parameter_name) 
            DO UPDATE SET
                enabled = :enabled,
                sensitivity = :sensitivity,
                method = :method,
                alert_threshold = :threshold,
                last_updated = :timestamp,
                updated_by = :username
            ''')
            
            conn.execute(query, {
                'param_name': parameter_name,
                'enabled': enabled,
                'sensitivity': sensitivity,
                'method': method,
                'threshold': alert_threshold,
                'timestamp': now,
                'username': username
            })
            
            conn.commit()
            
        except Exception as e:
            st.error(f"Error saving anomaly configuration: {e}")
        finally:
            conn.close()

# Function to get anomaly configuration
def get_anomaly_config(parameter_name=None):
    """
    Get anomaly detection configuration
    
    Args:
        parameter_name: Optional specific parameter to get config for
        
    Returns:
        DataFrame with configuration
    """
    conn = get_conn()
    if conn:
        try:
            if parameter_name:
                query = text('SELECT * FROM anomaly_config WHERE parameter_name = :param')
                result = conn.execute(query, {'param': parameter_name})
            else:
                query = text('SELECT * FROM anomaly_config')
                result = conn.execute(query)
            
            # Convert result to DataFrame
            df = pd.DataFrame(result.fetchall())
            
            if not df.empty:
                df.columns = result.keys()
            else:
                # Get column names from the table structure
                col_query = text('''
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'anomaly_config'
                ORDER BY ordinal_position
                ''')
                columns = [row[0] for row in conn.execute(col_query).fetchall()]
                df = pd.DataFrame(columns=columns)
                
            return df
            
        except Exception as e:
            st.error(f"Error getting anomaly configuration: {e}")
            # Return empty DataFrame with expected columns
            return pd.DataFrame(columns=[
                'parameter_name', 'enabled', 'sensitivity', 
                'method', 'alert_threshold', 'last_updated', 'updated_by'
            ])
        finally:
            conn.close()
    
    # Return empty DataFrame if connection failed
    return pd.DataFrame(columns=[
        'parameter_name', 'enabled', 'sensitivity', 
        'method', 'alert_threshold', 'last_updated', 'updated_by'
    ])

# Function to save anomaly alert
def save_anomaly_alert(parameter_name, observed_value, expected_value, deviation_score):
    """
    Save a detected anomaly alert
    
    Args:
        parameter_name: Name of the parameter with anomaly
        observed_value: The anomalous value observed
        expected_value: The expected value
        deviation_score: How far the value deviates from expected
        
    Returns:
        alert_id: ID of the created alert
    """
    conn = get_conn()
    if conn:
        try:
            alert_id = str(uuid.uuid4())
            now = dt.datetime.now()
            
            query = text('''
            INSERT INTO anomaly_alerts (
                alert_id, parameter_name, timestamp, observed_value, expected_value, 
                deviation_score, status
            )
            VALUES (
                :alert_id, :param_name, :timestamp, :observed, :expected, 
                :deviation, :status
            )
            ''')
            
            conn.execute(query, {
                'alert_id': alert_id,
                'param_name': parameter_name,
                'timestamp': now,
                'observed': observed_value,
                'expected': expected_value,
                'deviation': deviation_score,
                'status': 'new'
            })
            
            conn.commit()
            return alert_id
            
        except Exception as e:
            st.error(f"Error saving anomaly alert: {e}")
            return None
        finally:
            conn.close()
    
    return None

# Function to get anomaly alerts
def get_anomaly_alerts(status=None, days=7):
    """
    Get anomaly alerts
    
    Args:
        status: Optional filter by status (new, acknowledged, resolved)
        days: Number of days to look back
        
    Returns:
        DataFrame with alerts
    """
    conn = get_conn()
    if conn:
        try:
            # Build the query based on status
            if status:
                query = text('''
                SELECT * FROM anomaly_alerts 
                WHERE status = :status AND timestamp > :time_ago
                ORDER BY timestamp DESC
                ''')
                result = conn.execute(query, {
                    'status': status,
                    'time_ago': dt.datetime.now() - dt.timedelta(days=days)
                })
            else:
                query = text('''
                SELECT * FROM anomaly_alerts 
                WHERE timestamp > :time_ago
                ORDER BY timestamp DESC
                ''')
                result = conn.execute(query, {
                    'time_ago': dt.datetime.now() - dt.timedelta(days=days)
                })
            
            # Convert result to DataFrame
            df = pd.DataFrame(result.fetchall())
            
            if not df.empty:
                df.columns = result.keys()
                
            return df
        except Exception as e:
            st.error(f"Error getting anomaly alerts: {e}")
            return pd.DataFrame()
        finally:
            conn.close()
    
    return pd.DataFrame()

# Function to acknowledge alert
def acknowledge_alert(alert_id, notes=None):
    """
    Acknowledge an anomaly alert
    
    Args:
        alert_id: ID of the alert to acknowledge
        notes: Optional notes about acknowledgment
        
    Returns:
        success: Boolean indicating if acknowledgment was successful
    """
    if 'username' not in st.session_state:
        return False
        
    conn = get_conn()
    if conn:
        try:
            username = st.session_state.username
            now = dt.datetime.now()
            
            query = text('''
            UPDATE anomaly_alerts
            SET status = 'acknowledged',
                acknowledged_by = :username,
                acknowledged_time = :timestamp,
                notes = :notes
            WHERE alert_id = :alert_id AND status = 'new'
            ''')
            
            result = conn.execute(query, {
                'username': username,
                'timestamp': now,
                'notes': notes,
                'alert_id': alert_id
            })
            
            success = result.rowcount > 0
            conn.commit()
            return success
            
        except Exception as e:
            st.error(f"Error acknowledging alert: {e}")
            return False
        finally:
            conn.close()
    
    return False

# Function to resolve alert
def resolve_alert(alert_id, notes=None):
    """
    Resolve an anomaly alert
    
    Args:
        alert_id: ID of the alert to resolve
        notes: Optional notes about resolution
        
    Returns:
        success: Boolean indicating if resolution was successful
    """
    if 'username' not in st.session_state:
        return False
        
    conn = get_conn()
    if conn:
        try:
            # Get the existing notes
            query = text('SELECT notes FROM anomaly_alerts WHERE alert_id = :alert_id')
            result = conn.execute(query, {'alert_id': alert_id}).fetchone()
            existing_notes = result[0] if result and result[0] else ""
            
            # Append resolution notes
            if existing_notes and notes:
                updated_notes = f"{existing_notes}\n\nResolution: {notes}"
            elif notes:
                updated_notes = f"Resolution: {notes}"
            else:
                updated_notes = existing_notes
            
            # Update the alert
            update_query = text('''
            UPDATE anomaly_alerts
            SET status = 'resolved',
                notes = :notes
            WHERE alert_id = :alert_id AND (status = 'new' OR status = 'acknowledged')
            ''')
            
            result = conn.execute(update_query, {
                'notes': updated_notes,
                'alert_id': alert_id
            })
            
            success = result.rowcount > 0
            conn.commit()
            return success
            
        except Exception as e:
            st.error(f"Error resolving alert: {e}")
            return False
        finally:
            conn.close()
    
    return False

# Statistical anomaly detection
def detect_statistical_anomalies(data, parameter, sensitivity=0.9, threshold=3.0):
    """
    Detect anomalies using statistical methods
    
    Args:
        data: DataFrame with data
        parameter: Parameter to analyze
        sensitivity: Detection sensitivity (0-1)
        threshold: Z-score threshold for anomalies
        
    Returns:
        DataFrame with anomalies
    """
    if data.empty or parameter not in data.columns:
        return pd.DataFrame()
    
    # Filter relevant data
    param_data = data[[parameter, 'timestamp']].dropna()
    if len(param_data) < 5:  # Need enough data points
        return pd.DataFrame()
    
    # Calculate rolling statistics
    window_size = max(5, int(len(param_data) * 0.2))  # 20% of data or at least 5 points
    param_data['rolling_mean'] = param_data[parameter].rolling(window=window_size, min_periods=2).mean()
    param_data['rolling_std'] = param_data[parameter].rolling(window=window_size, min_periods=2).std()
    
    # Calculate z-scores
    param_data['z_score'] = (param_data[parameter] - param_data['rolling_mean']) / param_data['rolling_std'].replace(0, 1)
    
    # Adjust threshold based on sensitivity
    adjusted_threshold = threshold * (2 - sensitivity)
    
    # Identify anomalies
    anomalies = param_data[param_data['z_score'].abs() > adjusted_threshold].copy()
    
    if not anomalies.empty:
        anomalies['expected_value'] = anomalies['rolling_mean']
        anomalies['deviation_score'] = anomalies['z_score'].abs()
        anomalies = anomalies[['timestamp', parameter, 'expected_value', 'deviation_score']]
        anomalies.columns = ['timestamp', 'observed_value', 'expected_value', 'deviation_score']
    
    return anomalies

# Detect anomalies in recent data
def detect_anomalies(hours=24):
    """
    Detect anomalies in recent data
    
    Args:
        hours: Hours of recent data to analyze
        
    Returns:
        List of detected anomalies
    """
    # Get recent data
    end_date = dt.datetime.now()
    start_date = end_date - dt.timedelta(hours=hours)
    
    recent_data = get_check_data(start_date, end_date)
    if recent_data.empty:
        return []
    
    # Get anomaly configurations
    configs = get_anomaly_config()
    if configs.empty:
        return []
    
    detected_anomalies = []
    
    # Process each enabled parameter
    for _, config in configs[configs['enabled']].iterrows():
        parameter = config['parameter_name']
        
        if parameter not in recent_data.columns:
            continue
        
        # Apply the specified detection method
        if config['method'] == 'statistical':
            anomalies = detect_statistical_anomalies(
                recent_data, 
                parameter, 
                config['sensitivity'],
                config['alert_threshold']
            )
        else:
            # Default to statistical method
            anomalies = detect_statistical_anomalies(
                recent_data, 
                parameter, 
                config['sensitivity'],
                config['alert_threshold']
            )
        
        # Process anomalies
        if not anomalies.empty:
            for _, anomaly in anomalies.iterrows():
                # Check if this anomaly is already recorded
                conn = get_conn()
                if conn:
                    try:
                        # Look for similar anomalies in the last hour
                        one_hour_ago = anomaly['timestamp'] - dt.timedelta(hours=1)
                        query = text('''
                        SELECT COUNT(*) FROM anomaly_alerts 
                        WHERE parameter_name = :param 
                        AND timestamp > :time_ago
                        ''')
                        
                        result = conn.execute(query, {
                            'param': parameter,
                            'time_ago': one_hour_ago
                        })
                        
                        count = result.scalar() or 0
                    except Exception as e:
                        st.error(f"Error checking for existing anomalies: {e}")
                        count = 1  # Assume there's an existing anomaly to prevent duplicate alerts
                    finally:
                        conn.close()
                
                # Only add if we haven't detected a similar anomaly recently
                if count == 0:
                    alert_id = save_anomaly_alert(
                        parameter,
                        anomaly['observed_value'],
                        anomaly['expected_value'],
                        anomaly['deviation_score']
                    )
                    
                    detected_anomalies.append({
                        'alert_id': alert_id,
                        'parameter': parameter,
                        'timestamp': anomaly['timestamp'],
                        'observed_value': anomaly['observed_value'],
                        'expected_value': anomaly['expected_value'],
                        'deviation_score': anomaly['deviation_score']
                    })
    
    return detected_anomalies

# Function to display anomaly alerts
def display_anomaly_alerts(status=None, days=7):
    """
    Display anomaly alerts with action buttons
    
    Args:
        status: Optional filter by status
        days: Number of days to look back
    """
    alerts = get_anomaly_alerts(status, days)
    
    if alerts.empty:
        if status:
            st.info(f"No {status} alerts found.")
        else:
            st.info("No alerts found.")
        return
        
    # Format the dataframe for display
    display_df = alerts.copy()
    
    # Format timestamp
    if 'timestamp' in display_df.columns:
        display_df['timestamp'] = pd.to_datetime(display_df['timestamp']).dt.strftime('%Y-%m-%d %H:%M')
    
    # Format acknowledged_time
    if 'acknowledged_time' in display_df.columns:
        display_df['acknowledged_time'] = pd.to_datetime(display_df['acknowledged_time']).fillna(pd.NaT).dt.strftime('%Y-%m-%d %H:%M')
    
    # Round numerical values
    for col in ['observed_value', 'expected_value', 'deviation_score']:
        if col in display_df.columns:
            display_df[col] = display_df[col].round(3)
    
    # Rename columns for display
    display_df = display_df.rename(columns={
        'alert_id': 'Alert ID',
        'parameter_name': 'Parameter',
        'timestamp': 'Detected At',
        'observed_value': 'Observed Value',
        'expected_value': 'Expected Value',
        'deviation_score': 'Deviation Score',
        'status': 'Status',
        'acknowledged_by': 'Acknowledged By',
        'acknowledged_time': 'Acknowledged At',
        'notes': 'Notes'
    })
    
    # Select columns based on status
    if status == 'new':
        # For new alerts, show minimal info
        display_cols = ['Alert ID', 'Parameter', 'Detected At', 'Observed Value', 'Expected Value', 'Deviation Score']
    elif status == 'acknowledged':
        # For acknowledged alerts, include acknowledgment info
        display_cols = ['Alert ID', 'Parameter', 'Detected At', 'Observed Value', 'Expected Value', 'Deviation Score', 'Acknowledged By', 'Acknowledged At', 'Notes']
    else:
        # For all or resolved alerts, show all relevant columns
        display_cols = [col for col in ['Alert ID', 'Parameter', 'Detected At', 'Observed Value', 'Expected Value', 'Deviation Score', 'Status', 'Acknowledged By', 'Acknowledged At', 'Notes'] if col in display_df.columns]
    
    st.dataframe(display_df[display_cols], use_container_width=True)
    
    # Create action buttons for alerts
    if status == 'new' or status == 'acknowledged':
        # Create three columns for the alert ID, action buttons, and notes
        col1, col2, col3 = st.columns([1, 1, 2])
        
        with col1:
            selected_alert = st.selectbox("Select Alert ID", alerts['alert_id'].tolist())
        
        with col2:
            if status == 'new':
                action = st.selectbox("Action", ["Acknowledge", "Resolve"])
            else:
                action = "Resolve"
        
        with col3:
            notes = st.text_area("Notes", key="alert_notes", height=100)
        
        if st.button(f"{action} Selected Alert", type="primary"):
            if action == "Acknowledge":
                success = acknowledge_alert(selected_alert, notes)
                if success:
                    st.success(f"Alert {selected_alert} acknowledged successfully.")
                    st.rerun()
                else:
                    st.error(f"Failed to acknowledge alert {selected_alert}.")
            else:  # Resolve
                success = resolve_alert(selected_alert, notes)
                if success:
                    st.success(f"Alert {selected_alert} resolved successfully.")
                    st.rerun()
                else:
                    st.error(f"Failed to resolve alert {selected_alert}.")

# Function to create anomaly configuration page
def display_anomaly_config_page():
    """Display the anomaly detection configuration page"""
    st.title("Anomaly Detection Configuration")
    
    st.markdown("""
    Configure automated anomaly detection for quality parameters. The system will alert you when
    unusual values are detected, allowing quick intervention to prevent quality issues.
    """)
    
    # Get all parameters that can be monitored
    param_options = [
        {"name": "BRIX", "key": "brix"},
        {"name": "Torque Head 1", "key": "head1_torque"},
        {"name": "Torque Head 2", "key": "head2_torque"},
        {"name": "Torque Head 3", "key": "head3_torque"},
        {"name": "Torque Head 4", "key": "head4_torque"},
        {"name": "Torque Head 5", "key": "head5_torque"},
        {"name": "Titration Acid", "key": "titration_acid"},
        {"name": "Density", "key": "density"},
    ]
    
    # Get existing configurations
    configs = get_anomaly_config()
    
    # Create tabs for different operations
    tab1, tab2, tab3 = st.tabs(["Configure Parameters", "View Active Monitors", "Testing & Validation"])
    
    with tab1:
        st.subheader("Configure Anomaly Detection Parameters")
        
        # Parameter selection
        selected_param = st.selectbox(
            "Select Parameter", 
            [p["name"] for p in param_options],
            format_func=lambda x: x
        )
        
        # Get the parameter key
        param_key = next((p["key"] for p in param_options if p["name"] == selected_param), None)
        
        # Get existing configuration for this parameter
        existing_config = configs[configs['parameter_name'] == param_key] if not configs.empty else pd.DataFrame()
        
        # Default values
        default_enabled = existing_config['enabled'].iloc[0] if not existing_config.empty else True
        default_sensitivity = existing_config['sensitivity'].iloc[0] if not existing_config.empty else 0.8
        default_method = existing_config['method'].iloc[0] if not existing_config.empty else "statistical"
        default_threshold = existing_config['alert_threshold'].iloc[0] if not existing_config.empty else 3.0
        
        # Configuration form
        with st.form("anomaly_config_form"):
            enabled = st.checkbox("Enable Anomaly Detection", value=default_enabled)
            
            sensitivity = st.slider(
                "Detection Sensitivity", 
                min_value=0.1, 
                max_value=1.0, 
                value=default_sensitivity,
                step=0.1,
                help="Higher values make detection more sensitive (may increase false positives)"
            )
            
            method = st.selectbox(
                "Detection Method",
                ["statistical"],  # Can add more methods later
                index=0 if default_method=="statistical" else 0,
                help="Statistical detection uses z-scores to identify outliers"
            )
            
            alert_threshold = st.number_input(
                "Alert Threshold",
                min_value=1.0,
                max_value=10.0,
                value=default_threshold,
                step=0.5,
                help="Threshold for generating alerts (lower values are more sensitive)"
            )
            
            st.markdown("---")
            submitted = st.form_submit_button("Save Configuration", type="primary")
            
            if submitted:
                save_anomaly_config(param_key, enabled, sensitivity, method, alert_threshold)
                st.success(f"Configuration for {selected_param} saved successfully!")
        
        with st.expander("What do these settings mean?"):
            st.markdown("""
            ### Anomaly Detection Settings
            
            - **Sensitivity**: Controls how sensitive the detection is to deviations. Higher values detect more subtle anomalies but may increase false positives.
            
            - **Detection Method**:
              - **Statistical**: Uses statistical measures like Z-scores to identify values that deviate significantly from recent trends.
            
            - **Alert Threshold**: Specifies how far a value must deviate to trigger an alert. Lower values generate more alerts.
            
            ### Best Practices
            
            1. **Start Conservative**: Begin with lower sensitivity and gradually increase as needed.
            2. **Review Regularly**: Check for false positives and adjust accordingly.
            3. **Consider Process Variation**: Parameters with natural variation may need lower sensitivity.
            """)
    
    with tab2:
        st.subheader("Active Anomaly Monitors")
        
        if configs.empty:
            st.info("No anomaly detection configurations found. Configure parameters in the 'Configure Parameters' tab.")
        else:
            # Filter for enabled configurations
            active_configs = configs[configs['enabled']].copy()
            
            if active_configs.empty:
                st.info("No active monitors found. Enable detection for parameters in the 'Configure Parameters' tab.")
            else:
                # Format for display
                display_configs = active_configs.copy()
                
                # Add parameter names instead of keys
                display_configs['parameter_name'] = display_configs['parameter_name'].apply(
                    lambda x: next((p["name"] for p in param_options if p["key"] == x), x)
                )
                
                # Format timestamp
                if 'last_updated' in display_configs.columns:
                    display_configs['last_updated'] = pd.to_datetime(display_configs['last_updated']).dt.strftime('%Y-%m-%d %H:%M')
                
                # Rename columns for display
                display_configs = display_configs.rename(columns={
                    'parameter_name': 'Parameter',
                    'sensitivity': 'Sensitivity',
                    'method': 'Method',
                    'alert_threshold': 'Threshold',
                    'last_updated': 'Last Updated',
                    'updated_by': 'Updated By'
                })
                
                # Display active configurations
                st.dataframe(display_configs[['Parameter', 'Sensitivity', 'Method', 'Threshold', 'Last Updated', 'Updated By']], use_container_width=True)
                
                # Option to run detection manually
                if st.button("Run Detection Now", type="primary"):
                    with st.spinner("Running anomaly detection..."):
                        anomalies = detect_anomalies()
                        if anomalies:
                            st.success(f"Detection complete. Found {len(anomalies)} new anomalies.")
                        else:
                            st.success("Detection complete. No new anomalies found.")
    
    with tab3:
        st.subheader("Testing & Validation")
        
        st.markdown("""
        Test anomaly detection on historical data to validate configuration before enabling real-time detection.
        """)
        
        # Date range for testing
        test_date_range = st.date_input(
            "Historical Date Range",
            [dt.datetime.now() - dt.timedelta(days=30), dt.datetime.now()],
            max_value=dt.datetime.now()
        )
        
        # Parameter selection for testing
        test_param = st.selectbox(
            "Select Parameter to Test", 
            [p["name"] for p in param_options],
            key="test_param"
        )
        
        # Get the parameter key
        test_param_key = next((p["key"] for p in param_options if p["name"] == test_param), None)
        
        # Sensitivity setting for testing
        test_sensitivity = st.slider(
            "Test Sensitivity", 
            min_value=0.1, 
            max_value=1.0, 
            value=0.8,
            step=0.1,
            key="test_sensitivity"
        )
        
        # Threshold setting for testing
        test_threshold = st.number_input(
            "Test Threshold",
            min_value=1.0,
            max_value=10.0,
            value=3.0,
            step=0.5,
            key="test_threshold"
        )
        
        if st.button("Run Test Detection", key="run_test"):
            with st.spinner("Running test detection..."):
                # Get historical data
                start_date, end_date = test_date_range
                end_date = dt.datetime.combine(end_date, dt.time(23, 59, 59))
                
                historical_data = get_check_data(start_date, end_date)
                
                if historical_data.empty or test_param_key not in historical_data.columns:
                    st.error(f"No data available for {test_param} in the selected date range.")
                else:
                    # Run detection on historical data
                    test_anomalies = detect_statistical_anomalies(
                        historical_data, 
                        test_param_key, 
                        test_sensitivity,
                        test_threshold
                    )
                    
                    if test_anomalies.empty:
                        st.info(f"No anomalies detected for {test_param} with current settings.")
                    else:
                        st.success(f"Found {len(test_anomalies)} potential anomalies.")
                        
                        # Create a dataframe for display
                        display_anomalies = test_anomalies.copy()
                        display_anomalies['timestamp'] = pd.to_datetime(display_anomalies['timestamp']).dt.strftime('%Y-%m-%d %H:%M')
                        display_anomalies.columns = ['Time', 'Observed Value', 'Expected Value', 'Deviation Score']
                        
                        # Round numerical values
                        for col in ['Observed Value', 'Expected Value', 'Deviation Score']:
                            display_anomalies[col] = display_anomalies[col].round(3)
                        
                        # Show detected anomalies
                        st.dataframe(display_anomalies, use_container_width=True)
                        
                        # Create visualization
                        fig = go.Figure()
                        
                        # Add historical data
                        fig.add_trace(
                            go.Scatter(
                                x=historical_data['timestamp'],
                                y=historical_data[test_param_key],
                                mode='lines',
                                name='Historical Data',
                                line=dict(color='blue', width=1)
                            )
                        )
                        
                        # Add detected anomalies
                        fig.add_trace(
                            go.Scatter(
                                x=test_anomalies['timestamp'],
                                y=test_anomalies['observed_value'],
                                mode='markers',
                                name='Detected Anomalies',
                                marker=dict(
                                    color='red',
                                    size=10,
                                    symbol='circle',
                                    line=dict(color='black', width=1)
                                )
                            )
                        )
                        
                        # Update layout
                        fig.update_layout(
                            title=f"Anomaly Detection Test: {test_param}",
                            xaxis_title="Date",
                            yaxis_title=test_param,
                            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                            height=500
                        )
                        
                        st.plotly_chart(fig, use_container_width=True)
                        
                        with st.expander("Detection Explanation"):
                            st.markdown(f"""
                            ### How Anomalies Were Identified
                            
                            The system used statistical analysis to detect unusual values:
                            
                            1. **Window Size**: Used a rolling window of {max(5, int(len(historical_data) * 0.2))} data points
                            2. **Method**: Statistical z-score analysis
                            3. **Sensitivity**: {test_sensitivity} (higher values detect more subtle anomalies)
                            4. **Alert Threshold**: {test_threshold} (standard deviations from expected value)
                            
                            A total of {len(test_anomalies)} points were identified as anomalies from {len(historical_data)} data points.
                            """)

# Function to display anomaly alert dashboard
def display_anomaly_alert_dashboard():
    """Display the anomaly alerts dashboard"""
    st.title("Anomaly Alert Dashboard")
    
    st.markdown("""
    AI-powered anomaly detection continuously monitors your quality data and alerts you to unusual patterns
    that may indicate emerging quality issues.
    """)
    
    # Check for new anomalies (in real-time)
    with st.spinner("Scanning for anomalies..."):
        new_anomalies = detect_anomalies(hours=24)
    
    # Alert counts
    col1, col2, col3 = st.columns(3)
    
    new_alerts = get_anomaly_alerts(status='new')
    acknowledged_alerts = get_anomaly_alerts(status='acknowledged')
    resolved_alerts = get_anomaly_alerts(status='resolved')
    
    with col1:
        st.metric("New Alerts", len(new_alerts))
    
    with col2:
        st.metric("Acknowledged", len(acknowledged_alerts))
    
    with col3:
        st.metric("Resolved", len(resolved_alerts))
    
    # Display new alerts with attention needed
    st.subheader("New Alerts (Attention Needed)")
    
    if new_alerts.empty:
        st.success("No new alerts - all systems normal!")
    else:
        display_anomaly_alerts(status='new')
    
    # Display acknowledged alerts
    with st.expander("Acknowledged Alerts"):
        display_anomaly_alerts(status='acknowledged')
    
    # Display resolved alerts
    with st.expander("Recently Resolved Alerts"):
        display_anomaly_alerts(status='resolved')
    
    # Configuration link
    st.markdown("---")
    st.markdown("Configure anomaly detection settings [here](#anomaly-detection-configuration).")

# Main function to display anomaly detection page
def display_anomaly_detection_page():
    """Display the anomaly detection page with tabs"""
    initialize_anomaly_detection()
    
    # Create tabs
    tab1, tab2 = st.tabs(["Alert Dashboard", "Configuration"])
    
    with tab1:
        display_anomaly_alert_dashboard()
    
    with tab2:
        display_anomaly_config_page()