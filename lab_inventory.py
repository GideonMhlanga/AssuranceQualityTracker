import streamlit as st
import pandas as pd
import datetime as dt
from docx import Document
from docx.shared import Inches
from io import BytesIO

def display_lab_inventory_page():
    st.title("Lab Inventory Management")
    
    # Initialize session state for inventory if it doesn't exist
    if 'lab_inventory' not in st.session_state:
        # Load the initial data from the template you provided
        st.session_state.lab_inventory = initialize_inventory_data()
    
    # Main tabs for different sections
    tab1, tab2, tab3, tab4 = st.tabs(["Inventory Dashboard", "Add/Edit Items", "Low Stock Alerts", "Export Report"])
    
    with tab1:
        display_inventory_dashboard()
    
    with tab2:
        add_edit_inventory_items()
    
    with tab3:
        display_low_stock_alerts()
    
    with tab4:
        export_inventory_report()

def initialize_inventory_data():
    """Initialize with the data from your template"""
    chemicals_data = [
        # Chemicals and reagents
        {"Item": "DPD#4 tablets", "Minimum stock": 750, "Monthly usage": 125, "Stock on hand": 410, "Expiry date": "09/2028", "Comment": ""},
        {"Item": "DPD#1 tablets", "Minimum stock": 750, "Monthly usage": 125, "Stock on hand": 550, "Expiry date": "04/2034", "Comment": ""},
        {"Item": "TPTZ Iron sachets", "Minimum stock": 75, "Monthly usage": 25, "Stock on hand": 24, "Expiry date": "05/2028", "Comment": "restock"},
        # Add all other items from your template here...
    ]
    
    glassware_data = [
        # Glassware
        {"Item": "2000 cm³ volumetric flask", "Stock on hand": 2, "Comment": ""},
        {"Item": "1000ml volumetric flasks", "Stock on hand": 9, "Comment": ""},
        # Add all other glassware items...
    ]
    
    equipment_data = [
        # Equipment
        {"Equipment": "pH meter", "Stock at hand": 1, "Status": "Working", "Comment": ""},
        {"Equipment": "Refractometer (J57 automatic)", "Stock at hand": 2, "Status": "1 not working", "Comment": "Does not switch on"},
        # Add all other equipment...
    ]
    
    return {
        "chemicals": pd.DataFrame(chemicals_data),
        "glassware": pd.DataFrame(glassware_data),
        "equipment": pd.DataFrame(equipment_data)
    }

def display_inventory_dashboard():
    """Display summary of inventory"""
    st.subheader("Inventory Summary")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        total_chemicals = len(st.session_state.lab_inventory["chemicals"])
        expiring_soon = len(st.session_state.lab_inventory["chemicals"][
            st.session_state.lab_inventory["chemicals"]["Expiry date"].apply(
                lambda x: is_expiring_soon(x) if pd.notna(x) else False
            )
        ])
        st.metric("Chemicals/Reagents", total_chemicals, f"{expiring_soon} expiring soon")
    
    with col2:
        total_glassware = len(st.session_state.lab_inventory["glassware"])
        broken_items = len(st.session_state.lab_inventory["glassware"][
            st.session_state.lab_inventory["glassware"]["Comment"].str.contains("broken", case=False, na=False)
        ])
        st.metric("Glassware", total_glassware, f"{broken_items} broken/damaged")
    
    with col3:
        total_equipment = len(st.session_state.lab_inventory["equipment"])
        non_working = len(st.session_state.lab_inventory["equipment"][
            st.session_state.lab_inventory["equipment"]["Status"].str.contains("not working", case=False, na=False)
        ])
        st.metric("Equipment", total_equipment, f"{non_working} not working")
    
    # Display recent changes/activity log
    st.subheader("Recent Inventory Changes")
    # You would implement this based on your tracking needs

def is_expiring_soon(expiry_date, months=3):
    """Check if an item is expiring soon (within the next X months)"""
    try:
        if "/" in expiry_date:
            month, year = map(int, expiry_date.split("/"))
        elif "-" in expiry_date:
            year, month = map(int, expiry_date.split("-"))
        else:
            return False
        
        expiry_dt = dt.datetime(year=year, month=month, day=1)
        today = dt.datetime.now()
        return (expiry_dt - today).days <= months*30
    except:
        return False

