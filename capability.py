import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import scipy.stats as stats

def calculate_process_capability(data, column, lsl=None, usl=None):
    """
    Calculate process capability indices (Cp, Cpk, Pp, Ppk)
    
    Args:
        data: DataFrame containing the data
        column: Column name for analysis
        lsl: Lower specification limit (optional)
        usl: Upper specification limit (optional)
        
    Returns:
        dict with capability metrics
    """
    if data.empty or column not in data.columns:
        return {
            "cp": None, "cpk": None, "pp": None, "ppk": None,
            "mean": None, "std": None, "min": None, "max": None,
            "out_of_spec_percent": None
        }
    
    # Filter out missing values
    values = data[column].dropna()
    
    if len(values) < 10:  # Need minimum sample size for reliable calculations
        return {
            "cp": None, "cpk": None, "pp": None, "ppk": None,
            "mean": None, "std": None, "min": None, "max": None,
            "out_of_spec_percent": None
        }
    
    # Calculate basic statistics
    mean = values.mean()
    std = values.std(ddof=1)  # Sample standard deviation
    min_val = values.min()
    max_val = values.max()
    
    # Process capability calculations
    results = {
        "mean": mean,
        "std": std,
        "min": min_val,
        "max": max_val,
        "cp": None,
        "cpk": None,
        "pp": None,
        "ppk": None,
        "out_of_spec_percent": 0
    }
    
    # Check if specification limits are provided
    if lsl is None and usl is None:
        return results
    
    # Calculate out of spec percentage
    out_of_spec_count = 0
    if lsl is not None:
        out_of_spec_count += (values < lsl).sum()
    if usl is not None:
        out_of_spec_count += (values > usl).sum()
    
    results["out_of_spec_percent"] = 100 * out_of_spec_count / len(values)
    
    # Calculate process capability and performance indices
    if lsl is not None and usl is not None:
        # Cp - Process Capability (assumes process is centered)
        cp = (usl - lsl) / (6 * std)
        results["cp"] = cp
        
        # Cpk - Process Capability Index (accounts for process centering)
        cpu = (usl - mean) / (3 * std)
        cpl = (mean - lsl) / (3 * std)
        cpk = min(cpu, cpl)
        results["cpk"] = cpk
        
        # Pp - Process Performance (overall variation)
        # For short-term vs long-term distinction
        pp = cp  # In this simple implementation, we're using the same calculation
        results["pp"] = pp
        
        # Ppk - Process Performance Index
        ppk = cpk  # In this simple implementation, we're using the same calculation
        results["ppk"] = ppk
    
    elif usl is not None:
        # One-sided upper specification limit
        cpu = (usl - mean) / (3 * std)
        results["cp"] = cpu
        results["cpk"] = cpu
        results["pp"] = cpu
        results["ppk"] = cpu
    
    elif lsl is not None:
        # One-sided lower specification limit
        cpl = (mean - lsl) / (3 * std)
        results["cp"] = cpl
        results["cpk"] = cpl
        results["pp"] = cpl
        results["ppk"] = cpl
    
    return results

