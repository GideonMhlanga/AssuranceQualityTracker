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
from sqlalchemy import text, Date, Numeric
from database import get_conn
from datetime import date, datetime


# Configuration
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
INVENTORY_CATEGORIES = {
    "chemicals": ["Reagent", "Solvent", "Buffer", "Indicator", "Acid", "Base", "Consumables"],
    "glassware": ["Volumetric", "Measuring", "Container", "Specialty"],
    "equipment": ["Instrument", "Device", "Tool", "Machine"]
}

# ======================
# Utility Functions
# ======================

def validate_date(date_str):
    """Validate date in YYYY-MM-DD format"""
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
        return True
    except ValueError:
        return False

def format_date_for_display(date_str):
    """Convert YYYY-MM-DD to Month Year (e.g., September 2028) for display"""
    try:
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        return date_obj.strftime("%B %Y")
    except:
        return date_str

def calculate_category_stats(category):
    """Calculate statistics for a given inventory category"""
    df = st.session_state.lab_inventory[category].copy()
    stats = {
        'total': len(df),
        'low': 0,
        'expired': 0,
        'damaged': 0,
        'issues': 0
    }
    
    if category == "chemicals":
        stats['low'] = len(df[df['status'] == 'Low'])
        stats['expired'] = len(df[df['status'] == 'Expired'])
    elif category == "glassware":
        stats['damaged'] = len(df[df['status'] == 'Damaged'])
    elif category == "equipment":
        stats['issues'] = len(df[df['status'].str.contains('need|repair', case=False, na=False)])
    
    return stats

def style_inventory_rows(row):
    """Apply styling to inventory rows based on status"""
    styles = [''] * len(row)
    
    # Ensure we have a status column to check
    if 'status' in row.index:
        if row['status'] == 'Low':
            styles = ['background-color: #FFF3CD'] * len(row)
        elif row['status'] == 'Expired':
            styles = ['background-color: #F8D7DA'] * len(row)
        elif row['status'] == 'Damaged':
            styles = ['background-color: #F8D7DA'] * len(row)
        elif row['status'] in ['Needs service', 'In repair']:
            styles = ['background-color: #FFF3CD'] * len(row)

    # Format numeric values to 2 decimal places
    if 'current' in row.index and pd.notna(row['current']):
        row['current'] = f"{float(row['current']):.2f}"
    if 'minimum' in row.index and pd.notna(row['minimum']):
        row['minimum'] = f"{float(row['minimum']):.2f}"
    if 'monthly' in row.index and pd.notna(row['monthly']):
        row['monthly'] = f"{float(row['monthly']):.2f}"
    
    return styles

def calculate_months_of_stock(row):
    """Calculate months of remaining stock"""
    try:
        if pd.notna(row['monthly']) and float(row['monthly']) > 0:
            return float(row['current']) / float(row['monthly'])
    except (TypeError, ValueError, KeyError):
        pass
    return None

# ======================
# Database Functions
# ======================

