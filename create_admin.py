
from getpass import getpass

from app.dashboard.routes import app
from app.dashboard.auth import db, User


def create_admin():
    with app.app_context():
        username = input("Enter admin username: ").strip()

        if not username:
            print("Username cannot be empty.")
            return

        password = getpass("Enter admin password (minimum 8 characters): ")
        confirm_password = getpass("Confirm admin password: ")

        if len(password) < 8:
            print("Password must be at least 8 characters.")
            return

        if password != confirm_password:
            print("Passwords do not match.")
            return

        existing_user = User.query.filter_by(username=username).first()

        if existing_user:
            print("That username already exists. Choose another username.")
            return

        admin = User(username=username, role="admin")
        admin.set_password(password)

        db.session.add(admin)
        db.session.commit()

        print("Admin account created successfully.")


if __name__ == "__main__":
    create_admin()
