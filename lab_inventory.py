import streamlit as st
import pandas as pd
import numpy as np
import datetime as dt
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from docx import Document
from docx.shared import RGBColor, Inches, Pt
from io import BytesIO
import plotly.express as px
import plotly.graph_objects as go
from PIL import Image
import os

# Configuration
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
INVENTORY_CATEGORIES = {
    "chemicals": ["Reagent", "Solvent", "Buffer", "Indicator", "Acid", "Base"],
    "glassware": ["Volumetric", "Measuring", "Container", "Specialty"],
    "equipment": ["Instrument", "Device", "Tool", "Machine"]
}

class LabInventory:
    def __init__(self):
        self.initialize_data()
        
    def initialize_data(self):
        """Initialize inventory data structure"""
        if 'lab_inventory' not in st.session_state:
            st.session_state.lab_inventory = {
                "chemicals": pd.DataFrame(columns=[
                    "ID", "Item", "Category", "Minimum", "Current", "Unit", 
                    "Expiry", "Location", "Supplier", "Comment", "Status"
                ]),
                "glassware": pd.DataFrame(columns=[
                    "ID", "Item", "Category", "Current", "Unit", 
                    "Location", "Comment", "Status"
                ]),
                "equipment": pd.DataFrame(columns=[
                    "ID", "Item", "Category", "Current", "Unit", 
                    "Location", "Status", "Last Calibration", "Comment"
                ])
            }
            self.load_sample_data()
            self.check_restock_status()
    
    def load_sample_data(self):
        """Load sample inventory data"""
        sample_chemicals = [
            {"ID": "CHEM-001", "Item": "DPD#4 tablets", "Category": "Reagent", 
             "Minimum": 750, "Current": 410, "Unit": "tablets", 
             "Expiry": "09/2028", "Location": "Shelf A1", 
             "Supplier": "Sigma-Aldrich", "Comment": "", "Status": "Low"},
            {"ID": "CHEM-002", "Item": "Sodium Hydroxide", "Category": "Base", 
             "Minimum": 5, "Current": 3.7, "Unit": "kg", 
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
             "Last Calibration": "01/2024", "Comment": ""},
            {"ID": "EQUIP-002", "Item": "Analytical balance", 
             "Category": "Instrument", "Current": 2, "Unit": "units", 
             "Location": "Bench 1", "Status": "1 needs service", 
             "Last Calibration": "03/2024", "Comment": "Annual maintenance due"}
        ]
        
        st.session_state.lab_inventory["chemicals"] = pd.DataFrame(sample_chemicals)
        st.session_state.lab_inventory["glassware"] = pd.DataFrame(sample_glassware)
        st.session_state.lab_inventory["equipment"] = pd.DataFrame(sample_equipment)
    
    def check_restock_status(self):
        """Check and update inventory status"""
        chem_df = st.session_state.lab_inventory["chemicals"]
        
        # Update chemical status
        chem_df["Status"] = np.where(
            chem_df["Current"] < chem_df["Minimum"],
            "Low",
            "OK"
        )
        
        # Update expiry status
        today = dt.datetime.now()
        chem_df["Expiry"] = pd.to_datetime(chem_df["Expiry"], errors='coerce')
        mask = (chem_df["Expiry"] < today) & (~chem_df["Expiry"].isna())
        chem_df.loc[mask, "Status"] = "Expired"
        
        st.session_state.lab_inventory["chemicals"] = chem_df
    
    def display_main_interface(self):
        """Main inventory management interface"""
        st.title("🔬 Laboratory Inventory Management System")
        
        tabs = st.tabs([
            "📊 Dashboard", 
            "📦 Inventory", 
            "📈 Analytics", 
            "⚠️ Alerts", 
            "📤 Export"
        ])
        
        with tabs[0]:
            self.display_dashboard()
        with tabs[1]:
            self.display_inventory_management()
        with tabs[2]:
            self.display_analytics()
        with tabs[3]:
            self.display_alerts()
        with tabs[4]:
            self.display_export()
    
    def display_dashboard(self):
        """Display inventory dashboard"""
        st.subheader("Inventory Overview")
        
        # Calculate metrics
        chem_stats = self.calculate_category_stats("chemicals")
        glass_stats = self.calculate_category_stats("glassware")
        equip_stats = self.calculate_category_stats("equipment")
        
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
        
        # Recent activity
        st.subheader("Recent Activity")
        st.info("Feature coming soon! Will show recent inventory changes.")
        
        # Quick actions
        st.subheader("Quick Actions")
        if st.button("Check All Alerts", use_container_width=True):
            st.session_state.current_tab = "⚠️ Alerts"
            st.rerun()
    
    def calculate_category_stats(self, category):
        """Calculate statistics for a category"""
        df = st.session_state.lab_inventory[category]
        stats = {"total": len(df)}
        
        if category == "chemicals":
            stats["low"] = len(df[df["Status"] == "Low"])
            stats["expired"] = len(df[df["Status"] == "Expired"])
        elif category == "glassware":
            stats["damaged"] = len(df[df["Status"] == "Damaged"])
        elif category == "equipment":
            stats["issues"] = len(df[df["Status"].str.contains("need", case=False)])
        
        return stats
    
    def display_inventory_management(self):
        """Inventory management interface"""
        st.subheader("Manage Inventory")
        
        category = st.selectbox(
            "Select Category",
            ["Chemicals", "Glassware", "Equipment"],
            key="inventory_category"
        )
        
        if category == "Chemicals":
            self.manage_chemicals()
        elif category == "Glassware":
            self.manage_glassware()
        else:
            self.manage_equipment()
    
    def manage_chemicals(self):
        """Chemical inventory management"""
        df = st.session_state.lab_inventory["chemicals"]
        
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
                    current_stock = st.number_input("Current Stock", min_value=0.0, step=0.1)
                    unit = st.selectbox("Unit", ["g", "kg", "L", "mL", "tablets", "bottles"])
                with cols[2]:
                    expiry = st.text_input("Expiry (MM/YYYY)", placeholder="06/2025")
                    location = st.text_input("Storage Location")
                    supplier = st.text_input("Supplier")
                
                if st.form_submit_button("Add Chemical"):
                    new_item = {
                        "ID": new_id,
                        "Item": item_name,
                        "Category": category,
                        "Minimum": min_stock,
                        "Current": current_stock,
                        "Unit": unit,
                        "Expiry": expiry,
                        "Location": location,
                        "Supplier": supplier,
                        "Comment": "",
                        "Status": "Low" if current_stock < min_stock else "OK"
                    }
                    df.loc[len(df)] = new_item
                    st.success(f"Added {item_name} to inventory")
                    self.check_restock_status()
        
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
                "Expiry": st.column_config.DateColumn(
                    "Expiry Date",
                    format="MM/YYYY"
                )
            }
        )
        
        if not df.equals(edited_df):
            st.session_state.lab_inventory["chemicals"] = edited_df
            self.check_restock_status()
            st.rerun()
    
    def display_analytics(self):
        """Inventory analytics and visualization"""
        st.subheader("Inventory Analytics")
        
        # Create combined dataframe
        combined_df = self.create_combined_df()
        
        # Visualization options
        viz_option = st.selectbox(
            "Select Visualization",
            ["Status Distribution", "Stock Levels", "Expiry Timeline", "Location View"]
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
                    'Damaged': 'red'
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
                hover_data=['Item', 'Minimum'],
                color_discrete_map={
                    'OK': 'green',
                    'Low': 'orange',
                    'Expired': 'red',
                    'Damaged': 'red'
                }
            )
            st.plotly_chart(fig, use_container_width=True)
        
        elif viz_option == "Expiry Timeline":
            chem_df = st.session_state.lab_inventory["chemicals"].copy()
            chem_df['Expiry'] = pd.to_datetime(chem_df['Expiry'], errors='coerce')
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
    
    def display_alerts(self):
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
        issues = equip_df[equip_df["Status"].str.contains("need", case=False)]
        
        if not issues.empty:
            st.error(f"⚠️ {len(issues)} Equipment Issues")
            st.dataframe(
                issues[["ID", "Item", "Status", "Last Calibration"]],
                hide_index=True
            )
        
        if low_stock.empty and expired.empty and damaged.empty and issues.empty:
            st.success("✅ No critical alerts at this time")
    
    def display_export(self):
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
                self.export_word_report(export_type)
            elif format_type == "Excel":
                self.export_excel(export_type)
            else:
                self.export_csv(export_type)
        
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
                        self.send_email_report(recipient, subject, message, export_type)
                        st.success("Email sent successfully!")
                    except Exception as e:
                        st.error(f"Failed to send email: {str(e)}")
    
    def export_word_report(self, report_type):
        """Generate Word document report"""
        document = Document()
        
        # Add title and metadata
        document.add_heading('Lab Inventory Report', 0)
        document.add_paragraph(f"Report Type: {report_type}")
        document.add_paragraph(f"Generated on: {dt.datetime.now().strftime('%Y-%m-%d %H:%M')}")
        document.add_paragraph(f"Generated by: {st.session_state.get('username', 'System')}")
        
        # Add content based on report type
        if report_type in ["Full Inventory", "Chemicals Only"]:
            self.add_chemicals_to_word(document)
        
        if report_type in ["Full Inventory"]:
            self.add_glassware_to_word(document)
            self.add_equipment_to_word(document)
        
        if report_type == "Restocking List":
            self.add_restocking_list(document)
        
        if report_type == "Expiry Report":
            self.add_expiry_report(document)
        
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
    
    def send_email_report(self, recipient, subject, message, report_type):
        """Send inventory report via email"""
        # Create document
        document = Document()
        document.add_heading(subject, 0)
        document.add_paragraph(message)
        
        # Add report content
        if report_type in ["Full Inventory", "Chemicals Only"]:
            self.add_chemicals_to_word(document)
        
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
            f'attachment; filename="lab_inventory_{report_type.replace(' ', '_')}.docx"'
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
    
    def create_combined_df(self):
        """Create combined dataframe of all inventory"""
        chem = st.session_state.lab_inventory["chemicals"].copy()
        glass = st.session_state.lab_inventory["glassware"].copy()
        equip = st.session_state.lab_inventory["equipment"].copy()
        
        # Standardize columns
        chem["Type"] = "Chemical"
        glass["Type"] = "Glassware"
        equip["Type"] = "Equipment"
        
        # Combine relevant columns
        combined = pd.concat([
            chem[["ID", "Item", "Type", "Category", "Current", "Minimum", "Unit", "Status", "Location"]],
            glass[["ID", "Item", "Type", "Category", "Current", "Unit", "Status", "Location"]],
            equip[["ID", "Item", "Type", "Category", "Current", "Unit", "Status", "Location"]]
        ])
        
        return combined.fillna("")

# Main app execution
if __name__ == "__main__":
    inventory = LabInventory()
    inventory.display_main_interface()