"""Vehicle Management System - Main Entry Point & Authentication.

Handles user sign-in using bcrypt, session initialization, database diagnostics,
and multi-page navigation routing.
"""

import streamlit as st
import db
import ui_common

# Configure Page
st.set_page_config(
    page_title="AutoCore VMS - Portal",
    page_icon="🚗",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Apply common styles
ui_common.inject_custom_css()

# Test DB Connection on boot
conn_ok, conn_msg = db.test_db_connection()


def render_login_view():
    """Render the sign-in form for unauthenticated sessions."""
    col_left, col_center, col_right = st.columns([1, 1.2, 1])

    with col_center:
        st.markdown(
            """
            <div style="text-align: center; margin-bottom: 24px;">
                <h1 style="font-size: 2.2rem; margin-bottom: 4px; color: #0f172a;">🚗 <b>AutoCore</b> VMS</h1>
                <p style="color: #64748b; font-size: 0.95rem;">Automotive Inventory, Sales & Service Management Portal</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Friendly Database connection check banner
        if not conn_ok:
            st.error(f"⚠️ **Database Connection Notice:** {conn_msg}")

            cfg = db.get_db_config(include_db=True)
            with st.expander("🔍 Connection Diagnostics & Secrets Setup", expanded=True):
                is_aiven = "aivencloud.com" in str(cfg.get('host', '')) or cfg.get('user') == "avnadmin"
                st.write(f"- **Target Host:** `{cfg.get('host')}`")
                st.write(f"- **Target Port:** `{cfg.get('port')}`")
                st.write(f"- **User:** `{cfg.get('user')}`")
                st.write(f"- **Database Name:** `{cfg.get('database')}`")
                st.write(f"- **Password Set:** `{'Yes (' + str(len(cfg.get('password', ''))) + ' chars)' if cfg.get('password') else 'No (Empty)'}`")
                st.write(f"- **SSL Active:** `{'Yes' if not cfg.get('ssl_disabled', False) else 'No'}`")

                if is_aiven or "1045" in conn_msg:
                    st.warning(
                        "💡 **Aiven MySQL Troubleshooting Guide:**\n"
                        "1. **Password**: Go to Aiven Console ➔ Your MySQL Service ➔ Overview ➔ Click 'Reset Password' or copy the password.\n"
                        "2. **Single Quotes in Secrets**: If your password contains `#`, `$`, `@`, or `\\`, wrap it in single quotes in Streamlit Secrets: `DB_PASSWORD = '...'` so TOML does not truncate at `#`.\n"
                        "3. **Port**: Aiven uses a high custom port (e.g., `10000`-`29999`), NOT `3306`.\n"
                        "4. **Database**: Use `DB_NAME = 'defaultdb'` (Aiven's pre-created database).\n"
                        "5. **One-Line Service URI**: Alternatively, copy the **Service URI** directly from Aiven and set `SERVICE_URI = '...'` in Streamlit Secrets."
                    )

                st.markdown(
                    """
                    **Deploying on Streamlit Community Cloud?**
                    1. Open your Streamlit Cloud app dashboard.
                    2. Go to **Settings** ➔ **Secrets**.
                    3. Paste your cloud MySQL credentials (see `.streamlit/secrets.toml.example`):
                    ```toml
                    # Easiest with Aiven:
                    SERVICE_URI = "mysql://avnadmin:YOUR_PASSWORD@your-host.a.aivencloud.com:PORT/defaultdb?ssl-mode=REQUIRED"

                    # Or with individual parameters:
                    DB_HOST = "your-host.a.aivencloud.com"
                    DB_PORT = 12345
                    DB_USER = "avnadmin"
                    DB_PASSWORD = 'your_password_in_single_quotes'
                    DB_NAME = "defaultdb"
                    DB_SSL = true
                    ```
                    """
                )

            btn_col1, btn_col2 = st.columns(2)
            with btn_col1:
                if st.button("🛠️ Initialize / Restore Database", use_container_width=True, type="primary"):
                    success, init_msg = db.init_db()
                    if success:
                        st.success(init_msg)
                        st.rerun()
                    else:
                        st.error(init_msg)
            with btn_col2:
                if st.button("🔄 Retry Connection", use_container_width=True):
                    st.rerun()
            st.stop()

        with st.container(border=True):
            st.subheader("🔐 Account Sign In")
            st.caption("Enter your credentials to access the management portal.")

            with st.form("login_form", clear_on_submit=False):
                username = st.text_input("Username", placeholder="admin or staff")
                password = st.text_input("Password", type="password", placeholder="Enter your password")

                submit = st.form_submit_button("Sign In", type="primary", use_container_width=True)

                if submit:
                    if not username.strip() or not password:
                        st.error("Please enter both username and password.")
                    else:
                        user = db.authenticate_user(username, password)
                        if user:
                            st.session_state["logged_in"] = True
                            st.session_state["user_id"] = user["user_id"]
                            st.session_state["username"] = user["username"]
                            st.session_state["role"] = user["role"]
                            st.success(f"Welcome back, {user['username']} ({user['role'].title()})!")
                            try:
                                st.switch_page("pages/1_Dashboard.py")
                            except Exception:
                                st.rerun()
                        else:
                            st.error("Invalid username or password. Please verify and try again.")

        # Default Demo Credentials Card
        with st.expander("ℹ️ Default Demo Credentials", expanded=True):
            st.markdown(
                """
                - **Administrator Account:**
                  - Username: `admin`
                  - Password: `admin123`
                  - *Full access to inventory, sales, services, customers, and reports.*
                - **Staff Account:**
                  - Username: `staff`
                  - Password: `staff123`
                  - *Access for sales, services, and inventory tracking.*
                """
            )


def render_authenticated_home():
    """Render welcome screen and navigation launcher when already signed in."""
    ui_common.render_sidebar()

    username = st.session_state.get("username", "User")
    role = st.session_state.get("role", "staff").title()

    st.markdown(
        f"""
        <div style="background: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 100%); color: white; padding: 28px 32px; border-radius: 12px; margin-bottom: 24px;">
            <h1 style="color: white; margin: 0; font-size: 2rem;">Welcome, {username}! 👋</h1>
            <p style="color: #e0e7ff; margin: 6px 0 0 0; font-size: 1rem;">Role: <b>{role}</b> &bull; Connected to MySQL Database: <code>{db.get_db_config().get('database', 'vehicle_mgmt')}</code></p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.subheader("⚡ Quick Navigation")
    c1, c2, c3 = st.columns(3)

    with c1:
        with st.container(border=True):
            st.markdown("### 📊 Dashboard")
            st.write("View executive KPI metrics, sales trends, stock by brand, and low-inventory alerts.")
            if st.button("Open Dashboard ➜", key="btn_dash", use_container_width=True, type="primary"):
                st.switch_page("pages/1_Dashboard.py")

        with st.container(border=True):
            st.markdown("### 🚙 Vehicles")
            st.write("Browse, filter, add, edit, and track vehicles across models and fuel types.")
            if st.button("Manage Vehicles ➜", key="btn_veh", use_container_width=True):
                st.switch_page("pages/2_Vehicles.py")

    with c2:
        with st.container(border=True):
            st.markdown("### 👥 Customers")
            st.write("Manage client profiles with 10-digit mobile verification and purchase histories.")
            if st.button("Manage Customers ➜", key="btn_cust", use_container_width=True):
                st.switch_page("pages/3_Customers.py")

        with st.container(border=True):
            st.markdown("### 💳 Sales Orders")
            st.write("Execute atomic vehicle sales, decrement inventory, and generate receipts.")
            if st.button("New / View Sales ➜", key="btn_sales", use_container_width=True):
                st.switch_page("pages/4_Sales.py")

    with c3:
        with st.container(border=True):
            st.markdown("### 🔧 Service Center")
            st.write("Log vehicle maintenance, update status, track costs, and view pending jobs.")
            if st.button("Service Logs ➜", key="btn_service", use_container_width=True):
                st.switch_page("pages/5_Service.py")

        with st.container(border=True):
            st.markdown("### 📈 Reports & Exports")
            st.write("Analyze sales performance, best-selling brands, and download CSV data.")
            if st.button("View Reports ➜", key="btn_rep", use_container_width=True):
                st.switch_page("pages/6_Reports.py")

    # Full database master records card
    st.write("")
    with st.container(border=True):
        f1, f2 = st.columns([3, 1])
        with f1:
            st.markdown("### 🗄️ Master Database Explorer (All Data)")
            st.write("Inspect live counts for all relational tables, view joined sales & service records, search across all columns, and download CSVs.")
        with f2:
            st.write("")
            if st.button("Explore All Tables ➜", key="btn_all_data", use_container_width=True, type="secondary"):
                st.switch_page("pages/7_All_Data.py")


# Main display routing
if not st.session_state.get("logged_in"):
    render_login_view()
else:
    render_authenticated_home()
