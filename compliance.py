import streamlit as st
import pandas as pd
import datetime as dt
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import io
import base64
from database import BeverageQADatabase  # Updated import
from capability import calculate_process_capability
from spc import calculate_control_limits
from utils import format_timestamp

# Initialize database connection
db = BeverageQADatabase()

def generate_compliance_report(start_date, end_date, product_filter=None, report_type="GMP", facility_name=None, report_number=None):
    """
    Generate a comprehensive compliance report
    
    Args:
        start_date: Start date for report data
        end_date: End date for report data
        product_filter: Optional product filter
        report_type: Type of compliance report (GMP, ISO, etc.)
        facility_name: Optional facility name
        report_number: Optional report number for tracking
        
    Returns:
        DataFrame with report data and metadata
    """
    # Get data for the reporting period using the class method
    data = db.get_check_data(
        start_date=start_date,
        end_date=end_date,
        product_filter=product_filter if product_filter != ["All"] else None
    )
    
    if data.empty:
        return None
    
    # Generate a report number if not provided
    if report_number is None:
        report_number = f"CR-{dt.datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    # Set default facility name if not provided
    if facility_name is None:
        facility_name = "Main Production Facility"
    
    # Create report metadata
    report_metadata = {
        "report_number": report_number,
        "report_type": report_type,
        "facility_name": facility_name,
        "report_date": dt.datetime.now(),
        "report_period_start": start_date,
        "report_period_end": end_date,
        "generated_by": st.session_state.username if 'username' in st.session_state else "System",
        "products_covered": ", ".join(data['product'].dropna().unique()) if 'product' in data.columns else "All"
    }
    
    # Summarize data by check type
    check_summary = pd.DataFrame()
    
    if 'check_type' in data.columns:
        check_summary = data.groupby('check_type').agg({
            'check_id': 'count',
            'username': 'nunique'
        }).reset_index()
        
        check_summary.columns = ['Check Type', 'Number of Checks', 'Number of Inspectors']
    
    # Calculate compliance metrics
    compliance_metrics = {
        "total_checks": len(data),
        "total_inspectors": data['username'].nunique() if 'username' in data.columns else 0,
        "out_of_spec_count": 0,
        "compliance_rate": 100.0
    }
    
    # Check for out-of-spec measurements
    out_of_spec_count = 0
    
    # Check torque values (should be between 5-12)
    for head in ['head1_torque', 'head2_torque', 'head3_torque', 'head4_torque', 'head5_torque']:
        if head in data.columns:
            out_of_spec_count += ((data[head] < 5) | (data[head] > 12)).sum()
    
    # Check tamper evidence
    if 'tamper_evidence' in data.columns:
        out_of_spec_count += data['tamper_evidence'].str.contains('FAIL').sum()
    
    # Check other quality parameters (just examples)
    quality_checks = ['label_application', 'torque_test', 'pallet_check', 'date_code', 
                     'appearance', 'product_taste', 'filler_height', 'bottle_check']
    
    for check in quality_checks:
        if check in data.columns:
            out_of_spec_count += data[check].isin(['Not OK', 'FAIL', 'Not To Std']).sum()
    
    compliance_metrics["out_of_spec_count"] = out_of_spec_count
    
    # Calculate compliance rate
    if compliance_metrics["total_checks"] > 0:
        potential_issues = compliance_metrics["total_checks"] * 10  # Assuming 10 checkpoints per check on average
        issues_found = compliance_metrics["out_of_spec_count"]
        compliance_metrics["compliance_rate"] = 100 * (1 - (issues_found / potential_issues))
    
    # Create a results dictionary with all report components
    report_results = {
        "metadata": report_metadata,
        "compliance_metrics": compliance_metrics,
        "check_summary": check_summary,
        "raw_data": data
    }
    
    return report_results

def create_compliance_summary_chart(compliance_metrics, data):
    """Display a summary compliance report"""
    st.subheader("Compliance Summary Report")
    
    # Calculate basic statistics
    total_checks = len(data)
    unique_products = data['product'].nunique() if 'product' in data.columns else 0
    unique_inspectors = data['username'].nunique()
    
    # Display summary metrics
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Checks", total_checks)
    with col2:
        st.metric("Unique Products", unique_products)
    with col3:
        st.metric("Unique Inspectors", unique_inspectors)
    
    # Product distribution
    if 'product' in data.columns:
        st.markdown("#### Product Distribution")
        product_counts = data['product'].value_counts().reset_index()
        product_counts.columns = ['Product', 'Count']
        st.bar_chart(product_counts.set_index('Product'))
    
    # Check type distribution
    if 'source' in data.columns:
        st.markdown("#### Check Type Distribution")
        check_type_counts = data['source'].value_counts().reset_index()
        check_type_counts.columns = ['Check Type', 'Count']
        st.bar_chart(check_type_counts.set_index('Check Type'))