def create_capability_chart(data, column, lsl=None, usl=None, title=None):
    """
    Create a process capability chart with histogram and normal distribution overlay
    
    Args:
        data: DataFrame containing the data
        column: Column name for analysis
        lsl: Lower specification limit (optional)
        usl: Upper specification limit (optional)
        title: Chart title (optional)
        
    Returns:
        Plotly figure object
    """
    if data.empty or column not in data.columns:
        fig = go.Figure()
        fig.update_layout(title="No data available for capability analysis")
        return fig
    
    # Filter out missing values
    values = data[column].dropna()
    
    if len(values) < 10:  # Need minimum sample size for reliable histogram
        fig = go.Figure()
        fig.update_layout(title="Insufficient data for capability analysis")
        return fig
    
    # Calculate capability metrics
    capability = calculate_process_capability(data, column, lsl, usl)
    
    # Create figure
    fig = go.Figure()
    
    # Create histogram
    fig.add_trace(go.Histogram(
        x=values,
        histnorm='probability density',
        name='Data Distribution',
        marker=dict(color='lightblue'),
        opacity=0.75
    ))
    
    # Overlay normal distribution curve
    if capability["mean"] is not None and capability["std"] is not None:
        x = np.linspace(
            max(min(values) - 3 * capability["std"], lsl - capability["std"] if lsl is not None else -np.inf),
            min(max(values) + 3 * capability["std"], usl + capability["std"] if usl is not None else np.inf),
            100
        )
        y = stats.norm.pdf(x, capability["mean"], capability["std"])
        
        fig.add_trace(go.Scatter(
            x=x,
            y=y,
            mode='lines',
            name='Normal Distribution',
            line=dict(color='darkblue')
        ))
    
    # Add specification limits
    if lsl is not None:
        fig.add_vline(x=lsl, line_width=2, line_dash="dash", line_color="red",
                     annotation_text="LSL", annotation_position="bottom right")
    
    if usl is not None:
        fig.add_vline(x=usl, line_width=2, line_dash="dash", line_color="red",
                     annotation_text="USL", annotation_position="bottom left")
    
    # Add mean line
    if capability["mean"] is not None:
        fig.add_vline(x=capability["mean"], line_width=2, line_dash="solid", line_color="green",
                     annotation_text="Mean", annotation_position="bottom")
    
    # Set title and layout
    chart_title = title if title else f'Process Capability Analysis - {column}'
    if capability["cpk"] is not None:
        chart_title += f' (Cpk: {capability["cpk"]:.2f})'
    
    fig.update_layout(
        title=chart_title,
        xaxis_title=column,
        yaxis_title='Probability Density',
        showlegend=True,
        height=500
    )
    
    return fig

def display_capability_metrics(capability_data):
    """
    Display process capability metrics in a formatted way
    
    Args:
        capability_data: Dictionary of capability metrics from calculate_process_capability
    """
    # Create three columns for metrics display
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Process Capability (Cp)", 
                 f"{capability_data['cp']:.3f}" if capability_data['cp'] is not None else "N/A")
        st.metric("Min Value", 
                 f"{capability_data['min']:.3f}" if capability_data['min'] is not None else "N/A")
    
    with col2:
        st.metric("Process Capability Index (Cpk)", 
                 f"{capability_data['cpk']:.3f}" if capability_data['cpk'] is not None else "N/A")
        st.metric("Max Value", 
                 f"{capability_data['max']:.3f}" if capability_data['max'] is not None else "N/A")
    
    with col3:
        st.metric("Out of Specification %", 
                 f"{capability_data['out_of_spec_percent']:.2f}%" if capability_data['out_of_spec_percent'] is not None else "N/A")
        st.metric("Standard Deviation", 
                 f"{capability_data['std']:.3f}" if capability_data['std'] is not None else "N/A")

    # Capability index interpretation
    if capability_data['cpk'] is not None:
        cpk = capability_data['cpk']
        
        if cpk < 1.0:
            st.error("⚠️ Process is not capable (Cpk < 1.0). The process does not meet specifications.")
        elif cpk >= 1.0 and cpk < 1.33:
            st.warning("⚠️ Process is marginally capable (1.0 ≤ Cpk < 1.33). Improvement needed.")
        elif cpk >= 1.33 and cpk < 1.67:
            st.success("✓ Process is capable (1.33 ≤ Cpk < 1.67). Good process control.")
        else:
            st.success("✓✓ Process is highly capable (Cpk ≥ 1.67). Excellent process control.")

def display_capability_analysis(data, parameter, lsl=None, usl=None):
    """
    Display comprehensive capability analysis for a parameter
    
    Args:
        data: DataFrame with the data
        parameter: Parameter name to analyze
        lsl: Lower specification limit (optional)
        usl: Upper specification limit (optional)
    """
    if data.empty or parameter not in data.columns:
        st.info(f"No data available for {parameter} capability analysis")
        return
    
    # Calculate process capability
    capability_data = calculate_process_capability(data, parameter, lsl, usl)
    
    # Display metrics
    display_capability_metrics(capability_data)
    
    # Create and display capability chart
    fig = create_capability_chart(data, parameter, lsl, usl)
    st.plotly_chart(fig, use_container_width=True)
    
    # Show data summary
    with st.expander("View Data Summary"):
        st.dataframe(data[[parameter]].describe())

