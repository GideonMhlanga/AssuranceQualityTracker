import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from database import get_check_data

def calculate_control_limits(data, column, n_sigma=3):
    """
    Calculate control limits for a given data series
    
    Args:
        data: DataFrame containing the data
        column: The column to calculate control limits for
        n_sigma: Number of standard deviations for control limits (default: 3)
        
    Returns:
        dict with UCL (upper control limit), LCL (lower control limit),
        CL (center line/mean), and sigma (standard deviation)
    """
    if data.empty or column not in data.columns:
        return {'UCL': None, 'LCL': None, 'CL': None, 'sigma': None}
    
    # Filter out NaN values
    values = data[column].dropna()
    
    if len(values) < 2:
        return {'UCL': None, 'LCL': None, 'CL': None, 'sigma': None}
    
    mean = values.mean()
    sigma = values.std()
    
    ucl = mean + (n_sigma * sigma)
    lcl = mean - (n_sigma * sigma)
    
    # If LCL is negative and that doesn't make sense for the data, set to 0
    if lcl < 0 and all(values >= 0):
        lcl = 0
    
    return {
        'UCL': ucl,
        'LCL': lcl,
        'CL': mean,
        'sigma': sigma
    }

def create_xbar_chart(data, value_column, date_column='timestamp', title=None, n_sigma=3):
    """
    Create an X-bar control chart using Plotly
    
    Args:
        data: DataFrame containing the data
        value_column: Column for values to plot
        date_column: Column for dates (default: 'timestamp')
        title: Chart title (default: None)
        n_sigma: Number of standard deviations for control limits (default: 3)
        
    Returns:
        Plotly figure object
    """
    if data.empty or value_column not in data.columns:
        # Return empty figure if no data
        fig = go.Figure()
        fig.update_layout(title="No data available for SPC chart")
        return fig
    
    # Calculate control limits
    control_limits = calculate_control_limits(data, value_column, n_sigma)
    
    # If no valid statistics, return empty chart
    if control_limits['CL'] is None:
        fig = go.Figure()
        fig.update_layout(title="Insufficient data for SPC chart")
        return fig
    
    # Sort data by date
    data = data.sort_values(by=date_column)
    
    # Create figure
    fig = go.Figure()
    
    # Add data points
    fig.add_trace(go.Scatter(
        x=data[date_column],
        y=data[value_column],
        mode='lines+markers',
        name='Data',
        line=dict(color='blue')
    ))
    
    # Add center line (mean)
    fig.add_trace(go.Scatter(
        x=[data[date_column].min(), data[date_column].max()],
        y=[control_limits['CL'], control_limits['CL']],
        mode='lines',
        name='Mean (CL)',
        line=dict(color='green', dash='dash')
    ))
    
    # Add upper control limit
    fig.add_trace(go.Scatter(
        x=[data[date_column].min(), data[date_column].max()],
        y=[control_limits['UCL'], control_limits['UCL']],
        mode='lines',
        name=f'Upper Control Limit ({n_sigma}σ)',
        line=dict(color='red', dash='dash')
    ))
    
    # Add lower control limit
    fig.add_trace(go.Scatter(
        x=[data[date_column].min(), data[date_column].max()],
        y=[control_limits['LCL'], control_limits['LCL']],
        mode='lines',
        name=f'Lower Control Limit ({n_sigma}σ)',
        line=dict(color='red', dash='dash')
    ))
    
    # Find out-of-control points
    out_of_control = data[
        (data[value_column] > control_limits['UCL']) | 
        (data[value_column] < control_limits['LCL'])
    ]
    
    # Add out-of-control points as different markers
    if not out_of_control.empty:
        fig.add_trace(go.Scatter(
            x=out_of_control[date_column],
            y=out_of_control[value_column],
            mode='markers',
            name='Out of Control',
            marker=dict(color='red', size=10, symbol='circle-open')
        ))
    
    # Set title and layout
    fig.update_layout(
        title=title if title else f'Control Chart for {value_column}',
        xaxis_title='Date',
        yaxis_title=value_column,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        ),
        height=500
    )
    
    return fig

