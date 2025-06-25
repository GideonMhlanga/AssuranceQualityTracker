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
from datetime import date, datetime, timedelta

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
    
    if 'status' in row.index:
        if row['status'] == 'Low':
            styles = ['background-color: #FFF3CD'] * len(row)
        elif row['status'] == 'Expired':
            styles = ['background-color: #F8D7DA'] * len(row)
        elif row['status'] == 'Damaged':
            styles = ['background-color: #F8D7DA'] * len(row)
        elif row['status'] in ['Needs service', 'In repair']:
            styles = ['background-color: #FFF3CD'] * len(row)

    numeric_cols = ['current', 'minimum', 'monthly']
    for col in numeric_cols:
        if col in row.index and pd.notna(row[col]) and str(row[col]).strip():
            try:
                row[col] = f"{float(row[col]):.2f}"
            except (ValueError, TypeError):
                row[col] = ""
    
    return styles

def calculate_months_of_stock(row):
    """Calculate months of remaining stock"""
    try:
        if (pd.notna(row.get('monthly')) and pd.notna(row.get('current'))) and \
           (str(row['monthly']).strip() and str(row['current']).strip()):
            monthly = float(row['monthly'])
            current = float(row['current'])
            if monthly > 0:
                return current / monthly
    except (TypeError, ValueError, KeyError):
        pass
    return None

def generate_unique_id(category):
    """Generate a unique ID for any inventory category"""
    prefix = {
        "chemicals": "CHEM",
        "glassware": "GLAS",
        "equipment": "EQUIP"
    }.get(category, "ITEM")
    
    conn = get_conn()
    try:
        result = conn.execute(
            text(f"SELECT MAX(id) FROM {category}")
        ).fetchone()
        
        max_id = result[0] if result[0] else f"{prefix}-000"
        num_part = int(max_id.split('-')[1]) + 1
        return f"{prefix}-{num_part:03d}"
    except Exception as e:
        st.error(f"Error generating ID: {e}")
        return f"{prefix}-{len(st.session_state.lab_inventory[category])+1:03d}"
    finally:
        if conn:
            conn.close()

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
            
            for query in table_creation_queries:
                conn.execute(text(query))
            
            # Add sequences for ID generation
            for category in ["chemicals", "glassware", "equipment"]:
                conn.execute(text(f"""
                    CREATE SEQUENCE IF NOT EXISTS {category}_id_seq;
                    ALTER TABLE {category} ALTER COLUMN id SET DEFAULT 
                        CASE 
                            WHEN '{category}' = 'chemicals' THEN 'CHEM-' || LPAD(nextval('{category}_id_seq')::text, 3, '0')
                            WHEN '{category}' = 'glassware' THEN 'GLAS-' || LPAD(nextval('{category}_id_seq')::text, 3, '0')
                            WHEN '{category}' = 'equipment' THEN 'EQUIP-' || LPAD(nextval('{category}_id_seq')::text, 3, '0')
                        END;
                """))
                # Initialize sequence values
                conn.execute(text(f"""
                    SELECT setval('{category}_id_seq', 
                        COALESCE((SELECT MAX(SUBSTRING(id FROM '[0-9]+$')::int) FROM {category}), 0) + 1);
                """))
            
            # Check if Months Stock column exists and has correct type
            result = conn.execute(text("""
                SELECT data_type, numeric_precision, numeric_scale 
                FROM information_schema.columns 
                WHERE table_name='chemicals' AND column_name='Months Stock'
            """)).fetchone()
            
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
            df_to_save = df.copy()
            
            if category == "chemicals" and 'expiry' in df_to_save.columns:
                df_to_save['expiry'] = pd.to_datetime(
                    df_to_save['expiry'], 
                    format='%Y-%m-%d', 
                    errors='coerce'
                )
                df_to_save = df_to_save[~df_to_save['expiry'].isna()]
            
            if category == "chemicals":
                numeric_cols = ['minimum', 'current', 'monthly', 'Months Stock']
                for col in numeric_cols:
                    if col in df_to_save.columns:
                        df_to_save[col] = (
                            pd.to_numeric(df_to_save[col], errors='coerce')
                            .round(2)
                            .replace({np.nan: None})
                        )

            if category == "chemicals" and 'Months Stock' not in df_to_save.columns:
                df_to_save['Months Stock'] = df_to_save.apply(
                    lambda row: round(calculate_months_of_stock(row), 2), 
                    axis=1
                )
            
            conn.execute(text(f"DELETE FROM {category}"))
            
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
    conn = None
    try:
        conn = get_conn()
        if not conn:
            st.error("Database connection failed")
            return None

        if category == "chemicals" and "Months Stock" not in item_data:
            item_data["Months Stock"] = calculate_months_of_stock(item_data)

        columns = []
        placeholders = []
        params = {}
        
        for col, val in item_data.items():
            if ' ' in col:
                columns.append(f'"{col}"')
            else:
                columns.append(col)
            
            param_name = col.replace(' ', '_')
            params[param_name] = val
            placeholders.append(f':{param_name}')

        query = text(f"""
            INSERT INTO {category} ({', '.join(columns)})
            VALUES ({', '.join(placeholders)})
            RETURNING *
        """)

        result = conn.execute(query, params).fetchone()
        conn.commit()
        return result

    except Exception as e:
        if conn:
            conn.rollback()
        st.error(f"Database operation failed: {e}")
        return None
    finally:
        if conn:
            conn.close()

