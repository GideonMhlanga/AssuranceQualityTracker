from typing import Optional
import pandas as pd
import streamlit as st
from database import BeverageQADatabase

class HybridDatabase:
    def __init__(self, online_db: BeverageQADatabase):
        self.online_db = online_db
        try:
            from app import FallbackDatabase
            self.fallback = FallbackDatabase()
        except ImportError as e:
            st.warning(f"FallbackDatabase import failed, using minimal fallback: {str(e)}")
            self.fallback = self.create_minimal_fallback()
        self._last_online_success = True

    @staticmethod
    def create_minimal_fallback():
        """Create a minimal fallback database if import fails"""
        class MinimalFallback:
            def get_all_users_data(self):
                st.warning("Using minimal fallback database")
                return pd.DataFrame(columns=['username', 'role', 'created_at', 'last_login'])
            
            def create_user(self, *args, **kwargs):
                st.warning("Cannot create users in minimal fallback mode")
                return False, "Database unavailable"
                
            def test_connection(self):
                return False
                
            def __getattr__(self, name):
                """Handle any unimplemented methods"""
                st.warning(f"Fallback method {name} not implemented")
                return lambda *args, **kwargs: None
                
        return MinimalFallback()

    def get_all_users_data(self) -> pd.DataFrame:
        """Get all users data, falling back to local if online fails"""
        try:
            if self._last_online_success:
                data = self.online_db.get_all_users_data()
                if not data.empty:
                    return data
        except Exception as e:
            self._last_online_success = False
            st.warning(f"Online database failed, using fallback: {str(e)}")
        
        return self.fallback.get_all_users_data()

    def test_connection(self) -> bool:
        """Test connection to online database"""
        try:
            self._last_online_success = self.online_db.test_connection()
            return self._last_online_success
        except Exception as e:
            self._last_online_success = False
            st.warning(f"Connection test failed: {str(e)}")
            return False

    def create_user(self, username: str, password_hash: str, 
                   role: str = 'operator', permissions: Optional[dict] = None):
        """Create user with fallback handling"""
        try:
            if self._last_online_success:
                result = self.online_db.create_user(username, password_hash, role, permissions)
                if result[0]:  # If success
                    return result
        except Exception as e:
            self._last_online_success = False
            st.warning(f"Online create_user failed: {str(e)}")
        
        return self.fallback.create_user(username, password_hash, role, permissions)

    def __getattr__(self, name):
        """
        Forward any unimplemented methods to online DB first, 
        then fallback if that fails
        """
        def method(*args, **kwargs):
            try:
                if self._last_online_success:
                    online_method = getattr(self.online_db, name)
                    result = online_method(*args, **kwargs)
                    if result is not None:  # or other success check
                        return result
            except Exception as e:
                self._last_online_success = False
                st.warning(f"Online {name} failed, using fallback: {str(e)}")
                fallback_method = getattr(self.fallback, name)
                return fallback_method(*args, **kwargs)
        
        return method