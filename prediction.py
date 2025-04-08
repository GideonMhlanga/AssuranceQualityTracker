import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import datetime as dt
from scipy import stats
from database import get_check_data
from utils import format_timestamp
import statsmodels.api as sm
from statsmodels.tsa.arima.model import ARIMA
from statsmodels.tsa.statespace.sarimax import SARIMAX
from statsmodels.tsa.holtwinters import ExponentialSmoothing

def prepare_time_series_data(data, column, min_samples=30):
    """
    Prepare time series data for forecasting
    
    Args:
        data: DataFrame with timestamp column
        column: Column name to forecast
        min_samples: Minimum number of samples required
        
    Returns:
        Pandas Series with datetime index or None if insufficient data
    """
    if data.empty or column not in data.columns:
        return None
    
    # Filter out rows with NaN values in the target column
    filtered_data = data[data[column].notna()]
    
    if len(filtered_data) < min_samples:
        return None
    
    # Ensure timestamp is a datetime
    if not pd.api.types.is_datetime64_any_dtype(filtered_data['timestamp']):
        filtered_data['timestamp'] = pd.to_datetime(filtered_data['timestamp'])
    
    # Sort by timestamp
    filtered_data = filtered_data.sort_values('timestamp')
    
    # Create a time series with proper datetime index
    ts_data = filtered_data.set_index('timestamp')[column]
    
    # Resample data to handle irregular time intervals (daily average)
    ts_data = ts_data.resample('D').mean().fillna(method='ffill')
    
    return ts_data

def train_forecast_models(time_series, forecast_days=30):
    """
    Train multiple forecasting models and select the best one
    
    Args:
        time_series: Time series data with datetime index
        forecast_days: Number of days to forecast
        
    Returns:
        Dictionary with forecast results and model information
    """
    if time_series is None:
        return None
    
    results = {}
    models = {}
    forecasts = {}
    errors = {}
    
    # Split data for training and validation
    train_size = int(len(time_series) * 0.8)
    train_data = time_series[:train_size]
    test_data = time_series[train_size:]
    
    # Only proceed if we have enough data
    if len(train_data) < 10 or len(test_data) < 5:
        # Use all data for training if not enough for validation
        train_data = time_series
    
    # Simple Moving Average (last 7 days)
    try:
        # Calculate SMA for the last 7 values (or fewer if not available)
        window = min(7, len(train_data))
        sma_forecast = [train_data[-window:].mean()] * forecast_days
        
        # Create forecast index
        last_date = time_series.index[-1]
        forecast_index = pd.date_range(start=last_date + pd.Timedelta(days=1), periods=forecast_days)
        
        forecasts['SMA'] = pd.Series(sma_forecast, index=forecast_index)
        models['SMA'] = {"name": "Simple Moving Average", "complexity": "Low"}
        
        # Calculate error if we have test data
        if len(test_data) > 0:
            # Use SMA of training data for all test points
            sma_test = [train_data[-window:].mean()] * len(test_data)
            errors['SMA'] = np.mean(np.abs(test_data.values - sma_test))
        else:
            errors['SMA'] = 0  # No validation data
    except Exception as e:
        st.error(f"Error in SMA model: {e}")
    
    # Holt-Winters Exponential Smoothing
    try:
        # Use additive model for now
        hw_model = ExponentialSmoothing(
            train_data,
            trend='add',
            seasonal=None,
            initialization_method="estimated"
        )
        hw_fit = hw_model.fit()
        hw_forecast = hw_fit.forecast(forecast_days)
        
        forecasts['Holt-Winters'] = hw_forecast
        models['Holt-Winters'] = {"name": "Holt-Winters Exponential Smoothing", "complexity": "Medium"}
        
        # Calculate error if we have test data
        if len(test_data) > 0:
            hw_test = hw_fit.forecast(len(test_data))
            errors['Holt-Winters'] = np.mean(np.abs(test_data.values - hw_test.values))
        else:
            errors['Holt-Winters'] = 0  # No validation data
    except Exception as e:
        st.error(f"Error in Holt-Winters model: {e}")
    
    # ARIMA model
    try:
        # Use a simple ARIMA model
        arima_model = ARIMA(train_data, order=(1, 1, 0))
        arima_fit = arima_model.fit()
        arima_forecast = arima_fit.forecast(forecast_days)
        
        forecasts['ARIMA'] = arima_forecast
        models['ARIMA'] = {"name": "ARIMA(1,1,0)", "complexity": "High"}
        
        # Calculate error if we have test data
        if len(test_data) > 0:
            arima_test = arima_fit.forecast(len(test_data))
            errors['ARIMA'] = np.mean(np.abs(test_data.values - arima_test.values))
        else:
            errors['ARIMA'] = 0  # No validation data
    except Exception as e:
        st.error(f"Error in ARIMA model: {e}")
    
    # Select the best model based on validation error if we have test data
    if len(test_data) > 0 and errors:
        # Find model with minimum error
        min_error = float('inf')
        best_model = 'SMA'  # Default
        for model, error in errors.items():
            if error < min_error:
                min_error = error
                best_model = model
    else:
        # Default to simpler model if no validation is possible
        if 'Holt-Winters' in models:
            best_model = 'Holt-Winters'
        else:
            best_model = 'SMA'
    
    # Prepare results
    results = {
        'original_data': time_series,
        'forecasts': forecasts,
        'best_model': best_model,
        'model_info': models,
        'errors': errors
    }
    
    return results

