"""User accounts and roles: the only place that knows how users are stored and checked.

Roles
- admin: the developer. Everything a user can do, plus managing accounts.
- user:  Mr Msiza and anyone who helps him restock. Sees every page and changes stock.

ROLE_PERMISSIONS is the single list of who may do what. Routes ask can(user, action);
the account-management functions below check it again themselves, so a missing
check in a route can never let a normal user manage accounts.
"""
from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db
from app.models import ROLES
from app.models import User as UserRow
from app.services.errors import ConflictError, NotFoundError, PermissionDenied, ValidationError
from app.services.pagination import paginate_query

ROLE_PERMISSIONS = {
    "admin": {"view", "change_stock", "manage_users"},
    "user": {"view", "change_stock"},
}
MIN_PASSWORD_LENGTH = 8


class User(UserMixin):
    """Wraps a stored user row so Flask-Login can use it."""

    def __init__(self, row):
        self.id = str(row.user_id)      # Flask-Login needs the id as a string
        self.name = row.name
        self.email = row.email
        self.role = row.role
        self.active = row.is_active

    @property
    def is_active(self):
        return self.active

    @property
    def is_admin(self):
        return self.role == "admin"


def can(user, action):
    """True if this user's role allows `action` ("view", "change_stock", "manage_users")."""
    return bool(getattr(user, "is_authenticated", False)) and \
        action in ROLE_PERMISSIONS.get(getattr(user, "role", None), set())


def require(user, action):
    """Raise PermissionDenied unless the user may do `action`."""
    if not can(user, action):
        raise PermissionDenied("You do not have permission to do that.")


def _user_dict(row):
    if not isinstance(row, UserRow):
        row = row[0]
    return {"id": row.user_id, "name": row.name, "email": row.email, "role": row.role,
            "is_active": row.is_active, "created_at": row.created_at.isoformat(timespec="seconds")}


# ------------------------------------------------------------------ login
def get_user(user_id):
    """Used by Flask-Login to reload the logged-in user from the session."""
    try:
        row = db.session.get(UserRow, int(user_id))
    except (TypeError, ValueError):
        return None
    return User(row) if row and row.is_active else None


def verify_credentials(email, password):
    """Return the User if email and password match an active account, otherwise None."""
    row = db.session.scalar(db.select(UserRow).where(UserRow.email == email.strip().lower()))
    if row and row.is_active and check_password_hash(row.password_hash, password):
        return User(row)
    return None


# ------------------------------------------------------------------ creating accounts
def _check_password(password, field="password"):
    if len(password or "") < MIN_PASSWORD_LENGTH:
        raise ValidationError(f"Your password must be at least {MIN_PASSWORD_LENGTH} characters long.", field)


def create_user(name, email, password, role="user"):
    """Create an account (no permission check: used by `flask create-admin` and by
    admin_create_user below). Raises ValidationError / ConflictError with a friendly message."""
    name, email = (name or "").strip(), (email or "").strip().lower()
    if not name:
        raise ValidationError("Please enter your name.", "name")
    if "@" not in email or "." not in email.split("@")[-1]:
        raise ValidationError("Please enter a valid email address.", "email")
    _check_password(password)
    if role not in ROLES:
        raise ValidationError(f"role must be one of: {', '.join(ROLES)}.", "role")
    if db.session.scalar(db.select(UserRow.user_id).where(UserRow.email == email)):
        raise ConflictError("An account with that email already exists.", "email")
    row = UserRow(name=name, email=email, role=role, password_hash=generate_password_hash(password))
    db.session.add(row)
    db.session.commit()
    return User(row)


# ------------------------------------------------------------------ account management (admin only)
def _get_row(user_id):
    row = db.session.get(UserRow, user_id)
    if row is None:
        raise NotFoundError(f"User {user_id} does not exist.")
    return row


def _active_admins():
    return db.session.scalar(db.select(db.func.count()).select_from(UserRow)
                             .where(UserRow.role == "admin", UserRow.is_active.is_(True)))


def list_users(acting_user, page=None, per_page=None):
    require(acting_user, "manage_users")
    return paginate_query(db.select(UserRow).order_by(UserRow.name), _user_dict, page, per_page)


def admin_create_user(acting_user, name, email, password, role="user"):
    """An admin adds an account for Mr Msiza or one of his helpers."""
    require(acting_user, "manage_users")
    user = create_user(name, email, password, role)
    return _user_dict(_get_row(int(user.id)))


def set_role(acting_user, user_id, role):
    require(acting_user, "manage_users")
    if role not in ROLES:
        raise ValidationError(f"role must be one of: {', '.join(ROLES)}.", "role")
    row = _get_row(user_id)
    if row.user_id == int(acting_user.id):
        raise ConflictError("You cannot change your own role.", "role")
    row.role = role
    db.session.commit()
    return _user_dict(row)


def set_active(acting_user, user_id, active):
    """Switch an account on or off. Switched-off accounts cannot log in; their history stays."""
    require(acting_user, "manage_users")
    row = _get_row(user_id)
    if row.user_id == int(acting_user.id) and not active:
        raise ConflictError("You cannot switch off your own account.", "is_active")
    if not active and row.role == "admin" and row.is_active and _active_admins() <= 1:
        raise ConflictError("SmartStock must keep at least one active admin.", "is_active")
    row.is_active = bool(active)
    db.session.commit()
    return _user_dict(row)


def reset_password(acting_user, user_id, new_password):
    """An admin sets a new password for someone who forgot theirs."""
    require(acting_user, "manage_users")
    _check_password(new_password, "new_password")
    row = _get_row(user_id)
    row.password_hash = generate_password_hash(new_password)
    db.session.commit()


def change_own_password(user, current_password, new_password):
    """Any logged-in user changes their own password."""
    row = _get_row(int(user.id))
    if not check_password_hash(row.password_hash, current_password or ""):
        raise ValidationError("Your current password is incorrect.", "current_password")
    _check_password(new_password, "new_password")
    row.password_hash = generate_password_hash(new_password)
    db.session.commit()
