# 🚗 AutoCore - Vehicle Management System Website

A complete, enterprise-grade **Vehicle Management System (VMS)** website built in Python using **Streamlit** and a **MySQL** relational database. Features real-time automotive inventory tracking, 10-digit customer verification, atomic checkout transactions, maintenance service queues, interactive Plotly business analytics, and one-click CSV report exports.

---

## 🛠️ Technology Stack

- **Frontend & App Framework:** [Streamlit](https://streamlit.io/) (Pure Python web application)
- **Database Engine:** MySQL Server 8.0+ / MariaDB
- **Database Connector:** `mysql-connector-python`
- **Configuration & Security:** `python-dotenv`, `bcrypt` (salted password hashing)
- **Data & Business Analytics:** `pandas`, `plotly`

---

## 📁 Repository Structure

```text
vehicle-management/
│
├── app.py                     # Main application entrypoint, bcrypt sign-in & module router
├── db.py                      # Database connection pool, parameterized CRUD helpers, transactions
├── ui_common.py               # Shared UI layouts, authentication guard, global sidebar & quick-add dialog
├── schema.sql                 # Complete MySQL schema DDL + initial seed data
├── .env.example               # Example environment variables template
├── .env                       # Active local database connection settings (never hardcoded)
├── requirements.txt           # Python package dependencies
├── test_backend.py            # Automated end-to-end backend test suite
├── README.md                  # Detailed documentation and run instructions
│
└── pages/                     # Streamlit multi-page module structure
    ├── 1_Dashboard.py         # KPI cards, monthly trends, stock distribution, low-stock warnings (< 3)
    ├── 2_Vehicles.py          # Inventory catalog, search & multi-attribute filters, add/edit/delete
    ├── 3_Customers.py         # Customer directory, 10-digit mobile validation, duplicate prevention
    ├── 4_Sales.py             # Atomic sale checkout, stock decrement, auto 'Sold Out', inline customer add
    ├── 5_Service.py           # Maintenance ticket logging, pending service queue, status transitions
    ├── 6_Reports.py           # Custom date range audits, top-selling brands, CSV download exports
    └── 7_All_Data.py          # Unified database explorer, dynamic table discovery, joined records & CSVs
```

---

## 🗄️ Database Schema & Entities

The database name is **`vehicle_mgmt`** (InnoDB engine, `utf8mb4` charset):

1. **`users`**
   - `user_id` (INT, PK, AUTO_INCREMENT)
   - `username` (VARCHAR(50), UNIQUE, NOT NULL)
   - `password_hash` (VARCHAR(255), NOT NULL) - Bcrypt hashed
   - `role` (ENUM('admin', 'staff'), NOT NULL, DEFAULT 'staff')
   - `created_at` (TIMESTAMP, DEFAULT CURRENT_TIMESTAMP)

2. **`vehicles`**
   - `vehicle_id` (INT, PK, AUTO_INCREMENT)
   - `vin` (VARCHAR(50), UNIQUE, NOT NULL) - Vehicle Identification Number
   - `brand` (VARCHAR(50), NOT NULL)
   - `model` (VARCHAR(50), NOT NULL)
   - `year_made` (INT, NOT NULL)
   - `vehicle_type` (ENUM('Car', 'Bike', 'Truck', 'Bus', 'SUV'), NOT NULL)
   - `engine_type` (ENUM('Petrol', 'Diesel', 'CNG', 'Electric', 'Hybrid'), NOT NULL)
   - `colour` (VARCHAR(30), NOT NULL)
   - `price` (DECIMAL(12, 2), NOT NULL, CHECK price > 0)
   - `quantity` (INT, NOT NULL, CHECK quantity >= 0)
   - `status` (ENUM('Available', 'Sold Out', 'Under Service'), NOT NULL, DEFAULT 'Available')
   - `created_at` (TIMESTAMP, DEFAULT CURRENT_TIMESTAMP)

3. **`customers`**
   - `customer_id` (INT, PK, AUTO_INCREMENT)
   - `name` (VARCHAR(100), NOT NULL)
   - `phone` (VARCHAR(15), UNIQUE, NOT NULL) - Exactly 10 digits
   - `email` (VARCHAR(100), NULL)
   - `address` (TEXT, NULL)
   - `created_at` (TIMESTAMP, DEFAULT CURRENT_TIMESTAMP)

4. **`sales`**
   - `sale_id` (INT, PK, AUTO_INCREMENT)
   - `customer_id` (INT, FK -> `customers.customer_id`, ON DELETE RESTRICT)
   - `vehicle_id` (INT, FK -> `vehicles.vehicle_id`, ON DELETE RESTRICT)
   - `sale_date` (DATE, NOT NULL)
   - `quantity` (INT, NOT NULL, CHECK quantity > 0)
   - `total_price` (DECIMAL(12, 2), NOT NULL)
   - `payment_mode` (ENUM('Cash', 'UPI', 'Card', 'Loan'), NOT NULL)
   - `created_at` (TIMESTAMP, DEFAULT CURRENT_TIMESTAMP)

5. **`services`**
   - `service_id` (INT, PK, AUTO_INCREMENT)
   - `vehicle_id` (INT, FK -> `vehicles.vehicle_id`, ON DELETE RESTRICT)
   - `customer_id` (INT, FK -> `customers.customer_id`, ON DELETE RESTRICT)
   - `service_date` (DATE, NOT NULL)
   - `description` (TEXT, NOT NULL)
   - `cost` (DECIMAL(10, 2), NOT NULL, DEFAULT 0.00)
   - `status` (ENUM('Pending', 'In Progress', 'Completed'), NOT NULL, DEFAULT 'Pending')
   - `created_at` (TIMESTAMP, DEFAULT CURRENT_TIMESTAMP)

---

## ⚡ Key Features Walkthrough

### 1. Bcrypt Authentication & Protected Routing
- Users sign in from `app.py` with passwords checked using `bcrypt.checkpw()`.
- Every page in `pages/` executes `ui_common.require_auth()`: unauthenticated requests are stopped immediately with clear warning prompts.
- **Default Credentials:**
  - **Admin:** Username: `admin` | Password: `admin123`
  - **Staff:** Username: `staff` | Password: `staff123`

### 2. Executive Dashboard
- **KPI Metrics Cards:** Total Vehicles in Stock, Registered Customers, Current Month Sales Count, Monthly Revenue, All-Time Revenue.
- **Low-Stock Alert:** Vehicles with `quantity < 3` trigger a prominent warning banner and an expandable detail table with restock indicators.
- **Interactive Visualizations:**
  - Plotly Monthly Revenue Bar Chart
  - Plotly Brand Inventory Distribution Donut Chart

### 3. Inventory Management (Vehicles)
- Full-text search by VIN, Brand, or Model.
- Multi-attribute filters: Brand dropdown, Engine Type, Body Type, Status, and interactive Price Slider.
- Robust validation: Price > 0, Quantity >= 0, valid 4-digit manufacture year, duplicate VIN prevention with case-insensitive checks.
- Edit existing models and safe deletion with checks preventing deletion of vehicles tied to sales or service histories.

### 4. Customer Directory
- Search by customer name or phone number.
- Strict 10-digit mobile number validation (`validate_phone()`).
- Rejection of duplicate phone numbers with explicit feedback.
- Safe deletion with foreign key audit validation.

### 5. ⚡ Add Customer Anytime (3-Way Integration)
1. **Global Sidebar Button:** A persistent `➕ Add Customer` button visible on **EVERY** page opens an `@st.dialog` modal without leaving the current view.
2. **Sales Page Inline Quick-Add:** A `➕ New Customer` toggle directly next to the customer dropdown in `4_Sales.py`. Saving immediately auto-selects the customer for checkout without losing entered data.
3. **Service Page Inline Quick-Add:** The same seamless quick-add flow inside `5_Service.py`.

### 6. Atomic Sales Transactions
- Automatic stock inspection using `SELECT ... FOR UPDATE`.
- Atomicity: The sale record insertion and the vehicle quantity reduction happen in **ONE** database transaction (`START TRANSACTION` -> `COMMIT`).
- If an error or out-of-stock condition occurs, the transaction is **rolled back** immediately.
- Automatic status update: If the remaining stock reaches `0`, the vehicle status is automatically updated to **'Sold Out'**.

### 7. Maintenance & Service Center
- Create service tickets linking vehicle, customer, date, description, estimated cost, and status.
- Prominent **Maintenance Queue** with one-click actions:
  - `▶️ Start Service (In Progress)`
  - `✅ Mark Completed`
- Option to restore vehicle status back to `Available` upon service completion.

### 8. Reports & Data Export
- Filter sales performance by custom date ranges.
- KPI cards: Orders, Units Sold, Vehicle Revenue, Average Order Value, and Service Revenue.
- Best-selling brand ranking chart (Plotly) and monthly trend lines.
- **Instant CSV Downloads:**
  - 📥 Sales Ledger CSV
  - 📥 Vehicle Inventory CSV
  - 📥 Customer Directory CSV
  - 📥 Service Records CSV

---

## 🚀 Setup & Launch Instructions

### Prerequisites
- Python 3.10+ (tested on Python 3.11 and 3.14)
- MySQL Server 8.0+

### Step 1: Clone or Navigate to the Project Directory
```bash
git clone <your-repository-url>
cd vehicle-management
```

### Step 2: Install Python Dependencies
```bash
pip install -r requirements.txt
```

### Step 3: Configure Database Credentials
Create or edit your `.env` file in the root project folder (or configure `.streamlit/secrets.toml`):
```ini
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your_mysql_password
DB_NAME=vehicle_mgmt
```
*(If your MySQL server runs on a different port, set `DB_PORT` accordingly).*

### Step 4: Initialize the Database Schema (One-Time)
You can initialize the schema using the command line or directly from the website UI:
```bash
python -c "import db; ok, msg = db.init_db(); print(ok, msg)"
```
*Note: If the database is not initialized when you launch the website, `app.py` displays a 1-click **"Initialize / Restore Database"** button to set it up automatically without crashing!*

### Step 5: Run the Automated Test Suite (Optional)
```bash
python test_backend.py
```
*(All 8 test suites should pass with 100% success).*

### Step 6: Launch the Website
```bash
streamlit run app.py
```
Streamlit will launch the web application in your default browser at:
👉 **`http://127.0.0.1:8501`** (or your Streamlit Community Cloud URL)

Sign in with:
- **Username:** `admin`
- **Password:** `admin123`

---

## ☁️ Streamlit Community Cloud Deployment

To deploy this application on **Streamlit Community Cloud**:

1. Push your repository to GitHub (ensure `.env` and `.streamlit/secrets.toml` are in `.gitignore`).
2. Log in to [share.streamlit.io](https://share.streamlit.io/) and click **New app**.
3. Select your repository, branch (`main`), and set Main file path to **`app.py`**.
4. In **App settings ➔ Secrets**, enter your cloud MySQL database credentials.

### Connecting with Aiven MySQL (Recommended)

**Option A — Quickest (Using Aiven Service URI):**
In Aiven Console ➔ Your MySQL Service ➔ **Overview**, copy the **Service URI** and paste into Streamlit Secrets:
```toml
SERVICE_URI = "mysql://avnadmin:YOUR_PASSWORD@your-service-name.a.aivencloud.com:PORT/defaultdb?ssl-mode=REQUIRED"
```

**Option B — Using Individual Parameters:**
```toml
DB_HOST = "your-service-name.a.aivencloud.com"
DB_PORT = 12345                     # Aiven custom port (e.g. 10000-29999, NOT 3306)
DB_USER = "avnadmin"
DB_PASSWORD = 'YOUR_PASSWORD'       # MUST use single quotes so special chars (#, $, @) are not parsed as comments!
DB_NAME = "defaultdb"               # Use Aiven's default database name
DB_SSL = true
DB_SSL_VERIFY_CERT = false
```

> **Important Aiven Tips:**
> - If you receive `1045: Access denied for user 'avnadmin'`, reset your password in the Aiven console and copy the fresh password.
> - Always wrap passwords in **single quotes** (`'your_password'`) in Streamlit Secrets if the password has `#`, `@`, or `$`, because TOML treats `#` as a comment line and truncates your password.
> - Ensure the port is the custom high port shown in your Aiven dashboard (NOT `3306`).
> - The default pre-created database in Aiven is `defaultdb`.

5. Click **Save** and deploy! On first load, if the tables are not yet created, click the **"Initialize / Restore Database"** button on the home screen to automatically run the schema and seed the initial `admin` account.

---

## 🛡️ Security Best Practices
- **Parameterized SQL Queries:** All SQL queries use `%s` parameterization to prevent SQL injection.
- **Password Hashing:** Passwords stored using bcrypt with cryptographic salt; plain text passwords are never stored.
- **No Hardcoded Credentials:** Credentials are read from `st.secrets` first, falling back to `.env`.
- **Database Safety:** Safe deletions prevent orphan records or foreign key cascade accidents.
