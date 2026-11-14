"""Database management and helper functions for Vehicle Management System.

Handles MySQL connection pooling, parameterized execution, transaction safety,
schema initialization, and CRUD operations for users, vehicles, customers, sales, and services.
"""

import os
import re
import tempfile
import urllib.parse
from datetime import datetime
from decimal import Decimal
import bcrypt
import mysql.connector
from mysql.connector import Error, errorcode
import pandas as pd
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Global CA certificate file reference to keep temporary file alive
_CA_TEMP_FILE = None


def _clean_secret_string(val):
    """Clean whitespace and accidental enclosing quotes from configuration values."""
    if val is None:
        return ""
    s = str(val).strip()
    if (len(s) >= 2) and ((s[0] == '"' and s[-1] == '"') or (s[0] == "'" and s[-1] == "'")):
        s = s[1:-1].strip()
    return s


def _get_ca_file_path(ssl_ca_val):
    """Resolve SSL CA certificate from either a file path or direct PEM string."""
    global _CA_TEMP_FILE
    if not ssl_ca_val:
        return None
    ssl_ca_str = str(ssl_ca_val).strip()
    # 1. Existing file path
    if os.path.isfile(ssl_ca_str):
        return ssl_ca_str
    # 2. Raw PEM certificate content (e.g. pasted into Streamlit Secrets)
    if "-----BEGIN CERTIFICATE" in ssl_ca_str:
        try:
            if _CA_TEMP_FILE is None or not os.path.exists(_CA_TEMP_FILE.name):
                _CA_TEMP_FILE = tempfile.NamedTemporaryFile(mode="w", suffix="_aiven_ca.pem", delete=False)
                _CA_TEMP_FILE.write(ssl_ca_str)
                _CA_TEMP_FILE.flush()
            return _CA_TEMP_FILE.name
        except Exception:
            return None
    return None


def get_db_setting(key, default=""):
    """Retrieve setting from st.secrets first, then fall back to .env / os.environ.
    
    Supports:
    1. Full Service URI / Connection String (e.g. Aiven Service URI)
    2. Direct flat st.secrets keys (e.g. st.secrets["DB_HOST"])
    3. Nested sections (e.g. st.secrets["connections"]["mysql"], st.secrets["mysql"], st.secrets["aiven"])
    4. Common alias mappings (e.g. HOST, PORT, USER, USERNAME, PASSWORD, DATABASE)
    """
    key_upper = key.upper()

    # 1. Check if a complete Service URI is provided in Streamlit Secrets or Environment
    service_uri = None
    try:
        import streamlit as st
        if hasattr(st, "secrets") and st.secrets is not None:
            for uri_key in ("SERVICE_URI", "DATABASE_URL", "MYSQL_URL", "DB_URI", "DB_URL", "AIVEN_URL"):
                if uri_key in st.secrets and st.secrets[uri_key]:
                    service_uri = _clean_secret_string(st.secrets[uri_key])
                    break
    except Exception:
        pass

    if not service_uri:
        for uri_key in ("SERVICE_URI", "DATABASE_URL", "MYSQL_URL", "DB_URI", "DB_URL", "AIVEN_URL"):
            env_uri = os.getenv(uri_key)
            if env_uri and env_uri.strip():
                service_uri = _clean_secret_string(env_uri)
                break

    if service_uri and "://" in service_uri:
        try:
            parsed = urllib.parse.urlparse(service_uri)
            if key_upper == "DB_HOST":
                return parsed.hostname or default
            elif key_upper == "DB_PORT":
                return parsed.port or default
            elif key_upper in ("DB_USER", "DB_USERNAME"):
                return parsed.username or default
            elif key_upper == "DB_PASSWORD":
                return urllib.parse.unquote(parsed.password or "")
            elif key_upper in ("DB_NAME", "DB_DATABASE"):
                db_from_uri = parsed.path.lstrip("/")
                return db_from_uri if db_from_uri else default
            elif key_upper == "DB_SSL":
                qs = urllib.parse.parse_qs(parsed.query)
                ssl_mode = qs.get("ssl-mode", qs.get("sslmode", [""]))[0].upper()
                return "true" if ssl_mode in ("REQUIRED", "VERIFY-CA", "VERIFY-FULL", "TRUE") else default
        except Exception:
            pass

    # 2. Check individual keys in Streamlit Secrets
    try:
        import streamlit as st
        if hasattr(st, "secrets") and st.secrets is not None:
            # Direct flat key
            if key in st.secrets:
                return _clean_secret_string(st.secrets[key])

            # Case-insensitive direct key
            for sec_k, sec_v in st.secrets.items():
                if sec_k.lower() == key.lower():
                    return _clean_secret_string(sec_v)

            # Check nested sections: [connections.mysql], [mysql], [aiven]
            alias_map = {
                "DB_HOST": ["host", "hostname", "server"],
                "DB_PORT": ["port"],
                "DB_USER": ["user", "username"],
                "DB_PASSWORD": ["password", "pass"],
                "DB_NAME": ["database", "dbname", "db"],
                "DB_SSL": ["ssl", "ssl_mode", "sslmode", "require_ssl"],
                "DB_SSL_CA": ["ssl_ca", "ca_cert", "ca"],
            }
            candidate_keys = [key, key.lower()] + alias_map.get(key_upper, [])

            for section_name in ("mysql", "aiven"):
                if "connections" in st.secrets and section_name in st.secrets["connections"]:
                    sub_sec = st.secrets["connections"][section_name]
                    for ck in candidate_keys:
                        if ck in sub_sec:
                            return _clean_secret_string(sub_sec[ck])
                if section_name in st.secrets:
                    sub_sec = st.secrets[section_name]
                    for ck in candidate_keys:
                        if ck in sub_sec:
                            return _clean_secret_string(sub_sec[ck])
    except Exception:
        pass

    # 3. Fall back to environment variable or .env
    val = os.getenv(key)
    if val is not None and str(val).strip() != "":
        return _clean_secret_string(val)

    # Check common env aliases
    env_aliases = {
        "DB_HOST": ["MYSQL_HOST", "HOST"],
        "DB_PORT": ["MYSQL_PORT", "PORT"],
        "DB_USER": ["MYSQL_USER", "USER"],
        "DB_PASSWORD": ["MYSQL_PASSWORD", "PASSWORD"],
        "DB_NAME": ["MYSQL_DATABASE", "DATABASE"],
        "DB_SSL": ["MYSQL_SSL", "SSL"],
        "DB_SSL_CA": ["MYSQL_SSL_CA", "SSL_CA"],
    }
    for alias in env_aliases.get(key_upper, []):
        alias_val = os.getenv(alias)
        if alias_val is not None and str(alias_val).strip() != "":
            return _clean_secret_string(alias_val)

    return default


