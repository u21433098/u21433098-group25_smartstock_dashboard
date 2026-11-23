"""The catalogue: suppliers, products and machines. Create, read and update.

Stock levels change through inventory_service (counts, restocks, stock takes); this
module adds and edits the things that stock belongs to:

- a supplier (name, lead time),
- a product (name, supplier, unit cost, case size), which also starts its central
  storage row at 0 units,
- a machine (code, location, drawer capacity), and the products it carries
  (one machine slot and one drawer slot per product, both starting at 0 units).

Both roles may do this ("change_stock"): Mr Msiza runs the business and adds a new
product or machine himself. Every function checks the input and raises the same errors
as the rest of the services (ValidationError 400, NotFoundError 404, ConflictError 409).
"""
from decimal import Decimal, InvalidOperation

from app.extensions import db
from app.models import CentralStock, DrawerStock, Machine, MachineStock, Product, Supplier
from app.services.errors import ConflictError, NotFoundError, ValidationError
from app.services.pagination import paginate_list, parse_int, parse_sort, sort_list
from app.services.user_service import require

MAX_UNIT_COST = Decimal("999999.99")     # products.unit_cost is DECIMAL(8, 2)


# ------------------------------------------------------------------ input checks
def _text(value, field, max_length):
    value = (value or "").strip() if isinstance(value, str) else value
    if not isinstance(value, str) or not value:
        raise ValidationError(f"{field} is required.", field)
    if len(value) > max_length:
        raise ValidationError(f"{field} must be at most {max_length} characters.", field)
    return value


def _whole(value, field, minimum, maximum):
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationError(f"{field} must be a whole number.", field)
    if not minimum <= value <= maximum:
        raise ValidationError(f"{field} must be between {minimum} and {maximum}.", field)
    return value


def _money(value, field="unit_cost"):
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValidationError(f"{field} must be a number of rand, e.g. 9.50.", field)
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"))
    except InvalidOperation:
        raise ValidationError(f"{field} must be a number of rand, e.g. 9.50.", field)
    if not Decimal("0") <= amount <= MAX_UNIT_COST:
        raise ValidationError(f"{field} must be between 0 and {MAX_UNIT_COST}.", field)
    return amount


def _unique(model, column, value, field, label, ignore_id=None):
    """Refuse a name or code that another row already uses (409, not a database error)."""
    query = db.select(model).where(column == value)
    existing = db.session.scalars(query).first()
    if existing is not None and getattr(existing, model.__table__.primary_key.columns.keys()[0]) != ignore_id:
        raise ConflictError(f"A {label} called '{value}' already exists.", field)


def _get(model, key, label):
    row = db.session.get(model, key)
    if row is None:
        raise NotFoundError(f"{label} {key} does not exist.")
    return row


# ------------------------------------------------------------------ suppliers
def _supplier_dict(s):
    return {"id": s.supplier_id, "name": s.name, "lead_time_days": s.lead_time_days,
            "products": len(s.products)}


def list_suppliers(page=None, per_page=None):
    rows = [_supplier_dict(s) for s in db.session.scalars(db.select(Supplier).order_by(Supplier.name))]
    return paginate_list(rows, page, per_page)


def get_supplier(supplier_id):
    return _supplier_dict(_get(Supplier, supplier_id, "Supplier"))


def create_supplier(acting_user, name, lead_time_days):
    require(acting_user, "change_stock")
    name = _text(name, "name", 100)
    lead = _whole(lead_time_days, "lead_time_days", 0, 365)
    _unique(Supplier, Supplier.name, name, "name", "supplier")
    supplier = Supplier(name=name, lead_time_days=lead)
    db.session.add(supplier)
    db.session.commit()
    return _supplier_dict(supplier)


def update_supplier(acting_user, supplier_id, name=None, lead_time_days=None):
    require(acting_user, "change_stock")
    supplier = _get(Supplier, supplier_id, "Supplier")
    if name is not None:
        name = _text(name, "name", 100)
        _unique(Supplier, Supplier.name, name, "name", "supplier", ignore_id=supplier_id)
        supplier.name = name
    if lead_time_days is not None:
        supplier.lead_time_days = _whole(lead_time_days, "lead_time_days", 0, 365)
    db.session.commit()
    return _supplier_dict(supplier)


# ------------------------------------------------------------------ products
PRODUCT_SORTS = {"name", "supplier", "unit_cost", "central_qty"}


def _product_dict(p):
    central = db.session.get(CentralStock, p.product_id)
    machines = db.session.scalar(db.select(db.func.count()).select_from(MachineStock)
                                 .where(MachineStock.product_id == p.product_id))
    return {"id": p.product_id, "name": p.name, "supplier_id": p.supplier_id, "supplier": p.supplier.name,
            "unit_cost": float(p.unit_cost), "case_size": p.case_size,
            "central_qty": central.qty if central else 0,
            "central_threshold": central.threshold if central else 0,
            "machines": machines}