def add_edit_inventory_items():
    """Interface for adding or editing inventory items"""
    st.subheader("Manage Inventory Items")
    
    category = st.selectbox("Select Category", ["Chemicals/Reagents", "Glassware", "Equipment"])
    
    if category == "Chemicals/Reagents":
        manage_chemicals()
    elif category == "Glassware":
        manage_glassware()
    else:
        manage_equipment()

def manage_chemicals():
    """Manage chemicals and reagents"""
    df = st.session_state.lab_inventory["chemicals"]
    
    with st.expander("Add New Chemical/Reagent"):
        with st.form("add_chemical_form"):
            col1, col2 = st.columns(2)
            
            with col1:
                item = st.text_input("Item Name")
                min_stock = st.number_input("Minimum Stock Level", min_value=0)
                stock_on_hand = st.number_input("Current Stock", min_value=0)
            
            with col2:
                monthly_usage = st.number_input("Monthly Usage", min_value=0)
                expiry_date = st.text_input("Expiry Date (MM/YYYY)", placeholder="09/2028")
                comment = st.text_input("Comments")
            
            if st.form_submit_button("Add Item"):
                new_item = {
                    "Item": item,
                    "Minimum stock": min_stock,
                    "Monthly usage": monthly_usage,
                    "Stock on hand": stock_on_hand,
                    "Expiry date": expiry_date,
                    "Comment": comment
                }
                df.loc[len(df)] = new_item
                st.success("Item added successfully!")
                st.session_state.lab_inventory["chemicals"] = df
    
    st.subheader("Current Chemicals/Reagents")
    st.dataframe(df, use_container_width=True)

def manage_glassware():
    """Manage glassware items"""
    df = st.session_state.lab_inventory["glassware"]
    
    with st.expander("Add New Glassware"):
        with st.form("add_glassware_form"):
            item = st.text_input("Item Name")
            stock = st.number_input("Quantity in Stock", min_value=0)
            comment = st.text_input("Comments (e.g., broken, damaged)")
            
            if st.form_submit_button("Add Glassware"):
                new_item = {
                    "Item": item,
                    "Stock on hand": stock,
                    "Comment": comment
                }
                df.loc[len(df)] = new_item
                st.success("Glassware added successfully!")
                st.session_state.lab_inventory["glassware"] = df
    
    st.subheader("Current Glassware Inventory")
    st.dataframe(df, use_container_width=True)

def manage_equipment():
    """Manage equipment items"""
    df = st.session_state.lab_inventory["equipment"]
    
    with st.expander("Add New Equipment"):
        with st.form("add_equipment_form"):
            col1, col2 = st.columns(2)
            
            with col1:
                equipment = st.text_input("Equipment Name")
                stock = st.number_input("Quantity", min_value=0)
            
            with col2:
                status = st.selectbox("Status", ["Working", "Not working", "In repair"])
                comment = st.text_input("Comments")
            
            if st.form_submit_button("Add Equipment"):
                new_item = {
                    "Equipment": equipment,
                    "Stock at hand": stock,
                    "Status": status,
                    "Comment": comment
                }
                df.loc[len(df)] = new_item
                st.success("Equipment added successfully!")
                st.session_state.lab_inventory["equipment"] = df
    
    st.subheader("Current Equipment Inventory")
    st.dataframe(df, use_container_width=True)