def get_db_config(include_db=True, db_override=None):
    """Retrieve MySQL database configuration from st.secrets first, then .env.

    Converts DB_PORT to integer, sanitizes strings, and automatically configures
    SSL/TLS required for cloud databases such as Aiven MySQL.
    """
    raw_port = get_db_setting("DB_PORT", 3306)
    try:
        port = int(str(raw_port).strip())
    except (ValueError, TypeError):
        port = 3306

    host = str(get_db_setting("DB_HOST", "127.0.0.1")).strip()
    user = str(get_db_setting("DB_USER", "root")).strip()
    password = str(get_db_setting("DB_PASSWORD", ""))

    # On Aiven MySQL, default database is 'defaultdb'
    default_db = "defaultdb" if ("aivencloud" in host.lower() or user == "avnadmin") else "vehicle_mgmt"
    db_name = str(db_override or get_db_setting("DB_NAME", default_db)).strip()

    config = {
        "host": host,
        "port": port,
        "user": user,
        "password": password,
        "charset": "utf8mb4",
    }
    if include_db and db_name:
        config["database"] = db_name

    # SSL / TLS Configuration
    # Aiven MySQL requires SSL. Auto-enable SSL if connecting to Aiven or if requested.
    is_aiven = "aivencloud.com" in host.lower() or "aiven.io" in host.lower() or user == "avnadmin"
    db_ssl = get_db_setting("DB_SSL", "")
    ssl_requested = str(db_ssl).lower() in ("true", "1", "yes", "require", "required") or is_aiven

    ssl_disabled_setting = get_db_setting("DB_SSL_DISABLED", get_db_setting("ssl_disabled", None))
    if ssl_disabled_setting is not None:
        if isinstance(ssl_disabled_setting, bool):
            config["ssl_disabled"] = ssl_disabled_setting
        elif str(ssl_disabled_setting).lower() in ("true", "1", "yes"):
            config["ssl_disabled"] = True
        elif str(ssl_disabled_setting).lower() in ("false", "0", "no"):
            config["ssl_disabled"] = False
    elif ssl_requested:
        config["ssl_disabled"] = False

    # CA Certificate Handling
    raw_ca = get_db_setting("DB_SSL_CA", get_db_setting("ssl_ca", ""))
    ca_file_path = _get_ca_file_path(raw_ca)

    if ca_file_path and os.path.exists(ca_file_path):
        config["ssl_ca"] = ca_file_path
        config["ssl_verify_cert"] = True
    elif ssl_requested and not config.get("ssl_disabled", False):
        # When connecting to Aiven without a local CA file, enable TLS encryption
        # while disabling strict local CA verification so the connection succeeds out of the box
        config["ssl_verify_cert"] = False
        config["ssl_verify_identity"] = False

    ssl_verify_cert_setting = get_db_setting("DB_SSL_VERIFY_CERT", get_db_setting("ssl_verify_cert", None))
    if ssl_verify_cert_setting is not None:
        if isinstance(ssl_verify_cert_setting, bool):
            config["ssl_verify_cert"] = ssl_verify_cert_setting
        elif str(ssl_verify_cert_setting).lower() in ("false", "0", "no"):
            config["ssl_verify_cert"] = False
        elif str(ssl_verify_cert_setting).lower() in ("true", "1", "yes"):
            config["ssl_verify_cert"] = True

    return config


def get_connection(include_db=True, retry_defaultdb=True):
    """Establish and return a MySQL database connection.

    Includes intelligent fallback for cloud databases like Aiven: if connecting to a custom
    database fails because it has not been created yet, it connects to 'defaultdb' and creates
    the database automatically.

    Args:
        include_db: If True, connects directly to DB_NAME; if False, connects to host server.
        retry_defaultdb: Whether to retry with 'defaultdb' if the initial database is not found.

    Returns:
        mysql.connector.connection_cext.CMySQLConnection
    """
    config = get_db_config(include_db=include_db)
    target_db = config.get("database")

    try:
        return mysql.connector.connect(**config)
    except Error as err:
        # Check if the failure is because the database does not exist yet (Error 1049 or Error 1045)
        # On Aiven MySQL, 'defaultdb' is the pre-created database.
        if include_db and retry_defaultdb and target_db and target_db.lower() != "defaultdb":
            try:
                # Attempt connecting to 'defaultdb'
                fallback_config = get_db_config(include_db=True, db_override="defaultdb")
                conn_fallback = mysql.connector.connect(**fallback_config)
                # Connected to defaultdb! Try to create target_db and switch to it
                cursor = conn_fallback.cursor()
                try:
                    cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{target_db}` DEFAULT CHARACTER SET utf8mb4")
                    cursor.execute(f"USE `{target_db}`")
                    cursor.close()
                    return conn_fallback
                except Exception:
                    cursor.close()
                    # If target_db cannot be created, return connection on defaultdb
                    return conn_fallback
            except Exception:
                pass

        # If include_db=True fails and target_db is not created, try connecting without database
        if include_db and retry_defaultdb and target_db:
            try:
                server_config = get_db_config(include_db=False)
                conn_server = mysql.connector.connect(**server_config)
                cursor = conn_server.cursor()
                try:
                    cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{target_db}` DEFAULT CHARACTER SET utf8mb4")
                    cursor.execute(f"USE `{target_db}`")
                    cursor.close()
                    return conn_server
                except Exception:
                    cursor.close()
            except Exception:
                pass

        raise err


# ==============================================================================
# CORE TABLE SCHEMAS (DDL)
# ==============================================================================