def display_detailed_report(data):
    """Display a detailed compliance report"""
    st.subheader("Detailed Compliance Report")
    
    # Show all checks in a table
    st.dataframe(data, use_container_width=True)
    
    # Add download button
    csv = data.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="Download as CSV",
        data=csv,
        file_name="compliance_report.csv",
        mime="text/csv"
    )

def display_non_compliance_report(data):
    """Display a report of non-compliant checks"""
    st.subheader("Non-Compliance Report")
    
    # Identify non-compliant checks
    non_compliant = pd.DataFrame()
    
    # Check for torque issues
    if 'source' in data.columns and 'torque_tamper' in data['source'].values:
        torque_data = data[data['source'] == 'torque_tamper']
        for head in ['head1_torque', 'head2_torque', 'head3_torque', 'head4_torque', 'head5_torque']:
            if head in torque_data.columns:
                out_of_spec = torque_data[
                    (torque_data[head] < 5) | (torque_data[head] > 12)
                ]
                if not out_of_spec.empty:
                    non_compliant = pd.concat([non_compliant, out_of_spec])
    
    # Check for tamper evidence issues
    if 'tamper_evidence' in data.columns:
        tamper_issues = data[data['tamper_evidence'] == 'FAIL']
        if not tamper_issues.empty:
            non_compliant = pd.concat([non_compliant, tamper_issues])
    
    # Check for quality check issues
    quality_params = [
        'label_application', 'torque_test', 'pallet_check', 
        'date_code', 'odour', 'appearance', 'product_taste',
        'filler_height', 'bottle_check', 'bottle_seams',
        'container_rinse_inspection', 'container_rinse_water_odour'
    ]
    
    for param in quality_params:
        if param in data.columns:
            issues = data[data[param] == 'Not OK']
            if not issues.empty:
                non_compliant = pd.concat([non_compliant, issues])
    
    if non_compliant.empty:
        st.success("No non-compliant checks found!")
    else:
        st.dataframe(non_compliant, use_container_width=True)
        
        # Add download button
        csv = non_compliant.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="Download Non-Compliant Checks",
            data=csv,
            file_name="non_compliant_checks.csv",
            mime="text/csv"
        )

def display_compliance_metrics_section(compliance_metrics, data):
    """
    Display compliance metrics in a formatted section
    
    Args:
        compliance_metrics: Dictionary with compliance metrics
    """
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Total Quality Checks", compliance_metrics["total_checks"])
    
    with col2:
        st.metric("Out of Specification Findings", compliance_metrics["out_of_spec_count"])
    
    with col3:
        st.metric("Total Inspectors", compliance_metrics["total_inspectors"])
    
    # Display compliance rate chart
    compliance_chart = create_compliance_summary_chart(compliance_metrics)
    st.plotly_chart(compliance_chart, use_container_width=True)
    
    # Add compliance rate interpretation
    compliance_rate = compliance_metrics["compliance_rate"]
    
    if compliance_rate >= 95:
        st.success(f"✅ Excellent compliance rate of {compliance_rate:.1f}%. Process is under control and compliant with requirements.")
    elif compliance_rate >= 90:
        st.success(f"✅ Good compliance rate of {compliance_rate:.1f}%. Minor improvements may be needed.")
    elif compliance_rate >= 80:
        st.warning(f"⚠️ Marginal compliance rate of {compliance_rate:.1f}%. Process needs improvement.")
    else:
        st.error(f"❌ Poor compliance rate of {compliance_rate:.1f}%. Immediate corrective action is required.")

