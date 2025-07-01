import streamlit as st
import pandas as pd
import datetime as dt
import io
import base64
from database import BeverageQADatabase  # Updated import
from utils import format_timestamp

# Initialize database connection
db = BeverageQADatabase()

def generate_report(start_date, end_date):
    """
    Generate a report for the specified date range
    
    Args:
        start_date: Start date for the report
        end_date: End date for the report
        
    Returns:
        DataFrame with report data
    """
    # Get all check data for the period using the class method
    all_data = db.get_check_data(start_date, end_date)
    
    if all_data.empty:
        return None
        
    # Create a summary report dataframe
    report_data = pd.DataFrame()
    
    # Process data based on check type
    if 'source' in all_data.columns:
        # Separate data by source
        torque_data = all_data[all_data['source'] == 'torque_tamper']
        net_content_data = all_data[all_data['source'] == 'net_content']
        quality_data = all_data[all_data['source'] == 'quality_check']
        
        # Create report sections
        report_sections = []
        
        # 1. Summary statistics
        summary = {
            'Report Section': 'Summary',
            'Metric': [
                'Total Checks',
                'Torque & Tamper Checks',
                'Net Content Checks',
                '30-Minute Checks',
                'Unique Inspectors',
                'Date Range'
            ],
            'Value': [
                len(all_data),
                len(torque_data),
                len(net_content_data),
                len(quality_data),
                all_data['username'].nunique(),
                f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}"
            ]
        }
        summary_df = pd.DataFrame(summary)
        report_sections.append(summary_df)
        
        # 2. BRIX statistics
        if 'brix' in all_data.columns:
            brix_data = all_data[all_data['brix'].notna()]
            
            if not brix_data.empty:
                brix_stats = {
                    'Report Section': 'BRIX Statistics',
                    'Metric': [
                        'Average BRIX',
                        'Minimum BRIX',
                        'Maximum BRIX',
                        'Standard Deviation',
                        'Number of Readings'
                    ],
                    'Value': [
                        f"{brix_data['brix'].mean():.2f}",
                        f"{brix_data['brix'].min():.2f}",
                        f"{brix_data['brix'].max():.2f}",
                        f"{brix_data['brix'].std():.2f}",
                        len(brix_data)
                    ]
                }
                brix_df = pd.DataFrame(brix_stats)
                report_sections.append(brix_df)
        
        # 3. Torque statistics
        torque_cols = ['head1_torque', 'head2_torque', 'head3_torque', 'head4_torque', 'head5_torque']
        if not torque_data.empty and any(col in torque_data.columns for col in torque_cols):
            metrics = []
            values = []
            
            for head_col in [col for col in torque_cols if col in torque_data.columns]:
                head_num = head_col.split('_')[0][4:]
                avg = torque_data[head_col].mean()
                out_of_range = ((torque_data[head_col] < 5) | (torque_data[head_col] > 12)).sum()
                pct_in_range = 100 * (1 - out_of_range / len(torque_data))
                
                metrics.extend([
                    f"Head {head_num} - Average Torque",
                    f"Head {head_num} - Out of Range",
                    f"Head {head_num} - % In Range"
                ])
                
                values.extend([
                    f"{avg:.2f}",
                    out_of_range,
                    f"{pct_in_range:.1f}%"
                ])
            
            # Add overall torque statistics
            if metrics:
                torque_stats = {
                    'Report Section': 'Torque Statistics',
                    'Metric': metrics,
                    'Value': values
                }
                torque_df = pd.DataFrame(torque_stats)
                report_sections.append(torque_df)
        
        # 4. Tamper evidence statistics
        if not torque_data.empty and 'tamper_evidence' in torque_data.columns:
            pass_count = torque_data['tamper_evidence'].str.contains('PASS').sum()
            fail_count = torque_data['tamper_evidence'].str.contains('FAIL').sum()
            pass_pct = 100 * pass_count / (pass_count + fail_count) if (pass_count + fail_count) > 0 else 0
            
            tamper_stats = {
                'Report Section': 'Tamper Evidence',
                'Metric': [
                    'PASS Count',
                    'FAIL Count',
                    'Pass Rate'
                ],
                'Value': [
                    pass_count,
                    fail_count,
                    f"{pass_pct:.1f}%"
                ]
            }
            tamper_df = pd.DataFrame(tamper_stats)
            report_sections.append(tamper_df)
        
        # 5. Quality issues summary
        if not quality_data.empty:
            quality_params = [
                ('label_application', 'Not OK', 'Label Issues'),
                ('torque_test', 'FAIL', 'Torque Test Issues'),
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
            
            metrics = []
            values = []
            
            for param, fail_value, label in quality_params:
                if param in quality_data.columns:
                    issue_count = (quality_data[param] == fail_value).sum()
                    issue_pct = 100 * issue_count / len(quality_data)
                    
                    if issue_count > 0:
                        metrics.append(label)
                        values.append(f"{issue_count} ({issue_pct:.1f}%)")
            
            if metrics:
                quality_issues = {
                    'Report Section': 'Quality Issues',
                    'Metric': metrics,
                    'Value': values
                }
                quality_issues_df = pd.DataFrame(quality_issues)
                report_sections.append(quality_issues_df)
        
        # 6. Product distribution
        if not quality_data.empty and 'product' in quality_data.columns and 'trade_name' in quality_data.columns:
            product_counts = quality_data.groupby(['trade_name', 'product']).size().reset_index(name='count')
            product_pcts = []
            
            for _, row in product_counts.iterrows():
                pct = 100 * row['count'] / len(quality_data)
                product_pcts.append(f"{row['trade_name']} - {row['product']}")
                
            if product_pcts:
                product_stats = {
                    'Report Section': 'Product Distribution',
                    'Metric': product_pcts,
                    'Value': [f"{count} ({100 * count / len(quality_data):.1f}%)" for count in product_counts['count']]
                }
                product_df = pd.DataFrame(product_stats)
                report_sections.append(product_df)
        
        # Combine all report sections
        report_data = pd.concat(report_sections, ignore_index=True)
    
    return report_data

def download_report(report_data, filename_prefix):
    """
    Create a download link for the report
    
    Args:
        report_data: DataFrame with report data
        filename_prefix: Prefix for the download filename
    """
    # Create Excel file in memory
    output = io.BytesIO()
    
    # Create a Pandas Excel writer using the BytesIO object
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        # Split the report by sections
        sections = report_data['Report Section'].unique()
        
        for section in sections:
            section_data = report_data[report_data['Report Section'] == section].copy()
            section_data = section_data[['Metric', 'Value']]  # Remove section column
            sheet_name = section[:31]  # Excel sheet names limited to 31 chars
            section_data.to_excel(writer, sheet_name=sheet_name, index=False)
            
            # Set column widths
            worksheet = writer.sheets[sheet_name]
            worksheet.set_column('A:A', 30)
            worksheet.set_column('B:B', 25)
        
        # Create a summary sheet that links to all other sheets
        summary = pd.DataFrame({
            'Section': sections,
            'Link': ['Click to view'] * len(sections)
        })
        
        summary.to_excel(writer, sheet_name='Summary', index=False)
        worksheet = writer.sheets['Summary']
        worksheet.set_column('A:A', 25)
        worksheet.set_column('B:B', 15)
    
    # Generate download link
    b64 = base64.b64encode(output.getvalue()).decode()
    today = dt.datetime.now().strftime('%Y%m%d')
    filename = f"{filename_prefix}_{today}.xlsx"
    href = f'<a href="data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,{b64}" download="{filename}">Download Excel Report</a>'
    
    st.markdown(href, unsafe_allow_html=True)