CORE_TABLES_DDL = {
    "users": """
        CREATE TABLE IF NOT EXISTS users (
            user_id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(50) NOT NULL UNIQUE,
            password_hash VARCHAR(255) NOT NULL,
            role ENUM('admin', 'staff') NOT NULL DEFAULT 'staff',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    "customers": """
        CREATE TABLE IF NOT EXISTS customers (
            customer_id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            phone VARCHAR(15) NOT NULL UNIQUE,
            email VARCHAR(100) NULL,
            address TEXT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    "vehicles": """
        CREATE TABLE IF NOT EXISTS vehicles (
            vehicle_id INT AUTO_INCREMENT PRIMARY KEY,
            vin VARCHAR(50) NOT NULL UNIQUE,
            brand VARCHAR(50) NOT NULL,
            model VARCHAR(50) NOT NULL,
            year_made INT NOT NULL,
            vehicle_type ENUM('Car', 'Bike', 'Truck', 'Bus', 'SUV') NOT NULL,
            engine_type ENUM('Petrol', 'Diesel', 'CNG', 'Electric', 'Hybrid') NOT NULL,
            colour VARCHAR(30) NOT NULL,
            price DECIMAL(12, 2) NOT NULL CHECK (price > 0),
            quantity INT NOT NULL CHECK (quantity >= 0),
            status ENUM('Available', 'Sold Out', 'Under Service') NOT NULL DEFAULT 'Available',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    "sales": """
        CREATE TABLE IF NOT EXISTS sales (
            sale_id INT AUTO_INCREMENT PRIMARY KEY,
            customer_id INT NOT NULL,
            vehicle_id INT NOT NULL,
            sale_date DATE NOT NULL,
            quantity INT NOT NULL CHECK (quantity > 0),
            total_price DECIMAL(12, 2) NOT NULL,
            payment_mode ENUM('Cash', 'UPI', 'Card', 'Loan') NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_sales_customer FOREIGN KEY (customer_id) REFERENCES customers(customer_id) ON DELETE RESTRICT,
            CONSTRAINT fk_sales_vehicle FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id) ON DELETE RESTRICT
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    "services": """
        CREATE TABLE IF NOT EXISTS services (
            service_id INT AUTO_INCREMENT PRIMARY KEY,
            vehicle_id INT NOT NULL,
            customer_id INT NOT NULL,
            service_date DATE NOT NULL,
            description TEXT NOT NULL,
            cost DECIMAL(10, 2) NOT NULL DEFAULT 0.00,
            status ENUM('Pending', 'In Progress', 'Completed') NOT NULL DEFAULT 'Pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_services_vehicle FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id) ON DELETE RESTRICT,
            CONSTRAINT fk_services_customer FOREIGN KEY (customer_id) REFERENCES customers(customer_id) ON DELETE RESTRICT
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
}


def ensure_users_table(conn=None):
    """Ensure the users table exists and default admin/staff accounts are created.

    Safe and idempotent:
    - Creates users table IF NOT EXISTS.
    - Preserves all existing user records.
    - Creates default admin (admin / admin123) if not found.
    - Creates default staff (staff / staff123) if not found.
    - Uses bcrypt with cryptographic salt.
    """
    should_close = False
    if conn is None:
        conn = get_connection(include_db=True, retry_defaultdb=True)
        should_close = True

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(CORE_TABLES_DDL["users"])
        conn.commit()

        # Check if default admin exists; create only if missing
        cursor.execute("SELECT user_id, password_hash FROM users WHERE username = %s", ("admin",))
        if not cursor.fetchone():
            admin_hash = bcrypt.hashpw(b"admin123", bcrypt.gensalt()).decode("utf-8")
            cursor.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s)",
                ("admin", admin_hash, "admin"),
            )
            conn.commit()

        # Check if default staff exists; create only if missing
        cursor.execute("SELECT user_id, password_hash FROM users WHERE username = %s", ("staff",))
        if not cursor.fetchone():
            staff_hash = bcrypt.hashpw(b"staff123", bcrypt.gensalt()).decode("utf-8")
            cursor.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s)",
                ("staff", staff_hash, "staff"),
            )
            conn.commit()

        cursor.close()
        return True, "Users table verified and default accounts ready."
    except Exception as e:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        return False, f"Failed to ensure users table: {e}"
    finally:
        if should_close and conn:
            try:
                conn.close()
            except Exception:
                pass


def ensure_all_tables(conn=None):
    """Ensure all core tables exist and initial demo data is seeded if tables are empty.

    Safe and idempotent:
    - Uses CREATE TABLE IF NOT EXISTS.
    - Preserves existing records in all tables.
    - Seeds default admin, staff, sample vehicles, and customer without duplicates.
    """
    should_close = False
    if conn is None:
        conn = get_connection(include_db=True, retry_defaultdb=True)
        should_close = True

    try:
        cursor = conn.cursor(dictionary=True)

        # 1. Create tables in dependency order
        for tbl in ("users", "customers", "vehicles", "sales", "services"):
            cursor.execute(CORE_TABLES_DDL[tbl])
        conn.commit()

        # 2. Ensure default users
        ensure_users_table(conn=conn)

        # 3. Seed sample vehicles only if vehicles table is empty
        cursor.execute("SELECT COUNT(*) AS cnt FROM vehicles")
        v_cnt = cursor.fetchone().get("cnt", 0)
        if v_cnt == 0:
            sample_vehicles = [
                ('1HGCR2F83HA001234', 'Honda', 'Civic Sedan', 2024, 'Car', 'Petrol', 'Crystal Black', 28500.00, 5, 'Available'),
                ('5NMS3CAD1LH556789', 'Hyundai', 'Tucson AWD', 2023, 'SUV', 'Hybrid', 'Polar White', 34000.00, 2, 'Available'),
                ('1FTFW1ED4NFC99881', 'Tata', 'Nexon EV Max', 2024, 'SUV', 'Electric', 'Teal Blue', 22000.00, 4, 'Available'),
            ]
            for v in sample_vehicles:
                cursor.execute(
                    """INSERT INTO vehicles (vin, brand, model, year_made, vehicle_type, engine_type, colour, price, quantity, status)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                       ON DUPLICATE KEY UPDATE quantity = VALUES(quantity)""",
                    v
                )
            conn.commit()

        # 4. Seed sample customer only if customers table is empty
        cursor.execute("SELECT COUNT(*) AS cnt FROM customers")
        c_cnt = cursor.fetchone().get("cnt", 0)
        if c_cnt == 0:
            cursor.execute(
                """INSERT INTO customers (name, phone, email, address)
                   VALUES (%s, %s, %s, %s)
                   ON DUPLICATE KEY UPDATE name = VALUES(name)""",
                ('Rahul Sharma', '9876543210', 'rahul.sharma@example.com', '124 MG Road, Indiranagar, Bengaluru, Karnataka')
            )
            conn.commit()

        cursor.close()
        return True, "All database tables and seed records verified successfully."
    except Exception as e:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        return False, f"Database table initialization failed: {e}"
    finally:
        if should_close and conn:
            try:
                conn.close()
            except Exception:
                pass


def test_db_connection():
    """Test database connectivity with friendly, specific error diagnostics.

    Also auto-initializes tables and default accounts if connected to a blank database.

    Returns:
        tuple (bool, str): Status and informational message.
    """
    config = get_db_config(include_db=True)
    db_name = config.get("database", "vehicle_mgmt")
    host = config.get("host", "127.0.0.1")
    port = config.get("port", 3306)
    user = config.get("user", "root")
    is_aiven = "aivencloud" in host.lower() or user == "avnadmin"

    try:
        conn = get_connection(include_db=True)
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()

        # Auto-verify / auto-heal schema: if users table does not exist, initialize all tables!
        cursor.execute("SHOW TABLES LIKE 'users'")
        has_users = cursor.fetchone()
        cursor.close()
        conn.close()

        if not has_users:
            init_ok, init_msg = ensure_all_tables()
            if not init_ok:
                return False, f"Connected to MySQL server, but failed to initialize schema: {init_msg}"
            return True, "Connected and initialized database schema successfully."

        return True, "Connected successfully to database."
    except Error as e:
        err_no = getattr(e, "errno", None)
        err_msg = str(e)

        # 1. Error 1045: Access Denied (Authentication Failure)
        if err_no == 1045 or "1045" in err_msg:
            if is_aiven or user == "avnadmin":
                return False, (
                    f"❌ **Aiven MySQL Authentication Failed (Error 1045: Access Denied for user '{user}').**\n\n"
                    f"**Connection Target:** Host `{host}` on Port `{port}` (Database: `{db_name}`).\n\n"
                    "**How to fix this in Aiven & Streamlit Cloud:**\n"
                    "1. **Password Mismatch (Most Common):** Log in to your [Aiven Console](https://console.aiven.io/) ➔ select your MySQL service ➔ **Overview** tab. Click the copy icon next to **Password**.\n"
                    "2. **Streamlit Secrets Formatting:** In Streamlit Cloud (App Settings ➔ Secrets), ensure the password is wrapped in **single quotes** so characters like `#` are not treated as comments:\n"
                    "   ```toml\n"
                    "   DB_PASSWORD = 'your_exact_aiven_password'\n"
                    "   ```\n"
                    "3. **Reset Password:** If unsure of your current password, click **Reset password** in your Aiven MySQL console, copy the new password, and update it in Streamlit Secrets.\n"
                    "4. **Port Check:** Aiven does NOT use port 3306! Ensure `DB_PORT` matches your Aiven service port (e.g. `21435`).\n"
                    "5. **Database Name:** Aiven's default database is `defaultdb`. Ensure `DB_NAME = 'defaultdb'` (or the database you created in Aiven).\n"
                    "6. **Service URI Alternative:** Alternatively, copy the full **Service URI** from Aiven and paste it into Secrets as:\n"
                    "   ```toml\n"
                    "   SERVICE_URI = 'mysql://avnadmin:password@host:port/defaultdb?ssl-mode=REQUIRED'\n"
                    "   ```"
                )
            else:
                return False, (
                    f"❌ **MySQL Authentication Failed (Error 1045: Access Denied for user '{user}').**\n\n"
                    f"Target server `{host}:{port}` rejected the credentials for user `{user}`. "
                    "Please verify your `DB_USER` and `DB_PASSWORD` in Streamlit Secrets or `.env`."
                )

        # 2. Error 2003 / 2005: Can't connect to server / Unknown Host
        if err_no in (2003, 2005) or "2003" in err_msg or "2005" in err_msg:
            if "your-" in host.lower() or "example" in host.lower():
                return False, (
                    f"❌ **Placeholder Host Detected:** `{host}:{port}`.\n\n"
                    "You still have the example placeholder text in your Streamlit Secrets. "
                    "Please replace `your-aiven-host` with your **actual Aiven host** (e.g., `mysql-xxxx.a.aivencloud.com`) "
                    "or copy the full **Service URI** from your Aiven Console overview."
                )
            return False, (
                f"❌ **Cannot reach MySQL server at `{host}:{port}` (Error: {err_msg}).**\n\n"
                "**Troubleshooting steps:**\n"
                "1. Verify that your Aiven MySQL service status is **Running** (not rebuilding or powered off).\n"
                "2. Verify the hostname and port match your Aiven service overview.\n"
                "3. Ensure public access is enabled on your Aiven service (enabled by default)."
            )

        # 3. SSL / TLS Handshake Errors (2026, 2055)
        if "ssl" in err_msg.lower() or err_no in (2026, 2055):
            return False, (
                f"❌ **SSL/TLS Handshake Error connecting to `{host}:{port}`:** {err_msg}.\n\n"
                "Aiven MySQL requires an encrypted SSL connection. AutoCore has enabled SSL negotiation. "
                "If your cloud environment requires the CA certificate, download `ca.pem` from the Aiven console "
                "and paste its text into Streamlit Secrets as `DB_SSL_CA = '''-----BEGIN CERTIFICATE...'''`."
            )

        # 4. Error 1049: Unknown Database
        if err_no == 1049 or "1049" in err_msg:
            return False, (
                f"⚠️ **Database '{db_name}' not found on server `{host}:{port}`.**\n\n"
                "On Aiven, the default database is `defaultdb`. Click 'Initialize / Restore Database' below "
                "or set `DB_NAME = 'defaultdb'` in Streamlit Secrets."
            )

        # General error fallback
        return False, (
            f"Cannot connect to MySQL server at {host}:{port} as user '{user}'. Error: {err_msg}. "
            "Please verify your credentials in Streamlit Cloud Secrets or local .env."
        )


def init_db(schema_path=None):
    """Initialize database tables and default admin account if missing.

    Safe for existing databases: creates tables if they do not exist and guarantees
    that default admin (admin / admin123, bcrypt) is present without overwriting
    existing user data or crashing if the database already exists.
    """
    # 1. First ensure all core tables and default admin/staff are created via Python DDL
    ok, msg = ensure_all_tables()
    if not ok:
        return False, msg

    # 2. If an external schema.sql file exists, run it for any extra schema elements
    if schema_path is None:
        schema_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.sql")

    if os.path.exists(schema_path):
        conn = None
        try:
            conn = get_connection(include_db=True, retry_defaultdb=True)
            cursor = conn.cursor()
            with open(schema_path, "r", encoding="utf-8") as f:
                sql_content = f.read()

            statements = [stmt.strip() for stmt in sql_content.split(";") if stmt.strip()]
            for stmt in statements:
                upper_stmt = stmt.upper().replace("\n", " ").strip()
                if upper_stmt.startswith("CREATE DATABASE") or upper_stmt.startswith("USE "):
                    continue
                try:
                    cursor.execute(stmt)
                except Error as err:
                    if err.errno not in (errorcode.ER_TABLE_EXISTS_ERROR, errorcode.ER_DUP_ENTRY):
                        pass  # Non-fatal if tables already exist
            conn.commit()
            cursor.close()
            conn.close()
        except Exception:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    return True, "Database initialized successfully with required tables and default accounts."


# Backwards-compatibility alias
init_database = init_db


def execute_query(query, params=None, fetch=None, dictionary=True):
    """Execute a parameterized query safely with automatic commit or fetch.

    Args:
        query: SQL string with %s placeholders.
        params: Tuple or list of parameters.
        fetch: None (for DML), 'all' (for select all), or 'one' (for single record).
        dictionary: Whether to return rows as dictionaries.

    Returns:
        list of dicts, single dict, or lastrowid / affected rows.
    """
    conn = None
    cursor = None
    try:
        conn = get_connection(include_db=True)
        cursor = conn.cursor(dictionary=dictionary)
        cursor.execute(query, params or ())

        if fetch == "all":
            result = cursor.fetchall()
            return result
        elif fetch == "one":
            result = cursor.fetchone()
            return result
        else:
            conn.commit()
            return cursor.lastrowid if cursor.lastrowid else cursor.rowcount
    except Error as e:
        if conn:
            conn.rollback()
        raise e
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# ==============================================================================
# AUTHENTICATION & USERS
# ==============================================================================

def authenticate_user(username, password):
    """Verify user credentials with bcrypt.

    Auto-heals missing users table if connected to a fresh database without crashing.

    Args:
        username: Username string.
        password: Plaintext password.

    Returns:
        dict: User data if authentication succeeds, else None.
    """
    query = "SELECT user_id, username, password_hash, role FROM users WHERE username = %s"
    try:
        user = execute_query(query, (username.strip(),), fetch="one")
    except Error as e:
        err_no = getattr(e, "errno", None)
        err_msg = str(e)
        if err_no == 1146 or "1146" in err_msg or "doesn't exist" in err_msg.lower():
            # Auto-heal: users table missing -> create users table and default admin/staff!
            ensure_users_table()
            user = execute_query(query, (username.strip(),), fetch="one")
        else:
            raise e

    if not user:
        return None

    stored_hash = user["password_hash"]
    if isinstance(stored_hash, str):
        stored_hash = stored_hash.encode("utf-8")

    try:
        if bcrypt.checkpw(password.encode("utf-8"), stored_hash):
            return {
                "user_id": user["user_id"],
                "username": user["username"],
                "role": user["role"],
            }
    except Exception:
        return None
    return None


def create_user(username, password, role="staff"):
    """Create a new user with bcrypt-hashed password.

    Args:
        username: Unique username.
        password: Plaintext password.
        role: 'admin' or 'staff'.

    Returns:
        int: New user_id.
    """
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    query = "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s)"
    try:
        return execute_query(query, (username.strip(), hashed, role))
    except Error as e:
        err_no = getattr(e, "errno", None)
        err_msg = str(e)
        if err_no == 1146 or "1146" in err_msg or "doesn't exist" in err_msg.lower():
            ensure_users_table()
            return execute_query(query, (username.strip(), hashed, role))
        raise e


# ==============================================================================
# VEHICLES MANAGEMENT
# ==============================================================================

def get_vehicles(search="", brand="All", engine_type="All", vehicle_type="All", status="All", min_price=0, max_price=None):
    """Retrieve vehicles with dynamic filtering and search."""
    conditions = []
    params = []

    if search:
        search_pattern = f"%{search.strip()}%"
        conditions.append("(vin LIKE %s OR brand LIKE %s OR model LIKE %s)")
        params.extend([search_pattern, search_pattern, search_pattern])

    if brand and brand != "All":
        conditions.append("brand = %s")
        params.append(brand)

    if engine_type and engine_type != "All":
        conditions.append("engine_type = %s")
        params.append(engine_type)

    if vehicle_type and vehicle_type != "All":
        conditions.append("vehicle_type = %s")
        params.append(vehicle_type)

    if status and status != "All":
        conditions.append("status = %s")
        params.append(status)

    if min_price > 0:
        conditions.append("price >= %s")
        params.append(min_price)

    if max_price is not None and max_price > 0:
        conditions.append("price <= %s")
        params.append(max_price)

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    query = f"""
        SELECT vehicle_id, vin, brand, model, year_made, vehicle_type, 
               engine_type, colour, price, quantity, status, created_at
        FROM vehicles
        {where_clause}
        ORDER BY vehicle_id DESC
    """
    return execute_query(query, params, fetch="all")


def get_vehicle_by_id(vehicle_id):
    """Fetch single vehicle by ID."""
    query = "SELECT * FROM vehicles WHERE vehicle_id = %s"
    return execute_query(query, (vehicle_id,), fetch="one")


def get_vehicle_by_vin(vin):
    """Fetch single vehicle by VIN."""
    query = "SELECT * FROM vehicles WHERE UPPER(vin) = UPPER(%s)"
    return execute_query(query, (vin.strip(),), fetch="one")


def add_vehicle(vin, brand, model, year_made, vehicle_type, engine_type, colour, price, quantity, status="Available"):
    """Insert a new vehicle with duplicate VIN check.

    Returns:
        int: vehicle_id of inserted vehicle.
    """
    vin_clean = vin.strip().upper()
    existing = get_vehicle_by_vin(vin_clean)
    if existing:
        raise ValueError(f"Vehicle with VIN '{vin_clean}' already exists in inventory.")

    if price <= 0:
        raise ValueError("Vehicle price must be greater than zero.")
    if quantity < 0:
        raise ValueError("Vehicle quantity cannot be negative.")

    # Auto-adjust status if quantity is 0
    if quantity == 0 and status == "Available":
        status = "Sold Out"

    query = """
        INSERT INTO vehicles (vin, brand, model, year_made, vehicle_type, engine_type, colour, price, quantity, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    params = (
        vin_clean,
        brand.strip(),
        model.strip(),
        int(year_made),
        vehicle_type,
        engine_type,
        colour.strip(),
        float(price),
        int(quantity),
        status,
    )
    return execute_query(query, params)


def update_vehicle(vehicle_id, brand, model, year_made, vehicle_type, engine_type, colour, price, quantity, status):
    """Update existing vehicle record."""
    if price <= 0:
        raise ValueError("Price must be greater than zero.")
    if quantity < 0:
        raise ValueError("Quantity cannot be negative.")

    if quantity == 0 and status == "Available":
        status = "Sold Out"
    elif quantity > 0 and status == "Sold Out":
        status = "Available"

    query = """
        UPDATE vehicles
        SET brand = %s, model = %s, year_made = %s, vehicle_type = %s,
            engine_type = %s, colour = %s, price = %s, quantity = %s, status = %s
        WHERE vehicle_id = %s
    """
    params = (
        brand.strip(),
        model.strip(),
        int(year_made),
        vehicle_type,
        engine_type,
        colour.strip(),
        float(price),
        int(quantity),
        status,
        int(vehicle_id),
    )
    return execute_query(query, params)


def delete_vehicle(vehicle_id):
    """Safely delete vehicle with check for related sales/services."""
    # Check references
    sales = execute_query("SELECT COUNT(*) AS cnt FROM sales WHERE vehicle_id = %s", (vehicle_id,), fetch="one")
    if sales and sales["cnt"] > 0:
        raise ValueError(f"Cannot delete vehicle: It has {sales['cnt']} related sales record(s).")

    services = execute_query("SELECT COUNT(*) AS cnt FROM services WHERE vehicle_id = %s", (vehicle_id,), fetch="one")
    if services and services["cnt"] > 0:
        raise ValueError(f"Cannot delete vehicle: It has {services['cnt']} related service log(s).")

    query = "DELETE FROM vehicles WHERE vehicle_id = %s"
    return execute_query(query, (vehicle_id,))


def get_distinct_brands():
    """Retrieve list of distinct brands currently in inventory."""
    rows = execute_query("SELECT DISTINCT brand FROM vehicles ORDER BY brand ASC", fetch="all")
    return [r["brand"] for r in rows if r["brand"]]


# ==============================================================================
# CUSTOMER MANAGEMENT
# ==============================================================================

def validate_phone(phone):
    """Validate 10-digit phone number."""
    cleaned = re.sub(r"\D", "", phone.strip())
    if len(cleaned) != 10:
        return False, "Phone number must be exactly 10 digits."
    return True, cleaned


def get_customers(search=""):
    """Retrieve all customers with optional search by name or phone."""
    if search:
        search_pattern = f"%{search.strip()}%"
        query = """
            SELECT customer_id, name, phone, email, address, created_at
            FROM customers
            WHERE name LIKE %s OR phone LIKE %s
            ORDER BY customer_id DESC
        """
        return execute_query(query, (search_pattern, search_pattern), fetch="all")
    else:
        query = "SELECT * FROM customers ORDER BY customer_id DESC"
        return execute_query(query, fetch="all")


def get_customer_by_id(customer_id):
    """Fetch customer by ID."""
    query = "SELECT * FROM customers WHERE customer_id = %s"
    return execute_query(query, (customer_id,), fetch="one")


def get_customer_by_phone(phone):
    """Fetch customer by phone."""
    is_valid, cleaned_phone = validate_phone(phone)
    if not is_valid:
        return None
    query = "SELECT * FROM customers WHERE phone = %s"
    return execute_query(query, (cleaned_phone,), fetch="one")


def add_customer(name, phone, email=None, address=None):
    """Add a customer with 10-digit phone check and duplicate detection.

    Returns:
        int: customer_id of new customer.
    """
    if not name or not name.strip():
        raise ValueError("Customer name is required.")

    is_valid, cleaned_phone = validate_phone(phone)
    if not is_valid:
        raise ValueError(cleaned_phone)

    # Check duplicate phone
    existing = get_customer_by_phone(cleaned_phone)
    if existing:
        raise ValueError(f"A customer with phone number '{cleaned_phone}' already exists ({existing['name']}).")

    email_val = email.strip() if email and email.strip() else None
    address_val = address.strip() if address and address.strip() else None

    query = """
        INSERT INTO customers (name, phone, email, address)
        VALUES (%s, %s, %s, %s)
    """
    return execute_query(query, (name.strip(), cleaned_phone, email_val, address_val))


def update_customer(customer_id, name, phone, email=None, address=None):
    """Update customer details with duplicate phone validation."""
    if not name or not name.strip():
        raise ValueError("Customer name is required.")

    is_valid, cleaned_phone = validate_phone(phone)
    if not is_valid:
        raise ValueError(cleaned_phone)

    # Check duplicate phone for other customer
    existing = get_customer_by_phone(cleaned_phone)
    if existing and existing["customer_id"] != int(customer_id):
        raise ValueError(f"Phone number '{cleaned_phone}' is already registered to another customer.")

    email_val = email.strip() if email and email.strip() else None
    address_val = address.strip() if address and address.strip() else None

    query = """
        UPDATE customers
        SET name = %s, phone = %s, email = %s, address = %s
        WHERE customer_id = %s
    """
    return execute_query(query, (name.strip(), cleaned_phone, email_val, address_val, int(customer_id)))


def delete_customer(customer_id):
    """Safely delete customer with check for active sales/services."""
    sales = execute_query("SELECT COUNT(*) AS cnt FROM sales WHERE customer_id = %s", (customer_id,), fetch="one")
    if sales and sales["cnt"] > 0:
        raise ValueError(f"Cannot delete customer: {sales['cnt']} sales transaction(s) associated with this customer.")

    services = execute_query("SELECT COUNT(*) AS cnt FROM services WHERE customer_id = %s", (customer_id,), fetch="one")
    if services and services["cnt"] > 0:
        raise ValueError(f"Cannot delete customer: {services['cnt']} service record(s) associated with this customer.")

    query = "DELETE FROM customers WHERE customer_id = %s"
    return execute_query(query, (customer_id,))


# ==============================================================================
# SALES & TRANSACTIONS
# ==============================================================================

def execute_sale_transaction(customer_id, vehicle_id, sale_date, quantity, payment_mode):
    """Record a vehicle sale and decrement inventory in a single atomic transaction.

    Locks vehicle row with FOR UPDATE, verifies stock, inserts sale, updates stock,
    and sets status to 'Sold Out' if quantity reaches zero. Rolls back on any error.

    Returns:
        dict: Result info with sale_id, total_price, and remaining stock.
    """
    if quantity <= 0:
        raise ValueError("Sale quantity must be at least 1.")

    conn = None
    cursor = None
    try:
        conn = get_connection(include_db=True)
        conn.autocommit = False
        cursor = conn.cursor(dictionary=True)

        # 1. Lock and inspect vehicle stock
        cursor.execute(
            "SELECT vehicle_id, brand, model, price, quantity, status FROM vehicles WHERE vehicle_id = %s FOR UPDATE",
            (vehicle_id,)
        )
        vehicle = cursor.fetchone()
        if not vehicle:
            raise ValueError("Vehicle not found.")

        current_qty = vehicle["quantity"]
        unit_price = float(vehicle["price"])

        if current_qty < quantity:
            raise ValueError(
                f"Insufficient stock! Available: {current_qty}, Requested: {quantity} for {vehicle['brand']} {vehicle['model']}."
            )

        total_price = unit_price * quantity
        new_qty = current_qty - quantity
        new_status = "Sold Out" if new_qty == 0 else vehicle["status"]

        # 2. Insert Sale Record
        cursor.execute(
            """
            INSERT INTO sales (customer_id, vehicle_id, sale_date, quantity, total_price, payment_mode)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (customer_id, vehicle_id, sale_date, quantity, total_price, payment_mode)
        )
        sale_id = cursor.lastrowid

        # 3. Decrement Inventory & Update Status
        cursor.execute(
            """
            UPDATE vehicles
            SET quantity = %s, status = %s
            WHERE vehicle_id = %s
            """,
            (new_qty, new_status, vehicle_id)
        )

        # Commit atomic transaction
        conn.commit()

        return {
            "sale_id": sale_id,
            "total_price": total_price,
            "remaining_qty": new_qty,
            "vehicle_name": f"{vehicle['brand']} {vehicle['model']}",
        }
    except Exception as e:
        if conn:
            conn.rollback()
        raise e
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def get_sales(start_date=None, end_date=None, payment_mode="All", search=""):
    """Fetch sales history with joined customer and vehicle details."""
    conditions = []
    params = []

    if start_date:
        conditions.append("s.sale_date >= %s")
        params.append(start_date)

    if end_date:
        conditions.append("s.sale_date <= %s")
        params.append(end_date)

    if payment_mode and payment_mode != "All":
        conditions.append("s.payment_mode = %s")
        params.append(payment_mode)

    if search:
        pattern = f"%{search.strip()}%"
        conditions.append("(c.name LIKE %s OR c.phone LIKE %s OR v.brand LIKE %s OR v.model LIKE %s OR v.vin LIKE %s)")
        params.extend([pattern, pattern, pattern, pattern, pattern])

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    query = f"""
        SELECT s.sale_id, s.sale_date, s.quantity, s.total_price, s.payment_mode, s.created_at,
               c.customer_id, c.name AS customer_name, c.phone AS customer_phone,
               v.vehicle_id, v.brand, v.model, v.vin, v.colour, v.vehicle_type
        FROM sales s
        JOIN customers c ON s.customer_id = c.customer_id
        JOIN vehicles v ON s.vehicle_id = v.vehicle_id
        {where_clause}
        ORDER BY s.sale_date DESC, s.sale_id DESC
    """
    return execute_query(query, params, fetch="all")


# ==============================================================================
# SERVICES MANAGEMENT
# ==============================================================================

def add_service(vehicle_id, customer_id, service_date, description, cost, status="Pending", mark_vehicle_service=False):
    """Log a new vehicle service entry."""
    if not description or not description.strip():
        raise ValueError("Service description is required.")
    if cost < 0:
        raise ValueError("Service cost cannot be negative.")

    conn = None
    cursor = None
    try:
        conn = get_connection(include_db=True)
        conn.autocommit = False
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO services (vehicle_id, customer_id, service_date, description, cost, status)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (vehicle_id, customer_id, service_date, description.strip(), float(cost), status)
        )
        service_id = cursor.lastrowid

        if mark_vehicle_service and status in ("Pending", "In Progress"):
            cursor.execute("UPDATE vehicles SET status = 'Under Service' WHERE vehicle_id = %s", (vehicle_id,))

        conn.commit()
        return service_id
    except Exception as e:
        if conn:
            conn.rollback()
        raise e
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def update_service_status(service_id, new_status, new_cost=None, release_vehicle=False):
    """Update status and optional cost for a service record."""
    conn = None
    cursor = None
    try:
        conn = get_connection(include_db=True)
        conn.autocommit = False
        cursor = conn.cursor(dictionary=True)

        if new_cost is not None and new_cost >= 0:
            cursor.execute(
                "UPDATE services SET status = %s, cost = %s WHERE service_id = %s",
                (new_status, float(new_cost), service_id)
            )
        else:
            cursor.execute("UPDATE services SET status = %s WHERE service_id = %s", (new_status, service_id))

        if release_vehicle and new_status == "Completed":
            # If completed, check vehicle quantity to set Available or Sold Out
            cursor.execute(
                """
                UPDATE vehicles v
                JOIN services s ON v.vehicle_id = s.vehicle_id
                SET v.status = CASE WHEN v.quantity > 0 THEN 'Available' ELSE 'Sold Out' END
                WHERE s.service_id = %s
                """,
                (service_id,)
            )

        conn.commit()
        return True
    except Exception as e:
        if conn:
            conn.rollback()
        raise e
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def get_services(status="All", search=""):
    """Retrieve service records with vehicle and customer details."""
    conditions = []
    params = []

    if status and status != "All":
        conditions.append("s.status = %s")
        params.append(status)

    if search:
        pattern = f"%{search.strip()}%"
        conditions.append("(c.name LIKE %s OR c.phone LIKE %s OR v.brand LIKE %s OR v.model LIKE %s OR v.vin LIKE %s OR s.description LIKE %s)")
        params.extend([pattern, pattern, pattern, pattern, pattern, pattern])

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    query = f"""
        SELECT s.service_id, s.service_date, s.description, s.cost, s.status, s.created_at,
               v.vehicle_id, v.brand, v.model, v.vin, v.colour,
               c.customer_id, c.name AS customer_name, c.phone AS customer_phone
        FROM services s
        JOIN vehicles v ON s.vehicle_id = v.vehicle_id
        JOIN customers c ON s.customer_id = c.customer_id
        {where_clause}
        ORDER BY CASE s.status WHEN 'Pending' THEN 1 WHEN 'In Progress' THEN 2 ELSE 3 END,
                 s.service_date DESC, s.service_id DESC
    """
    return execute_query(query, params, fetch="all")


def get_pending_services():
    """Retrieve services in Pending or In Progress status."""
    query = """
        SELECT s.service_id, s.service_date, s.description, s.cost, s.status,
               v.vehicle_id, v.brand, v.model, v.vin,
               c.customer_id, c.name AS customer_name, c.phone AS customer_phone
        FROM services s
        JOIN vehicles v ON s.vehicle_id = v.vehicle_id
        JOIN customers c ON s.customer_id = c.customer_id
        WHERE s.status IN ('Pending', 'In Progress')
        ORDER BY s.service_date ASC
    """
    return execute_query(query, fetch="all")


# ==============================================================================
# DASHBOARD & REPORTS ANALYTICS
# ==============================================================================

def get_dashboard_kpis():
    """Calculate key performance indicators for the dashboard."""
    # 1. Total Stock (sum of vehicle quantities)
    stock_res = execute_query("SELECT COALESCE(SUM(quantity), 0) AS total_stock FROM vehicles", fetch="one")
    total_stock = stock_res["total_stock"] if stock_res else 0

    # 2. Total Customers
    cust_res = execute_query("SELECT COUNT(*) AS total_customers FROM customers", fetch="one")
    total_customers = cust_res["total_customers"] if cust_res else 0

    # 3. Monthly Sales Count & Monthly Revenue
    now = datetime.now()
    month_sales_res = execute_query(
        """
        SELECT COUNT(*) AS month_sales_count,
               COALESCE(SUM(total_price), 0.0) AS month_revenue
        FROM sales
        WHERE YEAR(sale_date) = %s AND MONTH(sale_date) = %s
        """,
        (now.year, now.month),
        fetch="one"
    )
    month_sales_count = month_sales_res["month_sales_count"] if month_sales_res else 0
    month_revenue = float(month_sales_res["month_revenue"]) if month_sales_res else 0.0

    # 4. All-time Total Revenue
    all_time_rev = execute_query("SELECT COALESCE(SUM(total_price), 0.0) AS total_revenue FROM sales", fetch="one")
    total_revenue = float(all_time_rev["total_revenue"]) if all_time_rev else 0.0

    # 5. Low-stock vehicles count (quantity < 3)
    low_stock_res = execute_query(
        """
        SELECT COUNT(*) AS low_stock_count
        FROM vehicles
        WHERE quantity < 3 AND status != 'Sold Out'
        """,
        fetch="one"
    )
    low_stock_count = low_stock_res["low_stock_count"] if low_stock_res else 0

    # 6. Pending Services
    pend_serv = execute_query("SELECT COUNT(*) AS pending_count FROM services WHERE status = 'Pending'", fetch="one")
    pending_services_count = pend_serv["pending_count"] if pend_serv else 0

    return {
        "total_stock": int(total_stock),
        "total_customers": int(total_customers),
        "month_sales_count": int(month_sales_count),
        "month_revenue": month_revenue,
        "total_revenue": total_revenue,
        "low_stock_count": int(low_stock_count),
        "pending_services_count": int(pending_services_count),
    }


def get_low_stock_vehicles():
    """Retrieve all vehicles with quantity < 3."""
    query = """
        SELECT vehicle_id, vin, brand, model, vehicle_type, quantity, price, status
        FROM vehicles
        WHERE quantity < 3
        ORDER BY quantity ASC, brand ASC
    """
    return execute_query(query, fetch="all")


def get_sales_by_month_data():
    """Get aggregated monthly sales revenue and count for charts."""
    query = """
        SELECT DATE_FORMAT(sale_date, '%Y-%m') AS sale_month,
               COUNT(*) AS sales_count,
               SUM(quantity) AS units_sold,
               SUM(total_price) AS total_revenue
        FROM sales
        GROUP BY DATE_FORMAT(sale_date, '%Y-%m')
        ORDER BY sale_month ASC
    """
    rows = execute_query(query, fetch="all")
    if not rows:
        return pd.DataFrame(columns=["sale_month", "sales_count", "units_sold", "total_revenue"])
    df = pd.DataFrame(rows)
    df["total_revenue"] = df["total_revenue"].astype(float)
    df["units_sold"] = df["units_sold"].astype(int)
    df["sales_count"] = df["sales_count"].astype(int)
    return df


def get_stock_by_brand_data():
    """Get inventory distribution grouped by brand."""
    query = """
        SELECT brand,
               SUM(quantity) AS total_stock,
               COUNT(*) AS model_count
        FROM vehicles
        GROUP BY brand
        ORDER BY total_stock DESC
    """
    rows = execute_query(query, fetch="all")
    if not rows:
        return pd.DataFrame(columns=["brand", "total_stock", "model_count"])
    df = pd.DataFrame(rows)
    df["total_stock"] = df["total_stock"].astype(int)
    return df


def get_stock_by_type_data():
    """Get vehicle count grouped by vehicle_type."""
    query = """
        SELECT vehicle_type,
               SUM(quantity) AS total_stock,
               COUNT(*) AS count
        FROM vehicles
        GROUP BY vehicle_type
        ORDER BY total_stock DESC
    """
    rows = execute_query(query, fetch="all")
    if not rows:
        return pd.DataFrame(columns=["vehicle_type", "total_stock", "count"])
    df = pd.DataFrame(rows)
    df["total_stock"] = df["total_stock"].astype(int)
    return df


def get_reports_summary(start_date, end_date):
    """Aggregate detailed financial and sales figures for reports."""
    query = """
        SELECT COUNT(*) AS total_transactions,
               COALESCE(SUM(quantity), 0) AS total_units_sold,
               COALESCE(SUM(total_price), 0.0) AS total_revenue,
               COALESCE(AVG(total_price), 0.0) AS avg_order_value
        FROM sales
        WHERE sale_date BETWEEN %s AND %s
    """
    sales_kpi = execute_query(query, (start_date, end_date), fetch="one")

    serv_query = """
        SELECT COUNT(*) AS services_count,
               COALESCE(SUM(cost), 0.0) AS service_revenue
        FROM services
        WHERE service_date BETWEEN %s AND %s
    """
    serv_kpi = execute_query(serv_query, (start_date, end_date), fetch="one")

    brand_query = """
        SELECT v.brand,
               COUNT(*) AS sales_count,
               SUM(s.quantity) AS units_sold,
               SUM(s.total_price) AS brand_revenue
        FROM sales s
        JOIN vehicles v ON s.vehicle_id = v.vehicle_id
        WHERE s.sale_date BETWEEN %s AND %s
        GROUP BY v.brand
        ORDER BY brand_revenue DESC
    """
    brand_rows = execute_query(brand_query, (start_date, end_date), fetch="all")
    brand_df = pd.DataFrame(brand_rows) if brand_rows else pd.DataFrame(columns=["brand", "sales_count", "units_sold", "brand_revenue"])
    if not brand_df.empty:
        brand_df["brand_revenue"] = brand_df["brand_revenue"].astype(float)
        brand_df["units_sold"] = brand_df["units_sold"].astype(int)

    return {
        "total_transactions": int(sales_kpi["total_transactions"]) if sales_kpi else 0,
        "total_units_sold": int(sales_kpi["total_units_sold"]) if sales_kpi else 0,
        "total_revenue": float(sales_kpi["total_revenue"]) if sales_kpi else 0.0,
        "avg_order_value": float(sales_kpi["avg_order_value"]) if sales_kpi else 0.0,
        "services_count": int(serv_kpi["services_count"]) if serv_kpi else 0,
        "service_revenue": float(serv_kpi["service_revenue"]) if serv_kpi else 0.0,
        "brand_summary": brand_df,
    }

