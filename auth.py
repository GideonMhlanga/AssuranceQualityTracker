import streamlit as st
import pandas as pd
import hashlib
import datetime as dt
from database import get_conn
from sqlalchemy import text

def hash_password(password):
    """Create a SHA-256 hash of the password"""
    return hashlib.sha256(password.encode()).hexdigest()

def authenticate_user(username, password):
    """
    Authenticate a user with username and password
    
    Args:
        username (str): The username to check
        password (str): The unhashed password to verify
        
    Returns:
        bool: True if authentication successful, False otherwise
    """
    if not username or not password:
        return False
        
    conn = get_conn()
    if conn:
        try:
            # Check if the user exists with the given password hash
            query = text("SELECT * FROM users WHERE username = :username AND password_hash = :password")
            hashed_password = hash_password(password)
            
            result = conn.execute(query, {'username': username, 'password': hashed_password})
            data = result.fetchall()
            
            if data:
                # Update last login time
                update_query = text("UPDATE users SET last_login = :login_time WHERE username = :username")
                conn.execute(update_query, {'login_time': dt.datetime.now(), 'username': username})
                conn.commit()
                return True
                
        except Exception as e:
            st.error(f"Database error: {e}")
        finally:
            conn.close()
            
    return False

def create_user_if_not_exists(username, password):
    """
    Create a new user if the username doesn't already exist
    
    Args:
        username (str): The new username
        password (str): The unhashed password to store
        
    Returns:
        bool: True if user created, False if username already exists
    """
    if not username or not password:
        return False
        
    conn = get_conn()
    if conn:
        try:
            # Check if username already exists
            check_query = text("SELECT username FROM users WHERE username = :username")
            result = conn.execute(check_query, {'username': username})
            data = result.fetchall()
            
            if data:
                return False  # Username already exists
                
            # Create the new user
            now = dt.datetime.now()
            
            insert_query = text("""
            INSERT INTO users (username, password_hash, created_at, last_login)
            VALUES (:username, :password_hash, :created_at, :last_login)
            """)
            
            conn.execute(insert_query, {
                'username': username,
                'password_hash': hash_password(password),
                'created_at': now,
                'last_login': now
            })
            
            conn.commit()
            return True
            
        except Exception as e:
            st.error(f"Database error: {e}")
        finally:
            conn.close()
            
    return False

def logout():
    """Clear session state and log out the user"""
    for key in list(st.session_state.keys()):
        del st.session_state[key]