def create_process_capability_section(data):
    """
    Create a process capability summary section
    
    Args:
        data: DataFrame with quality data
        
    Returns:
        Plotly figure object with capability summaries
    """
    # Parameters to check capability
    capability_params = {
        'brix': {'lsl': 8.0, 'usl': 9.5, 'title': 'BRIX'},
        'head1_torque': {'lsl': 5.0, 'usl': 12.0, 'title': 'Torque Head 1'},
        'head2_torque': {'lsl': 5.0, 'usl': 12.0, 'title': 'Torque Head 2'},
        'head3_torque': {'lsl': 5.0, 'usl': 12.0, 'title': 'Torque Head 3'},
        'head4_torque': {'lsl': 5.0, 'usl': 12.0, 'title': 'Torque Head 4'},
        'head5_torque': {'lsl': 5.0, 'usl': 12.0, 'title': 'Torque Head 5'}
    }
    
    # Create subplots for capability summary
    fig = make_subplots(
        rows=len(capability_params), 
        cols=1,
        subplot_titles=[params['title'] for param, params in capability_params.items()],
        vertical_spacing=0.05
    )
    
    row = 1
    capability_results = {}
    
    for param, specs in capability_params.items():
        if param in data.columns and data[param].notna().sum() >= 10:
            # Calculate capability
            cap = calculate_process_capability(
                data, 
                param, 
                specs['lsl'], 
                specs['usl']
            )
            
            capability_results[param] = cap
            
            # Create mini histogram
            values = data[param].dropna()
            
            # Add histogram
            fig.add_trace(
                go.Histogram(
                    x=values,
                    histnorm='probability density',
                    name=f"{param} Distribution",
                    marker=dict(color='lightblue'),
                    opacity=0.7,
                    showlegend=False
                ),
                row=row, col=1
            )
            
            # Add mean line
            if cap['mean'] is not None:
                fig.add_vline(
                    x=cap['mean'], 
                    line_width=2, 
                    line_dash="solid", 
                    line_color="green",
                    row=row, col=1
                )
            
            # Add specification limits
            if specs['lsl'] is not None:
                fig.add_vline(
                    x=specs['lsl'], 
                    line_width=2, 
                    line_dash="dash", 
                    line_color="red",
                    row=row, col=1
                )
            
            if specs['usl'] is not None:
                fig.add_vline(
                    x=specs['usl'], 
                    line_width=2, 
                    line_dash="dash", 
                    line_color="red",
                    row=row, col=1
                )
            
            # Update subplot title with Cpk value
            if cap['cpk'] is not None:
                current_title = fig.layout.annotations[row-1].text
                fig.layout.annotations[row-1].text = f"{current_title} (Cpk: {cap['cpk']:.2f})"
        
        row += 1
    
    # Update layout
    fig.update_layout(
        height=150 * len(capability_params),
        margin=dict(l=50, r=50, t=30, b=20),
        showlegend=False
    )
    
    return fig, capability_results

