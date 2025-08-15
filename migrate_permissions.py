from database import BeverageQADatabase
import json

def migrate_existing_users():
    db = BeverageQADatabase()
    
    # Get all users without permissions
    users = db.get_all_users_data()
    
    # Define default permissions based on roles
    role_permissions = {
        'admin': {
            'view_all_data': True,
            'edit_all_data': True,
            'manage_users': True,
            'add_comments': True,
            'export_data': True
        },
        'supervisor': {
            'view_all_data': True,
            'edit_all_data': True,
            'manage_users': False,
            'add_comments': True,
            'export_data': True
        },
        'operator': {
            'view_all_data': True,
            'edit_own_data': True,
            'manage_users': False,
            'add_comments': True,
            'export_data': True
        },
        'viewer': {
            'view_public_data': True,
            'edit_data': False,
            'manage_users': False,
            'add_comments': False,
            'export_data': False
        }
    }
    
    # Update each user with default permissions
    for _, user in users.iterrows():
        permissions = role_permissions.get(user['role'], {})
        db.update_user_permissions(user['username'], permissions)
    
    print(f"Migrated permissions for {len(users)} users")

if __name__ == "__main__":
    migrate_existing_users()