def create_forecast_chart(forecast_results, parameter_name, spec_limits=None):
    """
    Create a forecast chart with historical data and predictions
    
    Args:
        forecast_results: Dictionary with forecast results
        parameter_name: Name of the parameter being forecasted
        spec_limits: Dictionary with 'lsl' and 'usl' keys for specification limits
        
    Returns:
        Plotly figure object
    """
    if forecast_results is None:
        return None
    
    # Extract data
    historical_data = forecast_results['original_data']
    best_model = forecast_results['best_model']
    forecast_data = forecast_results['forecasts'][best_model]
    model_info = forecast_results['model_info'][best_model]
    
    # Create figure
    fig = go.Figure()
    
    # Add historical data
    fig.add_trace(
        go.Scatter(
            x=historical_data.index,
            y=historical_data.values,
            mode='lines+markers',
            name='Historical Data',
            line=dict(color='blue', width=2),
            marker=dict(size=5)
        )
    )
    
    # Add forecast data
    fig.add_trace(
        go.Scatter(
            x=forecast_data.index,
            y=forecast_data.values,
            mode='lines',
            name=f'Forecast ({model_info["name"]})',
            line=dict(color='red', width=2, dash='dash')
        )
    )
    
    # Add confidence interval (simple approximation)
    if forecast_data is not None and len(forecast_data) > 0:
        std_dev = historical_data.std()
        upper_bound = forecast_data.values + 1.96 * std_dev
        lower_bound = forecast_data.values - 1.96 * std_dev
        
        fig.add_trace(
            go.Scatter(
                x=forecast_data.index,
                y=upper_bound,
                mode='lines',
                name='Upper Bound (95%)',
                line=dict(color='rgba(255, 0, 0, 0.2)', width=0),
                showlegend=False
            )
        )
        
        fig.add_trace(
            go.Scatter(
                x=forecast_data.index,
                y=lower_bound,
                mode='lines',
                name='Lower Bound (95%)',
                fill='tonexty',
                fillcolor='rgba(255, 0, 0, 0.1)',
                line=dict(color='rgba(255, 0, 0, 0.2)', width=0),
                showlegend=False
            )
        )
    
    # Add specification limits if provided
    if spec_limits is not None:
        if 'lsl' in spec_limits and spec_limits['lsl'] is not None:
            fig.add_shape(
                type="line",
                x0=historical_data.index[0],
                y0=spec_limits['lsl'],
                x1=forecast_data.index[-1] if len(forecast_data) > 0 else historical_data.index[-1],
                y1=spec_limits['lsl'],
                line=dict(color="red", width=2, dash="dot")
            )
            
            fig.add_annotation(
                x=historical_data.index[0],
                y=spec_limits['lsl'],
                text="LSL",
                showarrow=False,
                yshift=10
            )
        
        if 'usl' in spec_limits and spec_limits['usl'] is not None:
            fig.add_shape(
                type="line",
                x0=historical_data.index[0],
                y0=spec_limits['usl'],
                x1=forecast_data.index[-1] if len(forecast_data) > 0 else historical_data.index[-1],
                y1=spec_limits['usl'],
                line=dict(color="red", width=2, dash="dot")
            )
            
            fig.add_annotation(
                x=historical_data.index[0],
                y=spec_limits['usl'],
                text="USL",
                showarrow=False,
                yshift=-10
            )
    
    # Update layout
    fig.update_layout(
        title=f"{parameter_name} Forecast",
        xaxis_title="Date",
        yaxis_title=parameter_name,
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=40, r=40, t=60, b=40),
        height=500
    )
    
    return fig

