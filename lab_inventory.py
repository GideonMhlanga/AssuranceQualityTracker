import streamlit as st
import pandas as pd
import numpy as np
import datetime as dt
from docx import Document
from docx.shared import RGBColor
from io import BytesIO
import plotly.express as px
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders

# Configuration
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
INVENTORY_CATEGORIES = {
    "chemicals": ["Reagent", "Solvent", "Buffer", "Indicator", "Acid", "Base", "Consumables"],
    "glassware": ["Volumetric", "Measuring", "Container", "Specialty"],
    "equipment": ["Instrument", "Device", "Tool", "Machine"]
}

def display_lab_inventory_page():
    """Main inventory management interface"""
    st.title("🔬 Laboratory Inventory Management System")
    
    # Initialize session state
    if 'lab_inventory' not in st.session_state:
        initialize_inventory_data()
    
    # Main tabs
    tabs = st.tabs(["📊 Dashboard", "📦 Inventory", "📈 Analytics", "⚠️ Alerts", "📤 Export"])
    
    with tabs[0]:
        display_dashboard()
    with tabs[1]:
        display_inventory_management()
    with tabs[2]:
        display_analytics()
    with tabs[3]:
        display_alerts()
    with tabs[4]:
        display_export()

def initialize_inventory_data():
    """Initialize inventory data structure"""
    st.session_state.lab_inventory = {
        "chemicals": pd.DataFrame(columns=[
            "ID", "Item", "Category", "Minimum", "Current", "Monthly", "Unit", 
            "Expiry", "Location", "Supplier", "Comment", "Status"
        ]),
        "glassware": pd.DataFrame(columns=[
            "ID", "Item", "Category", "Current", "Unit", 
            "Location", "Comment", "Status"
        ]),
        "equipment": pd.DataFrame(columns=[
            "ID", "Item", "Category", "Current", "Unit", 
            "Location", "Status", "Last_Calibration", "Comment"
        ])
    }
    load_sample_data()
    check_restock_status()

def load_sample_data():
    """Load sample inventory data"""
    sample_chemicals = [
        {"ID": "CHEM-001", "Item": "DPD#4 tablets", "Category": "Reagent", 
         "Minimum": 750, "Current": 410,"Monthly": 125, "Unit": "tablets", 
         "Expiry": "09/2028", "Location": "Shelf A1", 
         "Supplier": "Sigma-Aldrich", "Comment": "", "Status": "Low"},
        {"ID": "CHEM-002", "Item": "0.1N Sodium Hydroxide", "Category": "Base", 
         "Minimum": 5, "Current": 3.7, "Unit": "L", 
         "Expiry": "05/2025", "Location": "Cabinet B2", 
         "Supplier": "Fisher Scientific", "Comment": "Corrosive", "Status": "OK"}
    ]
    
    sample_glassware = [
        {"ID": "GLAS-001", "Item": "1000ml volumetric flask", 
         "Category": "Volumetric", "Current": 5, "Unit": "pieces", 
         "Location": "Cabinet 3", "Comment": "", "Status": "OK"},
        {"ID": "GLAS-002", "Item": "50ml burette", 
         "Category": "Measuring", "Current": 2, "Unit": "pieces", 
         "Location": "Drawer 1", "Comment": "1 needs repair", "Status": "Damaged"}
    ]
    
    sample_equipment = [
        {"ID": "EQUIP-001", "Item": "pH meter", 
         "Category": "Instrument", "Current": 1, "Unit": "units", 
         "Location": "Bench 2", "Status": "Working", 
         "Last_Calibration": "01/2024", "Comment": ""},
        {"ID": "EQUIP-002", "Item": "Analytical balance", 
         "Category": "Instrument", "Current": 2, "Unit": "units", 
         "Location": "Bench 1", "Status": "1 needs service", 
         "Last_Calibration": "03/2024", "Comment": "Annual maintenance due"}
    ]
    
    st.session_state.lab_inventory["chemicals"] = pd.DataFrame(sample_chemicals)
    st.session_state.lab_inventory["glassware"] = pd.DataFrame(sample_glassware)
    st.session_state.lab_inventory["equipment"] = pd.DataFrame(sample_equipment)

