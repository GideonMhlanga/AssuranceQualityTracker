import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np

def display_brix_visualization(data, height=600):
    """
    Display BRIX visualization from quality check data
    
    Args:
        data: DataFrame with check data
        height: Height of the plot
    """
    # Filter data that has BRIX values
    brix_data = None
    
    if 'brix' in data.columns:
        brix_data = data[data['brix'].notna()]
    
    if brix_data is None or brix_data.empty:
        st.info("No BRIX data available for visualization.")
        return
        
    # Check if product column exists (for quality checks)
    if 'product' in brix_data.columns:
        # Plot BRIX by product
        fig = px.line(
            brix_data.sort_values('timestamp'), 
            x='timestamp', 
            y='brix',
            color='product',
            markers=True,
            title='BRIX Values Over Time',
            labels={'timestamp': 'Date & Time', 'brix': 'BRIX Value'}
        )
    else:
        # Simple BRIX plot for net content checks
        fig = px.line(
            brix_data.sort_values('timestamp'), 
            x='timestamp', 
            y='brix',
            markers=True,
            title='BRIX Values Over Time',
            labels={'timestamp': 'Date & Time', 'brix': 'BRIX Value'}
        )
    
    # Add target line if available (from quality standards)
    # This is just an example - actual target values would come from standards
    fig.add_hline(
        y=10.5, 
        line_dash="dash", 
        line_color="green",
        annotation_text="Target BRIX",
        annotation_position="bottom right"
    )
    
    # Update layout
    fig.update_layout(
        height=height,
        hovermode='x unified',
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1)
    )
    
    st.plotly_chart(fig, use_container_width=True)
    
    # Add statistical summary
    if not brix_data.empty:
        st.subheader("BRIX Statistics")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Average BRIX", f"{brix_data['brix'].mean():.2f}")
        
        with col2:
            st.metric("Min BRIX", f"{brix_data['brix'].min():.2f}")
        
        with col3:
            st.metric("Max BRIX", f"{brix_data['brix'].max():.2f}")
        
        with col4:
            st.metric("Standard Deviation", f"{brix_data['brix'].std():.2f}")

def display_torque_visualization(data, height=600):
    """
    Display torque visualization from torque and tamper checks
    
    Args:
        data: DataFrame with check data
        height: Height of the plot
    """
    # Filter to get torque data
    torque_cols = ['head1_torque', 'head2_torque', 'head3_torque', 'head4_torque', 'head5_torque']
    
    # Check if any torque columns exist in the data
    if not any(col in data.columns for col in torque_cols):
        st.info("No torque data available for visualization.")
        return
    
    torque_data = data[['timestamp'] + [col for col in torque_cols if col in data.columns]]
    torque_data = torque_data.dropna(subset=[col for col in torque_cols if col in data.columns], how='all')
    
    if torque_data.empty:
        st.info("No torque data available for visualization.")
        return
    
    # Create a subplot with 2 rows
    fig = make_subplots(
        rows=2, 
        cols=1,
        subplot_titles=("Torque Values by Head", "Average Torque Over Time"),
        vertical_spacing=0.15,
        row_heights=[0.6, 0.4]
    )
    
    # Plot 1: Line chart of torque values over time for each head
    for i, head_col in enumerate([col for col in torque_cols if col in torque_data.columns]):
        head_num = int(head_col.split('_')[0][4:])
        fig.add_trace(
            go.Scatter(
                x=torque_data['timestamp'], 
                y=torque_data[head_col],
                mode='lines+markers',
                name=f'Head {head_num}',
                legendgroup=f'head{head_num}'
            ),
            row=1, col=1
        )
    
    # Add target range
    fig.add_hline(
        y=5, 
        line_dash="dash", 
        line_color="red",
        annotation_text="Min Acceptable",
        annotation_position="bottom right",
        row=1, col=1
    )
    
    fig.add_hline(
        y=12, 
        line_dash="dash", 
        line_color="red",
        annotation_text="Max Acceptable",
        annotation_position="top right",
        row=1, col=1
    )
    
    # Plot 2: Average torque across all heads
    avg_torque = torque_data[
        [col for col in torque_cols if col in torque_data.columns]
    ].mean(axis=1)
    
    fig.add_trace(
        go.Scatter(
            x=torque_data['timestamp'],
            y=avg_torque,
            mode='lines+markers',
            name='Average Torque',
            line=dict(color='black', width=3)
        ),
        row=2, col=1
    )
    
    # Add target range to the average plot too
    fig.add_hline(
        y=5, 
        line_dash="dash", 
        line_color="red",
        row=2, col=1
    )
    
    fig.add_hline(
        y=12, 
        line_dash="dash", 
        line_color="red",
        row=2, col=1
    )
    
    # Update layout
    fig.update_layout(
        height=height,
        hovermode='x unified',
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1),
        margin=dict(l=60, r=40, t=60, b=60)
    )
    
    fig.update_yaxes(title_text="Torque Value", row=1, col=1)
    fig.update_yaxes(title_text="Avg Torque", row=2, col=1)
    fig.update_xaxes(title_text="Date & Time", row=2, col=1)
    
    st.plotly_chart(fig, use_container_width=True)
    
    # Add statistical summary
    st.subheader("Torque Statistics by Head")
    
    stats_cols = []
    for head_col in [col for col in torque_cols if col in torque_data.columns]:
        head_num = int(head_col.split('_')[0][4:])
        avg = torque_data[head_col].mean()
        out_of_range = ((torque_data[head_col] < 5) | (torque_data[head_col] > 12)).sum()
        pct_compliant = 100 * (1 - out_of_range / len(torque_data))
        
        stats_cols.append({
            "head": f"Head {head_num}",
            "avg": avg,
            "out_of_range": out_of_range,
            "pct_compliant": pct_compliant
        })
    
    # Display stats in columns
    cols = st.columns(len(stats_cols))
    for i, col_data in enumerate(stats_cols):
        with cols[i]:
            st.metric(
                col_data["head"], 
                f"Avg: {col_data['avg']:.2f}",
                f"{col_data['pct_compliant']:.1f}% Compliant"
            )
            if col_data["out_of_range"] > 0:
                st.caption(f"{col_data['out_of_range']} readings out of range")

