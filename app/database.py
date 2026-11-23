import sqlite3
from datetime import datetime
from pathlib import Path
from flask import current_app, g
from werkzeug.security import generate_password_hash


def get_db():
    if "db" not in g:
        database_path = Path(current_app.config["DATABASE"]).expanduser().resolve()
        database_path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(str(database_path), timeout=5)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        db.execute("PRAGMA busy_timeout = 5000")
        g.db = db
    return g.db


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def init_db():
    """Create the fresh AutoCare database schema and seed master data.

    This function is intentionally non-destructive. For the Step 1 fresh-start
    database, delete the existing autocare.db once before the first run.
    """
    db = get_db()
    db.executescript(
        """
        PRAGMA journal_mode = WAL;
        PRAGMA foreign_keys = ON;

        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            username TEXT NOT NULL UNIQUE COLLATE NOCASE,
            email TEXT UNIQUE COLLATE NOCASE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'admin'
                CHECK (role IN ('admin','manager','receptionist','technician')),
            is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
            created_at TEXT NOT NULL,
            updated_at TEXT,
            last_login TEXT
        );

        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT NOT NULL,
            email TEXT,
            address TEXT,
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS vehicles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            registration TEXT,
            brand TEXT,
            model TEXT NOT NULL,
            year INTEGER,
            fuel TEXT,
            color TEXT,
            vin TEXT,
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT,
            UNIQUE (registration),
            UNIQUE (vin),
            UNIQUE (id, customer_id),
            FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE COLLATE NOCASE,
            description TEXT,
            base_price REAL NOT NULL DEFAULT 0 CHECK (base_price >= 0),
            estimated_hours REAL NOT NULL DEFAULT 0 CHECK (estimated_hours >= 0),
            category TEXT,
            is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
            created_at TEXT NOT NULL,
            updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS technicians (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT,
            specialization TEXT,
            experience TEXT,
            status TEXT NOT NULL DEFAULT 'Active'
                CHECK (status IN ('Active','Inactive','On Leave')),
            created_at TEXT NOT NULL,
            updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            booking_no TEXT UNIQUE,
            customer_id INTEGER,
            vehicle_id INTEGER,
            service_id INTEGER,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            message TEXT,
            pickup_required INTEGER NOT NULL DEFAULT 0 CHECK (pickup_required IN (0,1)),
            drop_required INTEGER NOT NULL DEFAULT 0 CHECK (drop_required IN (0,1)),
            preferred_contact TEXT NOT NULL DEFAULT 'Phone' CHECK (preferred_contact IN ('Phone','Email','WhatsApp')),
            whatsapp_opt_in INTEGER NOT NULL DEFAULT 0 CHECK (whatsapp_opt_in IN (0,1)),
            status TEXT NOT NULL DEFAULT 'Pending'
                CHECK (status IN ('Pending','Confirmed','In Progress','Completed','Cancelled')),
            home_visit_charge REAL NOT NULL DEFAULT 0 CHECK (home_visit_charge >= 0),
            visit_payment_status TEXT NOT NULL DEFAULT 'not_required'
                CHECK (visit_payment_status IN ('not_required','pending','paid','failed','refunded')),
            razorpay_order_id TEXT UNIQUE,
            visit_payment_token TEXT,
            razorpay_payment_id TEXT UNIQUE,
            visit_paid_at TEXT,
            dispatched_at TEXT,
            technician_id INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT,
            FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE SET NULL,
            FOREIGN KEY (vehicle_id, customer_id)
                REFERENCES vehicles(id, customer_id) ON DELETE SET NULL,
            FOREIGN KEY (service_id) REFERENCES services(id) ON DELETE SET NULL,
            FOREIGN KEY (technician_id) REFERENCES technicians(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS home_visit_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            booking_id INTEGER NOT NULL,
            provider TEXT NOT NULL DEFAULT 'razorpay',
            order_id TEXT NOT NULL UNIQUE,
            payment_id TEXT UNIQUE,
            amount_paise INTEGER NOT NULL CHECK (amount_paise > 0),
            currency TEXT NOT NULL DEFAULT 'INR',
            status TEXT NOT NULL DEFAULT 'created' CHECK (status IN ('created','authorized','captured','failed','refunded')),
            webhook_event_id TEXT UNIQUE,
            raw_provider_status TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT,
            FOREIGN KEY (booking_id) REFERENCES bookings(id) ON DELETE RESTRICT
        );

        CREATE TABLE IF NOT EXISTS notification_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            booking_id INTEGER,
            booking_no TEXT,
            event_status TEXT NOT NULL,
            channel TEXT NOT NULL CHECK (channel IN ('email','sms','whatsapp')),
            recipient_masked TEXT,
            status TEXT NOT NULL CHECK (status IN ('submitted','failed','skipped')),
            provider TEXT,
            provider_message_id TEXT,
            provider_status TEXT,
            error_message TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT,
            FOREIGN KEY (booking_id) REFERENCES bookings(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS job_cards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            booking_id INTEGER UNIQUE,
            customer_id INTEGER NOT NULL,
            vehicle_id INTEGER NOT NULL,
            complaint TEXT,
            diagnosis TEXT,
            work_done TEXT,
            technician_id INTEGER,
            odometer INTEGER CHECK (odometer IS NULL OR odometer >= 0),
            status TEXT NOT NULL DEFAULT 'Open'
                CHECK (status IN ('Open','In Progress','Ready','Closed')),
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT,
            FOREIGN KEY (booking_id) REFERENCES bookings(id) ON DELETE SET NULL,
            FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE RESTRICT,
            FOREIGN KEY (vehicle_id, customer_id)
                REFERENCES vehicles(id, customer_id) ON DELETE RESTRICT,
            FOREIGN KEY (technician_id) REFERENCES technicians(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS job_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_card_id INTEGER NOT NULL,
            service_id INTEGER,
            item_type TEXT NOT NULL DEFAULT 'service'
                CHECK (item_type IN ('service','part','labor','other')),
            description TEXT NOT NULL,
            quantity REAL NOT NULL DEFAULT 1 CHECK (quantity > 0),
            unit_price REAL NOT NULL DEFAULT 0 CHECK (unit_price >= 0),
            total REAL NOT NULL DEFAULT 0 CHECK (total >= 0),
            created_at TEXT NOT NULL,
            updated_at TEXT,
            FOREIGN KEY (job_card_id) REFERENCES job_cards(id) ON DELETE CASCADE,
            FOREIGN KEY (service_id) REFERENCES services(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS estimates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            vehicle_id INTEGER NOT NULL,
            job_card_id INTEGER,
            estimate_no TEXT NOT NULL UNIQUE,
            subtotal REAL NOT NULL DEFAULT 0 CHECK (subtotal >= 0),
            discount REAL NOT NULL DEFAULT 0 CHECK (discount >= 0),
            tax REAL NOT NULL DEFAULT 0 CHECK (tax >= 0),
            total REAL NOT NULL DEFAULT 0 CHECK (total >= 0),
            status TEXT NOT NULL DEFAULT 'Draft'
                CHECK (status IN ('Draft','Sent','Approved','Rejected','Expired')),
            created_at TEXT NOT NULL,
            updated_at TEXT,
            approved_at TEXT,
            FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE RESTRICT,
            FOREIGN KEY (vehicle_id, customer_id)
                REFERENCES vehicles(id, customer_id) ON DELETE RESTRICT,
            FOREIGN KEY (job_card_id) REFERENCES job_cards(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS estimate_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            estimate_id INTEGER NOT NULL,
            service_id INTEGER,
            item_type TEXT NOT NULL DEFAULT 'service'
                CHECK (item_type IN ('service','part','labor','other')),
            description TEXT NOT NULL,
            quantity REAL NOT NULL DEFAULT 1 CHECK (quantity > 0),
            unit_price REAL NOT NULL DEFAULT 0 CHECK (unit_price >= 0),
            total REAL NOT NULL DEFAULT 0 CHECK (total >= 0),
            created_at TEXT NOT NULL,
            updated_at TEXT,
            FOREIGN KEY (estimate_id) REFERENCES estimates(id) ON DELETE CASCADE,
            FOREIGN KEY (service_id) REFERENCES services(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_card_id INTEGER NOT NULL UNIQUE,
            estimate_id INTEGER UNIQUE,
            invoice_no TEXT NOT NULL UNIQUE,
            subtotal REAL NOT NULL DEFAULT 0 CHECK (subtotal >= 0),
            discount REAL NOT NULL DEFAULT 0 CHECK (discount >= 0),
            tax REAL NOT NULL DEFAULT 0 CHECK (tax >= 0),
            total REAL NOT NULL DEFAULT 0 CHECK (total >= 0),
            payment_status TEXT NOT NULL DEFAULT 'Unpaid'
                CHECK (payment_status IN ('Unpaid','Partially Paid','Paid')),
            paid_amount REAL NOT NULL DEFAULT 0 CHECK (paid_amount >= 0),
            created_at TEXT NOT NULL,
            updated_at TEXT,
            FOREIGN KEY (job_card_id) REFERENCES job_cards(id) ON DELETE RESTRICT,
            FOREIGN KEY (estimate_id) REFERENCES estimates(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_id INTEGER NOT NULL,
            amount REAL NOT NULL CHECK (amount > 0),
            payment_method TEXT NOT NULL
                CHECK (payment_method IN ('Cash','UPI','Card','Bank Transfer','Other')),
            transaction_id TEXT,
            payment_date TEXT NOT NULL,
            notes TEXT,
            created_by INTEGER,
            created_at TEXT NOT NULL,
            FOREIGN KEY (invoice_id) REFERENCES invoices(id) ON DELETE CASCADE,
            FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL
        );

        CREATE INDEX IF NOT EXISTS idx_customers_phone ON customers(phone);
        CREATE INDEX IF NOT EXISTS idx_vehicles_customer ON vehicles(customer_id);
        CREATE INDEX IF NOT EXISTS idx_vehicles_vin ON vehicles(vin);
        CREATE INDEX IF NOT EXISTS idx_bookings_date_status ON bookings(date, status);
        CREATE INDEX IF NOT EXISTS idx_bookings_no ON bookings(booking_no);
        CREATE INDEX IF NOT EXISTS idx_bookings_customer ON bookings(customer_id);
        CREATE INDEX IF NOT EXISTS idx_bookings_vehicle ON bookings(vehicle_id);
        CREATE INDEX IF NOT EXISTS idx_jobs_customer ON job_cards(customer_id);
        CREATE INDEX IF NOT EXISTS idx_jobs_vehicle ON job_cards(vehicle_id);
        CREATE INDEX IF NOT EXISTS idx_jobs_status ON job_cards(status);
        CREATE INDEX IF NOT EXISTS idx_job_items_job ON job_items(job_card_id);
        CREATE INDEX IF NOT EXISTS idx_estimates_customer ON estimates(customer_id);
        CREATE INDEX IF NOT EXISTS idx_estimates_status ON estimates(status);
        CREATE INDEX IF NOT EXISTS idx_estimate_items_estimate ON estimate_items(estimate_id);
        CREATE INDEX IF NOT EXISTS idx_invoices_status ON invoices(payment_status);
        CREATE INDEX IF NOT EXISTS idx_payments_invoice ON payments(invoice_id);
        CREATE INDEX IF NOT EXISTS idx_payments_date ON payments(payment_date);
        """
    )

    # Master data only. No customers, vehicles, bookings, jobs, estimates,
    # invoices or payments are imported or created here.
    services = [
        ("Mechanical Work", "Mechanical inspection and repair", 0, 0, "Mechanical"),
        ("Denting & Painting", "Body repair, dent removal and painting", 0, 0, "Body Work"),
        ("Washing & Detailing", "Exterior wash and detailing", 0, 0, "Detailing"),
        ("Electrical & Battery", "Electrical diagnostics and battery service", 0, 0, "Electrical"),
        ("AC Service", "Air-conditioning inspection and service", 0, 0, "AC"),
        ("Tyres & Alignment", "Tyre, balancing and wheel alignment service", 0, 0, "Tyres"),
        ("Basic Service", "Routine periodic maintenance service", 0, 0, "Service"),
        ("Premium Service", "Comprehensive periodic maintenance service", 0, 0, "Service"),
        ("Car Spa", "Interior and exterior premium detailing", 0, 0, "Detailing"),
    ]
    for row in services:
        db.execute(
            """INSERT OR IGNORE INTO services
               (name, description, base_price, estimated_hours, category, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (*row, now())
        )

    # Create the initial staff account from environment settings only when the
    # fresh database has no users. Passwords are stored as secure hashes.
    if db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        username = (current_app.config.get("ADMIN_USER") or "").strip()
        password = current_app.config.get("ADMIN_PASSWORD") or ""
        if current_app.config.get("ENVIRONMENT") == "production" and current_app.config.get("ADMIN_PASSWORD_IS_GENERATED"):
            raise RuntimeError("Set AUTOCARE_ADMIN_PASSWORD before first production startup.")
        if not username or not password:
            raise RuntimeError("AUTOCARE_ADMIN_USER and AUTOCARE_ADMIN_PASSWORD must be set for first startup.")
        timestamp = now()
        db.execute(
            """INSERT INTO users(name,username,email,password_hash,role,is_active,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?)""",
            ("Garage Administrator", username, None, generate_password_hash(password),
             "admin", 1, timestamp, timestamp),
        )

    # Add home-visit payment fields to existing databases without deleting records.
    booking_columns = {row["name"] for row in db.execute("PRAGMA table_info(bookings)").fetchall()}
    additions = [
        ("home_visit_charge", "REAL NOT NULL DEFAULT 0 CHECK (home_visit_charge >= 0)"),
        ("visit_payment_status", "TEXT NOT NULL DEFAULT 'not_required'"),
        ("razorpay_order_id", "TEXT"),
        ("visit_payment_token", "TEXT"),
        ("razorpay_payment_id", "TEXT"),
        ("visit_paid_at", "TEXT"),
        ("dispatched_at", "TEXT"),
        ("technician_id", "INTEGER"),
    ]
    for column, declaration in additions:
        if column not in booking_columns:
            db.execute(f"ALTER TABLE bookings ADD COLUMN {column} {declaration}")
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_bookings_razorpay_order ON bookings(razorpay_order_id) WHERE razorpay_order_id IS NOT NULL")
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_bookings_razorpay_payment ON bookings(razorpay_payment_id) WHERE razorpay_payment_id IS NOT NULL")
    db.commit()