def check_restock_status():
    """Check and update inventory status"""
    chem_df = st.session_state.lab_inventory["chemicals"]
    
    # Convert Expiry to datetime if needed
    if not pd.api.types.is_datetime64_any_dtype(chem_df["Expiry"]):
        chem_df["Expiry"] = pd.to_datetime(chem_df["Expiry"], format='%m/%Y', errors='coerce')
    
    # Update status
    chem_df["Status"] = np.where(
        chem_df["Current"] < chem_df["Minimum"],
        "Low",
        "OK"
    )
    
    # Mark expired items
    today = pd.to_datetime(dt.datetime.now().date())
    chem_df.loc[(chem_df["Expiry"] < today) & (~chem_df["Expiry"].isna()), "Status"] = "Expired"
    
    st.session_state.lab_inventory["chemicals"] = chem_df

def display_dashboard():
    """Display inventory dashboard with complete list"""
    st.subheader("Inventory Overview")
    
    # Calculate metrics
    chem_stats = calculate_category_stats("chemicals")
    glass_stats = calculate_category_stats("glassware")
    equip_stats = calculate_category_stats("equipment")
    
    # Display metrics
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("🧪 Chemicals", 
                f"{chem_stats['total']} items",
                f"{chem_stats['low']} low, {chem_stats['expired']} expired")
    with col2:
        st.metric("🔍 Glassware", 
                f"{glass_stats['total']} items",
                f"{glass_stats['damaged']} damaged")
    with col3:
        st.metric("⚙️ Equipment", 
                f"{equip_stats['total']} items",
                f"{equip_stats['issues']} with issues")
    
    # Display complete inventory list
    st.subheader("Complete Inventory List")
    combined_df = create_combined_df()
    st.dataframe(combined_df, use_container_width=True)

def calculate_category_stats(category):
    """Calculate statistics for a category"""
    df = st.session_state.lab_inventory[category]
    stats = {"total": len(df)}
    
    if category == "chemicals":
        stats["low"] = len(df[df["Status"] == "Low"])
        stats["expired"] = len(df[df["Status"] == "Expired"])
    elif category == "glassware":
        stats["damaged"] = len(df[df["Status"] == "Damaged"])
    elif category == "equipment":
        stats["issues"] = len(df[df["Status"].str.contains("need", case=False, na=False)])
    
    return stats

def display_inventory_management():
    """Inventory management interface"""
    st.subheader("Manage Inventory")
    
    category = st.selectbox(
        "Select Category",
        ["Chemicals", "Glassware", "Equipment"],
        key="inventory_category"
    )
    
    if category == "Chemicals":
        manage_chemicals()
    elif category == "Glassware":
        manage_glassware()
    else:
        manage_equipment()

