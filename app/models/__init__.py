"""MySQL tables for SmartStock, written as SQLAlchemy models.

One class = one table. The ERD in docs/erd.md shows how they connect.

Design notes
- Normalised to 3NF: every non-key column depends only on its table's key
  (e.g. a supplier's lead time lives in `suppliers`, never copied into `products`).
- Every table has `created_at` / `updated_at` audit columns (TimestampMixin).
- CHECK constraints stop impossible stock levels (negative, or above capacity)
  at the database level, not only in the Python code.
- Indexes follow how the app reads the data: by product across all machines,
  by date for the 30-day sales window, and newest-first for the audit trail.
"""
from app.extensions import db

ROLES = ("admin", "user")
TIERS = ("Machine", "Drawer", "Central")


class TimestampMixin:
    """Audit fields: when the row was created and last changed."""
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.text("CURRENT_TIMESTAMP"))
    updated_at = db.Column(db.DateTime, nullable=False, server_default=db.text("CURRENT_TIMESTAMP"),
                           onupdate=db.func.now())


# ------------------------------------------------------------------ people
class User(TimestampMixin, db.Model):
    __tablename__ = "users"
    user_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(255), nullable=False, unique=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(10), nullable=False, server_default="user")
    is_active = db.Column(db.Boolean, nullable=False, server_default=db.true())

    __table_args__ = (
        db.CheckConstraint("role IN ('admin', 'user')", name="role_valid"),
    )


# ------------------------------------------------------------------ catalogue
class Supplier(TimestampMixin, db.Model):
    __tablename__ = "suppliers"
    supplier_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    lead_time_days = db.Column(db.Integer, nullable=False)

    products = db.relationship("Product", back_populates="supplier")

    __table_args__ = (
        db.CheckConstraint("lead_time_days >= 0", name="lead_time_not_negative"),
    )


class Product(TimestampMixin, db.Model):
    __tablename__ = "products"
    product_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    supplier_id = db.Column(db.Integer, db.ForeignKey("suppliers.supplier_id", ondelete="RESTRICT"),
                            nullable=False, index=True)
    unit_cost = db.Column(db.Numeric(8, 2), nullable=False)
    case_size = db.Column(db.Integer, nullable=False)

    supplier = db.relationship("Supplier", back_populates="products")

    __table_args__ = (
        db.CheckConstraint("unit_cost >= 0", name="unit_cost_not_negative"),
        db.CheckConstraint("case_size > 0", name="case_size_positive"),
    )


class Machine(TimestampMixin, db.Model):
    __tablename__ = "machines"
    machine_id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), nullable=False, unique=True)
    location = db.Column(db.String(100), nullable=False)
    drawer_capacity = db.Column(db.Integer, nullable=False, server_default="50")  # total units

    __table_args__ = (
        db.CheckConstraint("drawer_capacity >= 0", name="drawer_capacity_not_negative"),
    )


# ------------------------------------------------------------------ the three stock tiers
class MachineStock(TimestampMixin, db.Model):
    """Tier 1: units inside the machine's sales compartment, per product slot."""
    __tablename__ = "machine_stock"
    machine_id = db.Column(db.Integer, db.ForeignKey("machines.machine_id", ondelete="CASCADE"),
                           primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.product_id", ondelete="RESTRICT"),
                           primary_key=True)
    qty = db.Column(db.Integer, nullable=False, server_default="0")
    capacity = db.Column(db.Integer, nullable=False)
    threshold = db.Column(db.Integer, nullable=False)

    product = db.relationship("Product")

    __table_args__ = (
        db.CheckConstraint("qty >= 0 AND qty <= capacity", name="qty_within_capacity"),
        db.CheckConstraint("threshold >= 0", name="threshold_not_negative"),
        # The primary key already serves "by machine" lookups; this one serves "by product".
        db.Index("ix_machine_stock_product_machine", "product_id", "machine_id"),
    )