def analyze_forecast_trends(forecast_results, spec_limits=None):
    """
    Analyze forecast trends and generate insights
    
    Args:
        forecast_results: Dictionary with forecast results
        spec_limits: Dictionary with 'lsl' and 'usl' keys for specification limits
        
    Returns:
        Dictionary with trend insights
    """
    if forecast_results is None:
        return None
    
    # Extract data
    historical_data = forecast_results['original_data']
    best_model = forecast_results['best_model']
    forecast_data = forecast_results['forecasts'][best_model]
    
    # Calculate basic statistics
    historical_mean = historical_data.mean()
    historical_std = historical_data.std()
    forecast_mean = forecast_data.mean()
    forecast_std = forecast_data.std()
    
    # Calculate trend direction
    trend_direction = "stable"
    percent_change = ((forecast_mean - historical_mean) / historical_mean) * 100
    
    if percent_change > 5:
        trend_direction = "increasing"
    elif percent_change < -5:
        trend_direction = "decreasing"
    
    # Check for out-of-spec predictions
    out_of_spec = False
    out_of_spec_days = 0
    
    if spec_limits is not None:
        if 'lsl' in spec_limits and spec_limits['lsl'] is not None:
            below_spec = (forecast_data < spec_limits['lsl']).sum()
            out_of_spec_days += below_spec
            if below_spec > 0:
                out_of_spec = True
        
        if 'usl' in spec_limits and spec_limits['usl'] is not None:
            above_spec = (forecast_data > spec_limits['usl']).sum()
            out_of_spec_days += above_spec
            if above_spec > 0:
                out_of_spec = True
    
    # Calculate stability
    cv_historical = (historical_std / historical_mean) * 100 if historical_mean != 0 else 0
    cv_forecast = (forecast_std / forecast_mean) * 100 if forecast_mean != 0 else 0
    
    stability_change = cv_forecast - cv_historical
    stability_trend = "stable"
    
    if stability_change > 10:
        stability_trend = "more variable"
    elif stability_change < -10:
        stability_trend = "more stable"
    
    # Generate insights
    insights = {
        "trend_direction": trend_direction,
        "percent_change": percent_change,
        "out_of_spec": out_of_spec,
        "out_of_spec_days": out_of_spec_days,
        "stability_trend": stability_trend,
        "forecast_mean": forecast_mean,
        "historical_mean": historical_mean,
        "forecast_std": forecast_std,
        "historical_std": historical_std,
        "forecast_length": len(forecast_data)
    }
    
    return insights