# ======================
# Core Functions
# ======================

def initialize_inventory_data():
    """Initialize inventory data structure with PostgreSQL"""
    try:
        init_inventory_tables()
        st.session_state.lab_inventory = load_from_db()
        
        if all(df.empty for df in st.session_state.lab_inventory.values()):
            st.warning("No inventory data found - loading sample data...")
            load_sample_data()
            
            for category, df in st.session_state.lab_inventory.items():
                save_to_db(category, df)
            
            st.session_state.lab_inventory = load_from_db()
        
        check_restock_status()
        
    except Exception as e:
        st.error(f"Error initializing inventory data: {e}")
        st.warning("Falling back to sample data...")
        load_sample_data()

def load_sample_data():
    """Load sample inventory data with YYYY-MM-DD date formats"""
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
            "item": "Sodium Thiosulfate", 
            "category": "Reagent", 
            "minimum": 500.0, 
            "current": 1200.0, 
            "monthly": 250.0, 
            "unit": "grams", 
            "expiry": "2026-05-15", 
            "location": "Shelf B2", 
            "supplier": "Fisher Scientific", 
            "comment": "Keep in amber bottle", 
            "status": "OK",
            "Months Stock": 4.8
        },
        {
            "id": "CHEM-003", 
            "item": "Hydrochloric Acid", 
            "category": "Acid", 
            "minimum": 1000.0, 
            "current": 2500.0, 
            "monthly": 500.0, 
            "unit": "mL", 
            "expiry": "2029-12-31", 
            "location": "Acid Cabinet", 
            "supplier": "VWR", 
            "comment": "Concentrated - handle with care", 
            "status": "OK",
            "Months Stock": 5.0
        },
        {
            "id": "CHEM-004", 
            "item": "Phenolphthalein", 
            "category": "Indicator", 
            "minimum": 50.0, 
            "current": 25.0, 
            "monthly": 10.0, 
            "unit": "mL", 
            "expiry": "2023-11-30", 
            "location": "Shelf C3", 
            "supplier": "Sigma-Aldrich", 
            "comment": "Expired - needs disposal", 
            "status": "Expired",
            "Months Stock": 2.5
        }
    ]
    
    sample_glassware = [
        {
            "id": "GLAS-001", 
            "item": "100 mL Volumetric Flask", 
            "category": "Volumetric", 
            "current": 12, 
            "unit": "pieces", 
            "location": "Cabinet 1", 
            "comment": "Class A", 
            "status": "OK"
        },
        {
            "id": "GLAS-002", 
            "item": "50 mL Burette", 
            "category": "Volumetric", 
            "current": 6, 
            "unit": "pieces", 
            "location": "Cabinet 2", 
            "comment": "With PTFE stopcock", 
            "status": "Damaged"
        },
        {
            "id": "GLAS-003", 
            "item": "250 mL Beaker", 
            "category": "Measuring", 
            "current": 24, 
            "unit": "pieces", 
            "location": "Shelf D4", 
            "comment": "", 
            "status": "OK"
        }
    ]
    
    sample_equipment = [
        {
            "id": "EQUIP-001", 
            "item": "pH Meter", 
            "category": "Instrument", 
            "current": 3, 
            "unit": "units", 
            "location": "Bench 1", 
            "status": "Working", 
            "last_calibration": "2023-10-15", 
            "comment": "Calibration due in 3 months"
        },
        {
            "id": "EQUIP-002", 
            "item": "Analytical Balance", 
            "category": "Instrument", 
            "current": 2, 
            "unit": "units", 
            "location": "Balance Room", 
            "status": "Needs service", 
            "last_calibration": "2023-09-01", 
            "comment": "Drifting - needs technician"
        },
        {
            "id": "EQUIP-003", 
            "item": "Hot Plate", 
            "category": "Device", 
            "current": 5, 
            "unit": "units", 
            "location": "Bench 3", 
            "status": "Working", 
            "last_calibration": "2023-08-20", 
            "comment": ""
        }
    ]
    
    st.session_state.lab_inventory = {
        "chemicals": pd.DataFrame(sample_chemicals),
        "glassware": pd.DataFrame(sample_glassware),
        "equipment": pd.DataFrame(sample_equipment)
    }

