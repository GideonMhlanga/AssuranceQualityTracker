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
                # Create users table (if it doesn't exist)
                conn.execute(text('''
                CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY,
                    password_hash TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL,
                    last_login TIMESTAMP
                )
                '''))
                
                # Add last_tab column if it doesn't exist
                try:
                    conn.execute(text('''
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS last_tab TEXT DEFAULT 'Dashboard'
                    '''))
                    logger.info("Added last_tab column to users table")
                except Exception as alter_error:
                    logger.error(f"Failed to add last_tab column: {alter_error}")
                    raise

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
        """Get all users data for user management"""
        with self.get_engine().connect() as conn:
            try:
                result = conn.execute(text("SELECT username, created_at, last_login FROM users"))
                return pd.DataFrame(result.fetchall(), columns=result.keys())
            except Exception as e:
                st.error(f"Error retrieving users: {e}")
                return pd.DataFrame()

    def get_recent_checks(self, limit=10):
        """Get recent checks from all tables"""
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
                # Ensure last_tab column exists
                conn.execute(text('''
                DO $$
                BEGIN
                    BEGIN
                        ALTER TABLE users ADD COLUMN last_tab TEXT DEFAULT 'Dashboard';
                        EXCEPTION WHEN duplicate_column THEN 
                        RAISE NOTICE 'column last_tab already exists in users';
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
        
    def create_user(self, username, password_hash, role='operator'):
        """Enhanced user creation with Neon-specific handling"""
        with self.get_engine().connect() as conn:
            try:
                with conn.begin():  # Explicit transaction
                    # Check existence
                    exists = conn.execute(
                        text("SELECT 1 FROM users WHERE username = :username"),
                        {'username': username}
                    ).scalar()
                    
                    if exists:
                        return False
                    
                    # Create user
                    conn.execute(
                        text("""
                        INSERT INTO users (username, password_hash, role, created_at, last_tab)
                        VALUES (:username, :password_hash, :role, NOW(), 'Dashboard')
                        """),
                        {
                            'username': username,
                            'password_hash': password_hash,
                            'role': role
                        }
                    )
                    
                    # Immediate verification within same transaction
                    created = conn.execute(
                        text("SELECT username FROM users WHERE username = :username"),
                        {'username': username}
                    ).fetchone()
                    
                    return bool(created)
                    
            except Exception as e:
                st.error(f"User creation error: {e}")
                return False
            
    def get_user(self, username):
        """Get user details with error handling"""
        with self.get_engine().connect() as conn:
            try:
                result = conn.execute(
                    text("SELECT * FROM users WHERE username = :username"),
                    {'username': username}
                )
                return result.fetchone()
            except Exception as e:
                st.error(f"Error fetching user: {e}")
                return None
            
    def get_user_last_tab(self, username):
        """Get the last visited tab for a user"""
        with self.get_engine().connect() as conn:
            try:
                result = conn.execute(
                    text("SELECT last_tab FROM users WHERE username = :username"),
                    {'username': username}
                )
                row = result.fetchone()
                return row[0] if row else 'Dashboard'
            except Exception as e:
                st.error(f"Error getting last tab: {e}")
                return 'Dashboard'

    def update_user_last_tab(self, username, tab_name):
        """Update the last visited tab for a user"""
        with self.get_engine().connect() as conn:
            try:
                conn.execute(
                    text("UPDATE users SET last_tab = :tab_name WHERE username = :username"),
                    {'tab_name': tab_name, 'username': username}
                )
                conn.commit()
                return True
            except Exception as e:
                conn.rollback()
                st.error(f"Error updating last tab: {e}")
                return False

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
    'get_db',
    'get_conn',
    'get_user_last_tab',
    'update_user_last_tab'
]