def manage_chemicals():
    """Chemical inventory management"""
    df = st.session_state.lab_inventory["chemicals"].copy()
    
    # Convert datetime to string for editing
    if not df.empty and 'Expiry' in df.columns:
        df['Expiry'] = df['Expiry'].dt.strftime('%m/%Y') if pd.api.types.is_datetime64_any_dtype(df['Expiry']) else df['Expiry']
    
    # Add new chemical
    with st.expander("➕ Add New Chemical", expanded=False):
        with st.form("add_chemical_form"):
            cols = st.columns([1, 2, 1])
            with cols[0]:
                new_id = f"CHEM-{len(df)+1:03d}"
                st.text_input("ID", value=new_id, disabled=True)
                item_name = st.text_input("Item Name")
                category = st.selectbox("Category", INVENTORY_CATEGORIES["chemicals"])
            with cols[1]:
                min_stock = st.number_input("Minimum Stock", min_value=0.0, step=0.1)
                monthly_usage = st.number_input("Monthly Usage", min_value=0.0, step=1.0)
                current_stock = st.number_input("Current Stock", min_value=0.0, step=0.1)
                unit = st.selectbox("Unit", ["g", "kg", "L", "mL", "tablets", "bottles", "satchets", "pieces"])
            with cols[2]:
                expiry = st.text_input("Expiry (MM/YYYY)", placeholder="06/2025")
                location = st.text_input("Storage Location")
                supplier = st.text_input("Supplier")
            
            if st.form_submit_button("Add Chemical"):
                # Check for duplicate item name (case insensitive)
                existing_items = df['Item'].str.lower().tolist()
                if item_name.lower() in existing_items:
                    st.error(f"An item with the name '{item_name}' already exists in Inventory")
                else:
                    new_item = {
                        "ID": new_id,
                        "Item": item_name,
                        "Category": category,
                        "Minimum": min_stock,
                        "Current": current_stock,
                        "Monthly": monthly_usage,
                        "Unit": unit,
                        "Expiry": expiry,
                        "Location": location,
                        "Supplier": supplier,
                        "Comment": "",
                        "Status": "Low" if current_stock < min_stock else "OK"
                    }
                    df.loc[len(df)] = new_item
                    st.session_state.lab_inventory["chemicals"] = df #Save to session state
                    st.success(f"Added {item_name} to inventory")
        
    # Edit existing chemicals
    st.subheader("Current Chemical Inventory")
    edited_df = st.data_editor(
        df,
        num_rows="dynamic",
        use_container_width=True,
        disabled=["ID"],
        column_config={
            "Status": st.column_config.SelectboxColumn(
                "Status",
                options=["OK", "Low", "Expired"],
                required=True
            ),
            "Expiry": st.column_config.TextColumn(
                "Expiry Date",
                help="Format: MM/YYYY",
                validate="^(0[1-9]|1[0-2])/[0-9]{4}$",
                default="01/2025"
            )
        }
    )
    
    # Handle save action
    if st.button("Save Changes"):
        # Convert back to datetime
        if not edited_df.empty and 'Expiry' in edited_df.columns:
            edited_df['Expiry'] = pd.to_datetime(edited_df['Expiry'], format='%m/%Y', errors='coerce')
            edited_df = edited_df[~edited_df['Expiry'].isna()]
        
        st.session_state.lab_inventory["chemicals"] = edited_df
        check_restock_status()
        st.success("Changes saved successfully!")
        st.rerun()

def manage_glassware():
    """Glassware inventory management"""
    df = st.session_state.lab_inventory["glassware"].copy()
    
    # Add new glassware
    with st.expander("➕ Add New Glassware", expanded=False):
        with st.form("add_glassware_form"):
            cols = st.columns([1, 2, 1])
            with cols[0]:
                new_id = f"GLAS-{len(df)+1:03d}"
                st.text_input("ID", value=new_id, disabled=True)
                item_name = st.text_input("Item Name", key= "new_glass_name")
                category = st.selectbox("Category", INVENTORY_CATEGORIES["glassware"])
            with cols[1]:
                current_stock = st.number_input("Quantity", min_value=0, step=1)
                unit = st.selectbox("Unit", ["pieces", "sets", "units"])
            with cols[2]:
                location = st.text_input("Storage Location")
                comment = st.text_input("Comments")
            
            if st.form_submit_button("Add Glassware"):
                # Check for duplicate item name (case.insensitive)
                existing_items = df['Item'].str.lower().tolist()
                if item_name.lower() in existing_items:
                    st.error(f"Glassware with the name '{item_name}' already exists in Inventory")
                else:
                    new_item = {
                        "ID": new_id,
                        "Item": item_name,
                        "Category": category,
                        "Current": current_stock,
                        "Unit": unit,
                        "Location": location,
                        "Comment": comment,
                        "Status": "OK"
                    }
                    df.loc[len(df)] = new_item
                    st.success(f"Added {item_name} to inventory")
        
    # Edit existing glassware
    st.subheader("Current Glassware Inventory")
    edited_df = st.data_editor(
        df,
        num_rows="dynamic",
        use_container_width=True,
        disabled=["ID"],
        column_config={
            "Status": st.column_config.SelectboxColumn(
                "Status",
                options=["OK", "Damaged"],
                required=True
            )
        }
    )
    
    if st.button("Save Glassware Changes"):
        st.session_state.lab_inventory["glassware"] = edited_df
        st.success("Changes saved successfully!")
        st.rerun()