def check_restock_status():
    """Check and update status for all inventory items"""
    today = datetime.now().date()
    
    # Update chemicals status
    if "chemicals" in st.session_state.lab_inventory:
        df = st.session_state.lab_inventory["chemicals"].copy()
        
        # Convert expiry to datetime if it's not already
        if 'expiry' in df.columns and df['expiry'].dtype == object:
            df['expiry'] = pd.to_datetime(df['expiry'], errors='coerce').dt.date
        
        # Calculate status based on conditions
        conditions = [
            (df['current'] <= df['minimum'] * 0.2) & (df['current'] > 0),
            df['current'] <= 0,
            (df['expiry'] < today) if 'expiry' in df.columns else False,
            (df['current'] <= df['minimum'] * 0.5) & (df['current'] > df['minimum'] * 0.2)
        ]
        choices = ["Critical", "Out of Stock", "Expired", "Low"]
        
        df['status'] = np.select(conditions, choices, default="OK")
        
        # Calculate months of stock
        if 'monthly' in df.columns and 'current' in df.columns:
            df['Months Stock'] = df.apply(
                lambda row: round(calculate_months_of_stock(row), 2) if pd.notna(row['monthly']) and float(row['monthly']) > 0 else None,
                axis=1
            )
        
        st.session_state.lab_inventory["chemicals"] = df
    
    # Update glassware status
    if "glassware" in st.session_state.lab_inventory:
        df = st.session_state.lab_inventory["glassware"].copy()
        if 'status' not in df.columns:
            df['status'] = "OK"
        st.session_state.lab_inventory["glassware"] = df
    
    # Update equipment status
    if "equipment" in st.session_state.lab_inventory:
        df = st.session_state.lab_inventory["equipment"].copy()
        if 'status' not in df.columns:
            df['status'] = "Working"
        st.session_state.lab_inventory["equipment"] = df

# ======================
# Inventory Management
# ======================