def display_low_stock_alerts():
    """Display items that need restocking"""
    st.subheader("Restocking Alerts")
    
    # Chemicals that are below minimum stock
    chemicals = st.session_state.lab_inventory["chemicals"]
    low_stock_chemicals = chemicals[chemicals["Stock on hand"] < chemicals["Minimum stock"]]
    
    # Expiring soon chemicals
    expiring_chemicals = chemicals[
        chemicals["Expiry date"].apply(
            lambda x: is_expiring_soon(x) if pd.notna(x) else False
        )
    ]
    
    # Glassware that needs attention (broken or low quantity)
    glassware = st.session_state.lab_inventory["glassware"]
    low_glassware = glassware[
        (glassware["Stock on hand"] < 2) | 
        (glassware["Comment"].str.contains("broken", case=False, na=False))
    ]
    
    # Equipment that's not working
    equipment = st.session_state.lab_inventory["equipment"]
    non_working_equip = equipment[
        equipment["Status"].str.contains("not working", case=False, na=False)
    ]
    
    # Display alerts in tabs
    tab1, tab2, tab3, tab4 = st.tabs(["Low Stock Chemicals", "Expiring Soon", "Glassware Issues", "Equipment Issues"])
    
    with tab1:
        if not low_stock_chemicals.empty:
            st.dataframe(low_stock_chemicals, use_container_width=True)
        else:
            st.success("No chemicals below minimum stock levels")
    
    with tab2:
        if not expiring_chemicals.empty:
            st.dataframe(expiring_chemicals, use_container_width=True)
        else:
            st.success("No chemicals expiring soon")
    
    with tab3:
        if not low_glassware.empty:
            st.dataframe(low_glassware, use_container_width=True)
        else:
            st.success("No glassware issues")
    
    with tab4:
        if not non_working_equip.empty:
            st.dataframe(non_working_equip, use_container_width=True)
        else:
            st.success("All equipment is functional")