def display_quality_metrics_visualization(data):
    """
    Display comprehensive quality metrics visualization
    
    Args:
        data: DataFrame with combined check data
    """
    if data.empty:
        st.info("No data available for visualization.")
        return
    
    st.subheader("Quality Metrics Overview")
    
    # Show multiple visualizations in tabs
    tab1, tab2, tab3, tab4 = st.tabs([
        "BRIX Analysis", 
        "Torque Performance", 
        "Quality Issues", 
        "Productivity"
    ])
    
    with tab1:
        display_brix_visualization(data)
    
    with tab2:
        display_torque_visualization(data)
    
    with tab3:
        st.subheader("Quality Issues by Category")
        
        # Collect quality issues data
        quality_issues = []
        
        # Process quality check data if available
        if 'source' in data.columns and 'quality_check' in data['source'].values:
            quality_data = data[data['source'] == 'quality_check']
            
            # Check each quality parameter
            quality_params = [
                ('label_application', 'Not OK', 'Label Issues'),
                ('torque_test', 'FAIL', 'Torque Issues'),
                ('pallet_check', 'Not OK', 'Pallet Issues'),
                ('date_code', 'Not OK', 'Date Code Issues'),
                ('odour', 'Bad Odour', 'Odour Issues'),
                ('appearance', 'Not To Std', 'Appearance Issues'),
                ('product_taste', 'Not To Std', 'Taste Issues'),
                ('filler_height', 'Not To Std', 'Filler Height Issues'),
                ('bottle_check', 'Not OK', 'Bottle Issues'),
                ('bottle_seams', 'Not OK', 'Bottle Seam Issues'),
                ('container_rinse_inspection', 'Not OK', 'Container Rinse Issues'),
                ('container_rinse_water_odour', 'Bad Odour', 'Rinse Water Issues')
            ]
            
            # Count issues for each parameter
            for param, fail_value, label in quality_params:
                if param in quality_data.columns:
                    count = (quality_data[param] == fail_value).sum()
                    if count > 0:
                        quality_issues.append({
                            'category': label,
                            'count': count
                        })
        
        # Process tamper evidence data if available
        if 'source' in data.columns and 'torque_tamper' in data['source'].values:
            tamper_data = data[data['source'] == 'torque_tamper']
            if 'tamper_evidence' in tamper_data.columns:
                tamper_fails = (tamper_data['tamper_evidence'].str.contains('FAIL')).sum()
                if tamper_fails > 0:
                    quality_issues.append({
                        'category': 'Tamper Evidence Issues',
                        'count': tamper_fails
                    })
        
        # Display quality issues chart if there are any issues
        if quality_issues:
            issues_df = pd.DataFrame(quality_issues)
            fig = px.bar(
                issues_df.sort_values('count', ascending=False),
                x='category',
                y='count',
                color='count',
                color_continuous_scale=px.colors.sequential.Reds,
                title='Quality Issues by Category',
                labels={'count': 'Number of Issues', 'category': 'Issue Category'}
            )
            
            fig.update_layout(
                height=500,
                xaxis_title="",
                yaxis_title="Count",
                coloraxis_showscale=False
            )
            
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No quality issues found in the selected data period.")
    
    with tab4:
        st.subheader("Productivity Analysis")
        
        # Calculate check durations
        if 'timestamp' in data.columns and 'start_time' in data.columns:
            data['duration_minutes'] = (pd.to_datetime(data['timestamp']) - 
                                     pd.to_datetime(data['start_time'])).dt.total_seconds() / 60
            
            # Group by date and calculate checks per day
            data['check_date'] = pd.to_datetime(data['timestamp']).dt.date
            checks_per_day = data.groupby('check_date').size().reset_index(name='count')
            
            # Plot checks per day
            fig = px.bar(
                checks_per_day,
                x='check_date',
                y='count',
                title='Quality Checks Per Day',
                labels={'check_date': 'Date', 'count': 'Number of Checks'}
            )
            
            fig.update_layout(height=400)
            st.plotly_chart(fig, use_container_width=True)
            
            # Plot average check duration
            if 'duration_minutes' in data.columns:
                avg_duration = data.groupby(['username', 'source'])['duration_minutes'].mean().reset_index()
                
                if not avg_duration.empty:
                    # Map source names to more readable form titles
                    source_mapping = {
                        'torque_tamper': 'Torque & Tamper',
                        'net_content': 'Net Content',
                        'quality_check': '30-Minute Check'
                    }
                    avg_duration['check_type'] = avg_duration['source'].map(source_mapping)
                    
                    fig = px.bar(
                        avg_duration,
                        x='username',
                        y='duration_minutes',
                        color='check_type',
                        barmode='group',
                        title='Average Check Duration by User and Type',
                        labels={
                            'username': 'User', 
                            'duration_minutes': 'Duration (minutes)',
                            'check_type': 'Check Type'
                        }
                    )
                    
                    fig.update_layout(height=400)
                    st.plotly_chart(fig, use_container_width=True)