def create_moving_range_chart(data, value_column, date_column='timestamp', title=None, n_sigma=3):
    """
    Create a Moving Range chart using Plotly
    
    Args:
        data: DataFrame containing the data
        value_column: Column for values to calculate moving ranges
        date_column: Column for dates (default: 'timestamp')
        title: Chart title (default: None)
        n_sigma: Number of standard deviations for control limits (default: 3)
        
    Returns:
        Plotly figure object
    """
    if data.empty or value_column not in data.columns:
        # Return empty figure if no data
        fig = go.Figure()
        fig.update_layout(title="No data available for Moving Range chart")
        return fig
    
    # Sort data by date
    data = data.sort_values(by=date_column)
    
    # Calculate moving ranges
    values = data[value_column].dropna()
    
    if len(values) < 2:
        fig = go.Figure()
        fig.update_layout(title="Insufficient data for Moving Range chart")
        return fig
    
    # Calculate moving ranges
    moving_ranges = values.diff().abs()
    
    # Calculate control limits for moving ranges
    mr_mean = moving_ranges.mean()
    mr_std = moving_ranges.std()
    
    # For moving range charts, the standard formula for control limits is different
    d2 = 1.128  # Constant for n=2 (moving range of 2 consecutive points)
    mr_ucl = mr_mean + (3 * mr_mean / d2)
    mr_lcl = 0  # Lower control limit for ranges is always 0
    
    # Create DataFrame for plotting
    mr_data = pd.DataFrame({
        date_column: data[date_column].iloc[1:].reset_index(drop=True),
        'moving_range': moving_ranges.iloc[1:].reset_index(drop=True)
    })
    
    # Create figure
    fig = go.Figure()
    
    # Add moving range data points
    fig.add_trace(go.Scatter(
        x=mr_data[date_column],
        y=mr_data['moving_range'],
        mode='lines+markers',
        name='Moving Range',
        line=dict(color='blue')
    ))
    
    # Add center line (mean)
    fig.add_trace(go.Scatter(
        x=[mr_data[date_column].min(), mr_data[date_column].max()],
        y=[mr_mean, mr_mean],
        mode='lines',
        name='Mean (CL)',
        line=dict(color='green', dash='dash')
    ))
    
    # Add upper control limit
    fig.add_trace(go.Scatter(
        x=[mr_data[date_column].min(), mr_data[date_column].max()],
        y=[mr_ucl, mr_ucl],
        mode='lines',
        name='Upper Control Limit (3σ)',
        line=dict(color='red', dash='dash')
    ))
    
    # Add lower control limit
    fig.add_trace(go.Scatter(
        x=[mr_data[date_column].min(), mr_data[date_column].max()],
        y=[mr_lcl, mr_lcl],
        mode='lines',
        name='Lower Control Limit (0)',
        line=dict(color='red', dash='dash')
    ))
    
    # Find out-of-control points
    out_of_control = mr_data[
        (mr_data['moving_range'] > mr_ucl) | 
        (mr_data['moving_range'] < mr_lcl)
    ]
    
    # Add out-of-control points as different markers
    if not out_of_control.empty:
        fig.add_trace(go.Scatter(
            x=out_of_control[date_column],
            y=out_of_control['moving_range'],
            mode='markers',
            name='Out of Control',
            marker=dict(color='red', size=10, symbol='circle-open')
        ))
    
    # Set title and layout
    fig.update_layout(
        title=title if title else f'Moving Range Chart for {value_column}',
        xaxis_title='Date',
        yaxis_title='Moving Range',
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        ),
        height=500
    )
    
    return fig