def manage_chemicals():
    """Chemical inventory management"""
    df = st.session_state.lab_inventory["chemicals"].copy()
    
    with st.expander("➕ Add New Chemical", expanded=False):
        with st.form("add_chemical_form"):
            cols = st.columns([1, 2, 1])
            with cols[0]:
                new_id = generate_unique_id("chemicals")
                st.text_input("ID", value=new_id, disabled=True)
                item_name = st.text_input("Item Name", key="new_chem_name")
                category = st.selectbox("Category", INVENTORY_CATEGORIES["chemicals"])
            with cols[1]:
                minimum_stock = st.number_input("Minimum Stock", min_value=0.0, step=0.1, format="%.2f")
                current_stock = st.number_input("Current Stock", min_value=0.0, step=0.1, format="%.2f")
                monthly_usage = st.number_input("Monthly Usage", min_value=0.0, step=0.1, format="%.2f")
                unit = st.selectbox("Unit", ["g", "kg", "mL", "L", "tablets", "bottles"])
            with cols[2]:
                expiry_date = st.text_input("Expiry Date (YYYY-MM-DD)", placeholder="2025-12-31")
                location = st.text_input("Storage Location")
                supplier = st.text_input("Supplier")
                comment = st.text_input("Comments")
            
            if st.form_submit_button("Add Chemical"):
                if expiry_date and not validate_date(expiry_date):
                    st.error("Invalid date format. Please use YYYY-MM-DD format.")
                    st.stop()
                
                existing_items = df['item'].str.lower().tolist()
                if item_name.lower() in existing_items:
                    st.error(f"A chemical with the name '{item_name}' already exists in Inventory!")
                else:
                    new_item = {
                        "id": new_id,
                        "item": item_name,
                        "category": category,
                        "minimum": minimum_stock,
                        "current": current_stock,
                        "monthly": monthly_usage,
                        "unit": unit,
                        "expiry": expiry_date if expiry_date else None,
                        "location": location,
                        "supplier": supplier,
                        "comment": comment,
                        "status": "OK"
                    }
                    
                    # Calculate months of stock
                    if monthly_usage > 0:
                        new_item["Months Stock"] = round(current_stock / monthly_usage, 2)
                    
                    # Double-check ID doesn't exist
                    conn = get_conn()
                    if conn:
                        existing_id = conn.execute(
                            text("SELECT id FROM chemicals WHERE id = :id"),
                            {"id": new_id}
                        ).fetchone()
                        
                        if existing_id:
                            st.error(f"ID {new_id} already exists! Generating new ID...")
                            new_id = generate_unique_id("chemicals")
                            new_item["id"] = new_id
                    
                    result = insert_item("chemicals", new_item)
                    if result:
                        st.session_state.lab_inventory["chemicals"] = pd.read_sql(
                            text("SELECT * FROM chemicals"), 
                            get_conn()
                        )
                        st.success(f"Added {item_name} to inventory")
                        st.rerun()
    
    st.subheader("Current Chemical Inventory")
    edited_df = st.data_editor(
        df,
        num_rows="dynamic",
        use_container_width=True,
        disabled=["id", "Months Stock"],
        column_config={
            "minimum": st.column_config.NumberColumn(format="%.2f"),
            "current": st.column_config.NumberColumn(format="%.2f"),
            "monthly": st.column_config.NumberColumn(format="%.2f"),
            "Months Stock": st.column_config.NumberColumn(format="%.2f"),
            "expiry": st.column_config.DateColumn(
                "Expiry Date",
                format="YYYY-MM-DD",
                help="Format: YYYY-MM-DD"
            ),
            "status": st.column_config.SelectboxColumn(
                "Status",
                options=["OK", "Low", "Critical", "Out of Stock", "Expired"],
                required=True
            )
        }
    )
    
    if st.button("Save Chemical Changes"):
        # Validate dates
        if 'expiry' in edited_df.columns:
            edited_df['expiry'] = pd.to_datetime(
                edited_df['expiry'], 
                format='%Y-%m-%d', 
                errors='coerce'
            )
            invalid_dates = edited_df[edited_df['expiry'].isna()]
            if not invalid_dates.empty:
                st.error("Some expiry dates are invalid. Please use YYYY-MM-DD format.")
                st.stop()
        
        # Recalculate months of stock
        if 'monthly' in edited_df.columns and 'current' in edited_df.columns:
            edited_df['Months Stock'] = edited_df.apply(
                lambda row: round(calculate_months_of_stock(row), 2), 
                axis=1
            )
        
        save_to_db("chemicals", edited_df)
        st.session_state.lab_inventory["chemicals"] = pd.read_sql(
            text("SELECT * FROM chemicals"), 
            get_conn()
        )
        st.success("Changes saved successfully!")
        st.rerun()