def export_inventory_report():
    """Generate and export a Word document report"""
    st.subheader("Export Inventory Report")
    
    # Report options
    col1, col2 = st.columns(2)
    
    with col1:
        report_type = st.selectbox(
            "Report Type",
            ["Full Inventory", "Chemicals Only", "Glassware Only", "Equipment Only", "Restocking List"]
        )
    
    with col2:
        include_comments = st.checkbox("Include Comments", value=True)
    
    # Generate report button
    if st.button("Generate Word Report"):
        document = Document()
        
        # Add title
        document.add_heading('Lab Inventory Report', 0)
        
        # Add metadata
        p = document.add_paragraph()
        p.add_run('Date: ').bold = True
        p.add_run(dt.datetime.now().strftime("%Y-%m-%d %H:%M"))
        
        p = document.add_paragraph()
        p.add_run('Generated by: ').bold = True
        p.add_run(st.session_state.username if 'username' in st.session_state else "System")
        
        # Add appropriate content based on report type
        if report_type in ["Full Inventory", "Chemicals Only"]:
            add_chemicals_to_doc(document, st.session_state.lab_inventory["chemicals"], include_comments)
        
        if report_type in ["Full Inventory", "Glassware Only"]:
            add_glassware_to_doc(document, st.session_state.lab_inventory["glassware"], include_comments)
        
        if report_type in ["Full Inventory", "Equipment Only"]:
            add_equipment_to_doc(document, st.session_state.lab_inventory["equipment"], include_comments)
        
        if report_type == "Restocking List":
            add_restocking_list_to_doc(document)
        
        # Save the document to a BytesIO stream
        file_stream = BytesIO()
        document.save(file_stream)
        file_stream.seek(0)
        
        # Download button
        st.download_button(
            label="Download Word Document",
            data=file_stream,
            file_name=f"lab_inventory_report_{dt.datetime.now().strftime('%Y%m%d')}.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )

def add_chemicals_to_doc(doc, df, include_comments):
    """Add chemicals section to Word document"""
    doc.add_heading('Chemicals and Reagents', level=1)
    
    table = doc.add_table(rows=1, cols=6)
    table.style = 'Table Grid'
    
    # Header row
    hdr_cells = table.rows[0].cells
    hdr_cells[0].text = 'Item'
    hdr_cells[1].text = 'Min Stock'
    hdr_cells[2].text = 'Monthly Usage'
    hdr_cells[3].text = 'Stock on Hand'
    hdr_cells[4].text = 'Expiry Date'
    if include_comments:
        hdr_cells[5].text = 'Comment'
    
    # Add data rows
    for _, row in df.iterrows():
        row_cells = table.add_row().cells
        row_cells[0].text = str(row['Item'])
        row_cells[1].text = str(row['Minimum stock'])
        row_cells[2].text = str(row['Monthly usage'])
        row_cells[3].text = str(row['Stock on hand'])
        row_cells[4].text = str(row['Expiry date']) if pd.notna(row['Expiry date']) else ""
        if include_comments:
            row_cells[5].text = str(row['Comment']) if pd.notna(row['Comment']) else ""
    
    doc.add_paragraph()

def add_glassware_to_doc(doc, df, include_comments):
    """Add glassware section to Word document"""
    doc.add_heading('Glassware', level=1)
    
    table = doc.add_table(rows=1, cols=3 if include_comments else 2)
    table.style = 'Table Grid'
    
    # Header row
    hdr_cells = table.rows[0].cells
    hdr_cells[0].text = 'Item'
    hdr_cells[1].text = 'Quantity'
    if include_comments:
        hdr_cells[2].text = 'Comment'
    
    # Add data rows
    for _, row in df.iterrows():
        row_cells = table.add_row().cells
        row_cells[0].text = str(row['Item'])
        row_cells[1].text = str(row['Stock on hand'])
        if include_comments:
            row_cells[2].text = str(row['Comment']) if pd.notna(row['Comment']) else ""
    
    doc.add_paragraph()

def add_equipment_to_doc(doc, df, include_comments):
    """Add equipment section to Word document"""
    doc.add_heading('Equipment', level=1)
    
    table = doc.add_table(rows=1, cols=4 if include_comments else 3)
    table.style = 'Table Grid'
    
    # Header row
    hdr_cells = table.rows[0].cells
    hdr_cells[0].text = 'Equipment'
    hdr_cells[1].text = 'Quantity'
    hdr_cells[2].text = 'Status'
    if include_comments:
        hdr_cells[3].text = 'Comment'
    
    # Add data rows
    for _, row in df.iterrows():
        row_cells = table.add_row().cells
        row_cells[0].text = str(row['Equipment'])
        row_cells[1].text = str(row['Stock at hand'])
        row_cells[2].text = str(row['Status'])
        if include_comments:
            row_cells[3].text = str(row['Comment']) if pd.notna(row['Comment']) else ""
    
    doc.add_paragraph()

def add_restocking_list_to_doc(doc):
    """Add restocking list to Word document"""
    doc.add_heading('Restocking List', level=1)
    doc.add_paragraph('Items that need to be reordered or require attention:')
    
    # Chemicals that are below minimum stock
    chemicals = st.session_state.lab_inventory["chemicals"]
    low_stock_chemicals = chemicals[chemicals["Stock on hand"] < chemicals["Minimum stock"]]
    
    if not low_stock_chemicals.empty:
        doc.add_heading('Chemicals Below Minimum Stock', level=2)
        table = doc.add_table(rows=1, cols=4)
        table.style = 'Table Grid'
        
        hdr_cells = table.rows[0].cells
        hdr_cells[0].text = 'Item'
        hdr_cells[1].text = 'Min Stock'
        hdr_cells[2].text = 'Current Stock'
        hdr_cells[3].text = 'Deficit'
        
        for _, row in low_stock_chemicals.iterrows():
            row_cells = table.add_row().cells
            row_cells[0].text = str(row['Item'])
            row_cells[1].text = str(row['Minimum stock'])
            row_cells[2].text = str(row['Stock on hand'])
            row_cells[3].text = str(row['Minimum stock'] - row['Stock on hand'])
    
    # Expiring soon chemicals
    expiring_chemicals = chemicals[
        chemicals["Expiry date"].apply(
            lambda x: is_expiring_soon(x) if pd.notna(x) else False
        )
    ]
    
    if not expiring_chemicals.empty:
        doc.add_heading('Chemicals Expiring Soon (within 3 months)', level=2)
        table = doc.add_table(rows=1, cols=3)
        table.style = 'Table Grid'
        
        hdr_cells = table.rows[0].cells
        hdr_cells[0].text = 'Item'
        hdr_cells[1].text = 'Expiry Date'
        hdr_cells[2].text = 'Current Stock'
        
        for _, row in expiring_chemicals.iterrows():
            row_cells = table.add_row().cells
            row_cells[0].text = str(row['Item'])
            row_cells[1].text = str(row['Expiry date'])
            row_cells[2].text = str(row['Stock on hand'])
    
    # Add other sections for glassware and equipment as needed