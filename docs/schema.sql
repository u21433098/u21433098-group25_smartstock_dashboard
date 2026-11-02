-- SmartStock MySQL schema (generated from migrations/versions/0001_initial_schema.py)
-- Normal setup uses 'flask db upgrade'; this file is for reading, or for loading by hand:
--   mysql -u smartstock -p smartstock < docs/schema.sql

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 0001

CREATE TABLE machines (
    machine_id INTEGER NOT NULL AUTO_INCREMENT, 
    code VARCHAR(20) NOT NULL, 
    location VARCHAR(100) NOT NULL, 
    drawer_capacity INTEGER NOT NULL DEFAULT '50', 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    CONSTRAINT pk_machines PRIMARY KEY (machine_id), 
    CONSTRAINT ck_machines_drawer_capacity_not_negative CHECK (drawer_capacity >= 0), 
    CONSTRAINT uq_machines_code UNIQUE (code)
);

CREATE TABLE suppliers (
    supplier_id INTEGER NOT NULL AUTO_INCREMENT, 
    name VARCHAR(100) NOT NULL, 
    lead_time_days INTEGER NOT NULL, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    CONSTRAINT pk_suppliers PRIMARY KEY (supplier_id), 
    CONSTRAINT ck_suppliers_lead_time_not_negative CHECK (lead_time_days >= 0), 
    CONSTRAINT uq_suppliers_name UNIQUE (name)
);

CREATE TABLE users (
    user_id INTEGER NOT NULL AUTO_INCREMENT, 
    name VARCHAR(100) NOT NULL, 
    email VARCHAR(255) NOT NULL, 
    password_hash VARCHAR(255) NOT NULL, 
    `role` VARCHAR(10) NOT NULL DEFAULT 'user', 
    is_active BOOL NOT NULL DEFAULT true, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    CONSTRAINT pk_users PRIMARY KEY (user_id), 
    CONSTRAINT ck_users_role_valid CHECK (role IN ('admin', 'user')), 
    CONSTRAINT uq_users_email UNIQUE (email)
);

CREATE TABLE products (
    product_id INTEGER NOT NULL AUTO_INCREMENT, 
    name VARCHAR(100) NOT NULL, 
    supplier_id INTEGER NOT NULL, 
    unit_cost NUMERIC(8, 2) NOT NULL, 
    case_size INTEGER NOT NULL, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    CONSTRAINT pk_products PRIMARY KEY (product_id), 
    CONSTRAINT ck_products_case_size_positive CHECK (case_size > 0), 
    CONSTRAINT ck_products_unit_cost_not_negative CHECK (unit_cost >= 0), 
    CONSTRAINT fk_products_supplier_id_suppliers FOREIGN KEY(supplier_id) REFERENCES suppliers (supplier_id) ON DELETE RESTRICT, 
    CONSTRAINT uq_products_name UNIQUE (name)
);

CREATE INDEX ix_products_supplier_id ON products (supplier_id);

CREATE TABLE central_stock (
    product_id INTEGER NOT NULL, 
    qty INTEGER NOT NULL DEFAULT '0', 
    threshold INTEGER NOT NULL, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    CONSTRAINT pk_central_stock PRIMARY KEY (product_id), 
    CONSTRAINT ck_central_stock_qty_not_negative CHECK (qty >= 0), 
    CONSTRAINT ck_central_stock_threshold_not_negative CHECK (threshold >= 0), 
    CONSTRAINT fk_central_stock_product_id_products FOREIGN KEY(product_id) REFERENCES products (product_id) ON DELETE RESTRICT
);

CREATE TABLE drawer_stock (
    machine_id INTEGER NOT NULL, 
    product_id INTEGER NOT NULL, 
    qty INTEGER NOT NULL DEFAULT '0', 
    capacity INTEGER NOT NULL, 
    threshold INTEGER NOT NULL, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    CONSTRAINT pk_drawer_stock PRIMARY KEY (machine_id, product_id), 
    CONSTRAINT ck_drawer_stock_qty_within_capacity CHECK (qty >= 0 AND qty <= capacity), 
    CONSTRAINT ck_drawer_stock_threshold_not_negative CHECK (threshold >= 0), 
    CONSTRAINT fk_drawer_stock_machine_id_machines FOREIGN KEY(machine_id) REFERENCES machines (machine_id) ON DELETE CASCADE, 
    CONSTRAINT fk_drawer_stock_product_id_products FOREIGN KEY(product_id) REFERENCES products (product_id) ON DELETE RESTRICT
);