def generate_gmp_report_doc(report_data):
    """
    Generate a GMP compliance report document
    
    Args:
        report_data: Dictionary with report components
        
    Returns:
        HTML report content
    """
    metadata = report_data["metadata"]
    metrics = report_data["compliance_metrics"]
    check_summary = report_data["check_summary"]
    data = report_data["raw_data"]
    
    # Start HTML report
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>GMP Compliance Report</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                margin: 20px;
                color: #333;
            }}
            .header {{
                text-align: center;
                border-bottom: 2px solid #ddd;
                padding-bottom: 10px;
                margin-bottom: 20px;
            }}
            .section {{
                margin-bottom: 30px;
            }}
            .section-title {{
                background-color: #f0f0f0;
                padding: 5px 10px;
                border-left: 4px solid #0066cc;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
                margin-bottom: 20px;
            }}
            th, td {{
                border: 1px solid #ddd;
                padding: 8px;
                text-align: left;
            }}
            th {{
                background-color: #f0f0f0;
            }}
            tr:nth-child(even) {{
                background-color: #f9f9f9;
            }}
            .metrics {{
                display: flex;
                justify-content: space-between;
                margin-bottom: 20px;
            }}
            .metric-card {{
                width: 30%;
                border: 1px solid #ddd;
                border-radius: 5px;
                padding: 10px;
                text-align: center;
            }}
            .metric-value {{
                font-size: 24px;
                font-weight: bold;
                color: #0066cc;
            }}
            .metric-label {{
                font-size: 14px;
                color: #666;
            }}
            .footer {{
                margin-top: 30px;
                border-top: 1px solid #ddd;
                padding-top: 10px;
                font-size: 12px;
                color: #666;
                text-align: center;
            }}
            .approval {{
                margin-top: 50px;
                display: flex;
                justify-content: space-between;
            }}
            .signature {{
                width: 30%;
                border-top: 1px solid #333;
                padding-top: 5px;
                text-align: center;
            }}
            .compliance-rating {{
                font-size: 18px;
                font-weight: bold;
                padding: 10px;
                border-radius: 5px;
                text-align: center;
                margin: 20px 0;
            }}
            .excellent {{
                background-color: #d4edda;
                color: #155724;
            }}
            .good {{
                background-color: #d4edda;
                color: #155724;
            }}
            .marginal {{
                background-color: #fff3cd;
                color: #856404;
            }}
            .poor {{
                background-color: #f8d7da;
                color: #721c24;
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>GMP Compliance Report</h1>
            <h3>{metadata["facility_name"]}</h3>
            <p>Report Number: {metadata["report_number"]}</p>
            <p>Period: {metadata["report_period_start"].strftime('%Y-%m-%d')} to {metadata["report_period_end"].strftime('%Y-%m-%d')}</p>
        </div>
        
        <div class="section">
            <h2 class="section-title">Report Information</h2>
            <table>
                <tr>
                    <th>Report Date:</th>
                    <td>{metadata["report_date"].strftime('%Y-%m-%d %H:%M:%S')}</td>
                    <th>Generated By:</th>
                    <td>{metadata["generated_by"]}</td>
                </tr>
                <tr>
                    <th>Compliance Standard:</th>
                    <td>Good Manufacturing Practice (GMP)</td>
                    <th>Products Covered:</th>
                    <td>{metadata["products_covered"]}</td>
                </tr>
            </table>
        </div>
        
        <div class="section">
            <h2 class="section-title">Compliance Summary</h2>
            
            <div class="metrics">
                <div class="metric-card">
                    <div class="metric-value">{metrics["total_checks"]}</div>
                    <div class="metric-label">Total Quality Checks</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value">{metrics["out_of_spec_count"]}</div>
                    <div class="metric-label">Out of Specification Findings</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value">{metrics["total_inspectors"]}</div>
                    <div class="metric-label">Quality Inspectors</div>
                </div>
            </div>
    """
    
    # Add compliance rating
    compliance_rate = metrics["compliance_rate"]
    rating_class = ""
    rating_text = ""
    
    if compliance_rate >= 95:
        rating_class = "excellent"
        rating_text = f"Excellent compliance rate of {compliance_rate:.1f}%. Process is under control and compliant with GMP requirements."
    elif compliance_rate >= 90:
        rating_class = "good"
        rating_text = f"Good compliance rate of {compliance_rate:.1f}%. Minor improvements may be needed to achieve full GMP compliance."
    elif compliance_rate >= 80:
        rating_class = "marginal"
        rating_text = f"Marginal compliance rate of {compliance_rate:.1f}%. Process improvements needed to achieve GMP compliance."
    else:
        rating_class = "poor"
        rating_text = f"Poor compliance rate of {compliance_rate:.1f}%. Significant improvements required to meet GMP standards."
    
    html_content += f"""
            <div class="compliance-rating {rating_class}">
                {rating_text}
            </div>
    """
    
    # Add check summary if available
    if not check_summary.empty:
        html_content += """
        <div class="section">
            <h2 class="section-title">Quality Check Summary</h2>
            <table>
                <tr>
                    <th>Check Type</th>
                    <th>Number of Checks</th>
                    <th>Number of Inspectors</th>
                </tr>
        """
        
        for _, row in check_summary.iterrows():
            html_content += f"""
                <tr>
                    <td>{row['Check Type']}</td>
                    <td>{row['Number of Checks']}</td>
                    <td>{row['Number of Inspectors']}</td>
                </tr>
            """
        
        html_content += """
            </table>
        </div>
        """
    
    # Add observations and findings
    html_content += """
        <div class="section">
            <h2 class="section-title">Key Observations & Findings</h2>
    """
    
    # Add quality issues summary
    html_content += """
            <h3>Quality Issues</h3>
            <table>
                <tr>
                    <th>Issue Type</th>
                    <th>Occurrences</th>
                    <th>Impact Level</th>
                </tr>
    """
    
    # Check for specific quality issues
    quality_issues = []
    
    # Torque issues
    torque_cols = ['head1_torque', 'head2_torque', 'head3_torque', 'head4_torque', 'head5_torque']
    torque_issues = 0
    for col in torque_cols:
        if col in data.columns:
            torque_issues += ((data[col] < 5) | (data[col] > 12)).sum()
    
    if torque_issues > 0:
        impact = "High" if torque_issues > metrics["total_checks"] * 0.1 else "Medium"
        quality_issues.append(("Torque Out of Range", torque_issues, impact))
    
    # Tamper evidence issues
    if 'tamper_evidence' in data.columns:
        tamper_issues = data['tamper_evidence'].str.contains('FAIL').sum()
        if tamper_issues > 0:
            impact = "Critical" if tamper_issues > 0 else "Low"
            quality_issues.append(("Tamper Evidence Failures", tamper_issues, impact))
    
    # Other quality issues
    issue_mapping = [
        ('label_application', 'Not OK', 'Label Issues', 'Medium'),
        ('torque_test', 'FAIL', 'Torque Test Issues', 'High'),
        ('pallet_check', 'Not OK', 'Pallet Issues', 'Low'),
        ('date_code', 'Not OK', 'Date Code Issues', 'Medium'),
        ('odour', 'Bad Odour', 'Odour Issues', 'High'),
        ('appearance', 'Not To Std', 'Appearance Issues', 'Medium'),
        ('product_taste', 'Not To Std', 'Taste Issues', 'Critical'),
        ('filler_height', 'Not To Std', 'Filler Height Issues', 'Medium')
    ]
    
    for col, fail_value, issue_name, impact in issue_mapping:
        if col in data.columns:
            issue_count = (data[col] == fail_value).sum()
            if issue_count > 0:
                quality_issues.append((issue_name, issue_count, impact))
    
    # If no issues found
    if not quality_issues:
        html_content += """
                <tr>
                    <td colspan="3">No significant quality issues detected in this reporting period.</td>
                </tr>
        """
    else:
        for issue, count, impact in quality_issues:
            impact_color = {
                "Low": "#e1f5fe",
                "Medium": "#fff9c4",
                "High": "#ffccbc",
                "Critical": "#ffcdd2"
            }.get(impact, "#ffffff")
            
            html_content += f"""
                <tr>
                    <td>{issue}</td>
                    <td>{count}</td>
                    <td style="background-color: {impact_color}">{impact}</td>
                </tr>
            """
    
    html_content += """
            </table>
        </div>
    """
    
    # Add compliance recommendations
    html_content += """
        <div class="section">
            <h2 class="section-title">Compliance Recommendations</h2>
            <ol>
    """
    
    # Generate recommendations based on issues
    recommendations = []
    
    if torque_issues > 0:
        recommendations.append("Review torque application equipment calibration and maintenance records")
    
    if 'tamper_evidence' in data.columns and data['tamper_evidence'].str.contains('FAIL').sum() > 0:
        recommendations.append("Investigate tamper evidence failures and improve application process")
    
    # Add standard recommendations
    standard_recommendations = [
        "Ensure all operators have completed required GMP training",
        "Verify all documentation is being properly completed and archived",
        "Implement regular quality circles to discuss improvement opportunities",
        "Review cleaning and sanitation procedures",
        "Ensure calibration of all quality measuring devices is up-to-date"
    ]
    
    all_recommendations = recommendations + [rec for rec in standard_recommendations if rec not in recommendations]
    
    for rec in all_recommendations:
        html_content += f"""
                <li>{rec}</li>
        """
    
    html_content += """
            </ol>
        </div>
    """
    
    # Add approval section
    html_content += """
        <div class="section">
            <h2 class="section-title">Report Approval</h2>
            <div class="approval">
                <div class="signature">
                    <p>Quality Manager</p>
                    <p>Date: _______________</p>
                </div>
                <div class="signature">
                    <p>Production Manager</p>
                    <p>Date: _______________</p>
                </div>
                <div class="signature">
                    <p>Compliance Officer</p>
                    <p>Date: _______________</p>
                </div>
            </div>
        </div>
    """
    
    # Add footer
    html_content += f"""
        <div class="footer">
            <p>Generated by Beverage QA Tracker on {metadata["report_date"].strftime('%Y-%m-%d %H:%M:%S')}</p>
            <p>Report Number: {metadata["report_number"]}</p>
        </div>
    </body>
    </html>
    """
    
    return html_content

def get_html_download_link(html_content, filename="compliance_report.html"):
    """
    Generate a download link for HTML content
    
    Args:
        html_content: HTML content to download
        filename: Name of the file to download
    
    Returns:
        HTML link for downloading the content
    """
    b64 = base64.b64encode(html_content.encode()).decode()
    
    # Create download link
    href = f'<a href="data:text/html;base64,{b64}" download="{filename}">Download Compliance Report</a>'
    
    return href

def display_compliance_report_page():
    """
    Display the compliance report generation page
    """
    st.title("Compliance Report Generator")
    
    st.markdown("""
    Generate comprehensive compliance reports for regulatory purposes. These reports provide evidence of 
    quality control practices and help demonstrate adherence to standards like GMP and ISO 9001.
    """)
    
    # Report configuration
    st.subheader("Report Configuration")
    
    col1, col2 = st.columns(2)
    
    with col1:
        report_type = st.selectbox(
            "Compliance Standard",
            ["GMP", "ISO 9001:2017", "FSSC 22000", "Custom"]
        )
        
        if report_type == "Custom":
            custom_standard = st.text_input("Custom Standard Name")
    
    with col2:
        facility_name = st.text_input("Facility Name", "Main Production Facility")
    
    # Report period
    col1, col2 = st.columns(2)
    
    with col1:
        report_period = st.selectbox(
            "Report Period",
            ["Last Month", "Last Quarter", "Last Year", "Custom Period"]
        )
    
    with col2:
        if report_period == "Custom Period":
            date_range = st.date_input(
                "Select Date Range",
                [dt.datetime.now() - dt.timedelta(days=30), dt.datetime.now()],
                max_value=dt.datetime.now()
            )
            start_date, end_date = date_range
        else:
            end_date = dt.datetime.now().date()
            
            if report_period == "Last Month":
                start_date = end_date - dt.timedelta(days=30)
            elif report_period == "Last Quarter":
                start_date = end_date - dt.timedelta(days=90)
            else:  # Last Year
                start_date = end_date - dt.timedelta(days=365)
                
            st.info(f"Report will cover from {start_date} to {end_date}")
    
    # Product filter
    product_filter = st.multiselect(
        "Filter by Product",
        ["All", "Blackberry", "Raspberry", "Cream Soda", "Mazoe Orange Crush", "Bonaqua Water", "Schweppes Still Water"],
        default=["All"]
    )
    
    # Report number
    report_number = st.text_input(
        "Report Number", 
        f"CR-{dt.datetime.now().strftime('%Y%m%d%H%M')}"
    )
    
    # Generate report button
    if st.button("Generate Compliance Report", type="primary"):
        with st.spinner("Generating compliance report..."):
            # Generate report data
            report_data = generate_compliance_report(
                start_date, 
                end_date, 
                product_filter if "All" not in product_filter else None, 
                report_type,
                facility_name,
                report_number
            )
            
            if report_data is None or report_data["raw_data"].empty:
                st.error("No data available for the selected period. Cannot generate report.")
            else:
                # Display report preview
                st.subheader("Compliance Report Preview")
                
                # Report metadata
                st.markdown(f"""
                **Report Number:** {report_data['metadata']['report_number']}  
                **Facility:** {report_data['metadata']['facility_name']}  
                **Period:** {report_data['metadata']['report_period_start'].strftime('%Y-%m-%d')} to {report_data['metadata']['report_period_end'].strftime('%Y-%m-%d')}  
                **Generated By:** {report_data['metadata']['generated_by']}  
                **Products Covered:** {report_data['metadata']['products_covered']}
                """)
                
                # Compliance metrics
                st.subheader("Compliance Metrics")
                display_compliance_metrics_section(report_data["compliance_metrics"])
                
                # Check summary
                if not report_data["check_summary"].empty:
                    st.subheader("Quality Check Summary")
                    st.dataframe(report_data["check_summary"], use_container_width=True)
                
                # Process capability summary
                st.subheader("Process Capability Summary")
                capability_fig, capability_results = create_process_capability_section(report_data["raw_data"])
                st.plotly_chart(capability_fig, use_container_width=True)
                
                # Generate downloadable report
                st.subheader("Download Full Report")
                
                # Generate HTML report
                html_report = generate_gmp_report_doc(report_data)
                
                # Create download link
                report_filename = f"{report_type}_{report_number}_{dt.datetime.now().strftime('%Y%m%d')}.html"
                download_link = get_html_download_link(html_report, report_filename)
                
                st.markdown(download_link, unsafe_allow_html=True)
                
                st.success("Report generated successfully. Click the link above to download.")
                
                # Report guidance
                with st.expander("Report Usage Instructions"):
                    st.markdown("""
                    ### Using This Compliance Report
                    
                    - **Regulatory Submissions**: Include this report in regulatory submissions to demonstrate GMP compliance
                    - **Audit Preparation**: Use for audit preparation and during actual audits as evidence of quality controls
                    - **Internal Reviews**: Share with management for internal quality reviews and decision making
                    - **Continuous Improvement**: Identify trends and opportunities for process improvements
                    
                    **Note**: This report includes electronic signatures. If required by your regulatory framework, 
                    print and obtain physical signatures from the required personnel.
                    """)