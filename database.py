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

class BeverageQADatabase:
    def __init__(self):
        self.DATABASE_URL = os.getenv('DATABASE_URL') 
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
        if not hasattr(self, '_engine'):
            logger.info("Creating new database engine")
            try: 
                self._engine = create_engine(
                    self.DATABASE_URL,
                    pool_size=5,           # Number of permanent connections
                    max_overflow=10,        # Additional connections when needed
                    pool_timeout=30,        # Wait 30 seconds for connection
                    pool_pre_ping=True,     # Test connections before use
                    pool_recycle=300         # Recycle connections after 5 minutes
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
                
                # Add the permissions column if it doesn't exist
                conn.execute(text('''
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 
                        FROM information_schema.columns 
                        WHERE table_name='users' AND column_name='permissions'
                    ) THEN
                        ALTER TABLE users ADD COLUMN permissions JSONB;
                    END IF;
                END $$;
                '''))
                
                # Create torque_tamper table
                conn.execute(text('''
                CREATE TABLE IF NOT EXISTS torque_tamper (
                    check_id TEXT PRIMARY KEY,
                    username TEXT NOT NULL,
                    timestamp TIMESTAMP NOT NULL,
                    start_time TIMESTAMP NOT NULL,
                    head1_torque FLOAT,
                    head2_torque FLOAT,
                    head3_torque FLOAT,
                    head4_torque FLOAT,
                    head5_torque FLOAT,
                    tamper_evidence TEXT,
                    comments TEXT,
                    FOREIGN KEY (username) REFERENCES users(username)
                )
                '''))
                
                # Create net_content table
                conn.execute(text('''
                CREATE TABLE IF NOT EXISTS net_content (
                    check_id TEXT PRIMARY KEY,
                    username TEXT NOT NULL,
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
                    comments TEXT,
                    FOREIGN KEY (username) REFERENCES users(username)
                )
                '''))
                
                # Create quality_check table
                conn.execute(text('''
                CREATE TABLE IF NOT EXISTS quality_check (
                    check_id TEXT PRIMARY KEY,
                    username TEXT NOT NULL,
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
                    comments TEXT,
                    FOREIGN KEY (username) REFERENCES users(username)
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
                    username TEXT NOT NULL,
                    FOREIGN KEY (username) REFERENCES users(username)
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
                    username TEXT NOT NULL,
                    FOREIGN KEY (username) REFERENCES users(username)
                )
                '''))
                
                # Create shift handover table
                conn.execute(text('''
                CREATE TABLE IF NOT EXISTS shift_handover (
                    id SERIAL PRIMARY KEY,
                    shift TEXT NOT NULL,
                    handover_from TEXT NOT NULL,
                    handover_to TEXT NOT NULL,
                    timestamp TIMESTAMP NOT NULL,
                    notes TEXT,
                    issues TEXT,
                    actions TEXT,
                    FOREIGN KEY (handover_from) REFERENCES users(username),
                    FOREIGN KEY (handover_to) REFERENCES users(username)
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
                    checked_by TEXT,
                    notes TEXT,
                    FOREIGN KEY (checked_by) REFERENCES users(username)
                )
                '''))
                
                conn.commit()
                logger.info("Database initialization completed successfully")
            except Exception as e:
                logger.error(f"Database initialization failed: {str(e)}")
                conn.rollback()
                st.error(f"Error initializing database: {e}")
                raise

    # Data Operations
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

    # Data Retrieval
    def get_all_users_data(self):
        """
        Retrieve all users data with robust permission handling
        
        Returns:
            pd.DataFrame: Columns - username, role, created_at, last_login, permissions
                        Empty DataFrame on error with consistent columns
        """
        # Define consistent columns for all return paths
        result_columns = ['username', 'role', 'created_at', 'last_login', 'permissions']
        
        with self.get_engine().connect() as conn:
            try:
                # Execute query with explicit column selection
                result = conn.execute(text("""
                SELECT 
                    username, 
                    role, 
                    created_at, 
                    last_login,
                    CASE 
                        WHEN permissions IS NULL THEN '{}'::jsonb
                        ELSE permissions
                    END AS permissions
                FROM users
                ORDER BY username ASC
                """))
                
                # Process results efficiently
                users_data = []
                for row in result.mappings():  # Get rows as dictionaries
                    try:
                        # Handle permissions conversion
                        permissions = row['permissions']
                        if isinstance(permissions, str):
                            permissions = json.loads(permissions)
                        
                        users_data.append({
                            'username': row['username'],
                            'role': row['role'],
                            'created_at': row['created_at'],
                            'last_login': row['last_login'],
                            'permissions': permissions or {}  # Ensure dict
                        })
                    except (json.JSONDecodeError, KeyError) as e:
                        logger.warning(f"Permission parsing error for user {row.get('username')}: {e}")
                        continue
                
                # Create DataFrame with consistent structure
                if users_data:
                    return pd.DataFrame(users_data, columns=result_columns)
                
                return pd.DataFrame(columns=result_columns)
                
            except Exception as e:
                logger.error(f"Database error in get_all_users_data: {str(e)}")
                st.error("Error retrieving user data. Please try again.")
                return pd.DataFrame(columns=result_columns)
        
    def update_user_permissions(self, username, permissions):
        """Update a user's permissions"""
        with self.get_engine().connect() as conn:
            try:
                conn.execute(
                    text("UPDATE users SET permissions = :permissions WHERE username = :username"),
                    {
                        'permissions': json.dumps(permissions),
                        'username': username
                    }
                )
                conn.commit()
                return True
            except Exception as e:
                conn.rollback()
                st.error(f"Error updating user permissions: {e}")
                return False
            
    def get_user_checks(self, username, limit=10):
        """Get recent checks for a specific user"""
        with self.get_engine().connect() as conn:
            try:
                result = conn.execute(text("""
                SELECT check_id, 'Torque & Tamper' as check_type, username, timestamp,
                       NULL as trade_name, NULL as product
                FROM torque_tamper
                WHERE username = :username
                UNION ALL
                SELECT check_id, 'Net Content' as check_type, username, timestamp,
                      NULL as trade_name, NULL as product
                FROM net_content
                WHERE username = :username
                UNION ALL
                SELECT check_id, '30-Min Check' as check_type, username, timestamp,
                       trade_name, product
                FROM quality_check
                WHERE username = :username
                ORDER BY timestamp DESC
                LIMIT :limit
                """), {'username': username, 'limit': limit})
                
                df = pd.DataFrame(result.fetchall(), columns=result.keys())
                if not df.empty:
                    df['timestamp'] = pd.to_datetime(df['timestamp'])
                return df
            except Exception as e:
                st.error(f"Error retrieving user checks: {e}")
                return pd.DataFrame()

    def get_public_checks(self, limit=5):
        """Get public checks (limited information)"""
        with self.get_engine().connect() as conn:
            try:
                result = conn.execute(text("""
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
                LIMIT :limit
                """), {'limit': limit})
                
                df = pd.DataFrame(result.fetchall(), columns=result.keys())
                if not df.empty:
                    df['timestamp'] = pd.to_datetime(df['timestamp'])
                return df
            except Exception as e:
                st.error(f"Error retrieving public checks: {e}")
                return pd.DataFrame()

    def get_recent_checks(self, limit=10):
        """Get recent checks from all tables (full access)"""
        with self.get_engine().connect() as conn:
            try:
                result = conn.execute(text("""
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
                LIMIT :limit
                """), {'limit': limit})
                
                df = pd.DataFrame(result.fetchall(), columns=result.keys())
                if not df.empty:
                    df['timestamp'] = pd.to_datetime(df['timestamp'])
                return df
            except Exception as e:
                st.error(f"Error retrieving recent checks: {e}")
                return pd.DataFrame()

    def get_check_data(self, start_date, end_date, product_filter=None):
        """Get combined check data for visualization or reporting"""
        with self.get_engine().connect() as conn:
            try:
                # Start with an empty DataFrame
                combined_data = pd.DataFrame()
                
                # Get torque and tamper data
                torque_result = conn.execute(text("""
                SELECT * FROM torque_tamper 
                WHERE timestamp BETWEEN :start_date AND :end_date
                """), {
                    'start_date': start_date,
                    'end_date': end_date
                })
                torque_df = pd.DataFrame(torque_result.fetchall(), columns=torque_result.keys())
                
                # Get net content data
                net_result = conn.execute(text("""
                SELECT * FROM net_content 
                WHERE timestamp BETWEEN :start_date AND :end_date
                """), {
                    'start_date': start_date,
                    'end_date': end_date
                })
                net_df = pd.DataFrame(net_result.fetchall(), columns=net_result.keys())
                
                # Get quality check data with optional product filter
                quality_params = {
                    'start_date': start_date,
                    'end_date': end_date
                }
                
                if product_filter and 'All' not in product_filter:
                    placeholders = []
                    for i, product in enumerate(product_filter):
                        param_name = f"product_{i}"
                        placeholders.append(f":product_{i}")
                        quality_params[param_name] = product
                    
                    product_clause = f" AND product IN ({','.join(placeholders)})"
                    quality_query = text(f"""
                    SELECT * FROM quality_check 
                    WHERE timestamp BETWEEN :start_date AND :end_date
                    {product_clause}
                    """)
                else:
                    quality_query = text("""
                    SELECT * FROM quality_check 
                    WHERE timestamp BETWEEN :start_date AND :end_date
                    """)
                    
                quality_result = conn.execute(quality_query, quality_params)
                quality_df = pd.DataFrame(quality_result.fetchall(), columns=quality_result.keys())
                
                # Convert timestamp strings to datetime
                for df in [torque_df, net_df, quality_df]:
                    if not df.empty:
                        df['timestamp'] = pd.to_datetime(df['timestamp'])
                        df['start_time'] = pd.to_datetime(df['start_time'])
                
                # Combine all data
                combined_data = pd.concat([
                    torque_df.assign(source='torque_tamper'),
                    net_df.assign(source='net_content'),
                    quality_df.assign(source='quality_check')
                ], ignore_index=True)
                
                return combined_data
                
            except Exception as e:
                st.error(f"Error retrieving check data: {e}")
                return pd.DataFrame()
            
    def test_connection(self):
        """Test database connection and basic functionality"""
        logger.info("Testing database connection")
        try:
            with self.get_engine().connect() as conn:
                # Test simple query
                if conn.execute(text("SELECT 1")).scalar() != 1:
                    logger.warning("Basic connection test failed")
                    return False
                
                # Verify critical tables exist
                required_tables = ['users', 'torque_tamper', 'net_content', 'quality_check']
                for table in required_tables:
                    if not conn.execute(
                        text("SELECT 1 FROM information_schema.tables WHERE table_name = :table"),
                        {'table': table}
                    ).scalar():
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
        with self.get_engine().connect() as conn:
            try:
                # Ensure all required columns exist
                conn.execute(text('''
                DO $$
                BEGIN
                    BEGIN
                        ALTER TABLE users ADD COLUMN IF NOT EXISTS role TEXT DEFAULT 'operator';
                        ALTER TABLE users ADD COLUMN IF NOT EXISTS permissions JSONB;
                        ALTER TABLE users ADD COLUMN IF NOT EXISTS last_tab TEXT DEFAULT 'Dashboard';
                        EXCEPTION WHEN duplicate_column THEN 
                        RAISE NOTICE 'columns already exist in users';
                    END;
                END $$;
                '''))
                
                conn.commit()
                logger.info("Database repair completed")
                return True
            except Exception as e:
                logger.error(f"Repair failed: {e}")
                conn.rollback()
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
        valid_roles = ['admin', 'supervisor', 'operator', 'viewer']
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
        
        with self.get_engine().connect() as conn:
            try:
                with conn.begin():  # Transaction block
                    # Check for existing user
                    if conn.execute(
                        text("SELECT 1 FROM users WHERE username = :username"),
                        {'username': username.strip().lower()}
                    ).scalar():
                        return False, "Username already exists"
                    
                    # Create new user
                    result = conn.execute(
                        text("""
                        INSERT INTO users (
                            username, 
                            password_hash, 
                            role, 
                            permissions, 
                            created_at, 
                            last_tab
                        ) VALUES (
                            :username, 
                            :password_hash, 
                            :role, 
                            :permissions, 
                            NOW(), 
                            'Dashboard'
                        )
                        RETURNING username, role, created_at
                        """),
                        {
                            'username': username.strip(),
                            'password_hash': password_hash,
                            'role': role.lower(),
                            'permissions': permissions_json
                        }
                    )
                    
                    # Verify creation
                    if result.fetchone():
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
        with self.get_engine().connect() as conn:
            try:
                result = conn.execute(
                    text("""
                    SELECT 
                        username, 
                        password_hash, 
                        role, 
                        COALESCE(permissions, '{}'::jsonb) as permissions,
                        created_at,
                        last_login,
                        last_tab
                    FROM users 
                    WHERE username = :username
                    """),
                    {'username': username}
                )
                user = result.fetchone()
                
                if user:
                    # Convert permissions JSONB to Python dict if it's a string
                    permissions = user.permissions
                    if isinstance(permissions, str):
                        try:
                            permissions = json.loads(permissions)
                        except json.JSONDecodeError:
                            permissions = {}
                    
                    return {
                        'username': user.username,
                        'password_hash': user.password_hash,
                        'role': user.role,
                        'permissions': permissions,
                        'created_at': user.created_at,
                        'last_login': user.last_login,
                        'last_tab': user.last_tab
                    }
                return None
                
            except Exception as e:
                st.error(f"Error fetching user: {e}")
                return None
            
    def get_user_last_tab(self, username):
        """Get the last visited tab for a user from user_settings table"""
        try:
            # First try the new user_settings table
            result = self.execute_query(
                "SELECT last_tab FROM user_settings WHERE username = %s",
                (username,)
            )
            
            if result:  # Found in user_settings
                return result[0]['last_tab']
                
            # Fallback to old users table if not found
            result = self.execute_query(
                "SELECT last_tab FROM users WHERE username = %s",
                (username,)
            )
            
            if result:  # Found in users table
                last_tab = result[0]['last_tab']
                # Migrate to new table
                self.update_user_last_tab(username, last_tab)
                return last_tab
                
            return "Dashboard"  # Default if user not found
            
        except Exception as e:
            st.error(f"Error getting last tab: {e}")
            return "Dashboard"

    def update_user_last_tab(self, username, tab_name):
        """Update the last visited tab in user_settings table with UPSERT"""
        try:
            # First ensure the user exists
            user_exists = self.execute_query(
                "SELECT 1 FROM users WHERE username = %s",
                (username,)
            )
            
            if not user_exists:
                return False
                
            # Update or insert into user_settings
            self.execute_query(
                """INSERT INTO user_settings (username, last_tab) 
                VALUES (%s, %s)
                ON CONFLICT (username) 
                DO UPDATE SET last_tab = EXCLUDED.last_tab""",
                (username, tab_name)
            )
            
            # Also update the legacy users table for backward compatibility
            self.execute_query(
                "UPDATE users SET last_tab = %s WHERE username = %s",
                (tab_name, username)
            )
            
            return True
            
        except Exception as e:
            st.error(f"Error updating last tab: {e}")
            return False
    
    def update_user_role(self, username, new_role):
        """Update a user's role"""
        with self.get_engine().connect() as conn:
            try:
                conn.execute(
                    text("UPDATE users SET role = :new_role WHERE username = :username"),
                    {'new_role': new_role, 'username': username}
                )
                conn.commit()
                return True
            except Exception as e:
                conn.rollback()
                st.error(f"Error updating user role: {e}")
                return False

    def save_shift_handover(self, data):
        """Save shift handover information"""
        with self.get_engine().connect() as conn:
            try:
                conn.execute(text('''
                INSERT INTO shift_handover (
                    shift, handover_from, handover_to, timestamp, 
                    notes, issues, actions
                ) VALUES (
                    :shift, :handover_from, :handover_to, :timestamp,
                    :notes, :issues, :actions
                )
                '''), data)
                conn.commit()
                return True
            except Exception as e:
                conn.rollback()
                st.error(f"Error saving shift handover: {e}")
                return False

    def get_shift_handovers(self, limit=5):
        """Get recent shift handovers"""
        with self.get_engine().connect() as conn:
            try:
                result = conn.execute(text("""
                SELECT * FROM shift_handover
                ORDER BY timestamp DESC
                LIMIT :limit
                """), {'limit': limit})
                return pd.DataFrame(result.fetchall(), columns=result.keys())
            except Exception as e:
                st.error(f"Error retrieving shift handovers: {e}")
                return pd.DataFrame()

    def save_lab_inventory(self, data):
        """Save lab inventory information"""
        with self.get_engine().connect() as conn:
            try:
                conn.execute(text('''
                INSERT INTO lab_inventory (
                    item_name, quantity, unit, location,
                    last_checked, checked_by, notes
                ) VALUES (
                    :item_name, :quantity, :unit, :location,
                    :last_checked, :checked_by, :notes
                )
                '''), data)
                conn.commit()
                return True
            except Exception as e:
                conn.rollback()
                st.error(f"Error saving lab inventory: {e}")
                return False

    def get_lab_inventory(self):
        """Get all lab inventory items"""
        with self.get_engine().connect() as conn:
            try:
                result = conn.execute(text("""
                SELECT * FROM lab_inventory
                ORDER BY item_name
                """))
                return pd.DataFrame(result.fetchall(), columns=result.keys())
            except Exception as e:
                st.error(f"Error retrieving lab inventory: {e}")
                return pd.DataFrame()
            
    def execute_query(self, query, params=None):
        """Execute a SQL query and return results as DataFrame"""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(query, params or ())
                if cursor.description:  # If it's a SELECT query
                    columns = [col[0] for col in cursor.description]
                    data = cursor.fetchall()
                    return pd.DataFrame(data, columns=columns)
                return pd.DataFrame()
        except Exception as e:
            st.error(f"Database query failed: {str(e)}")
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

# LEGACY FUNCTIONS (module-level)
def get_check_data(start_date, end_date, product_filter=None):
    """Get combined check data for visualization or reporting"""
    try:
        db = BeverageQADatabase()
        with st.spinner("Loading data..."):  # Add visual feedback
            data = db.get_check_data(start_date, end_date, product_filter)
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

def get_user_checks(username, limit=10):
    """Get checks for a specific user"""
    db = BeverageQADatabase()
    return db.get_user_checks(username, limit)

def get_public_checks(limit=5):
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