class DrawerStock(TimestampMixin, db.Model):
    """Tier 2: the buffer drawer at the base of each machine, per product."""
    __tablename__ = "drawer_stock"
    machine_id = db.Column(db.Integer, db.ForeignKey("machines.machine_id", ondelete="CASCADE"),
                           primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.product_id", ondelete="RESTRICT"),
                           primary_key=True)
    qty = db.Column(db.Integer, nullable=False, server_default="0")
    capacity = db.Column(db.Integer, nullable=False)
    threshold = db.Column(db.Integer, nullable=False)

    product = db.relationship("Product")

    __table_args__ = (
        db.CheckConstraint("qty >= 0 AND qty <= capacity", name="qty_within_capacity"),
        db.CheckConstraint("threshold >= 0", name="threshold_not_negative"),
        db.Index("ix_drawer_stock_product_machine", "product_id", "machine_id"),
    )


class CentralStock(TimestampMixin, db.Model):
    """Tier 3: the shared pool at the Adlers café (one row per product)."""
    __tablename__ = "central_stock"
    product_id = db.Column(db.Integer, db.ForeignKey("products.product_id", ondelete="RESTRICT"),
                           primary_key=True)
    qty = db.Column(db.Integer, nullable=False, server_default="0")
    threshold = db.Column(db.Integer, nullable=False)

    product = db.relationship("Product")

    __table_args__ = (
        db.CheckConstraint("qty >= 0", name="qty_not_negative"),
        db.CheckConstraint("threshold >= 0", name="threshold_not_negative"),
    )


# ------------------------------------------------------------------ history
class Sale(TimestampMixin, db.Model):
    """Units of one product sold by one machine on one day (daily total)."""
    __tablename__ = "sales"
    sale_id = db.Column(db.Integer, primary_key=True)
    machine_id = db.Column(db.Integer, db.ForeignKey("machines.machine_id", ondelete="CASCADE"),
                           nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.product_id", ondelete="RESTRICT"),
                           nullable=False)
    sale_date = db.Column(db.Date, nullable=False)
    qty = db.Column(db.Integer, nullable=False)

    __table_args__ = (
        db.CheckConstraint("qty >= 0", name="qty_not_negative"),
        # One total per machine, product and day. This unique key is also the index
        # used to read one machine's 30-day history.
        db.UniqueConstraint("machine_id", "product_id", "sale_date"),
        # Fleet-wide totals per product over a date range (shopping list, best sellers).
        db.Index("ix_sales_product_date", "product_id", "sale_date"),
        db.Index("ix_sales_sale_date", "sale_date"),
    )


class StockMovement(db.Model):
    """Audit trail: every change to any stock tier, who made it and why.

    Rows are never edited, so there is no updated_at column.
    """
    __tablename__ = "stock_movements"
    movement_id = db.Column(db.Integer, primary_key=True)
    machine_id = db.Column(db.Integer, db.ForeignKey("machines.machine_id", ondelete="CASCADE"),
                           nullable=True)   # NULL for central-storage stock takes
    product_id = db.Column(db.Integer, db.ForeignKey("products.product_id", ondelete="RESTRICT"),
                           nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.user_id", ondelete="SET NULL"),
                        nullable=True, index=True)
    tier = db.Column(db.String(10), nullable=False)
    old_qty = db.Column(db.Integer, nullable=False)
    new_qty = db.Column(db.Integer, nullable=False)
    note = db.Column(db.String(255), nullable=False, server_default="")
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.text("CURRENT_TIMESTAMP"))

    product = db.relationship("Product")
    machine = db.relationship("Machine")
    user = db.relationship("User")

    __table_args__ = (
        db.CheckConstraint("tier IN ('Machine', 'Drawer', 'Central')", name="tier_valid"),
        db.Index("ix_stock_movements_machine_created", "machine_id", "created_at"),
        db.Index("ix_stock_movements_created", "created_at"),
    )