def display_spc_dashboard(start_date, end_date, product_filter=None):
    """
    Display an SPC dashboard with multiple charts
    
    Args:
        start_date: Start date for filtering data
        end_date: End date for filtering data
        product_filter: Optional product filter
    """
    # Get data
    data = get_check_data(start_date, end_date, product_filter)
    
    if data.empty:
        st.warning("No data available for the selected time period")
        return
    
    # Create tabs for different chart types
    tab_torque, tab_brix, tab_weight, tab_net_content = st.tabs(["Torque", "BRIX", "Average Weight", "Net Content"])
    
    with tab_torque:
        st.subheader("Torque Statistical Process Control")
        
        # Filter for torque data
        torque_data = data[data['source'] == 'torque_tamper'].copy()
        quality_torque_data = data[data['source'] == 'quality_check'].copy()
        
        # Check if we have torque test data in the quality checks
        if 'torque_test' in quality_torque_data.columns:
            st.markdown("#### Overall Torque Test Results")
            # Convert PASS/FAIL to 1/0 for charting purposes
            if quality_torque_data['torque_test'].notna().sum() > 0:
                quality_torque_data['torque_numeric'] = quality_torque_data['torque_test'].apply(lambda x: 1 if x == 'PASS' else 0)
                
                # Calculate pass rate percentage
                pass_rate = quality_torque_data['torque_numeric'].mean() * 100
                st.metric("Torque Test Pass Rate", f"{pass_rate:.1f}%")
                
                # Display torque test trend if we have enough data
                if quality_torque_data['torque_numeric'].notna().sum() >= 5:
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(
                        x=quality_torque_data['timestamp'],
                        y=quality_torque_data['torque_numeric'].rolling(window=5, min_periods=1).mean() * 100,
                        mode='lines+markers',
                        name='Pass Rate (5-point moving average)',
                        line=dict(color='blue')
                    ))
                    fig.update_layout(
                        title="Torque Test Pass Rate Trend",
                        xaxis_title="Date",
                        yaxis_title="Pass Rate (%)",
                        yaxis=dict(range=[0, 105]),
                        height=300
                    )
                    st.plotly_chart(fig, use_container_width=True)
        
        if not torque_data.empty:
            st.markdown("#### Individual Torque Measurements")
            # Create individual charts for each head
            for head in ['head1_torque', 'head2_torque', 'head3_torque', 'head4_torque', 'head5_torque']:
                # Skip if no non-NA values
                if torque_data[head].notna().sum() < 2:
                    continue
                    
                st.markdown(f"#### {head.replace('_', ' ').title()}")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    # X-bar chart
                    fig_xbar = create_xbar_chart(
                        torque_data, 
                        head, 
                        title=f"Individual Values Chart - {head.replace('_', ' ').title()}"
                    )
                    st.plotly_chart(fig_xbar, use_container_width=True)
                
                with col2:
                    # Moving Range chart
                    fig_mr = create_moving_range_chart(
                        torque_data,
                        head,
                        title=f"Moving Range Chart - {head.replace('_', ' ').title()}"
                    )
                    st.plotly_chart(fig_mr, use_container_width=True)
                
                # Add torque metrics
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Average Torque", f"{torque_data[head].mean():.2f}")
                with col2:
                    st.metric("Min Torque", f"{torque_data[head].min():.2f}")
                with col3:
                    st.metric("Max Torque", f"{torque_data[head].max():.2f}")
                
                # Add specification limits
                st.markdown("**Specification Limits**: 5.0 - 12.0")
                
                # Calculate percentage within specs
                within_spec = ((torque_data[head] >= 5.0) & (torque_data[head] <= 12.0)).mean() * 100
                st.metric("Percentage Within Spec", f"{within_spec:.1f}%")
                
                st.markdown("---")
        else:
            st.info("No torque data available for the selected time period")
    
    with tab_brix:
        st.subheader("BRIX Statistical Process Control")
        
        # Filter for brix data (can be in either net_content or quality_check)
        brix_data = pd.concat([
            data[data['source'] == 'net_content'][['timestamp', 'brix', 'product']],
            data[data['source'] == 'quality_check'][['timestamp', 'brix', 'product']]
        ]).dropna(subset=['brix'])
        
        if len(brix_data) >= 2:
            # Add product-specific analysis if we have product information
            if 'product' in brix_data.columns and brix_data['product'].notna().any():
                # Get unique products for selection
                products = sorted(brix_data['product'].dropna().unique())
                if len(products) > 1:
                    selected_product = st.selectbox("Select Product for BRIX Analysis", 
                                                  ["All Products"] + list(products))
                    
                    if selected_product != "All Products":
                        brix_data = brix_data[brix_data['product'] == selected_product]
                        st.subheader(f"BRIX Analysis for {selected_product}")
            
            col1, col2 = st.columns(2)
            
            with col1:
                # X-bar chart for BRIX
                fig_brix = create_xbar_chart(
                    brix_data, 
                    'brix', 
                    title="Individual Values Chart - BRIX"
                )
                st.plotly_chart(fig_brix, use_container_width=True)
            
            with col2:
                # Moving Range chart for BRIX
                fig_brix_mr = create_moving_range_chart(
                    brix_data,
                    'brix',
                    title="Moving Range Chart - BRIX"
                )
                st.plotly_chart(fig_brix_mr, use_container_width=True)
            
            # Add BRIX metrics
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Average BRIX", f"{brix_data['brix'].mean():.2f}")
            with col2:
                st.metric("Min BRIX", f"{brix_data['brix'].min():.2f}")
            with col3:
                st.metric("Max BRIX", f"{brix_data['brix'].max():.2f}")
            with col4:
                st.metric("BRIX Std Dev", f"{brix_data['brix'].std():.3f}")
            
            # BRIX trend chart
            st.markdown("#### BRIX Trend")
            fig = go.Figure()
            
            # Sort data by timestamp for trend analysis
            trend_data = brix_data.sort_values('timestamp')
            
            # Add individual data points
            fig.add_trace(go.Scatter(
                x=trend_data['timestamp'],
                y=trend_data['brix'],
                mode='markers',
                name='BRIX Values',
                marker=dict(color='blue', size=8)
            ))
            
            # Add trend line (moving average)
            if len(trend_data) >= 3:
                fig.add_trace(go.Scatter(
                    x=trend_data['timestamp'],
                    y=trend_data['brix'].rolling(window=3, min_periods=1).mean(),
                    mode='lines',
                    name='Trend (3-point MA)',
                    line=dict(color='red', width=2)
                ))
            
            fig.update_layout(
                title="BRIX Trend Over Time",
                xaxis_title="Date",
                yaxis_title="BRIX Value",
                height=400
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Insufficient BRIX data for SPC analysis")
    
    with tab_weight:
        st.subheader("Average Weight Statistical Process Control")
        
        # Filter for average weight data
        weight_data = data[data['source'] == 'net_content'].copy()
        
        if not weight_data.empty and 'average_weight' in weight_data.columns:
            # Check if enough non-NA values
            if weight_data['average_weight'].notna().sum() >= 2:
                col1, col2 = st.columns(2)
                
                with col1:
                    # X-bar chart for Average Weight
                    fig_weight = create_xbar_chart(
                        weight_data, 
                        'average_weight', 
                        title="Individual Values Chart - Average Weight"
                    )
                    st.plotly_chart(fig_weight, use_container_width=True)
                
                with col2:
                    # Moving Range chart for Average Weight
                    fig_weight_mr = create_moving_range_chart(
                        weight_data,
                        'average_weight',
                        title="Moving Range Chart - Average Weight"
                    )
                    st.plotly_chart(fig_weight_mr, use_container_width=True)
                
                # Weight metrics
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Average Weight", f"{weight_data['average_weight'].mean():.2f}")
                with col2:
                    st.metric("Min Weight", f"{weight_data['average_weight'].min():.2f}")
                with col3:
                    st.metric("Max Weight", f"{weight_data['average_weight'].max():.2f}")
                with col4:
                    st.metric("Weight Std Dev", f"{weight_data['average_weight'].std():.3f}")
                
                # Show individual bottle weights distribution if available
                bottle_cols = ['bottle1_weight', 'bottle2_weight', 'bottle3_weight', 
                               'bottle4_weight', 'bottle5_weight']
                if all(col in weight_data.columns for col in bottle_cols):
                    st.markdown("#### Individual Bottle Weights Distribution")
                    
                    # Gather all individual bottle weights
                    all_weights = []
                    for col in bottle_cols:
                        all_weights.extend(weight_data[col].dropna().tolist())
                    
                    if all_weights:
                        # Create histogram
                        fig = go.Figure()
                        fig.add_trace(go.Histogram(
                            x=all_weights,
                            nbinsx=20,
                            marker_color='blue',
                            opacity=0.7
                        ))
                        
                        fig.update_layout(
                            title="Distribution of Individual Bottle Weights",
                            xaxis_title="Weight",
                            yaxis_title="Count",
                            height=400
                        )
                        st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Insufficient Average Weight data for SPC analysis")
        else:
            st.info("No Average Weight data available for the selected time period")
    
    with tab_net_content:
        st.subheader("Net Content Statistical Process Control")
        
        # Filter for net content data
        net_content_data = data[data['source'] == 'net_content'].copy()
        
        if not net_content_data.empty and 'net_content' in net_content_data.columns:
            # Check if enough non-NA values
            if net_content_data['net_content'].notna().sum() >= 2:
                col1, col2 = st.columns(2)
                
                with col1:
                    # X-bar chart for Net Content
                    fig_nc = create_xbar_chart(
                        net_content_data, 
                        'net_content', 
                        title="Individual Values Chart - Net Content"
                    )
                    st.plotly_chart(fig_nc, use_container_width=True)
                
                with col2:
                    # Moving Range chart for Net Content
                    fig_nc_mr = create_moving_range_chart(
                        net_content_data,
                        'net_content',
                        title="Moving Range Chart - Net Content"
                    )
                    st.plotly_chart(fig_nc_mr, use_container_width=True)
                
                # Net content metrics
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Average Net Content", f"{net_content_data['net_content'].mean():.2f}")
                with col2:
                    st.metric("Min Net Content", f"{net_content_data['net_content'].min():.2f}")
                with col3:
                    st.metric("Max Net Content", f"{net_content_data['net_content'].max():.2f}")
                with col4:
                    st.metric("Net Content Std Dev", f"{net_content_data['net_content'].std():.3f}")
            else:
                st.info("Insufficient Net Content data for SPC analysis")
        else:
            st.info("No Net Content data available for the selected time period")
            
    # Add explanations about SPC charts
    with st.expander("About Statistical Process Control Charts"):
        st.markdown("""
        ### Understanding SPC Charts
        
        Statistical Process Control (SPC) charts are tools used to monitor process performance over time.
        
        #### Individual Values Chart
        - The blue line represents individual measurements over time
        - The green dashed line is the mean (average) of all measurements
        - The red dashed lines are the Upper and Lower Control Limits (UCL/LCL), set at 3 standard deviations from the mean
        - Red circles indicate out-of-control points that exceed the control limits
        
        #### Moving Range Chart
        - Shows the absolute difference between consecutive measurements
        - Helps identify instability or unusual variation in the process
        - Points above the Upper Control Limit indicate abnormal variation
        
        ### Interpreting the Charts
        
        A process is considered "in control" when:
        - All points fall within the control limits
        - No unusual patterns or trends exist
        
        Signs of an "out of control" process:
        - Points outside the control limits
        - Runs of 7+ points all above or below the center line
        - Trends of 7+ points continuously increasing or decreasing
        
        When a process is out of control, investigate the causes and take corrective action.
        """)

def display_spc_page():
    """Display the SPC page with filters and charts"""
    st.title("Statistical Process Control (SPC)")
    
    st.markdown("""
    This page provides Statistical Process Control (SPC) analysis for key quality metrics.
    SPC helps monitor process stability and detect abnormal variations that require investigation.
    """)
    
    # Get data for filtering
    # First get all data to extract product list
    all_data = get_check_data(
        start_date="1900-01-01", 
        end_date="2100-01-01"
    )
    
    # Filter sidebar
    st.sidebar.header("SPC Analysis Filters")
    
    # Time period selection
    time_periods = ["Last Week", "Last Month", "Last Quarter", "Last Year", "Custom Range"]
    selected_period = st.sidebar.selectbox("Time Period", time_periods)
    
    if selected_period == "Custom Range":
        # Custom date range
        col1, col2 = st.sidebar.columns(2)
        with col1:
            start_date = st.date_input("Start Date")
        with col2:
            end_date = st.date_input("End Date")
    else:
        # Predefined time periods
        end_date = pd.Timestamp.now().date()
        
        if selected_period == "Last Week":
            start_date = end_date - pd.Timedelta(days=7)
        elif selected_period == "Last Month":
            start_date = end_date - pd.Timedelta(days=30)
        elif selected_period == "Last Quarter":
            start_date = end_date - pd.Timedelta(days=90)
        else:  # Last Year
            start_date = end_date - pd.Timedelta(days=365)
    
    # Filter by product
    products = []
    if not all_data.empty and 'product' in all_data.columns:
        products = sorted(all_data['product'].dropna().unique().tolist())
    
    if products:
        products.insert(0, "All Products")
        selected_products = st.sidebar.multiselect(
            "Filter by Product", 
            products,
            default=["All Products"]
        )
        
        # Convert to format expected by get_check_data
        if "All Products" in selected_products:
            product_filter = None
        else:
            product_filter = selected_products
    else:
        product_filter = None
    
    # Reset button
    if st.sidebar.button("Reset Filters"):
        st.rerun()
    
    # Display SPC dashboard
    display_spc_dashboard(start_date, end_date, product_filter)