def manage_glassware():
    """Glassware inventory management"""
    df = st.session_state.lab_inventory["glassware"].copy()
    
    with st.expander("➕ Add New Glassware", expanded=False):
        with st.form("add_glassware_form"):
            cols = st.columns([1, 2, 1])
            with cols[0]:
                new_id = generate_unique_id("glassware")
                st.text_input("ID", value=new_id, disabled=True)
                item_name = st.text_input("Item Name", key="new_glass_name")
                category = st.selectbox("Category", INVENTORY_CATEGORIES["glassware"])
            with cols[1]:
                current_stock = st.number_input("Quantity", min_value=0, step=1, format="%d")
                unit = st.selectbox("Unit", ["pieces", "sets", "units"])
            with cols[2]:
                location = st.text_input("Storage Location")
                comment = st.text_input("Comments")
            
            if st.form_submit_button("Add Glassware"):
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
                    
                    # Double-check ID doesn't exist
                    conn = get_conn()
                    if conn:
                        existing_id = conn.execute(
                            text("SELECT id FROM glassware WHERE id = :id"),
                            {"id": new_id}
                        ).fetchone()
                        
                        if existing_id:
                            st.error(f"ID {new_id} already exists! Generating new ID...")
                            new_id = generate_unique_id("glassware")
                            new_item["id"] = new_id
                    
                    result = insert_item("glassware", new_item)
                    if result:
                        st.session_state.lab_inventory["glassware"] = pd.read_sql(
                            text("SELECT * FROM glassware"), 
                            get_conn()
                        )
                        st.success(f"Added {item_name} to inventory")
                        st.rerun()
    
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
        save_to_db("glassware", edited_df)
        st.session_state.lab_inventory["glassware"] = pd.read_sql(
            text("SELECT * FROM glassware"), 
            get_conn()
        )
        st.success("Changes saved successfully!")
        st.rerun()

def manage_equipment():
    """Equipment inventory management"""
    df = st.session_state.lab_inventory["equipment"].copy()
    
    with st.expander("➕ Add New Equipment", expanded=False):
        with st.form("add_equipment_form"):
            cols = st.columns([1, 2, 1])
            with cols[0]:
                new_id = generate_unique_id("equipment")
                st.text_input("ID", value=new_id, disabled=True)
                item_name = st.text_input("Item Name", key="new_equip_name")
                category = st.selectbox("Category", INVENTORY_CATEGORIES["equipment"])
            with cols[1]:
                current_stock = st.number_input("Quantity", min_value=0, step=1, format="%d")
                unit = st.selectbox("Unit", ["units", "sets"])
                last_calibration = st.text_input("Last Calibration (YYYY-MM-DD)", placeholder="2024-01-01")
            with cols[2]:
                location = st.text_input("Storage Location")
                status = st.selectbox("Status", ["Working", "Needs service", "In repair"])
                comment = st.text_input("Comments")
            
            if st.form_submit_button("Add Equipment"):
                if last_calibration and not validate_date(last_calibration):
                    st.error("Invalid date format. Please use YYYY-MM-DD format.")
                    st.stop()
                
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
                    
                    # Double-check ID doesn't exist
                    conn = get_conn()
                    if conn:
                        existing_id = conn.execute(
                            text("SELECT id FROM equipment WHERE id = :id"),
                            {"id": new_id}
                        ).fetchone()
                        
                        if existing_id:
                            st.error(f"ID {new_id} already exists! Generating new ID...")
                            new_id = generate_unique_id("equipment")
                            new_item["id"] = new_id
                    
                    result = insert_item("equipment", new_item)
                    if result:
                        st.session_state.lab_inventory["equipment"] = pd.read_sql(
                            text("SELECT * FROM equipment"), 
                            get_conn()
                        )
                        st.success(f"Added {item_name} to inventory")
                        st.rerun()
    
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
        
        save_to_db("equipment", edited_df)
        st.session_state.lab_inventory["equipment"] = pd.read_sql(
            text("SELECT * FROM equipment"), 
            get_conn()
        )
        st.success("Changes saved successfully!")
        st.rerun()

# ======================
# Reporting Functions
# ======================