def manage_equipment():
    """Equipment inventory management"""
    df = st.session_state.lab_inventory["equipment"].copy()
    
    # Add new equipment
    with st.expander("➕ Add New Equipment", expanded=False):
        with st.form("add_equipment_form"):
            cols = st.columns([1, 2, 1])
            with cols[0]:
                new_id = f"EQUIP-{len(df)+1:03d}"
                st.text_input("ID", value=new_id, disabled=True)
                item_name = st.text_input("Item Name", key="new_equip_name")
                category = st.selectbox("Category", INVENTORY_CATEGORIES["equipment"])
            with cols[1]:
                current_stock = st.number_input("Quantity", min_value=0, step=1)
                unit = st.selectbox("Unit", ["units", "sets"])
                last_calibration = st.text_input("Last Calibration (MM/YYYY)", placeholder="01/2024")
            with cols[2]:
                location = st.text_input("Storage Location")
                status = st.selectbox("Status", ["Working", "Needs service", "In repair"])
                comment = st.text_input("Comments")
            
            if st.form_submit_button("Add Equipment"):
                # Check for duplicate item name (case insensitive)
                existing_items = df['Item'].str.lower().tolist()
                if item_name.lower() in existing_items:
                    st.error(f"An equipment item with the name '{item_name}' already exists in Inventory!")
                else:
                    new_item = {
                        "ID": new_id,
                        "Item": item_name,
                        "Category": category,
                        "Current": current_stock,
                        "Unit": unit,
                        "Location": location,
                        "Status": status,
                        "Last_Calibration": last_calibration,
                        "Comment": comment
                    }
                    df.loc[len(df)] = new_item
                    st.success(f"Added {item_name} to inventory")
    
    # Edit existing equipment
    st.subheader("Current Equipment Inventory")
    edited_df = st.data_editor(
        df,
        num_rows="dynamic",
        use_container_width=True,
        disabled=["ID"],
        column_config={
            "Status": st.column_config.SelectboxColumn(
                "Status",
                options=["Working", "Needs service", "In repair"],
                required=True
            ),
            "Last_Calibration": st.column_config.TextColumn(
                "Last Calibration",
                help="Format: MM/YYYY",
                validate="^(0[1-9]|1[0-2])/[0-9]{4}$"
            )
        }
    )
    
    if st.button("Save Equipment Changes"):
        st.session_state.lab_inventory["equipment"] = edited_df
        st.success("Changes saved successfully!")
        st.rerun()