def display_forecast_insights(insights, parameter_name, spec_limits=None):
    """
    Display forecast insights in a formatted way
    
    Args:
        insights: Dictionary with trend insights
        parameter_name: Name of the parameter being forecasted
        spec_limits: Dictionary with 'lsl' and 'usl' keys for specification limits
    """
    if insights is None:
        st.warning("Insufficient data for generating insights.")
        return
    
    # Create columns for metrics
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric(
            "Trend Direction", 
            insights["trend_direction"].capitalize(),
            f"{insights['percent_change']:.1f}%"
        )
    
    with col2:
        st.metric(
            "Forecast Mean", 
            f"{insights['forecast_mean']:.2f}",
            f"{insights['forecast_mean'] - insights['historical_mean']:.2f}"
        )
    
    with col3:
        if spec_limits is not None and insights["out_of_spec"]:
            st.metric(
                "Out of Spec Days", 
                f"{insights['out_of_spec_days']} days",
                delta_color="inverse"
            )
        else:
            st.metric(
                "Stability Trend", 
                insights["stability_trend"].capitalize()
            )
    
    # Add interpretation
    st.subheader("Forecast Interpretation")
    
    trend_interpretation = f"The {parameter_name} value is predicted to "
    if insights["trend_direction"] == "increasing":
        trend_interpretation += f"**increase by {insights['percent_change']:.1f}%** over the forecast period."
    elif insights["trend_direction"] == "decreasing":
        trend_interpretation += f"**decrease by {abs(insights['percent_change']):.1f}%** over the forecast period."
    else:
        trend_interpretation += "**remain stable** over the forecast period."
    
    st.markdown(trend_interpretation)
    
    # Add stability interpretation
    stability_interpretation = "The process is expected to be "
    if insights["stability_trend"] == "more variable":
        stability_interpretation += "**more variable** than historical data, which may indicate developing process issues."
    elif insights["stability_trend"] == "more stable":
        stability_interpretation += "**more stable** than historical data, suggesting process improvements."
    else:
        stability_interpretation += "**similarly stable** to historical patterns."
    
    st.markdown(stability_interpretation)
    
    # Add spec limit interpretation if applicable
    if spec_limits is not None:
        if insights["out_of_spec"]:
            spec_interpretation = f"⚠️ **Warning:** The forecast predicts {insights['out_of_spec_days']} days where {parameter_name} may be out of specification limits."
            
            if 'lsl' in spec_limits and 'usl' in spec_limits:
                spec_interpretation += f" (LSL: {spec_limits['lsl']}, USL: {spec_limits['usl']})"
            
            st.markdown(spec_interpretation)
            
            st.markdown("**Recommended Action:** Consider adjusting process parameters or implementing preventive maintenance to avoid out-of-specification conditions.")
        else:
            st.markdown("✅ The forecast predicts all values will remain within specification limits.")