def display_capability_page(data, product_filter=None):
    """
    Display capability analysis page with parameter selection
    
    Args:
        data: DataFrame with all quality data
        product_filter: Optional product filter
    """
    st.title("Process Capability Analysis")
    
    st.markdown("""
    Process capability analysis measures how well your production process meets specifications.
    It quantifies process performance with indices like Cp and Cpk to assess quality and consistency.
    """)
    
    # Available parameters for capability analysis
    numerical_columns = [col for col in data.columns if 
                         pd.api.types.is_numeric_dtype(data[col]) and 
                         data[col].notna().sum() >= 10]
    
    if not numerical_columns:
        st.warning("Insufficient data for capability analysis. Need at least 10 measurements.")
        return
    
    # Parameter selection
    parameter = st.selectbox(
        "Select Parameter for Analysis",
        numerical_columns
    )
    
    # Set specification limits
    st.subheader("Specification Limits")
    st.markdown("Enter the specification limits for the selected parameter:")
    
    col1, col2 = st.columns(2)
    
    with col1:
        lsl = st.number_input("Lower Specification Limit (LSL)", 
                           value=None, step=0.1, key="lsl_input")
        if lsl == 0.0:  # Streamlit doesn't support true None for number_input
            lsl = None
    
    with col2:
        usl = st.number_input("Upper Specification Limit (USL)", 
                           value=None, step=0.1, key="usl_input")
        if usl == 0.0:  # Streamlit doesn't support true None for number_input
            usl = None
    
    # Apply specification defaults for common parameters
    spec_defaults = {
        "brix": {"lsl": 8.0, "usl": 9.5},
        "head1_torque": {"lsl": 5.0, "usl": 12.0},
        "head2_torque": {"lsl": 5.0, "usl": 12.0},
        "head3_torque": {"lsl": 5.0, "usl": 12.0},
        "head4_torque": {"lsl": 5.0, "usl": 12.0},
        "head5_torque": {"lsl": 5.0, "usl": 12.0}
    }
    
    if parameter in spec_defaults and (lsl is None or usl is None):
        default_specs = spec_defaults[parameter]
        if lsl is None:
            lsl = default_specs["lsl"]
            st.info(f"Using default LSL of {lsl} for {parameter}")
        if usl is None:
            usl = default_specs["usl"]
            st.info(f"Using default USL of {usl} for {parameter}")
    
    # Warn if no specification limits are set
    if lsl is None and usl is None:
        st.warning("No specification limits set. Cannot calculate Cp/Cpk without at least one limit.")
    
    # Display capability analysis
    display_capability_analysis(data, parameter, lsl, usl)
    
    # Guide for interpreting process capability
    with st.expander("How to Interpret Process Capability", expanded=False):
        st.markdown("""
        ### Process Capability Interpretation Guide
        
        Process capability indices measure how well your process meets specifications:
        
        #### Cp (Process Capability)
        - Measures potential capability if the process is centered
        - Cp = (USL - LSL) / (6 × standard deviation)
        - Doesn't account for process centering
        
        #### Cpk (Process Capability Index)
        - Measures actual capability, accounting for process centering
        - Cpk = min[(USL - mean) / (3 × std), (mean - LSL) / (3 × std)]
        - Always less than or equal to Cp
        
        #### Interpretation
        
        | Cpk Value | Interpretation | Action |
        |-----------|----------------|--------|
        | < 1.0 | Not capable | Immediate improvement needed |
        | 1.0 - 1.33 | Marginally capable | Process improvement required |
        | 1.33 - 1.67 | Capable | Monitor and maintain |
        | > 1.67 | Highly capable | Excellent, maintain controls |
        
        #### Out of Specification Percentage
        - Shows the estimated percentage of products outside specification limits
        - Lower percentages indicate better process capability
        """)