def display_analytics():
    """Inventory analytics and visualization"""
    st.subheader("Inventory Analytics")
    
    # Create combined dataframe
    combined_df = create_combined_df()
    
    # Visualization options
    viz_option = st.selectbox(
        "Select Visualization",
        ["Status Distribution", "Stock Levels", "Expiry Timeline"]
    )
    
    if viz_option == "Status Distribution":
        fig = px.pie(
            combined_df, 
            names='Status', 
            title='Inventory Status Distribution',
            color='Status',
            color_discrete_map={
                'OK': 'green',
                'Low': 'orange',
                'Expired': 'red',
                'Damaged': 'red',
                'Needs service': 'orange',
                'In repair': 'red'
            }
        )
        st.plotly_chart(fig, use_container_width=True)
    
    elif viz_option == "Stock Levels":
        fig = px.bar(
            combined_df,
            x='Category',
            y='Current',
            color='Status',
            title='Stock Levels by Category',
            hover_data=['Item', 'Unit'],
            color_discrete_map={
                'OK': 'green',
                'Low': 'orange',
                'Expired': 'red',
                'Damaged': 'red',
                'Needs service': 'orange',
                'In repair': 'red'
            }
        )
        st.plotly_chart(fig, use_container_width=True)
    
    elif viz_option == "Expiry Timeline":
        chem_df = st.session_state.lab_inventory["chemicals"].copy()
        chem_df['Expiry'] = pd.to_datetime(chem_df['Expiry'], format='%m/%Y', errors='coerce')
        chem_df = chem_df.dropna(subset=['Expiry'])
        
        if not chem_df.empty:
            chem_df['Days Until Expiry'] = (chem_df['Expiry'] - pd.to_datetime('today')).dt.days
            fig = px.scatter(
                chem_df,
                x='Expiry',
                y='Item',
                size='Current',
                color='Days Until Expiry',
                hover_data=['Minimum', 'Location'],
                title='Chemical Expiry Timeline'
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("No chemicals with valid expiry dates found")

def display_alerts():
    """Display inventory alerts"""
    st.subheader("Inventory Alerts")
    
    # Chemical alerts
    chem_df = st.session_state.lab_inventory["chemicals"]
    low_stock = chem_df[chem_df["Status"] == "Low"]
    expired = chem_df[chem_df["Status"] == "Expired"]
    
    if not low_stock.empty:
        st.warning(f"🧪 {len(low_stock)} Chemicals Need Restocking")
        st.dataframe(
            low_stock[["ID", "Item", "Current", "Minimum", "Unit", "Location"]],
            hide_index=True
        )
    
    if not expired.empty:
        st.error(f"⏳ {len(expired)} Expired Chemicals")
        st.dataframe(
            expired[["ID", "Item", "Expiry", "Location"]],
            hide_index=True
        )
    
    # Glassware alerts
    glass_df = st.session_state.lab_inventory["glassware"]
    damaged = glass_df[glass_df["Status"] == "Damaged"]
    
    if not damaged.empty:
        st.error(f"🔧 {len(damaged)} Damaged Glassware Items")
        st.dataframe(
            damaged[["ID", "Item", "Comment", "Location"]],
            hide_index=True
        )
    
    # Equipment alerts
    equip_df = st.session_state.lab_inventory["equipment"]
    issues = equip_df[equip_df["Status"].str.contains("need|repair", case=False, na=False)]
    
    if not issues.empty:
        st.error(f"⚠️ {len(issues)} Equipment Issues")
        st.dataframe(
            issues[["ID", "Item", "Status", "Last_Calibration"]],
            hide_index=True
        )
    
    if low_stock.empty and expired.empty and damaged.empty and issues.empty:
        st.success("✅ No critical alerts at this time")

def display_export():
    """Export and email functionality"""
    st.subheader("Export Inventory Data")
    
    # Export options
    export_type = st.selectbox(
        "Export Type",
        ["Full Inventory", "Chemicals Only", "Restocking List", "Expiry Report"]
    )
    
    format_type = st.selectbox(
        "Format",
        ["Word Document", "Excel", "CSV"]
    )
    
    # Generate report
    if st.button("Generate Report"):
        if format_type == "Word Document":
            export_word_report(export_type)
        elif format_type == "Excel":
            export_excel(export_type)
        else:
            export_csv(export_type)
    
    # Email functionality
    st.subheader("Email Report")
    with st.form("email_form"):
        recipient = st.text_input("Recipient Email")
        subject = st.text_input("Subject", value="Lab Inventory Report")
        message = st.text_area("Message")
        
        if st.form_submit_button("Send Email"):
            if not recipient:
                st.error("Please enter a recipient email")
            else:
                try:
                    send_email_report(recipient, subject, message, export_type)
                    st.success("Email sent successfully!")
                except Exception as e:
                    st.error(f"Failed to send email: {str(e)}")

def create_combined_df():
    """Create combined dataframe of all inventory"""
    chem = st.session_state.lab_inventory["chemicals"].copy()
    glass = st.session_state.lab_inventory["glassware"].copy()
    equip = st.session_state.lab_inventory["equipment"].copy()
    
    # Standardize columns
    chem["Type"] = "Chemical"
    glass["Type"] = "Glassware"
    equip["Type"] = "Equipment"

    # Select columns that exist in the DataFrame
    chem_columns = ["ID", "Item", "Type", "Category", "Current", "Minimum", "Unit", "Status", "Location"]
    if "Monthly" in chem.columns:
        chem_columns.insert(6, "Monthly")  # Insert Monthly at position 6 if it exists
    
    # Combine relevant columns
    combined = pd.concat([
        chem[["ID", "Item", "Type", "Category", "Current", "Minimum", "Monthly", "Unit", "Status", "Location"]],
        glass[["ID", "Item", "Type", "Category", "Current", "Unit", "Status", "Location"]],
        equip[["ID", "Item", "Type", "Category", "Current", "Unit", "Status", "Location"]]
    ])
    
    return combined.fillna("")

def add_chemicals_to_word(document):
    """Add chemicals section to Word document"""
    chem_df = st.session_state.lab_inventory["chemicals"]
    document.add_heading('Chemicals Inventory', level=1)
    
    if not chem_df.empty:
        table = document.add_table(rows=1, cols=len(chem_df.columns), style='Table Grid')
        hdr_cells = table.rows[0].cells
        
        # Add headers
        for i, col in enumerate(chem_df.columns):
            hdr_cells[i].text = str(col)
        
        # Add data rows
        for _, row in chem_df.iterrows():
            row_cells = table.add_row().cells
            for i, value in enumerate(row):
                row_cells[i].text = str(value)
    else:
        document.add_paragraph("No chemical items in inventory")

def add_glassware_to_word(document):
    """Add glassware section to Word document"""
    glass_df = st.session_state.lab_inventory["glassware"]
    document.add_heading('Glassware Inventory', level=1)
    
    if not glass_df.empty:
        table = document.add_table(rows=1, cols=len(glass_df.columns), style='Table Grid')
        hdr_cells = table.rows[0].cells
        
        # Add headers
        for i, col in enumerate(glass_df.columns):
            hdr_cells[i].text = str(col)
        
        # Add data rows
        for _, row in glass_df.iterrows():
            row_cells = table.add_row().cells
            for i, value in enumerate(row):
                row_cells[i].text = str(value)
    else:
        document.add_paragraph("No glassware items in inventory")

def add_equipment_to_word(document):
    """Add equipment section to Word document"""
    equip_df = st.session_state.lab_inventory["equipment"]
    document.add_heading('Equipment Inventory', level=1)
    
    if not equip_df.empty:
        table = document.add_table(rows=1, cols=len(equip_df.columns), style='Table Grid')
        hdr_cells = table.rows[0].cells
        
        # Add headers
        for i, col in enumerate(equip_df.columns):
            hdr_cells[i].text = str(col)
        
        # Add data rows
        for _, row in equip_df.iterrows():
            row_cells = table.add_row().cells
            for i, value in enumerate(row):
                row_cells[i].text = str(value)
    else:
        document.add_paragraph("No equipment items in inventory")

def add_restocking_list(document):
    """Add restocking list to Word document"""
    document.add_heading('Restocking List', level=1)
    
    chem_df = st.session_state.lab_inventory["chemicals"]
    low_stock = chem_df[chem_df["Status"] == "Low"]
    
    if not low_stock.empty:
        document.add_paragraph('Chemicals needing restocking:')
        table = document.add_table(rows=1, cols=5, style='Table Grid')
        hdr_cells = table.rows[0].cells
        hdr_cells[0].text = "ID"
        hdr_cells[1].text = "Item"
        hdr_cells[2].text = "Current"
        hdr_cells[3].text = "Minimum"
        hdr_cells[4].text = "Deficit"
        
        for _, row in low_stock.iterrows():
            row_cells = table.add_row().cells
            row_cells[0].text = str(row["ID"])
            row_cells[1].text = str(row["Item"])
            row_cells[2].text = str(row["Current"])
            row_cells[3].text = str(row["Minimum"])
            row_cells[4].text = str(row["Minimum"] - row["Current"])
    else:
        document.add_paragraph("No items currently need restocking")

def add_expiry_report(document):
    """Add expiry report to Word document"""
    document.add_heading('Expiry Report', level=1)
    
    chem_df = st.session_state.lab_inventory["chemicals"]
    chem_df['Expiry'] = pd.to_datetime(chem_df['Expiry'], format='%m/%Y', errors='coerce')
    expiring = chem_df[~chem_df['Expiry'].isna()]
    
    if not expiring.empty:
        document.add_paragraph('Chemicals with expiry dates:')
        table = document.add_table(rows=1, cols=4, style='Table Grid')
        hdr_cells = table.rows[0].cells
        hdr_cells[0].text = "ID"
        hdr_cells[1].text = "Item"
        hdr_cells[2].text = "Expiry Date"
        hdr_cells[3].text = "Days Until Expiry"
        
        for _, row in expiring.iterrows():
            days_until = (row['Expiry'] - pd.to_datetime('today')).days
            row_cells = table.add_row().cells
            row_cells[0].text = str(row["ID"])
            row_cells[1].text = str(row["Item"])
            row_cells[2].text = row['Expiry'].strftime('%m/%Y')
            row_cells[3].text = str(days_until)
    else:
        document.add_paragraph("No chemicals with expiry dates in inventory")

def export_word_report(report_type):
    """Generate Word document report"""
    document = Document()
    
    # Add title and metadata
    document.add_heading('Lab Inventory Report', 0)
    document.add_paragraph(f"Report Type: {report_type}")
    document.add_paragraph(f"Generated on: {dt.datetime.now().strftime('%Y-%m-%d %H:%M')}")
    document.add_paragraph(f"Generated by: {st.session_state.get('username', 'System')}")
    
    # Add content based on report type
    if report_type in ["Full Inventory", "Chemicals Only"]:
        add_chemicals_to_word(document)
    
    if report_type in ["Full Inventory"]:
        add_glassware_to_word(document)
        add_equipment_to_word(document)
    
    if report_type == "Restocking List":
        add_restocking_list(document)
    
    if report_type == "Expiry Report":
        add_expiry_report(document)
    
    # Save to BytesIO and offer download
    file_stream = BytesIO()
    document.save(file_stream)
    file_stream.seek(0)
    
    st.download_button(
        label="Download Word Report",
        data=file_stream,
        file_name=f"lab_inventory_{report_type.replace(' ', '_')}.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )

def export_excel(report_type):
    """Generate Excel report"""
    if report_type == "Full Inventory":
        df = create_combined_df()
    elif report_type == "Chemicals Only":
        df = st.session_state.lab_inventory["chemicals"].copy()
    elif report_type == "Restocking List":
        chem_df = st.session_state.lab_inventory["chemicals"].copy()
        df = chem_df[chem_df["Status"] == "Low"]
    elif report_type == "Expiry Report":
        chem_df = st.session_state.lab_inventory["chemicals"].copy()
        chem_df['Expiry'] = pd.to_datetime(chem_df['Expiry'], format='%m/%Y', errors='coerce')
        df = chem_df[~chem_df['Expiry'].isna()]
    
    # Create Excel file
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Inventory')
    output.seek(0)
    
    st.download_button(
        label="Download Excel Report",
        data=output,
        file_name=f"lab_inventory_{report_type.replace(' ', '_')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

def export_csv(report_type):
    """Generate CSV report"""
    if report_type == "Full Inventory":
        df = create_combined_df()
    elif report_type == "Chemicals Only":
        df = st.session_state.lab_inventory["chemicals"].copy()
    elif report_type == "Restocking List":
        chem_df = st.session_state.lab_inventory["chemicals"].copy()
        df = chem_df[chem_df["Status"] == "Low"]
    elif report_type == "Expiry Report":
        chem_df = st.session_state.lab_inventory["chemicals"].copy()
        chem_df['Expiry'] = pd.to_datetime(chem_df['Expiry'], format='%m/%Y', errors='coerce')
        df = chem_df[~chem_df['Expiry'].isna()]
    
    # Create CSV file
    csv = df.to_csv(index=False).encode('utf-8')
    
    st.download_button(
        label="Download CSV Report",
        data=csv,
        file_name=f"lab_inventory_{report_type.replace(' ', '_')}.csv",
        mime="text/csv"
    )

def send_email_report(recipient, subject, message, report_type):
    """Send inventory report via email"""
    try:
        # Check if email credentials exist
        if not hasattr(st, 'secrets') or not st.secrets.get("email", {}).get("username"):
            raise Exception("Email credentials not configured")
        
        # Create document
        document = Document()
        document.add_heading(subject, 0)
        document.add_paragraph(message)
        
        # Add report content
        if report_type in ["Full Inventory", "Chemicals Only"]:
            add_chemicals_to_word(document)
        
        if report_type in ["Full Inventory"]:
            add_glassware_to_word(document)
            add_equipment_to_word(document)
        
        if report_type == "Restocking List":
            add_restocking_list(document)
        
        if report_type == "Expiry Report":
            add_expiry_report(document)
        
        # Create email message
        msg = MIMEMultipart()
        msg['From'] = st.secrets["email"]["username"]
        msg['To'] = recipient
        msg['Subject'] = subject
        
        # Add text and attachment
        msg.attach(MIMEText(message, 'plain'))
        
        file_stream = BytesIO()
        document.save(file_stream)
        file_stream.seek(0)
        
        part = MIMEBase('application', 'octet-stream')
        part.set_payload(file_stream.read())
        encoders.encode_base64(part)
        part.add_header(
            'Content-Disposition',
            f'attachment; filename="lab_inventory_{report_type.replace(" ", "_")}.docx"'
        )
        msg.attach(part)
        
        # Send email
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(
                st.secrets["email"]["username"],
                st.secrets["email"]["password"]
            )
            server.send_message(msg)
            
    except Exception as e:
        st.error(f"Email sending failed: {str(e)}")
        raise

# For testing the page directly
if __name__ == "__main__":
    display_lab_inventory_page()