def list_products(search=None, supplier_id=None, sort=None, page=None, per_page=None):
    key, descending = parse_sort(sort, PRODUCT_SORTS, "name")
    supplier_id = parse_int(supplier_id, "supplier_id", minimum=1)
    query = db.select(Product)
    if supplier_id is not None:
        query = query.where(Product.supplier_id == supplier_id)
    rows = [_product_dict(p) for p in db.session.scalars(query)]
    if search:
        rows = [r for r in rows if search.strip().lower() in r["name"].lower()]
    return paginate_list(sort_list(rows, key, descending), page, per_page)


def get_product(product_id):
    return _product_dict(_get(Product, product_id, "Product"))


def create_product(acting_user, name, supplier_id, unit_cost, case_size, central_threshold=20):
    """Add a product. Its central storage row starts at 0 units with the given threshold."""
    require(acting_user, "change_stock")
    name = _text(name, "name", 100)
    supplier_id = _whole(supplier_id, "supplier_id", 1, 10**9)
    _get(Supplier, supplier_id, "Supplier")
    cost = _money(unit_cost)
    case = _whole(case_size, "case_size", 1, 1000)
    threshold = _whole(central_threshold, "central_threshold", 0, 5000)
    _unique(Product, Product.name, name, "name", "product")
    product = Product(name=name, supplier_id=supplier_id, unit_cost=cost, case_size=case)
    db.session.add(product)
    db.session.flush()                                   # gives the product its id
    db.session.add(CentralStock(product_id=product.product_id, qty=0, threshold=threshold))
    db.session.commit()
    return _product_dict(product)


def update_product(acting_user, product_id, name=None, supplier_id=None, unit_cost=None, case_size=None):
    require(acting_user, "change_stock")
    product = _get(Product, product_id, "Product")
    if name is not None:
        name = _text(name, "name", 100)
        _unique(Product, Product.name, name, "name", "product", ignore_id=product_id)
        product.name = name
    if supplier_id is not None:
        product.supplier_id = _get(Supplier, _whole(supplier_id, "supplier_id", 1, 10**9), "Supplier").supplier_id
    if unit_cost is not None:
        product.unit_cost = _money(unit_cost)
    if case_size is not None:
        product.case_size = _whole(case_size, "case_size", 1, 1000)
    db.session.commit()
    return _product_dict(product)


# ------------------------------------------------------------------ machines
def _machine_dict(m):
    carried = db.session.scalar(db.select(db.func.count()).select_from(MachineStock)
                                .where(MachineStock.machine_id == m.machine_id))
    return {"id": m.machine_id, "code": m.code, "location": m.location,
            "drawer_capacity": m.drawer_capacity, "products": carried}


def create_machine(acting_user, code, location, drawer_capacity=50):
    """Add a machine. Give it products with add_product_to_machine()."""
    require(acting_user, "change_stock")
    code = _text(code, "code", 20).upper()
    location = _text(location, "location", 100)
    capacity = _whole(drawer_capacity, "drawer_capacity", 0, 1000)
    _unique(Machine, Machine.code, code, "code", "machine")
    machine = Machine(code=code, location=location, drawer_capacity=capacity)
    db.session.add(machine)
    db.session.commit()
    return _machine_dict(machine)


def update_machine(acting_user, machine_id, location=None, drawer_capacity=None):
    """Change where a machine stands or how much its drawer holds. The code stays fixed."""
    require(acting_user, "change_stock")
    machine = _get(Machine, machine_id, "Machine")
    if location is not None:
        machine.location = _text(location, "location", 100)
    if drawer_capacity is not None:
        machine.drawer_capacity = _whole(drawer_capacity, "drawer_capacity", 0, 1000)
    db.session.commit()
    return _machine_dict(machine)


def add_product_to_machine(acting_user, machine_id, product_id, capacity=20, threshold=5,
                           drawer_capacity=12, drawer_threshold=2):
    """Start carrying a product in a machine: one machine slot and one drawer slot, both empty.

    Restock it afterwards with inventory_service.restock_visit().
    """
    require(acting_user, "change_stock")
    _get(Machine, machine_id, "Machine")
    product_id = _whole(product_id, "product_id", 1, 10**9)
    _get(Product, product_id, "Product")
    capacity = _whole(capacity, "capacity", 1, 1000)
    threshold = _whole(threshold, "threshold", 0, capacity)
    drawer_capacity = _whole(drawer_capacity, "drawer_capacity", 0, 1000)
    drawer_threshold = _whole(drawer_threshold, "drawer_threshold", 0, max(drawer_capacity, 0))
    if db.session.get(MachineStock, (machine_id, product_id)) is not None:
        raise ConflictError("That machine already carries this product.", "product_id")
    db.session.add(MachineStock(machine_id=machine_id, product_id=product_id, qty=0,
                                capacity=capacity, threshold=threshold))
    db.session.add(DrawerStock(machine_id=machine_id, product_id=product_id, qty=0,
                               capacity=drawer_capacity, threshold=drawer_threshold))
    db.session.commit()
    from app.services import inventory_service
    return next(r for r in inventory_service.get_machine_rows(machine_id) if r["product_id"] == product_id)