def generate_inventory_report():
    """Generate a comprehensive inventory report"""
    doc = Document()
    doc.add_heading('Laboratory Inventory Report', 0)
    
    # Add date and time
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    doc.add_paragraph(f"Report generated on: {current_time}")
    
    # Add summary statistics
    doc.add_heading('Summary Statistics', level=1)
    
    summary_data = []
    for category in ["chemicals", "glassware", "equipment"]:
        stats = calculate_category_stats(category)
        summary_data.append({
            "Category": category.capitalize(),
            "Total Items": stats['total'],
            "Low Stock": stats.get('low', 0),
            "Expired": stats.get('expired', 0),
            "Damaged": stats.get('damaged', 0),
            "Issues": stats.get('issues', 0)
        })
    
    # Add summary table
    table = doc.add_table(rows=1, cols=6)
    table.style = 'Table Grid'
    hdr_cells = table.rows[0].cells
    hdr_cells[0].text = 'Category'
    hdr_cells[1].text = 'Total Items'
    hdr_cells[2].text = 'Low Stock'
    hdr_cells[3].text = 'Expired'
    hdr_cells[4].text = 'Damaged'
    hdr_cells[5].text = 'Issues'
    
    for item in summary_data:
        row_cells = table.add_row().cells
        row_cells[0].text = item['Category']
        row_cells[1].text = str(item['Total Items'])
        row_cells[2].text = str(item['Low Stock'])
        row_cells[3].text = str(item['Expired'])
        row_cells[4].text = str(item['Damaged'])
        row_cells[5].text = str(item['Issues'])
    
    # Add detailed sections for each category
    for category in ["chemicals", "glassware", "equipment"]:
        doc.add_heading(f"{category.capitalize()} Inventory", level=1)
        df = st.session_state.lab_inventory[category].copy()
        
        if category == "chemicals":
            if 'expiry' in df.columns:
                df['expiry'] = pd.to_datetime(df['expiry']).dt.strftime('%Y-%m-%d')
        
        # Create table
        table = doc.add_table(rows=1, cols=len(df.columns)+1)
        table.style = 'Table Grid'
        
        # Add headers
        hdr_cells = table.rows[0].cells
        for i, col in enumerate(df.columns):
            hdr_cells[i].text = str(col)
        
        # Add data rows with conditional formatting
        for _, row in df.iterrows():
            row_cells = table.add_row().cells
            for i, col in enumerate(df.columns):
                row_cells[i].text = str(row[col])
                
                # Apply color based on status
                if 'status' in df.columns and col == 'status':
                    if row['status'] == 'Low':
                        for paragraph in row_cells[i].paragraphs:
                            for run in paragraph.runs:
                                run.font.color.rgb = RGBColor(0x80, 0x00, 0x00)  # Dark red
                    elif row['status'] == 'Expired':
                        for paragraph in row_cells[i].paragraphs:
                            for run in paragraph.runs:
                                run.font.color.rgb = RGBColor(0xFF, 0x00, 0x00)  # Bright red
                    elif row['status'] == 'Damaged':
                        for paragraph in row_cells[i].paragraphs:
                            for run in paragraph.runs:
                                run.font.color.rgb = RGBColor(0xFF, 0x00, 0x00)  # Bright red
                    elif row['status'] in ['Needs service', 'In repair']:
                        for paragraph in row_cells[i].paragraphs:
                            for run in paragraph.runs:
                                run.font.color.rgb = RGBColor(0x80, 0x80, 0x00)  # Dark yellow
    
    # Save to BytesIO buffer
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer

def send_email_report(receiver_email, subject, body, attachment=None):
    """Send inventory report via email with improved error handling"""
    try:
        # Verify email configuration exists
        if "email" not in st.secrets:
            st.error("Email configuration not found in secrets")
            return False
            
        email_config = st.secrets["email"]
        
        # Validate required fields
        required_fields = ["sender", "password", "smtp_server", "smtp_port"]
        for field in required_fields:
            if field not in email_config:
                st.error(f"Missing required email configuration: {field}")
                return False
        
        # Create message container
        msg = MIMEMultipart()
        msg['From'] = email_config["sender"]
        msg['To'] = receiver_email
        msg['Subject'] = subject
        
        # Attach body
        msg.attach(MIMEText(body, 'plain'))
        
        # Attach file if provided
        if attachment:
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(attachment.read())
            encoders.encode_base64(part)
            part.add_header('Content-Disposition', 
                          'attachment; filename="inventory_report.docx"')
            msg.attach(part)
        
        # Connect to server and send email
        try:
            # Note: Using port 465 with SMTP_SSL instead of port 587 with starttls
            with smtplib.SMTP_SSL(
                email_config["smtp_server"], 
                int(email_config["smtp_port"])
            ) as server:
                server.login(email_config["sender"], email_config["password"])
                server.send_message(msg)
                st.success("Email sent successfully!")
                return True
                
        except smtplib.SMTPAuthenticationError:
            st.error("Authentication failed. Please check your email and password.")
            return False
        except smtplib.SMTPException as e:
            st.error(f"SMTP error occurred: {str(e)}")
            return False
            
    except Exception as e:
        st.error(f"Unexpected error occurred: {str(e)}")
        return False