def init_inventory_tables():
    """Initialize inventory tables in the database if they don't exist"""
    conn = get_conn()
    if conn:
        try:
            # SQL commands to create tables with proper numeric precision
            table_creation_queries = [
                """
                CREATE TABLE IF NOT EXISTS chemicals (
                    id TEXT PRIMARY KEY,
                    item TEXT UNIQUE NOT NULL,
                    category TEXT NOT NULL,
                    minimum NUMERIC(10,2),
                    current NUMERIC(10,2),
                    monthly NUMERIC(10,2),
                    unit TEXT,
                    expiry DATE,
                    location TEXT,
                    supplier TEXT,
                    comment TEXT,
                    status TEXT,
                    "Months Stock" NUMERIC(10,2),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS glassware (
                    id TEXT PRIMARY KEY,
                    item TEXT UNIQUE NOT NULL,
                    category TEXT NOT NULL,
                    current INTEGER,
                    unit TEXT,
                    location TEXT,
                    comment TEXT,
                    status TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS equipment (
                    id TEXT PRIMARY KEY,
                    item TEXT UNIQUE NOT NULL,
                    category TEXT NOT NULL,
                    current INTEGER,
                    unit TEXT,
                    location TEXT,
                    status TEXT,
                    last_calibration TEXT,
                    comment TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            ]
            
            # Execute each table creation query
            for query in table_creation_queries:
                conn.execute(text(query))
            
            # Check if Months Stock column exists and has correct type
            result = conn.execute(text("""
                SELECT data_type, numeric_precision, numeric_scale 
                FROM information_schema.columns 
                WHERE table_name='chemicals' AND column_name='Months Stock'
            """)).fetchone()
            
            # Only alter if column doesn't exist or has wrong type
            if not result or result[0] != 'numeric' or result[1] != 10 or result[2] != 2:
                conn.execute(text("""
                    ALTER TABLE chemicals 
                    ALTER COLUMN "Months Stock" TYPE NUMERIC(10,2),
                    ALTER COLUMN minimum TYPE NUMERIC(10,2),
                    ALTER COLUMN current TYPE NUMERIC(10,2),
                    ALTER COLUMN monthly TYPE NUMERIC(10,2)
                """))
                conn.commit()

            # Create triggers for each table
            for table in ["chemicals", "glassware", "equipment"]:
                conn.execute(text(f"""
                    CREATE OR REPLACE FUNCTION update_{table}_timestamp()
                    RETURNS TRIGGER AS $$
                    BEGIN
                        NEW.updated_at = CURRENT_TIMESTAMP;
                        RETURN NEW;
                    END;
                    $$ LANGUAGE plpgsql;
                """))
                
                conn.execute(text(f"""
                    DROP TRIGGER IF EXISTS trigger_update_{table}_timestamp ON {table};
                    CREATE TRIGGER trigger_update_{table}_timestamp
                    BEFORE UPDATE ON {table}
                    FOR EACH ROW EXECUTE FUNCTION update_{table}_timestamp();
                """))
            
            conn.commit()
        except Exception as e:
            conn.rollback()
            st.error(f"Error initializing tables: {e}")
            raise e
        finally:
            conn.close()
                
def load_from_db():
    """Load all inventory data from PostgreSQL"""
    inventory = {
        "chemicals": pd.DataFrame(),
        "glassware": pd.DataFrame(),
        "equipment": pd.DataFrame()
    }
    
    conn = get_conn()
    if conn:
        try:
            inventory["chemicals"] = pd.read_sql(text("SELECT * FROM chemicals"), conn)
            inventory["glassware"] = pd.read_sql(text("SELECT * FROM glassware"), conn)
            inventory["equipment"] = pd.read_sql(text("SELECT * FROM equipment"), conn)
        except Exception as e:
            st.error(f"Error loading inventory data: {e}")
        finally:
            conn.close()
    return inventory

def save_to_db(category, df):
    """Save a DataFrame back to the database with proper date and numeric handling"""
    conn = get_conn()
    if conn:
        try:
            # Make a copy to avoid modifying the original
            df_to_save = df.copy()
            
            # Convert dates if this is the chemicals table
            if category == "chemicals" and 'expiry' in df_to_save.columns:
                df_to_save['expiry'] = pd.to_datetime(
                    df_to_save['expiry'], 
                    format='%Y-%m-%d', 
                    errors='coerce'
                )
                # Drop rows with invalid dates
                df_to_save = df_to_save[~df_to_save['expiry'].isna()]
            
            # Round numeric columns to 2 decimal places
            if category == "chemicals":
                numeric_cols = ['minimum', 'current', 'monthly', 'Months Stock']
                for col in numeric_cols:
                    if col in df_to_save.columns:
                        df_to_save[col] = df_to_save[col].apply(
                            lambda x: round(float(x), 2) if pd.notna(x) else None
                        )
            
            # Ensure Months Stock is calculated if missing
            if category == "chemicals" and 'Months Stock' not in df_to_save.columns:
                df_to_save['Months Stock'] = df_to_save.apply(
                    lambda row: round(calculate_months_of_stock(row), 2), 
                    axis=1
                )
            
            # Delete existing data
            conn.execute(text(f"DELETE FROM {category}"))
            
            # Insert new data
            df_to_save.to_sql(
                category, 
                conn, 
                if_exists='append', 
                index=False,
                dtype={
                    'expiry': Date,
                    'Months Stock': Numeric(10,2),
                    'minimum': Numeric(10,2),
                    'current': Numeric(10,2),
                    'monthly': Numeric(10,2)
                } if category == "chemicals" else None
            )
            conn.commit()
        except Exception as e:
            conn.rollback()
            st.error(f"Error saving {category} data: {e}")
            raise e
        finally:
            conn.close()

def insert_item(category, item_data):
    """Insert a new item into the specified category with proper date handling"""
    conn = get_conn()
    if conn:
        try:
            # Validate date format if needed
            if category == "chemicals" and 'expiry' in item_data:
                if not validate_date(item_data['expiry']):
                    st.error("Invalid date format. Please use YYYY-MM-DD format.")
                    return None
            
            columns = ', '.join(item_data.keys())
            placeholders = ', '.join([':%s' % k for k in item_data.keys()])
            
            query = text(f"""
                INSERT INTO {category} ({columns})
                VALUES ({placeholders})
                RETURNING *
            """)
            
            result = conn.execute(query, item_data).fetchone()
            conn.commit()
            return result
        except Exception as e:
            conn.rollback()
            st.error(f"Error inserting item: {e}")
            return None
        finally:
            conn.close()
    return None

# ======================
# Core Functions
# ======================

def initialize_inventory_data():
    """Initialize inventory data structure with PostgreSQL"""
    try:
        # First initialize tables
        init_inventory_tables()
        
        # Then load data from database
        st.session_state.lab_inventory = load_from_db()
        
        # Check if we need to load sample data
        if all(df.empty for df in st.session_state.lab_inventory.values()):
            st.warning("No inventory data found - loading sample data...")
            load_sample_data()
            
            # Save sample data to database
            for category, df in st.session_state.lab_inventory.items():
                save_to_db(category, df)
            
            # Reload from database to ensure consistency
            st.session_state.lab_inventory = load_from_db()
        
        # Ensure status is calculated for all items
        check_restock_status()
        
    except Exception as e:
        st.error(f"Error initializing inventory data: {e}")
        st.warning("Falling back to sample data...")
        load_sample_data()

def load_sample_data():
    """Load sample inventory data with YYYY-MM-DD date formats"""
    # Sample chemicals with all required fields
    sample_chemicals = [
        {
            "id": "CHEM-001", 
            "item": "DPD#4 tablets", 
            "category": "Reagent", 
            "minimum": 750.0, 
            "current": 410.0, 
            "monthly": 125.0, 
            "unit": "tablets", 
            "expiry": "2028-09-01", 
            "location": "Shelf A1", 
            "supplier": "Sigma-Aldrich", 
            "comment": "", 
            "status": "Low",
            "Months Stock": 3.28
        },
        {
            "id": "CHEM-002", 
            "item": "0.1N Sodium Hydroxide", 
            "category": "Base", 
            "minimum": 5.0, 
            "current": 3.7, 
            "monthly": 1.2, 
            "unit": "L", 
            "expiry": "2025-05-01", 
            "location": "Cabinet B2", 
            "supplier": "Fisher Scientific", 
            "comment": "Corrosive", 
            "status": "OK",
            "Months Stock": 3.08
        },
        {
            "id": "CHEM-003",
            "item": "Ethanol 95%",
            "category": "Solvent",
            "minimum": 10.0,
            "current": 15.5,
            "monthly": 5.0,
            "unit": "L",
            "expiry": "2026-12-31",
            "location": "Flammable Cabinet",
            "supplier": "VWR",
            "comment": "Flammable liquid",
            "status": "OK",
            "Months Stock": 3.1
        }
    ]

    # Sample glassware with all required fields
    sample_glassware = [
        {
            "id": "GLAS-001", 
            "item": "1000ml volumetric flask", 
            "category": "Volumetric", 
            "current": 5, 
            "unit": "pieces", 
            "location": "Cabinet 3", 
            "comment": "", 
            "status": "OK"
        },
        {
            "id": "GLAS-002", 
            "item": "50ml burette", 
            "category": "Measuring", 
            "current": 2, 
            "unit": "pieces", 
            "location": "Drawer 1", 
            "comment": "1 needs repair", 
            "status": "Damaged"
        },
        {
            "id": "GLAS-003",
            "item": "250ml beaker",
            "category": "Container",
            "current": 12,
            "unit": "pieces",
            "location": "Shelf B2",
            "comment": "",
            "status": "OK"
        }
    ]
    
    # Sample equipment with all required fields
    sample_equipment = [
        {
            "id": "EQUIP-001", 
            "item": "pH meter", 
            "category": "Instrument", 
            "current": 1, 
            "unit": "units", 
            "location": "Bench 2", 
            "status": "Working", 
            "last_calibration": "2024-01-01", 
            "comment": ""
        },
        {
            "id": "EQUIP-002", 
            "item": "Analytical balance", 
            "category": "Instrument", 
            "current": 2, 
            "unit": "units", 
            "location": "Bench 1", 
            "status": "Needs service", 
            "last_calibration": "2024-03-01", 
            "comment": "Annual maintenance due"
        },
        {
            "id": "EQUIP-003",
            "item": "Centrifuge",
            "category": "Machine",
            "current": 1,
            "unit": "units",
            "location": "Lab Station 3",
            "status": "Working",
            "last_calibration": "2024-02-15",
            "comment": "RPM needs verification"
        }
    ]
    
    # Create DataFrames with all required columns
    st.session_state.lab_inventory = {
        "chemicals": pd.DataFrame(sample_chemicals),
        "glassware": pd.DataFrame(sample_glassware),
        "equipment": pd.DataFrame(sample_equipment)
    }

def check_restock_status():
    """Check and update inventory status"""
    try:
        chem_df = st.session_state.lab_inventory["chemicals"].copy()
        
        if not chem_df.empty:
            # Initialize status column if it doesn't exist
            if 'status' not in chem_df.columns:
                chem_df['status'] = 'OK'
            
            if not pd.api.types.is_datetime64_any_dtype(chem_df["expiry"]):
                chem_df["expiry"] = pd.to_datetime(chem_df["expiry"], errors='coerce')
            
            chem_df["status"] = np.where(
                chem_df["current"] < chem_df["minimum"],
                "Low",
                "OK"
            )
            
            today = pd.to_datetime(dt.datetime.now().date())
            chem_df.loc[(chem_df["expiry"] < today) & (~chem_df["expiry"].isna()), "status"] = "Expired"
            
            st.session_state.lab_inventory["chemicals"] = chem_df
    except Exception as e:
        st.error(f"Error checking restock status: {e}")
        
def create_combined_df():
    """Create combined dataframe of all inventory with proper column handling"""
    chem = st.session_state.lab_inventory["chemicals"].copy()
    glass = st.session_state.lab_inventory["glassware"].copy()
    equip = st.session_state.lab_inventory["equipment"].copy()
    
    # Standardize columns
    chem["type"] = "Chemical"
    glass["type"] = "Glassware"
    equip["type"] = "Equipment"
    
    # Define all possible columns we might want to include
    all_columns = [
        "id", "item", "type", "category", "current", 
        "minimum", "monthly", "unit", "status", "location"
    ]
    
    # Function to get only existing columns from a dataframe
    def get_existing_columns(df, columns):
        return [col for col in columns if col in df.columns]
    
    # Get existing columns for each dataframe
    chem_cols = get_existing_columns(chem, all_columns)
    glass_cols = get_existing_columns(glass, all_columns)
    equip_cols = get_existing_columns(equip, all_columns)
    
    # Combine relevant columns
    combined = pd.concat([
        chem[chem_cols],
        glass[glass_cols],
        equip[equip_cols]
    ])
    
    # Add default values for any missing critical columns
    if 'status' not in combined.columns:
        combined['status'] = 'OK'
    if 'current' not in combined.columns:
        combined['current'] = 0
    if 'unit' not in combined.columns:
        combined['unit'] = 'units'
    
    # Add months of stock for chemicals if possible
    if 'monthly' in combined.columns and 'current' in combined.columns:
        combined['Months Stock'] = combined.apply(
            lambda row: calculate_months_of_stock(row) if row['type'] == 'Chemical' else None, 
            axis=1
        )
    
    return combined.fillna("")

# ======================
# UI Functions
# ======================

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

def display_dashboard():
    """Display inventory dashboard"""
    st.title("🔬 Laboratory Inventory Management System")
    
    # Initialize session state if not already done
    if 'lab_inventory' not in st.session_state:
        initialize_inventory_data()
    
    st.subheader("Inventory Overview")
    
    try:
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
        
        if combined_df.empty:
            st.error("Inventory is empty - please check database connection")
        else:
            # Reset index to ensure uniqueness and convert to styled DataFrame
            styled_df = (
                combined_df
                .reset_index(drop=True)  # Ensure unique index
                .style
                .apply(style_inventory_rows, axis=1)
            )
            
            st.dataframe(
                styled_df,
                use_container_width=True,
                height=400
            )
            
    except Exception as e:
        st.error(f"Error displaying dashboard: {str(e)}")
        st.button("Reload Data", on_click=initialize_inventory_data)

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
    """Chemical inventory management with enhanced date handling and validation"""
    # Load and prepare data
    df = st.session_state.lab_inventory["chemicals"].copy()
    
    # Convert expiry dates to consistent YYYY-MM-DD string format
    df = normalize_expiry_dates(df)
    
    # Calculate months of stock
    df['Months Stock'] = df.apply(calculate_months_of_stock, axis=1)
    
    # Add new chemical form
    add_new_chemical_form(df)
    
    # Edit existing chemicals
    edit_existing_chemicals(df)

def normalize_expiry_dates(df):
    """Ensure expiry dates are in YYYY-MM-DD string format"""
    if not df.empty and 'expiry' in df.columns:
        try:
            if pd.api.types.is_datetime64_any_dtype(df['expiry']):
                df['expiry'] = df['expiry'].dt.strftime('%Y-%m-%d')
            else:
                # Try parsing any date format and convert to YYYY-MM-DD
                df['expiry'] = pd.to_datetime(df['expiry'], errors='coerce').dt.strftime('%Y-%m-%d')
        except Exception as e:
            st.error(f"Error processing expiry dates: {str(e)}")
    return df

def add_new_chemical_form(df):
    """Form to add new chemicals with validation"""
    with st.expander("➕ Add New Chemical", expanded=False):
        with st.form("add_chemical_form", clear_on_submit=True):
            cols = st.columns([1, 2, 1])
            
            with cols[0]:  # Identification
                new_id = generate_chemical_id(df)
                st.text_input("ID", value=new_id, disabled=True)
                item_name = st.text_input("Item Name*", key="new_chem_name")
                category = st.selectbox("Category*", INVENTORY_CATEGORIES["chemicals"])
            
            with cols[1]:  # Stock information
                min_stock = st.number_input("Minimum Stock*", min_value=0.0, step=0.1, format="%.2f")
                monthly_usage = st.number_input("Monthly Usage*", min_value=0.0, step=1.0, format="%.2f")
                current_stock = st.number_input("Current Stock*", min_value=0.0, step=0.1, format="%.2f")
                unit = st.selectbox("Unit*", ["g", "kg", "L", "mL", "tablets", "bottles", "satchets", "pieces"])
            
            with cols[2]:  # Additional info
                expiry = st.date_input(
                    "Expiry Date*",
                    min_value=date.today(),  # This is where it goes
                    help="Select expiry date from calendar"
                ).strftime('%Y-%m-%d')
                location = st.text_input("Storage Location*")
                supplier = st.text_input("Supplier")
            
            submitted = st.form_submit_button("Add Chemical")
            
            if submitted:
                if not all([item_name, category, min_stock, monthly_usage, current_stock, unit, location]):
                    st.error("Please fill all required fields (marked with *)")
                    st.stop()
                
                if is_duplicate_item(df, item_name):
                    st.error(f"An item with the name '{item_name}' already exists")
                    st.stop()
                
                add_chemical_to_inventory(df, new_id, {
                    "item": item_name,
                    "category": category,
                    "minimum": min_stock,
                    "current": current_stock,
                    "monthly": monthly_usage,
                    "unit": unit,
                    "expiry": expiry,
                    "location": location,
                    "supplier": supplier,
                    "comment": "",
                    "status": "Low" if current_stock < min_stock else "OK"
                })

def generate_chemical_id(df):
    """Generate a new chemical ID in CHEM-XXX format"""
    return f"CHEM-{len(df)+1:03d}"

def is_duplicate_item(df, item_name):
    """Check if item name already exists (case-insensitive)"""
    return item_name.lower() in df['item'].str.lower().tolist()

def add_chemical_to_inventory(df, new_id, item_data):
    """Add new chemical to inventory and refresh data"""
    item_data["id"] = new_id
    result = insert_item("chemicals", item_data)
    if result:
        st.session_state.lab_inventory["chemicals"] = pd.read_sql(
            text("SELECT * FROM chemicals"), 
            get_conn()
        )
        st.success(f"Added {item_data['item']} to inventory")
        st.rerun()

def edit_existing_chemicals(df):
    """Edit existing chemicals with data editor including styling and proper numeric handling"""
    st.subheader("Current Chemical Inventory")
    
    # Make a working copy and ensure 'expiry' column exists
    editable_df = df.copy()
    
    # Initialize 'expiry' column if it doesn't exist
    if 'expiry' not in editable_df.columns:
        editable_df['expiry'] = pd.NaT
    
    # Convert expiry to datetime, handling errors
    try:
        editable_df['expiry'] = pd.to_datetime(editable_df['expiry'], errors='coerce')
    except Exception as e:
        st.error(f"Error processing expiry dates: {str(e)}")
        editable_df['expiry'] = pd.NaT
    
    # Calculate and round Months Stock to 2 decimal places
    editable_df['Months Stock'] = editable_df.apply(
        lambda row: round(calculate_months_of_stock(row), 2) 
        if calculate_months_of_stock(row) is not None 
        else None,
        axis=1
    )
    
    # Round numeric columns to 2 decimal places
    numeric_cols = ['minimum', 'current', 'monthly']
    for col in numeric_cols:
        if col in editable_df.columns:
            editable_df[col] = editable_df[col].apply(
                lambda x: round(float(x), 2) if pd.notna(x) else None
            )
    
    # Configure columns for editing
    column_config = {
        "item": st.column_config.TextColumn("Item Name", required=True),
        "category": st.column_config.SelectboxColumn(
            "Category",
            options=INVENTORY_CATEGORIES["chemicals"],
            required=True
        ),
        "minimum": st.column_config.NumberColumn(
            "Minimum Stock", 
            required=True,
            format="%.2f",
            step=0.01
        ),
        "current": st.column_config.NumberColumn(
            "Current Stock",
            required=True,
            format="%.2f",
            step=0.01
        ),
        "monthly": st.column_config.NumberColumn(
            "Monthly Usage",
            required=True,
            format="%.2f",
            step=0.01
        ),
        "unit": st.column_config.SelectboxColumn(
            "Unit",
            options=["g", "kg", "L", "mL", "tablets", "bottles", "satchets", "pieces"],
            required=True
        ),
        "expiry": st.column_config.DateColumn(
            "Expiry Date",
            format="YYYY-MM-DD",
            min_value=date.today(),
            required=True
        ),
        "location": st.column_config.TextColumn("Storage Location", required=True),
        "status": st.column_config.SelectboxColumn(
            "Status",
            options=["OK", "Low", "Expired"],
            required=True
        ),
        "Months Stock": st.column_config.NumberColumn(
            "Months Stock",
            format="%.2f",
            disabled=True
        )
    }
    
    # Display styled read-only version as reference
    st.caption("Color Key: 🟡 Low Stock | 🔴 Expired")
    st.dataframe(
        editable_df.style.apply(style_inventory_rows, axis=1),
        use_container_width=True,
        hide_index=True
    )
    
    # Display editable version
    with st.expander("✏️ Edit Inventory", expanded=True):
        edited_df = st.data_editor(
            editable_df,
            num_rows="dynamic",
            use_container_width=True,
            disabled=["id", "Months Stock"],
            column_config=column_config,
            key="chemical_editor"
        )
    
    # Handle save action
    if st.button("💾 Save All Changes", type="primary"):
        # Convert dates back to string format
        if 'expiry' in edited_df.columns:
            edited_df['expiry'] = edited_df['expiry'].dt.strftime('%Y-%m-%d')
        
        # Round numeric columns again in case manual edits occurred
        for col in numeric_cols:
            if col in edited_df.columns:
                edited_df[col] = edited_df[col].apply(
                    lambda x: round(float(x), 2) if pd.notna(x) else None
                )
        
        # Recalculate Months Stock with updated values
        edited_df['Months Stock'] = edited_df.apply(
            lambda row: round(calculate_months_of_stock(row), 2) 
            if calculate_months_of_stock(row) is not None 
            else None,
            axis=1
        )
        
        # Validate required fields
        required_fields = ['item', 'category', 'minimum', 'current', 
                         'monthly', 'unit', 'expiry', 'location']
        missing_fields = [field for field in required_fields 
                        if field in edited_df.columns and edited_df[field].isna().any()]
        
        if missing_fields:
            st.error(f"Missing values in required fields: {', '.join(missing_fields)}")
            st.stop()
        
        # Check for invalid dates
        if 'expiry' in edited_df.columns and edited_df['expiry'].isna().any():
            st.error("Some dates are invalid. Please use YYYY-MM-DD format.")
            st.stop()
        
        # Update status based on new values
        edited_df['status'] = np.where(
            edited_df['current'] < edited_df['minimum'],
            "Low",
            np.where(
                pd.to_datetime(edited_df['expiry']) < pd.to_datetime('today'),
                "Expired",
                "OK"
            )
        )
        
        # Update database
        save_to_db("chemicals", edited_df)
        
        # Refresh session state
        st.session_state.lab_inventory["chemicals"] = pd.read_sql(
            text("SELECT * FROM chemicals"), 
            get_conn()
        )
        
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
                item_name = st.text_input("Item Name", key="new_glass_name")
                category = st.selectbox("Category", INVENTORY_CATEGORIES["glassware"])
            with cols[1]:
                current_stock = st.number_input("Quantity", min_value=0, step=1, format = "%2.f")
                unit = st.selectbox("Unit", ["pieces", "sets", "units"])
            with cols[2]:
                location = st.text_input("Storage Location")
                comment = st.text_input("Comments")
            
            if st.form_submit_button("Add Glassware"):
                # Check for duplicate item name
                existing_items = df['item'].str.lower().tolist()
                if item_name.lower() in existing_items:
                    st.error(f"Glassware with the name '{item_name}' already exists in Inventory")
                else:
                    new_item = {
                        "id": new_id,
                        "item": item_name,
                        "category": category,
                        "current": current_stock,
                        "unit": unit,
                        "location": location,
                        "comment": comment,
                        "status": "OK"
                    }
                    
                    # Insert into database
                    result = insert_item("glassware", new_item)
                    if result:
                        st.session_state.lab_inventory["glassware"] = pd.read_sql(
                            text("SELECT * FROM glassware"), 
                            get_conn()
                        )
                        st.success(f"Added {item_name} to inventory")
                        st.rerun()
    
    # Edit existing glassware
    st.subheader("Current Glassware Inventory")
    edited_df = st.data_editor(
        df,
        num_rows="dynamic",
        use_container_width=True,
        disabled=["id"],
        column_config={
            "status": st.column_config.SelectboxColumn(
                "Status",
                options=["OK", "Damaged"],
                required=True
            )
        }
    )
    
    if st.button("Save Glassware Changes"):
        # Update database
        save_to_db("glassware", edited_df)
        
        # Refresh session state
        st.session_state.lab_inventory["glassware"] = pd.read_sql(
            text("SELECT * FROM glassware"), 
            get_conn()
        )
        
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
                current_stock = st.number_input("Quantity", min_value=0, step=1, format="%.2f")
                unit = st.selectbox("Unit", ["units", "sets"])
                last_calibration = st.text_input("Last Calibration (YYYY-MM-DD)", placeholder="2024-01-01")
            with cols[2]:
                location = st.text_input("Storage Location")
                status = st.selectbox("Status", ["Working", "Needs service", "In repair"])
                comment = st.text_input("Comments")
            
            if st.form_submit_button("Add Equipment"):
                # Validate calibration date
                if last_calibration and not validate_date(last_calibration):
                    st.error("Invalid date format. Please use YYYY-MM-DD format.")
                    st.stop()
                
                # Check for duplicate item name
                existing_items = df['item'].str.lower().tolist()
                if item_name.lower() in existing_items:
                    st.error(f"An equipment item with the name '{item_name}' already exists in Inventory!")
                else:
                    new_item = {
                        "id": new_id,
                        "item": item_name,
                        "category": category,
                        "current": current_stock,
                        "unit": unit,
                        "location": location,
                        "status": status,
                        "last_calibration": last_calibration,
                        "comment": comment
                    }
                    
                    # Insert into database
                    result = insert_item("equipment", new_item)
                    if result:
                        st.session_state.lab_inventory["equipment"] = pd.read_sql(
                            text("SELECT * FROM equipment"), 
                            get_conn()
                        )
                        st.success(f"Added {item_name} to inventory")
                        st.rerun()
    
    # Edit existing equipment
    st.subheader("Current Equipment Inventory")
    edited_df = st.data_editor(
        df,
        num_rows="dynamic",
        use_container_width=True,
        disabled=["id"],
        column_config={
            "status": st.column_config.SelectboxColumn(
                "Status",
                options=["Working", "Needs service", "In repair"],
                required=True
            ),
            "last_calibration": st.column_config.TextColumn(
                "Last Calibration",
                help="Format: YYYY-MM-DD",
                validate="^[0-9]{4}-(0[1-9]|1[0-2])-(0[1-9]|[1-2][0-9]|3[0-1])$"
            )
        }
    )
    
    if st.button("Save Equipment Changes"):
        # Validate dates before saving
        if 'last_calibration' in edited_df.columns:
            edited_df['last_calibration'] = pd.to_datetime(
                edited_df['last_calibration'], 
                format='%Y-%m-%d', 
                errors='coerce'
            )
            invalid_dates = edited_df[edited_df['last_calibration'].isna()]
            if not invalid_dates.empty:
                st.error("Some calibration dates are invalid. Please use YYYY-MM-DD format.")
                st.stop()
        
        # Update database
        save_to_db("equipment", edited_df)
        
        # Refresh session state
        st.session_state.lab_inventory["equipment"] = pd.read_sql(
            text("SELECT * FROM equipment"), 
            get_conn()
        )
        
        st.success("Changes saved successfully!")
        st.rerun()

def display_analytics():
    """Inventory analytics and visualization"""
    st.subheader("Inventory Analytics")
    
    # Create combined dataframe
    combined_df = create_combined_df()
    
    if combined_df.empty:
        st.warning("No inventory data available")
        return
    
    # Visualization options
    viz_option = st.selectbox(
        "Select Visualization",
        ["Status Distribution", "Stock Levels", "Expiry Timeline"]
    )
    
    if viz_option == "Status Distribution":
        fig = px.pie(
            combined_df, 
            names='status', 
            title='Inventory Status Distribution',
            color='status',
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
            x='category',
            y='current',
            color='status',
            title='Stock Levels by Category',
            hover_data=['item', 'unit'],
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
        if 'chemicals' not in st.session_state.lab_inventory:
            st.warning("No chemical data available")
            return
            
        chem_df = st.session_state.lab_inventory["chemicals"].copy()
        if 'expiry' not in chem_df.columns:
            st.warning("No expiry data available for chemicals")
            return
            
        chem_df['expiry'] = pd.to_datetime(chem_df['expiry'], format='%Y-%m-%d', errors='coerce')
        chem_df = chem_df.dropna(subset=['expiry'])
        
        if not chem_df.empty:
            chem_df['Days Until Expiry'] = (chem_df['expiry'] - pd.to_datetime('today')).dt.days
            # Format dates for display
            chem_df['Expiry Display'] = chem_df['expiry'].dt.strftime('%b %Y')
            fig = px.scatter(
                chem_df,
                x='expiry',
                y='item',
                size='current',
                color='Days Until Expiry',
                hover_data=['minimum', 'location'],
                title='Chemical Expiry Timeline',
                labels={'expiry': 'Expiry Date', 'Expiry Display': 'Expiry Date'}
            )
            fig.update_xaxes(tickformat="%b %Y")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("No chemicals with valid expiry dates found")

def display_alerts():
    """Display inventory alerts"""
    st.subheader("Inventory Alerts")
    
    # Chemical alerts
    chem_df = st.session_state.lab_inventory["chemicals"]
    
    # Initialize empty DataFrames for alerts
    low_stock = pd.DataFrame()
    expired = pd.DataFrame()
    
    if not chem_df.empty and 'status' in chem_df.columns:
        low_stock = chem_df[chem_df["status"] == "Low"]
        expired = chem_df[chem_df["status"] == "Expired"]
    
    if not low_stock.empty:
        st.warning(f"🧪 {len(low_stock)} Chemicals Need Restocking")
        st.dataframe(
            low_stock[["id", "item", "current", "minimum", "unit", "location"]],
            hide_index=True
        )
    
    if not expired.empty:
        st.error(f"⏳ {len(expired)} Expired Chemicals")
        st.dataframe(
            expired[["id", "item", "expiry", "location"]],
            hide_index=True
        )
    
    # Glassware alerts
    glass_df = st.session_state.lab_inventory["glassware"]
    damaged = pd.DataFrame()
    
    if not glass_df.empty and 'status' in glass_df.columns:
        damaged = glass_df[glass_df["status"] == "Damaged"]
    
    if not damaged.empty:
        st.error(f"🔧 {len(damaged)} Damaged Glassware Items")
        st.dataframe(
            damaged[["id", "item", "comment", "location"]],
            hide_index=True
        )
    
    # Equipment alerts
    equip_df = st.session_state.lab_inventory["equipment"]
    issues = pd.DataFrame()
    
    if not equip_df.empty and 'status' in equip_df.columns:
        issues = equip_df[equip_df["status"].str.contains("need|repair", case=False, na=False)]
    
    if not issues.empty:
        st.error(f"⚠️ {len(issues)} Equipment Issues")
        st.dataframe(
            issues[["id", "item", "status", "last_calibration"]],
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
                if col == 'expiry' and pd.notna(value):
                    row_cells[i].text = format_date_for_display(value)
                else:
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
                if col == 'last_calibration' and pd.notna(value):
                    row_cells[i].text = format_date_for_display(value)
                else:
                    row_cells[i].text = str(value)
    else:
        document.add_paragraph("No equipment items in inventory")

def add_restocking_list(document):
    """Add restocking list to Word document"""
    document.add_heading('Restocking List', level=1)
    
    chem_df = st.session_state.lab_inventory["chemicals"]
    low_stock = chem_df[chem_df["status"] == "Low"]
    
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
            row_cells[0].text = str(row["id"])
            row_cells[1].text = str(row["item"])
            row_cells[2].text = str(row["current"])
            row_cells[3].text = str(row["minimum"])
            row_cells[4].text = str(row["minimum"] - row["current"])
    else:
        document.add_paragraph("No items currently need restocking")

def add_expiry_report(document):
    """Add expiry report to Word document"""
    document.add_heading('Expiry Report', level=1)
    
    chem_df = st.session_state.lab_inventory["chemicals"]
    chem_df['expiry'] = pd.to_datetime(chem_df['expiry'], format='%Y-%m-%d', errors='coerce')
    expiring = chem_df[~chem_df['expiry'].isna()]
    
    if not expiring.empty:
        document.add_paragraph('Chemicals with expiry dates:')
        table = document.add_table(rows=1, cols=4, style='Table Grid')
        hdr_cells = table.rows[0].cells
        hdr_cells[0].text = "ID"
        hdr_cells[1].text = "Item"
        hdr_cells[2].text = "Expiry Date"
        hdr_cells[3].text = "Days Until Expiry"
        
        for _, row in expiring.iterrows():
            days_until = (row['expiry'] - pd.to_datetime('today')).days
            row_cells = table.add_row().cells
            row_cells[0].text = str(row["id"])
            row_cells[1].text = str(row["item"])
            row_cells[2].text = format_date_for_display(row['expiry'].strftime('%Y-%m-%d'))
            row_cells[3].text = str(days_until)
    else:
        document.add_paragraph("No chemicals with expiry dates in inventory")

def export_excel(report_type):
    """Generate Excel report"""
    if report_type == "Full Inventory":
        df = create_combined_df()
    elif report_type == "Chemicals Only":
        df = st.session_state.lab_inventory["chemicals"].copy()
    elif report_type == "Restocking List":
        chem_df = st.session_state.lab_inventory["chemicals"].copy()
        df = chem_df[chem_df["status"] == "Low"]
        if not df.empty:
            df['Deficit'] = df['minimum'] - df['current']
    elif report_type == "Expiry Report":
        chem_df = st.session_state.lab_inventory["chemicals"].copy()
        chem_df['expiry'] = pd.to_datetime(chem_df['expiry'], format='%Y-%m-%d', errors='coerce')
        df = chem_df[~chem_df['expiry'].isna()]
        if not df.empty:
            df['Days Until Expiry'] = (df['expiry'] - pd.to_datetime('today')).dt.days
    
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
        df = chem_df[chem_df["status"] == "Low"]
        if not df.empty:
            df['Deficit'] = df['minimum'] - df['current']
    elif report_type == "Expiry Report":
        chem_df = st.session_state.lab_inventory["chemicals"].copy()
        chem_df['expiry'] = pd.to_datetime(chem_df['expiry'], format='%Y-%m-%d', errors='coerce')
        df = chem_df[~chem_df['expiry'].isna()]
        if not df.empty:
            df['Days Until Expiry'] = (df['expiry'] - pd.to_datetime('today')).dt.days
    
    csv = df.to_csv(index=False).encode('utf-8')
    
    st.download_button(
        label="Download CSV Report",
        data=csv,
        file_name=f"lab_inventory_{report_type.replace(' ', '_')}.csv",
        mime="text/csv"
    )

def send_email_report(recipient, subject, message, report_type):
    """Send inventory report via email"""
    # Create email message
    msg = MIMEMultipart()
    msg['From'] = st.secrets["email"]["username"]
    msg['To'] = recipient
    msg['Subject'] = subject
    
    # Add message body
    msg.attach(MIMEText(message, 'plain'))
    
    # Create attachment based on report type
    if report_type == "Full Inventory":
        df = create_combined_df()
        filename = "full_inventory.csv"
        attachment = MIMEBase('application', 'octet-stream')
        attachment.set_payload(df.to_csv(index=False).encode('utf-8'))
    elif report_type == "Chemicals Only":
        df = st.session_state.lab_inventory["chemicals"].copy()
        filename = "chemicals_inventory.csv"
        attachment = MIMEBase('application', 'octet-stream')
        attachment.set_payload(df.to_csv(index=False).encode('utf-8'))
    elif report_type == "Restocking List":
        chem_df = st.session_state.lab_inventory["chemicals"].copy()
        df = chem_df[chem_df["status"] == "Low"]
        if not df.empty:
            df['Deficit'] = df['minimum'] - df['current']
        filename = "restocking_list.csv"
        attachment = MIMEBase('application', 'octet-stream')
        attachment.set_payload(df.to_csv(index=False).encode('utf-8'))
    elif report_type == "Expiry Report":
        chem_df = st.session_state.lab_inventory["chemicals"].copy()
        chem_df['expiry'] = pd.to_datetime(chem_df['expiry'], format='%Y-%m-%d', errors='coerce')
        df = chem_df[~chem_df['expiry'].isna()]
        if not df.empty:
            df['Days Until Expiry'] = (df['expiry'] - pd.to_datetime('today')).dt.days
        filename = "expiry_report.csv"
        attachment = MIMEBase('application', 'octet-stream')
        attachment.set_payload(df.to_csv(index=False).encode('utf-8'))
    
    # Add attachment headers
    encoders.encode_base64(attachment)
    attachment.add_header('Content-Disposition', f'attachment; filename={filename}')
    msg.attach(attachment)
    
    # Connect to SMTP server and send
    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(st.secrets["email"]["username"], st.secrets["email"]["password"])
        server.send_message(msg)
        server.quit()
    except Exception as e:
        raise Exception(f"Email sending failed: {str(e)}")

if __name__ == "__main__":
    try:
        # Initialize database connection
        conn = get_conn()
        if conn:
            try:
                # Initialize tables if they don't exist
                init_inventory_tables()
                
                # Load initial data
                st.session_state.lab_inventory = load_from_db()
                
                # Check if we need to load sample data
                if all(df.empty for df in st.session_state.lab_inventory.values()):
                    load_sample_data()
                    for category, df in st.session_state.lab_inventory.items():
                        save_to_db(category, df)
                    st.session_state.lab_inventory = load_from_db()
                
                # Check restock status
                check_restock_status()
                
                # Display the main interface
                display_lab_inventory_page()
            finally:
                conn.close()
    except Exception as e:
        st.error(f"Application error: {e}")