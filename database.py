import logging
from logging.handlers import RotatingFileHandler
import os
import time
import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool
from dotenv import load_dotenv
from datetime import datetime
import json

# Set up logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        RotatingFileHandler(
            'database_operations.log', 
            maxBytes=1024*1024,  # 1MB
            backupCount=5
        ),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

import os
import json
import time
import logging
import pandas as pd
import psycopg2
from psycopg2.extras import RealDictCursor
from sqlalchemy import create_engine, text
import streamlit as st

logger = logging.getLogger(__name__)

class BeverageQADatabase:
    def __init__(self):
        self.DATABASE_URL = os.getenv('DATABASE_URL')
        self.connection = None  # Initialize psycopg2 connection attribute
        self._engine = None     # SQLAlchemy engine
        
        if not self.DATABASE_URL:
            logger.critical("DATABASE_URL environment variable not set")
            st.error("""
            Database connection error:
            - DATABASE_URL environment variable not set
            - Please configure your database connection
            """)
            raise ValueError("Database connection URL not configured")
        
        try:
            self._initialize_with_retries(max_attempts=3)
        except ConnectionError as e:
            # Provide detailed troubleshooting help
            st.error(f"""
            Database Connection Failed:
            
            Could not connect to: {self._obfuscated_db_url()}
            
            Troubleshooting Steps:
            1. Verify PostgreSQL is running
            2. Check your connection string:
               - Current: postgresql://username:****@host:port/dbname
            3. Test connection using psql:
               psql -h localhost -p 5432 -U anesu beverage_qa_db
            4. Verify firewall settings
            5. Check PostgreSQL logs for errors
            
            Error Details: {str(e)}
            """)
            raise ConnectionError("Could not establish database connection") from e

    def _create_connection(self):
        """Create a new psycopg2 database connection"""
        try:
            return psycopg2.connect(
                self.DATABASE_URL,
                cursor_factory=RealDictCursor
            )
        except Exception as e:
            logger.error(f"Connection failed: {str(e)}")
            raise ConnectionError(f"Could not connect to database: {str(e)}")

    def _obfuscated_db_url(self):
        """Return a safe version of the DB URL for error messages"""
        if not self.DATABASE_URL:
            return "Not configured"
        try:
            parts = self.DATABASE_URL.split('@')
            if len(parts) > 1:
                return f"postgresql://****:****@{parts[1]}"
            return "postgresql://****:****@[hidden]"
        except:
            return "[malformed connection string]"
        
    def _initialize_with_retries(self, max_attempts=3):
        """Initialize database with retry logic"""
        for attempt in range(1, max_attempts + 1):
            try:
                logger.info(f"Database initialization attempt {attempt}/{max_attempts}")
                
                # Test basic connection first
                if not self.test_connection():
                    raise ConnectionError("Initial connection test failed")
                    
                # Initialize schema
                self.initialize_database()
                
                # Final verification
                if not self.test_connection():
                    raise ConnectionError("Post-initialization test failed")
                    
                logger.info("Database initialization successful")
                return
                
            except Exception as e:
                logger.error(f"Attempt {attempt} failed: {e}")
                if attempt == max_attempts:
                    logger.critical("Max initialization attempts reached")
                    raise ConnectionError("Could not establish database connection") from e
                time.sleep(2 ** attempt)  # Exponential backoff

    def get_engine(self):
        """Get SQLAlchemy engine with connection pooling"""
        if not self._engine:
            logger.info("Creating new database engine")
            try: 
                self._engine = create_engine(
                    self.DATABASE_URL,
                    pool_size=5,           # Number of permanent connections
                    max_overflow=10,       # Additional connections when needed
                    pool_timeout=30,       # Wait 30 seconds for connection
                    pool_pre_ping=True,    # Test connections before use
                    pool_recycle=300       # Recycle connections after 5 minutes
                )
                logger.info("Database engine created successfully")
            except Exception as e:
                logger.critical(f"Failed to create database engine: {str(e)}")
                raise
        return self._engine

    def initialize_database(self):
        """Initialize all database tables if they don't exist"""
        logger.info("Initializing database tables")
        with self.get_engine().connect() as conn:
            try:
                # Create users table with role and permissions
                conn.execute(text('''
                CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'operator',
                    permissions JSONB,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    last_login TIMESTAMP,
                    last_tab TEXT DEFAULT 'Dashboard'
                )
                '''))
                
                
                # Create user_settings table for additional user preferences
                conn.execute(text('''
                CREATE TABLE IF NOT EXISTS user_settings (
                    username TEXT PRIMARY KEY REFERENCES users(username),
                    last_tab TEXT DEFAULT 'Dashboard',
                    preferences JSONB
                )
                '''))
                
                # Create torque_tamper table
                conn.execute(text('''
                CREATE TABLE IF NOT EXISTS torque_tamper (
                    check_id TEXT PRIMARY KEY,
                    username TEXT NOT NULL REFERENCES users(username),
                    timestamp TIMESTAMP NOT NULL,
                    start_time TIMESTAMP NOT NULL,
                    head1_torque FLOAT,
                    head2_torque FLOAT,
                    head3_torque FLOAT,
                    head4_torque FLOAT,
                    head5_torque FLOAT,
                    tamper_evidence TEXT,
                    comments TEXT
                )
                '''))
                
                # Create net_content table
                conn.execute(text('''
                CREATE TABLE IF NOT EXISTS net_content (
                    check_id TEXT PRIMARY KEY,
                    username TEXT NOT NULL REFERENCES users(username),
                    timestamp TIMESTAMP NOT NULL,
                    start_time TIMESTAMP NOT NULL,
                    brix FLOAT,
                    titration_acid FLOAT,
                    density FLOAT,
                    tare FLOAT,
                    nominal_volume FLOAT,
                    bottle1_weight FLOAT,
                    bottle2_weight FLOAT,
                    bottle3_weight FLOAT,
                    bottle4_weight FLOAT,
                    bottle5_weight FLOAT,
                    average_weight FLOAT,
                    net_content FLOAT,
                    comments TEXT
                )
                '''))
                
                # Create quality_check table
                conn.execute(text('''
                CREATE TABLE IF NOT EXISTS quality_check (
                    check_id TEXT PRIMARY KEY,
                    username TEXT NOT NULL REFERENCES users(username),
                    timestamp TIMESTAMP NOT NULL,
                    start_time TIMESTAMP NOT NULL,
                    trade_name TEXT,
                    product TEXT,
                    volume TEXT,
                    best_before DATE,
                    manufacturing_date DATE,
                    cap_colour TEXT,
                    tare FLOAT,
                    brix FLOAT,
                    tank_number TEXT,
                    label_type TEXT,
                    label_application TEXT,
                    torque_test TEXT,
                    pack_size TEXT,
                    pallet_check TEXT,
                    date_code TEXT,
                    odour TEXT,
                    appearance TEXT,
                    product_taste TEXT,
                    filler_height TEXT,
                    keepers_sample TEXT,
                    colour_taste_sample TEXT,
                    micro_sample TEXT,
                    bottle_check TEXT,
                    bottle_seams TEXT,
                    foreign_material_test TEXT,
                    container_rinse_inspection TEXT,
                    container_rinse_water_odour TEXT,
                    comments TEXT
                )
                '''))
                
                # Create SPC data table
                conn.execute(text('''
                CREATE TABLE IF NOT EXISTS spc_data (
                    id SERIAL PRIMARY KEY,
                    check_id TEXT NOT NULL,
                    check_type TEXT NOT NULL,
                    parameter TEXT NOT NULL,
                    value FLOAT NOT NULL,
                    timestamp TIMESTAMP NOT NULL,
                    username TEXT NOT NULL REFERENCES users(username)
                )
                '''))
                
                # Create capability data table
                conn.execute(text('''
                CREATE TABLE IF NOT EXISTS capability_data (
                    id SERIAL PRIMARY KEY,
                    product TEXT NOT NULL,
                    parameter TEXT NOT NULL,
                    cp FLOAT,
                    cpk FLOAT,
                    pp FLOAT,
                    ppk FLOAT,
                    sigma FLOAT,
                    timestamp TIMESTAMP NOT NULL,
                    username TEXT NOT NULL REFERENCES users(username)
                )
                '''))
                
                # Create shift handover table
                conn.execute(text('''
                CREATE TABLE IF NOT EXISTS shift_handover (
                    id SERIAL PRIMARY KEY,
                    shift TEXT NOT NULL,
                    handover_from TEXT NOT NULL REFERENCES users(username),
                    handover_to TEXT NOT NULL REFERENCES users(username),
                    timestamp TIMESTAMP NOT NULL,
                    notes TEXT,
                    issues TEXT,
                    actions TEXT
                )
                '''))
                
                # Create lab inventory table
                conn.execute(text('''
                CREATE TABLE IF NOT EXISTS lab_inventory (
                    id SERIAL PRIMARY KEY,
                    item_name TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    unit TEXT NOT NULL,
                    location TEXT,
                    last_checked TIMESTAMP,
                    checked_by TEXT REFERENCES users(username),
                    notes TEXT
                )
                '''))
                
                conn.commit()
                logger.info("Database initialization completed successfully")
            except Exception as e:
                logger.error(f"Database initialization failed: {str(e)}")
                conn.rollback()
                st.error(f"Error initializing database: {e}")
                raise

    def execute_query(self, query, params=None):
        """Execute a SQL query and return results as DataFrame using psycopg2"""
        if not self.connection or self.connection.closed:
            self.connection = self._create_connection()
            
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(query, params or ())
                if cursor.description:  # If it's a SELECT query
                    columns = [col[0] for col in cursor.description]
                    data = cursor.fetchall()
                    return pd.DataFrame(data, columns=columns)
                self.connection.commit()
                return pd.DataFrame({'status': ['success']})  # For non-SELECT queries
        except Exception as e:
            logger.error(f"Query failed: {str(e)}")
            if self.connection:
                self.connection.rollback()
            st.error(f"Database query failed: {str(e)}")
            return pd.DataFrame()

    # Data Operations (using SQLAlchemy)
    def save_torque_tamper(self, data):
        """Save torque and tamper evidence data"""
        with self.get_engine().connect() as conn:
            try:
                conn.execute(text('''
                INSERT INTO torque_tamper (
                    check_id, username, timestamp, start_time,
                    head1_torque, head2_torque, head3_torque, head4_torque, head5_torque,
                    tamper_evidence, comments
                ) VALUES (
                    :check_id, :username, :timestamp, :start_time, 
                    :head1_torque, :head2_torque, :head3_torque, :head4_torque, :head5_torque,
                    :tamper_evidence, :comments
                )
                '''), data)
                conn.commit()
                return True
            except Exception as e:
                conn.rollback()
                st.error(f"Error saving torque/tamper data: {e}")
                return False

    def save_net_content(self, data):
        """Save net content measurement data"""
        with self.get_engine().connect() as conn:
            try:
                conn.execute(text('''
                INSERT INTO net_content (
                    check_id, username, timestamp, start_time,
                    brix, titration_acid, density, tare, nominal_volume,
                    bottle1_weight, bottle2_weight, bottle3_weight, bottle4_weight, bottle5_weight,
                    average_weight, net_content, comments
                ) VALUES (
                    :check_id, :username, :timestamp, :start_time,
                    :brix, :titration_acid, :density, :tare, :nominal_volume,
                    :bottle1_weight, :bottle2_weight, :bottle3_weight, :bottle4_weight, :bottle5_weight,
                    :average_weight, :net_content, :comments
                )
                '''), data)
                conn.commit()
                return True
            except Exception as e:
                conn.rollback()
                st.error(f"Error saving net content data: {e}")
                return False

    def save_quality_check(self, data):
        """Save 30-minute quality check data"""
        with self.get_engine().connect() as conn:
            try:
                conn.execute(text('''
                INSERT INTO quality_check (
                    check_id, username, timestamp, start_time,
                    trade_name, product, volume, best_before, manufacturing_date,
                    cap_colour, tare, brix, tank_number, label_type, label_application,
                    torque_test, pack_size, pallet_check, date_code, odour, appearance,
                    product_taste, filler_height, keepers_sample, colour_taste_sample,
                    micro_sample, bottle_check, bottle_seams, foreign_material_test,
                    container_rinse_inspection, container_rinse_water_odour, comments
                ) VALUES (
                    :check_id, :username, :timestamp, :start_time,
                    :trade_name, :product, :volume, :best_before, :manufacturing_date,
                    :cap_colour, :tare, :brix, :tank_number, :label_type, :label_application,
                    :torque_test, :pack_size, :pallet_check, :date_code, :odour, :appearance,
                    :product_taste, :filler_height, :keepers_sample, :colour_taste_sample,
                    :micro_sample, :bottle_check, :bottle_seams, :foreign_material_test,
                    :container_rinse_inspection, :container_rinse_water_odour, :comments
                )
                '''), data)
                conn.commit()
                return True
            except Exception as e:
                conn.rollback()
                st.error(f"Error saving quality check data: {e}")
                return False

    # Data Retrieval Methods
    def get_all_users_data(self):
        """
        Retrieve all users data with robust permission handling
        
        Returns:
            pd.DataFrame: Columns - username, role, created_at, last_login, permissions
                        Empty DataFrame on error with consistent columns
        """
        # Define consistent columns for all return paths
        result_columns = ['username', 'role', 'created_at', 'last_login', 'permissions']
        
        try:
            result = self.execute_query("""
            SELECT 
                username, 
                role, 
                created_at, 
                last_login,
                COALESCE(permissions, '{}'::jsonb) as permissions
            FROM users
            ORDER BY username ASC
            """)
            
            if not result.empty:
                # Process permissions
                result['permissions'] = result['permissions'].apply(
                    lambda x: json.loads(x) if isinstance(x, str) else (x or {})
                )
                return result[result_columns]
            
            return pd.DataFrame(columns=result_columns)
            
        except Exception as e:
            logger.error(f"Database error in get_all_users_data: {str(e)}")
            st.error("Error retrieving user data. Please try again.")
            return pd.DataFrame(columns=result_columns)
    
    def update_user_permissions(self, username, permissions):
        """Update a user's permissions"""
        try:
            result = self.execute_query(
                "UPDATE users SET permissions = %s WHERE username = %s RETURNING 1",
                (json.dumps(permissions), username))
            return not result.empty
        except Exception as e:
            st.error(f"Error updating user permissions: {e}")
            return False

    def get_user_checks(self, username, limit=10):
        """Get recent checks for a specific user"""
        try:
            df = self.execute_query("""
            SELECT check_id, 'Torque & Tamper' as check_type, username, timestamp,
                   NULL as trade_name, NULL as product
            FROM torque_tamper
            WHERE username = %s
            UNION ALL
            SELECT check_id, 'Net Content' as check_type, username, timestamp,
                  NULL as trade_name, NULL as product
            FROM net_content
            WHERE username = %s
            UNION ALL
            SELECT check_id, '30-Min Check' as check_type, username, timestamp,
                   trade_name, product
            FROM quality_check
            WHERE username = %s
            ORDER BY timestamp DESC
            LIMIT %s
            """, (username, username, username, limit))
            
            if not df.empty:
                df['timestamp'] = pd.to_datetime(df['timestamp'])
            return df
        except Exception as e:
            st.error(f"Error retrieving user checks: {e}")
            return pd.DataFrame()

    def get_public_checks(self, limit=5):
        """Get public checks (limited information)"""
        try:
            df = self.execute_query("""
            SELECT check_id, 'Torque & Tamper' as check_type, timestamp,
                   NULL as trade_name, NULL as product
            FROM torque_tamper
            UNION ALL
            SELECT check_id, 'Net Content' as check_type, timestamp,
                  NULL as trade_name, NULL as product
            FROM net_content
            UNION ALL
            SELECT check_id, '30-Min Check' as check_type, timestamp,
                   trade_name, product
            FROM quality_check
            ORDER BY timestamp DESC
            LIMIT %s
            """, (limit,))
            
            if not df.empty:
                df['timestamp'] = pd.to_datetime(df['timestamp'])
            return df
        except Exception as e:
            st.error(f"Error retrieving public checks: {e}")
            return pd.DataFrame()

    def get_recent_checks(self, limit=10, include_measurements=False):
        """Get recent checks from all tables (full access)"""
        try:
            df = self.execute_query("""
            SELECT check_id, 'Torque & Tamper' as check_type, username, timestamp,
                   NULL as trade_name, NULL as product
            FROM torque_tamper
            UNION ALL
            SELECT check_id, 'Net Content' as check_type, username, timestamp,
                  NULL as trade_name, NULL as product
            FROM net_content
            UNION ALL
            SELECT check_id, '30-Min Check' as check_type, username, timestamp,
                   trade_name, product
            FROM quality_check
            ORDER BY timestamp DESC
            LIMIT %s
            """, (limit,))
            
            if not df.empty:
                df['timestamp'] = pd.to_datetime(df['timestamp'])
            return df
        except Exception as e:
            st.error(f"Error retrieving recent checks: {e}")
            return pd.DataFrame()

    def get_check_data(self, start_date, end_date, product_filter=None):
        """Get combined check data for visualization or reporting"""
        try:
            # Start with an empty DataFrame
            combined_data = pd.DataFrame()
            
            # Get torque and tamper data
            torque_df = self.execute_query("""
            SELECT *, 'torque_tamper' as source FROM torque_tamper 
            WHERE timestamp BETWEEN %s AND %s
            """, (start_date, end_date))
            
            # Get net content data
            net_df = self.execute_query("""
            SELECT *, 'net_content' as source FROM net_content 
            WHERE timestamp BETWEEN %s AND %s
            """, (start_date, end_date))
            
            # Get quality check data with optional product filter
            if product_filter and 'All' not in product_filter:
                placeholders = ','.join(['%s'] * len(product_filter))
                quality_query = f"""
                SELECT *, 'quality_check' as source FROM quality_check 
                WHERE timestamp BETWEEN %s AND %s
                AND product IN ({placeholders})
                """
                quality_df = self.execute_query(
                    quality_query, 
                    [start_date, end_date] + product_filter
                )
            else:
                quality_df = self.execute_query("""
                SELECT *, 'quality_check' as source FROM quality_check 
                WHERE timestamp BETWEEN %s AND %s
                """, (start_date, end_date))
            
            # Convert timestamp strings to datetime
            for df in [torque_df, net_df, quality_df]:
                if not df.empty:
                    df['timestamp'] = pd.to_datetime(df['timestamp'])
                    if 'start_time' in df.columns:
                        df['start_time'] = pd.to_datetime(df['start_time'])
            
            # --- NEW IMPROVED CONCATENATION LOGIC ---
            # Get all possible columns across all DataFrames
            all_columns = set()
            for df in [torque_df, net_df, quality_df]:
                all_columns.update(df.columns)
            
            # Create template with all possible columns
            template_columns = list(all_columns)
            
            # Align each DataFrame with the template
            dfs_to_concat = []
            for df in [torque_df, net_df, quality_df]:
                if not df.empty:
                    # Ensure all columns exist (add missing as NaN)
                    aligned_df = df.reindex(columns=template_columns)
                    dfs_to_concat.append(aligned_df)
            
            # Concatenate all aligned DataFrames
            if dfs_to_concat:
                combined_data = pd.concat(dfs_to_concat, ignore_index=True)
            else:
                combined_data = pd.DataFrame(columns=template_columns)
            
            # Convert datetime columns to timezone-naive if needed
            datetime_cols = ['timestamp', 'start_time']
            for col in datetime_cols:
                if col in combined_data.columns:
                    combined_data[col] = pd.to_datetime(combined_data[col])
            
            return combined_data
            
        except Exception as e:
            st.error(f"Error retrieving check data: {e}")
            return pd.DataFrame()
    
    def test_connection(self):
        """Test database connection and basic functionality"""
        logger.info("Testing database connection")
        try:
            # Test both SQLAlchemy and psycopg2 connections
            with self.get_engine().connect() as conn:
                if conn.execute(text("SELECT 1")).scalar() != 1:
                    logger.warning("SQLAlchemy connection test failed")
                    return False
            
            # Test psycopg2 connection
            test_result = self.execute_query("SELECT 1")
            if test_result.empty or test_result.iloc[0, 0] != 1:
                logger.warning("Psycopg2 connection test failed")
                return False
                
            # Verify critical tables exist
            required_tables = ['users', 'torque_tamper', 'net_content', 'quality_check']
            for table in required_tables:
                result = self.execute_query(
                    "SELECT 1 FROM information_schema.tables WHERE table_name = %s",
                    (table,))
                if result.empty:
                    logger.error(f"Missing required table: {table}")
                    return False
            
            logger.info("Database connection test passed")
            return True
            
        except Exception as e:
            logger.critical(f"Connection test failed: {e}")
            return False
    
    def repair_database(self):
        """Attempt to repair common database issues"""
        logger.info("Attempting database repair")
        try:
            self.execute_query('''
            DO $$
            BEGIN
                BEGIN
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS role TEXT DEFAULT 'operator';
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS permissions JSONB;
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS last_tab TEXT DEFAULT 'Dashboard';
                    EXCEPTION WHEN duplicate_column THEN 
                    RAISE NOTICE 'columns already exist in users';
                END;
                
                -- Ensure user_settings table exists
                CREATE TABLE IF NOT EXISTS user_settings (
                    username TEXT PRIMARY KEY REFERENCES users(username),
                    last_tab TEXT DEFAULT 'Dashboard',
                    preferences JSONB
                );
            END $$;
            ''')
            logger.info("Database repair completed")
            return True
        except Exception as e:
            logger.error(f"Repair failed: {e}")
            return False
    
    def create_user(self, username, password_hash, role='operator', permissions=None):
        """
        Enhanced user creation with role and permissions validation
        
        Args:
            username (str): Unique username (3-20 chars)
            password_hash (str): Hashed password
            role (str): User role (admin/supervisor/operator/viewer)
            permissions (dict, optional): Custom permissions dictionary
        
        Returns:
            tuple: (success: bool, message: str)
        """
        # Input validation
        if not isinstance(username, str) or not 3 <= len(username) <= 20:
            return False, "Username must be 3-20 characters"
        
        if not isinstance(password_hash, str) or not password_hash:
            return False, "Invalid password hash"
        
        # Role validation
        valid_roles = ['admin', 'supervisor', 'operator', 'viewer', 'guest']
        if role not in valid_roles:
            return False, f"Invalid role. Must be one of: {', '.join(valid_roles)}"
        
        # Set default permissions based on role if not provided
        if permissions is None:
            permissions = {
                'view_all_data': role in ['admin', 'supervisor'],
                'edit_all_data': role == 'admin',
                'edit_own_data': role in ['admin', 'supervisor', 'operator'],
                'manage_users': role == 'admin',
                'add_comments': role in ['admin', 'supervisor', 'operator'],
                'export_data': role in ['admin', 'supervisor'],
                'access_reports': True,
                'access_analytics': role != 'viewer'
            }
        elif not isinstance(permissions, dict):
            return False, "Permissions must be a dictionary"
        
        try:
            # Serialize permissions to JSON
            permissions_json = json.dumps(permissions)
        except (TypeError, ValueError) as e:
            return False, f"Invalid permissions format: {str(e)}"
        
        try:
            # Check for existing user
            exists = self.execute_query(
                "SELECT 1 FROM users WHERE username = %s",
                (username.strip().lower(),)
            )
            if not exists.empty:
                return False, "Username already exists"
            
            # Create new user
            result = self.execute_query("""
            INSERT INTO users (
                username, 
                password_hash, 
                role, 
                permissions, 
                created_at, 
                last_tab
            ) VALUES (
                %s, %s, %s, %s, NOW(), 'Dashboard'
            )
            RETURNING username, role, created_at
            """, (
                username.strip(),
                password_hash,
                role.lower(),
                permissions_json
            ))
            
            if not result.empty:
                # Also create user settings entry
                self.execute_query("""
                INSERT INTO user_settings (username) VALUES (%s)
                ON CONFLICT (username) DO NOTHING
                """, (username.strip(),))
                
                return True, f"User '{username}' created successfully as {role}"
            return False, "Failed to create user"
                
        except Exception as e:
            error_type = e.__class__.__name__
            error_details = str(e)
            
            # Handle specific error cases
            if "permissions" in error_details.lower():
                return False, "Invalid permissions format"
            elif "unique" in error_details.lower():
                return False, "Username already exists"
            elif "connection" in error_details.lower():
                return False, "Database connection error"
            
            # Generic error message
            logger.error(f"User creation failed ({error_type}): {error_details}")
            return False, f"System error: {error_details}"
            
    def get_user(self, username):
        """Get user details with error handling"""
        try:
            result = self.execute_query("""
            SELECT 
                u.username, 
                u.password_hash, 
                u.role, 
                COALESCE(u.permissions, '{}'::jsonb) as permissions,
                u.created_at,
                u.last_login,
                COALESCE(s.last_tab, u.last_tab, 'Dashboard') as last_tab
            FROM users u
            LEFT JOIN user_settings s ON u.username = s.username
            WHERE u.username = %s
            """, (username,))
            
            if not result.empty:
                user = result.iloc[0]
                # Convert permissions JSONB to Python dict
                permissions = user['permissions']
                if isinstance(permissions, str):
                    try:
                        permissions = json.loads(permissions)
                    except json.JSONDecodeError:
                        permissions = {}
                
                return {
                    'username': user['username'],
                    'password_hash': user['password_hash'],
                    'role': user['role'],
                    'permissions': permissions or {},
                    'created_at': user['created_at'],
                    'last_login': user['last_login'],
                    'last_tab': user['last_tab']
                }
            return None
            
        except Exception as e:
            st.error(f"Error fetching user: {e}")
            return None
    
    def get_user_last_tab(self, username):
        """Get the last visited tab for a user"""
        try:
            result = self.execute_query("""
            SELECT COALESCE(
                (SELECT last_tab FROM user_settings WHERE username = %s),
                (SELECT last_tab FROM users WHERE username = %s),
                'Dashboard'
            ) as last_tab
            """, (username, username))
            
            if not result.empty:
                return result.iloc[0]['last_tab']
            return "Dashboard"
            
        except Exception as e:
            st.error(f"Error getting last tab: {e}")
            return "Dashboard"

    def update_user_last_tab(self, username, tab_name):
        """Update the last visited tab for a user"""
        try:
            # Update both user_settings and users tables
            result = self.execute_query("""
            WITH updated_user AS (
                UPDATE users SET last_tab = %s 
                WHERE username = %s
                RETURNING 1
            )
            INSERT INTO user_settings (username, last_tab)
            VALUES (%s, %s)
            ON CONFLICT (username) 
            DO UPDATE SET last_tab = EXCLUDED.last_tab
            RETURNING 1
            """, (tab_name, username, username, tab_name))
            
            return not result.empty
        except Exception as e:
            st.error(f"Error updating last tab: {e}")
            return False
    
    def update_user_role(self, username, new_role):
        """Update a user's role"""
        try:
            result = self.execute_query(
                "UPDATE users SET role = %s WHERE username = %s RETURNING 1",
                (new_role, username))
            return not result.empty
        except Exception as e:
            st.error(f"Error updating user role: {e}")
            return False

    def save_shift_handover(self, data):
        """Save shift handover information"""
        try:
            result = self.execute_query('''
            INSERT INTO shift_handover (
                shift, handover_from, handover_to, timestamp, 
                notes, issues, actions
            ) VALUES (
                %(shift)s, %(handover_from)s, %(handover_to)s, %(timestamp)s,
                %(notes)s, %(issues)s, %(actions)s
            )
            RETURNING 1
            ''', data)
            return not result.empty
        except Exception as e:
            st.error(f"Error saving shift handover: {e}")
            return False

    def get_shift_handovers(self, limit=5):
        """Get recent shift handovers"""
        try:
            return self.execute_query("""
            SELECT * FROM shift_handover
            ORDER BY timestamp DESC
            LIMIT %s
            """, (limit,))
        except Exception as e:
            st.error(f"Error retrieving shift handovers: {e}")
            return pd.DataFrame()

    def save_lab_inventory(self, data):
        """Save lab inventory information"""
        try:
            result = self.execute_query('''
            INSERT INTO lab_inventory (
                item_name, quantity, unit, location,
                last_checked, checked_by, notes
            ) VALUES (
                %(item_name)s, %(quantity)s, %(unit)s, %(location)s,
                %(last_checked)s, %(checked_by)s, %(notes)s
            )
            RETURNING 1
            ''', data)
            return not result.empty
        except Exception as e:
            st.error(f"Error saving lab inventory: {e}")
            return False

    def get_lab_inventory(self):
        """Get all lab inventory items"""
        try:
            return self.execute_query("""
            SELECT * FROM lab_inventory
            ORDER BY item_name
            """)
        except Exception as e:
            st.error(f"Error retrieving lab inventory: {e}")
            return pd.DataFrame()