def show_reporting_section():
    """Display the reporting interface"""
    st.header("📊 Inventory Reporting")
    
    with st.expander("📄 Generate Report", expanded=True):
        report_type = st.selectbox("Select Report Type", 
                                 ["Full Inventory", "Chemicals Only", "Glassware Only", "Equipment Only"])
        
        if st.button("Generate Report"):
            with st.spinner("Generating report..."):
                report_buffer = generate_inventory_report()
                st.success("Report generated successfully!")
                
                st.download_button(
                    label="Download Report",
                    data=report_buffer,
                    file_name=f"lab_inventory_report_{datetime.now().strftime('%Y%m%d')}.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                )
                
                # Email report option
                with st.expander("📧 Email Report"):
                    receiver_email = st.text_input("Recipient Email")
                    email_subject = st.text_input("Subject", value=f"Lab Inventory Report - {datetime.now().strftime('%Y-%m-%d')}")
                    email_body = st.text_area("Email Body", value="Please find attached the latest laboratory inventory report.")
                    
                    if st.button("Send Email"):
                        if not receiver_email:
                            st.error("Please enter a recipient email address")
                        else:
                            if send_email_report(receiver_email, email_subject, email_body, report_buffer):
                                st.success("Email sent successfully!")
                            else:
                                st.error("Failed to send email")
    
    with st.expander("📈 Visualizations", expanded=False):
        st.subheader("Inventory Visualizations")
        
        # Chemicals visualization
        if not st.session_state.lab_inventory["chemicals"].empty:
            st.markdown("#### Chemicals Status")
            chem_df = st.session_state.lab_inventory["chemicals"].copy()
            
            # Status distribution
            fig1 = px.pie(chem_df, names='status', title='Chemical Status Distribution')
            st.plotly_chart(fig1, use_container_width=True)
            
            # Months of stock histogram
            if 'Months Stock' in chem_df.columns:
                fig2 = px.histogram(
                    chem_df, 
                    x='Months Stock', 
                    title='Months of Stock Remaining',
                    nbins=20
                )
                st.plotly_chart(fig2, use_container_width=True)
        
        # Equipment visualization
        if not st.session_state.lab_inventory["equipment"].empty:
            st.markdown("#### Equipment Status")
            equip_df = st.session_state.lab_inventory["equipment"].copy()
            
            fig3 = px.pie(equip_df, names='status', title='Equipment Status Distribution')
            st.plotly_chart(fig3, use_container_width=True)

# ======================
# Main Page
# ======================

def display_lab_inventory_page():
    """Main inventory management interface"""
    st.title("🧪 Laboratory Inventory Management")
    
    if 'lab_inventory' not in st.session_state:
        initialize_inventory_data()
    
    # Display summary cards
    st.subheader("Inventory Summary")
    cols = st.columns(3)
    
    for i, category in enumerate(["chemicals", "glassware", "equipment"]):
        stats = calculate_category_stats(category)
        
        with cols[i]:
            container = st.container(border=True)
            container.markdown(f"**{category.capitalize()}**")
            container.metric("Total Items", stats['total'])
            
            if category == "chemicals":
                container.metric("Low Stock", stats['low'], delta=f"-{stats['low']} items")
                container.metric("Expired", stats['expired'], delta_color="inverse")
            elif category == "glassware":
                container.metric("Damaged", stats['damaged'], delta_color="inverse")
            elif category == "equipment":
                container.metric("Needs Attention", stats['issues'], delta_color="inverse")
    
    # Navigation tabs
    tab1, tab2, tab3, tab4 = st.tabs([
        "🧪 Chemicals", 
        "🧫 Glassware", 
        "⚙️ Equipment", 
        "📊 Reports"
    ])
    
    with tab1:
        manage_chemicals()
    
    with tab2:
        manage_glassware()
    
    with tab3:
        manage_equipment()
    
    with tab4:
        show_reporting_section()

if __name__ == "__main__":
    try:
        conn = get_conn()
        if conn:
            try:
                init_inventory_tables()
                st.session_state.lab_inventory = load_from_db()
                
                if all(df.empty for df in st.session_state.lab_inventory.values()):
                    load_sample_data()
                    for category, df in st.session_state.lab_inventory.items():
                        save_to_db(category, df)
                    st.session_state.lab_inventory = load_from_db()
                
                check_restock_status()
                display_lab_inventory_page()
            finally:
                conn.close()
    except Exception as e:
        st.error(f"Application error: {e}")