def display_prediction_page():
    """
    Display the prediction analysis page
    """
    st.title("Trend Prediction Analysis")
    
    st.markdown("""
    This tool uses advanced statistical models to predict future trends in your quality metrics.
    The system automatically selects the best forecasting model based on your historical data.
    """)
    
    # Filter controls
    col1, col2 = st.columns(2)
    
    with col1:
        date_range = st.date_input(
            "Historical Data Range",
            [dt.datetime.now() - dt.timedelta(days=90), dt.datetime.now()],
            max_value=dt.datetime.now()
        )
    
    with col2:
        product_filter = st.multiselect(
            "Filter by Product",
            ["All", "Blackberry", "Raspberry", "Cream Soda", "Mazoe Orange Crush", "Bonaqua Water", "Schweppes Still Water"],
            default=["All"]
        )
    
    # Get data based on filters
    start_date, end_date = date_range
    end_date = dt.datetime.combine(end_date, dt.time(23, 59, 59))
    
    with st.spinner("Loading data..."):
        data = get_check_data(start_date, end_date, product_filter)
    
    if data.empty:
        st.warning("No data available for the selected filters. Please adjust the date range or product filter.")
        return
    
    # Select parameter for forecasting
    forecast_params = {
        "brix": {
            "name": "BRIX",
            "spec_limits": {"lsl": 8.0, "usl": 9.5}
        },
        "head1_torque": {
            "name": "Torque (Head 1)",
            "spec_limits": {"lsl": 5.0, "usl": 12.0}
        },
        "head2_torque": {
            "name": "Torque (Head 2)",
            "spec_limits": {"lsl": 5.0, "usl": 12.0}
        },
        "head3_torque": {
            "name": "Torque (Head 3)",
            "spec_limits": {"lsl": 5.0, "usl": 12.0}
        },
        "head4_torque": {
            "name": "Torque (Head 4)",
            "spec_limits": {"lsl": 5.0, "usl": 12.0}
        },
        "head5_torque": {
            "name": "Torque (Head 5)",
            "spec_limits": {"lsl": 5.0, "usl": 12.0}
        },
        "titration_acid": {
            "name": "Titration Acid",
            "spec_limits": {"lsl": None, "usl": None}
        },
        "density": {
            "name": "Density",
            "spec_limits": {"lsl": None, "usl": None}
        }
    }
    
    # Filter to show only parameters that exist in the data
    available_params = [param for param in forecast_params.keys() if param in data.columns]
    
    if not available_params:
        st.warning("No suitable parameters found in the data for forecasting.")
        return
    
    selected_param = st.selectbox(
        "Select Parameter to Forecast",
        available_params,
        format_func=lambda x: forecast_params[x]["name"]
    )
    
    forecast_days = st.slider(
        "Forecast Horizon (Days)",
        min_value=7,
        max_value=90,
        value=30,
        step=1,
        help="Number of days to forecast into the future"
    )
    
    # Create forecast
    if st.button("Generate Forecast", type="primary"):
        with st.spinner("Analyzing data and generating forecast..."):
            # Prepare time series data
            ts_data = prepare_time_series_data(data, selected_param)
            
            if ts_data is None or len(ts_data) < 10:
                st.error(f"Insufficient data for forecasting {forecast_params[selected_param]['name']}. Need at least 10 data points.")
                return
            
            # Train models and generate forecast
            forecast_results = train_forecast_models(ts_data, forecast_days)
            
            if forecast_results is None:
                st.error("Failed to generate forecast. Try adjusting the date range or selecting a different parameter.")
                return
            
            # Display forecast chart
            st.subheader(f"{forecast_params[selected_param]['name']} Forecast")
            
            forecast_chart = create_forecast_chart(
                forecast_results, 
                forecast_params[selected_param]["name"],
                forecast_params[selected_param]["spec_limits"]
            )
            
            st.plotly_chart(forecast_chart, use_container_width=True)
            
            # Generate and display insights
            insights = analyze_forecast_trends(
                forecast_results,
                forecast_params[selected_param]["spec_limits"]
            )
            
            st.subheader("Forecast Insights")
            
            display_forecast_insights(
                insights,
                forecast_params[selected_param]["name"],
                forecast_params[selected_param]["spec_limits"]
            )
            
            # Display model information
            with st.expander("Model Information"):
                best_model = forecast_results['best_model']
                model_info = forecast_results['model_info'][best_model]
                
                st.markdown(f"""
                **Selected Model:** {model_info['name']}  
                **Model Complexity:** {model_info['complexity']}  
                **Historical Data Points:** {len(forecast_results['original_data'])}  
                **Forecast Period:** {forecast_days} days
                """)
                
                if 'errors' in forecast_results and forecast_results['errors']:
                    st.markdown("**Model Comparison (Mean Absolute Error):**")
                    for model, error in forecast_results['errors'].items():
                        if error > 0:  # Only show models with validation
                            st.markdown(f"- {model}: {error:.4f}")
                
                st.markdown("""
                **Note:** The system automatically selects the best forecasting model based on your data 
                characteristics and validation error.
                """)
    
    # Educational information
    with st.expander("About Trend Prediction"):
        st.markdown("""
        ### How Trend Prediction Works
        
        This feature uses time series forecasting techniques to predict future values of quality metrics based on 
        historical patterns. The system automatically evaluates multiple forecasting models and selects the best 
        one for your specific data.
        
        **Models used:**
        
        1. **Simple Moving Average (SMA)** - Uses the average of recent values to forecast future values.
           Works well for stable processes with little trend or seasonality.
        
        2. **Holt-Winters Exponential Smoothing** - A more sophisticated approach that can capture trends 
           in the data. It gives more weight to recent observations.
        
        3. **ARIMA (AutoRegressive Integrated Moving Average)** - A comprehensive statistical model that can 
           capture complex patterns in time series data.
        
        ### Using Forecast Insights
        
        The forecast insights can help you:
        
        - **Plan production adjustments** before quality metrics drift out of specification
        - **Schedule preventive maintenance** when trends indicate potential issues
        - **Optimize resource allocation** based on predicted quality performance
        - **Reduce quality incidents** by taking proactive action on predicted issues
        
        ### Interpretation Guidelines
        
        - A **strong trend** (>10% change) suggests systematic shifts in your process
        - **Increasing variability** may indicate developing equipment issues or process instability
        - **Out-of-spec predictions** require immediate attention and preventive action
        - **Stable forecasts** within specification limits indicate a well-controlled process
        """)