# Singleton instance for the application
_global_db_instance = None 

def get_db():
    """Get the global database instance"""
    global _global_db_instance
    if _global_db_instance is None:
        _global_db_instance = BeverageQADatabase()
    return _global_db_instance

def get_conn():
    """Backward compatible connection getter"""
    return get_db().get_engine().connect()

def get_check_data(start_date, end_date, product_filter=None):
    """Get combined check data for visualization or reporting"""
    try:
        db = BeverageQADatabase()
        with st.spinner("Loading data..."):  # Add visual feedback
            data = st.session_state.db.get_check_data(start_date, end_date)
            if 'product' in data.columns:
                product_options = ["All"] + list(data['product'].dropna().unique())
            else:
                product_options = ["All"]
        return data
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return pd.DataFrame()  # Return empty DataFrame on error
    
def initialize_database():
    """Initialize the database tables"""
    return BeverageQADatabase()

def save_torque_tamper_data(data):
    """Save torque and tamper evidence data"""
    db = BeverageQADatabase()
    return db.save_torque_tamper(data)

def save_net_content_data(data):
    """Save net content measurement data"""
    db = BeverageQADatabase()
    return db.save_net_content(data)

def save_quality_check_data(data):
    """Save 30-minute quality check data"""
    db = BeverageQADatabase()
    return db.save_quality_check(data)

def get_all_users_data():
    """Get all users data for user management"""
    db = BeverageQADatabase()
    return db.get_all_users_data()

def get_recent_checks(limit=10):
    """Get recent checks from all tables"""
    db = BeverageQADatabase()
    return db.get_recent_checks(limit)

def get_user_checks(username, limit=10, include_measurements=False):
    """Get checks for a specific user"""
    db = BeverageQADatabase()
    return db.get_user_checks(username, limit)

def get_public_checks(self, limit=5, include_measurements=False):
    """Get public checks (limited information)"""
    db = BeverageQADatabase()
    return db.get_public_checks(limit)

# Make sure these are available for import
__all__ = [
    'BeverageQADatabase',
    'get_check_data',
    'initialize_database',
    'save_torque_tamper_data',
    'save_net_content_data', 
    'save_quality_check_data',
    'get_all_users_data',
    'get_recent_checks',
    'get_user_checks',
    'get_public_checks',
    'get_db',
    'get_conn',
    'get_user_last_tab',
    'update_user_last_tab',
    'update_user_role',
    'save_shift_handover',
    'get_shift_handovers',
    'save_lab_inventory',
    'get_lab_inventory'
]