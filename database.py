import pandas as pd
import streamlit as st
import datetime as dt
import os
import sqlalchemy
from sqlalchemy import create_engine, text
import psycopg2
from urllib.parse import urlparse

# Get database URL from environment variable
DATABASE_URL = os.environ.get('DATABSE_URL') or 'postgresql://anesu:shammah2002*@localhost:5432/beverage_qa_db'

def get_conn():
    """Get connection to PostgreSQL database"""
    try:
        # Create SQLAlchemy engine
        engine = create_engine(DATABASE_URL)
        conn = engine.connect()
        return conn
    except Exception as e:
        st.error(f"Error connecting to database: {e}")
        return None

def initialize_database():
    """Initialize the database with required tables if they don't exist"""
    conn = get_conn()
    if conn:
        try:
            # Use SQLAlchemy text for SQL execution
            from anomaly import initialize_anomaly_detection
            from handover import initialize_handover
            
            # Initialize anomaly detection and handover tables
            initialize_anomaly_detection()
            initialize_handover()
            # Create users table
            conn.execute(text('''
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL,
                last_login TIMESTAMP
            )
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
            
            # Commit the changes
            conn.commit()
        except Exception as e:
            st.error(f"Error initializing database: {e}")
        finally:
            conn.close()

def save_torque_tamper_data(data):
    """Save torque and tamper evidence data to the database"""
    conn = get_conn()
    if conn:
        try:
            # Using SQLAlchemy parameterized query
            insert_query = text('''
            INSERT INTO torque_tamper (
                check_id, username, timestamp, start_time,
                head1_torque, head2_torque, head3_torque, head4_torque, head5_torque,
                tamper_evidence, comments
            ) VALUES (:check_id, :username, :timestamp, :start_time, 
                      :head1_torque, :head2_torque, :head3_torque, :head4_torque, :head5_torque,
                      :tamper_evidence, :comments)
            ''')
            
            conn.execute(insert_query, {
                'check_id': data['check_id'],
                'username': data['username'],
                'timestamp': data['timestamp'],
                'start_time': data['start_time'],
                'head1_torque': data['head1_torque'],
                'head2_torque': data['head2_torque'],
                'head3_torque': data['head3_torque'],
                'head4_torque': data['head4_torque'],
                'head5_torque': data['head5_torque'],
                'tamper_evidence': data['tamper_evidence'],
                'comments': data['comments']
            })
            
            conn.commit()
            return True
        except Exception as e:
            st.error(f"Error saving data: {e}")
            return False
        finally:
            conn.close()

def save_net_content_data(data):
    """Save net content data to the database"""
    conn = get_conn()
    if conn:
        try:
            # Using SQLAlchemy parameterized query
            insert_query = text('''
            INSERT INTO net_content (
                check_id, username, timestamp, start_time,
                brix, titration_acid, density, tare, nominal_volume,
                bottle1_weight, bottle2_weight, bottle3_weight, bottle4_weight, bottle5_weight,
                average_weight, net_content, comments
            ) VALUES (:check_id, :username, :timestamp, :start_time,
                    :brix, :titration_acid, :density, :tare, :nominal_volume,
                    :bottle1_weight, :bottle2_weight, :bottle3_weight, :bottle4_weight, :bottle5_weight,
                    :average_weight, :net_content, :comments)
            ''')
            
            conn.execute(insert_query, {
                'check_id': data['check_id'],
                'username': data['username'],
                'timestamp': data['timestamp'],
                'start_time': data['start_time'],
                'brix': data['brix'],
                'titration_acid': data['titration_acid'],
                'density': data['density'],
                'tare': data['tare'],
                'nominal_volume': data['nominal_volume'],
                'bottle1_weight': data['bottle1_weight'],
                'bottle2_weight': data['bottle2_weight'],
                'bottle3_weight': data['bottle3_weight'],
                'bottle4_weight': data['bottle4_weight'],
                'bottle5_weight': data['bottle5_weight'],
                'average_weight': data['average_weight'],
                'net_content': data['net_content'],
                'comments': data['comments']
            })
            
            conn.commit()
            return True
        except Exception as e:
            st.error(f"Error saving data: {e}")
            return False
        finally:
            conn.close()

def save_quality_check_data(data):
    """Save 30-minute quality check data to the database"""
    conn = get_conn()
    if conn:
        try:
            # Using SQLAlchemy parameterized query
            insert_query = text('''
            INSERT INTO quality_check (
                check_id, username, timestamp, start_time,
                trade_name, product, volume, best_before, manufacturing_date,
                cap_colour, tare, brix, tank_number, label_type, label_application,
                torque_test, pack_size, pallet_check, date_code, odour, appearance,
                product_taste, filler_height, keepers_sample, colour_taste_sample,
                micro_sample, bottle_check, bottle_seams, foreign_material_test,
                container_rinse_inspection, container_rinse_water_odour, comments
            ) VALUES (:check_id, :username, :timestamp, :start_time,
                    :trade_name, :product, :volume, :best_before, :manufacturing_date,
                    :cap_colour, :tare, :brix, :tank_number, :label_type, :label_application,
                    :torque_test, :pack_size, :pallet_check, :date_code, :odour, :appearance,
                    :product_taste, :filler_height, :keepers_sample, :colour_taste_sample,
                    :micro_sample, :bottle_check, :bottle_seams, :foreign_material_test,
                    :container_rinse_inspection, :container_rinse_water_odour, :comments)
            ''')
            
            conn.execute(insert_query, {
                'check_id': data['check_id'],
                'username': data['username'],
                'timestamp': data['timestamp'],
                'start_time': data['start_time'],
                'trade_name': data['trade_name'],
                'product': data['product'],
                'volume': data['volume'],
                'best_before': data['best_before'],
                'manufacturing_date': data['manufacturing_date'],
                'cap_colour': data['cap_colour'],
                'tare': data['tare'],
                'brix': data['brix'],
                'tank_number': data['tank_number'],
                'label_type': data['label_type'],
                'label_application': data['label_application'],
                'torque_test': data['torque_test'],
                'pack_size': data['pack_size'],
                'pallet_check': data['pallet_check'],
                'date_code': data['date_code'],
                'odour': data['odour'],
                'appearance': data['appearance'],
                'product_taste': data['product_taste'],
                'filler_height': data['filler_height'],
                'keepers_sample': data['keepers_sample'],
                'colour_taste_sample': data['colour_taste_sample'],
                'micro_sample': data['micro_sample'],
                'bottle_check': data['bottle_check'],
                'bottle_seams': data['bottle_seams'],
                'foreign_material_test': data['foreign_material_test'],
                'container_rinse_inspection': data['container_rinse_inspection'],
                'container_rinse_water_odour': data['container_rinse_water_odour'],
                'comments': data['comments']
            })
            
            conn.commit()
            return True
        except Exception as e:
            st.error(f"Error saving data: {e}")
            return False
        finally:
            conn.close()

def get_all_users_data():
    """Get all users data for user management"""
    conn = get_conn()
    if conn:
        try:
            query = text("SELECT username, created_at, last_login FROM users")
            result = conn.execute(query)
            df = pd.DataFrame(result.fetchall(), columns=result.keys())
            return df
        except Exception as e:
            st.error(f"Error retrieving users: {e}")
            return pd.DataFrame()
        finally:
            conn.close()
    return pd.DataFrame()

def get_recent_checks(limit=10):
    """Get recent checks for dashboard display"""
    conn = get_conn()
    if conn:
        try:
            # Combine data from all check tables with a UNION
            query = text("""
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
            """)
            
            result = conn.execute(query, {'limit': limit})
            df = pd.DataFrame(result.fetchall(), columns=result.keys())
            
            # Convert timestamp string to datetime
            if not df.empty:
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                
            return df
        except Exception as e:
            st.error(f"Error retrieving recent checks: {e}")
            return pd.DataFrame()
        finally:
            conn.close()
    return pd.DataFrame()

def get_check_data(start_date, end_date, product_filter=None):
    """
    Get check data for visualization or reporting
    
    Args:
        start_date: Start date for filtering
        end_date: End date for filtering
        product_filter: Optional product filter
        
    Returns:
        DataFrame with combined check data
    """
    conn = get_conn()
    if conn:
        try:
            # Start with an empty DataFrame
            combined_data = pd.DataFrame()
            
            # Get torque and tamper data
            torque_query = text("""
            SELECT * FROM torque_tamper 
            WHERE timestamp BETWEEN :start_date AND :end_date
            """)
            
            torque_result = conn.execute(torque_query, {
                'start_date': start_date,
                'end_date': end_date
            })
            torque_df = pd.DataFrame(torque_result.fetchall(), columns=torque_result.keys())
            
            # Get net content data
            net_query = text("""
            SELECT * FROM net_content 
            WHERE timestamp BETWEEN :start_date AND :end_date
            """)
            
            net_result = conn.execute(net_query, {
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
        finally:
            conn.close()
    return pd.DataFrame()