CREATE INDEX ix_drawer_stock_product_machine ON drawer_stock (product_id, machine_id);

CREATE TABLE machine_stock (
    machine_id INTEGER NOT NULL, 
    product_id INTEGER NOT NULL, 
    qty INTEGER NOT NULL DEFAULT '0', 
    capacity INTEGER NOT NULL, 
    threshold INTEGER NOT NULL, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    CONSTRAINT pk_machine_stock PRIMARY KEY (machine_id, product_id), 
    CONSTRAINT ck_machine_stock_qty_within_capacity CHECK (qty >= 0 AND qty <= capacity), 
    CONSTRAINT ck_machine_stock_threshold_not_negative CHECK (threshold >= 0), 
    CONSTRAINT fk_machine_stock_machine_id_machines FOREIGN KEY(machine_id) REFERENCES machines (machine_id) ON DELETE CASCADE, 
    CONSTRAINT fk_machine_stock_product_id_products FOREIGN KEY(product_id) REFERENCES products (product_id) ON DELETE RESTRICT
);

CREATE INDEX ix_machine_stock_product_machine ON machine_stock (product_id, machine_id);

CREATE TABLE sales (
    sale_id INTEGER NOT NULL AUTO_INCREMENT, 
    machine_id INTEGER NOT NULL, 
    product_id INTEGER NOT NULL, 
    sale_date DATE NOT NULL, 
    qty INTEGER NOT NULL, 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    CONSTRAINT pk_sales PRIMARY KEY (sale_id), 
    CONSTRAINT ck_sales_qty_not_negative CHECK (qty >= 0), 
    CONSTRAINT fk_sales_machine_id_machines FOREIGN KEY(machine_id) REFERENCES machines (machine_id) ON DELETE CASCADE, 
    CONSTRAINT fk_sales_product_id_products FOREIGN KEY(product_id) REFERENCES products (product_id) ON DELETE RESTRICT, 
    CONSTRAINT uq_sales_machine_id_product_id_sale_date UNIQUE (machine_id, product_id, sale_date)
);

CREATE INDEX ix_sales_product_date ON sales (product_id, sale_date);

CREATE INDEX ix_sales_sale_date ON sales (sale_date);

CREATE TABLE stock_movements (
    movement_id INTEGER NOT NULL AUTO_INCREMENT, 
    machine_id INTEGER, 
    product_id INTEGER NOT NULL, 
    user_id INTEGER, 
    tier VARCHAR(10) NOT NULL, 
    old_qty INTEGER NOT NULL, 
    new_qty INTEGER NOT NULL, 
    note VARCHAR(255) NOT NULL DEFAULT '', 
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, 
    CONSTRAINT pk_stock_movements PRIMARY KEY (movement_id), 
    CONSTRAINT ck_stock_movements_tier_valid CHECK (tier IN ('Machine', 'Drawer', 'Central')), 
    CONSTRAINT fk_stock_movements_machine_id_machines FOREIGN KEY(machine_id) REFERENCES machines (machine_id) ON DELETE CASCADE, 
    CONSTRAINT fk_stock_movements_product_id_products FOREIGN KEY(product_id) REFERENCES products (product_id) ON DELETE RESTRICT, 
    CONSTRAINT fk_stock_movements_user_id_users FOREIGN KEY(user_id) REFERENCES users (user_id) ON DELETE SET NULL
);

CREATE INDEX ix_stock_movements_created ON stock_movements (created_at);

CREATE INDEX ix_stock_movements_machine_created ON stock_movements (machine_id, created_at);

CREATE INDEX ix_stock_movements_user_id ON stock_movements (user_id);

INSERT INTO alembic_version (version_num) VALUES ('0001');

