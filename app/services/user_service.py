"""User accounts: the only place that knows how users are stored and checked."""
from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app.data import seed_data as db


class User(UserMixin):
    """Wraps a stored user record so Flask-Login can use it."""

    def __init__(self, record):
        self.id = str(record["id"])      # Flask-Login needs the id as a string
        self.name = record["name"]
        self.email = record["email"]
        self.role = record["role"]


def get_user(user_id):
    """Used by Flask-Login to reload the logged-in user from the session."""
    try:
        record = db.USERS.get(int(user_id))
    except (TypeError, ValueError):
        return None
    return User(record) if record else None


def verify_credentials(email, password):
    """Return the User if email and password match, otherwise None."""
    for record in db.USERS.values():
        if record["email"] == email and check_password_hash(record["password_hash"], password):
            return User(record)
    return None


def create_user(name, email, password):
    """Register a new restocker account. Raises ValueError with a friendly message."""
    name, email = name.strip(), email.strip().lower()
    if not name:
        raise ValueError("Please enter your name.")
    if "@" not in email or "." not in email.split("@")[-1]:
        raise ValueError("Please enter a valid email address.")
    if len(password) < 8:
        raise ValueError("Your password must be at least 8 characters long.")
    if any(record["email"] == email for record in db.USERS.values()):
        raise ValueError("An account with that email already exists.")
    new_id = max(db.USERS) + 1
    db.USERS[new_id] = {"id": new_id, "name": name, "email": email,
                        "password_hash": generate_password_hash(password),
                        "role": "restocker"}
    return User(db.USERS[new_id])
