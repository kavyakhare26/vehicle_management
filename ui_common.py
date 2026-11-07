"""Shared UI components, session authentication guards, and theme styling for Vehicle Management System.
"""

import streamlit as st
import db


def inject_custom_css():
    """Inject custom modern CSS styling across pages."""
    st.markdown(
        """
        <style>
        /* Base and Font */
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
        html, body, [class*="css"] {
            font-family: 'Inter', sans-serif;
        }

        /* Metric KPI Card Styling */
        .metric-card {
            background: linear-gradient(135deg, #ffffff 0%, #f8fafc 100%);
            border: 1px solid #e2e8f0;
            border-radius: 12px;
            padding: 20px;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
            transition: all 0.2s ease;
        }
        .metric-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 15px -3px rgba(0, 0, 0, 0.08);
            border-color: #cbd5e1;
        }
        .metric-title {
            color: #64748b;
            font-size: 0.85rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 6px;
        }
        .metric-value {
            color: #0f172a;
            font-size: 1.85rem;
            font-weight: 700;
            line-height: 1.2;
        }
        .metric-subtitle {
            color: #94a3b8;
            font-size: 0.8rem;
            margin-top: 4px;
        }

        /* Status Badges */
        .badge {
            display: inline-block;
            padding: 4px 10px;
            border-radius: 9999px;
            font-size: 0.78rem;
            font-weight: 600;
            text-align: center;
        }
        .badge-available { background-color: #dcfce7; color: #166534; }
        .badge-soldout { background-color: #fee2e2; color: #991b1b; }
        .badge-underservice { background-color: #fef3c7; color: #92400e; }
        .badge-pending { background-color: #fed7aa; color: #9a3412; }
        .badge-inprogress { background-color: #dbeafe; color: #1e40af; }
        .badge-completed { background-color: #dcfce7; color: #166534; }

        /* Sidebar Styling */
        .sidebar-brand {
            padding: 10px 0 16px 0;
            border-bottom: 1px solid #e2e8f0;
            margin-bottom: 16px;
        }
        .user-badge {
            background-color: #eff6ff;
            border: 1px solid #bfdbfe;
            border-radius: 8px;
            padding: 10px 14px;
            margin-bottom: 14px;
        }
        .user-name {
            font-weight: 700;
            color: #1e3a8a;
            font-size: 0.95rem;
        }
        .user-role {
            font-size: 0.75rem;
            color: #3b82f6;
            text-transform: uppercase;
            font-weight: 600;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


@st.dialog("➕ Quick Add Customer")
def quick_add_customer_modal():
    """Streamlit Dialog form to add a new customer anytime from any page."""
    st.write("Register a new customer instantly. Phone number must be unique and 10 digits.")

    with st.form("quick_add_customer_form", clear_on_submit=False):
        name = st.text_input("Full Name *", placeholder="e.g. Priya Patel")
        phone = st.text_input("10-Digit Mobile Number *", placeholder="e.g. 9876543210")
        email = st.text_input("Email Address", placeholder="e.g. priya@example.com")
        address = st.text_area("Address", placeholder="e.g. 42 Park Avenue, Mumbai")

        col1, col2 = st.columns([1, 1])
        with col1:
            submit_btn = st.form_submit_button("Save Customer", use_container_width=True, type="primary")

        if submit_btn:
            if not name.strip():
                st.error("Customer name cannot be empty.")
            else:
                try:
                    new_id = db.add_customer(name=name, phone=phone, email=email, address=address)
                    st.success(f"Customer '{name.strip()}' registered successfully! (ID: {new_id})")
                    # Store latest added customer id in session state so calling forms can auto-select it
                    st.session_state["latest_customer_id"] = new_id
                    st.session_state["latest_customer_name"] = name.strip()
                    st.rerun()
                except ValueError as ve:
                    st.error(str(ve))
                except Exception as e:
                    st.error(f"Failed to add customer: {e}")


def render_sidebar():
    """Render common sidebar content: Branding, User Profile, Quick Add Customer, and Logout."""
    with st.sidebar:
        st.markdown(
            """
            <div class="sidebar-brand">
                <h2 style="margin: 0; font-size: 1.35rem; color: #0f172a;">🚗 <b>AutoCore</b> VMS</h2>
                <div style="font-size: 0.75rem; color: #64748b;">Vehicle Management System</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # User profile badge
        if st.session_state.get("logged_in"):
            username = st.session_state.get("username", "User")
            role = st.session_state.get("role", "staff")
            role_label = "Administrator" if role == "admin" else "Staff Member"
            st.markdown(
                f"""
                <div class="user-badge">
                    <div class="user-name">👤 {username}</div>
                    <div class="user-role">{role_label}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            # Quick Customer Add Button (Visible on EVERY page!)
            st.caption("⚡ FAST ACTIONS")
            if st.button("➕ Add Customer", use_container_width=True, help="Register a customer anytime from any page"):
                quick_add_customer_modal()

            st.divider()

            # Sign Out Button
            if st.button("🚪 Sign Out", use_container_width=True):
                st.session_state.clear()
                st.success("Signed out successfully.")
                st.rerun()
        else:
            st.info("Please log in to access the system.")


def require_auth():
    """Guard function: Ensures user is authenticated before rendering the page.

    Halts execution if not logged in or if database connection fails.
    """
    inject_custom_css()
    render_sidebar()

    # Friendly database connectivity check
    conn_ok, conn_msg = db.test_db_connection()
    if not conn_ok:
        st.error(f"⚠️ **Database Connection Error:** {conn_msg}")
        st.info("Please verify your database credentials in Streamlit Cloud Secrets or local .env.")
        st.stop()

    if not st.session_state.get("logged_in"):
        st.error("🔒 Access Denied: You must be logged in to view this page.")
        st.info("Please navigate to the main **Login** page from the sidebar or click below:")
        col1, _ = st.columns([1, 2])
        with col1:
            if st.button("Go to Login Page", type="primary", use_container_width=True):
                st.switch_page("app.py")
        st.stop()


def format_currency(amount):
    """Format numeric value into standard currency display."""
    try:
        val = float(amount)
        return f"${val:,.2f}"
    except (ValueError, TypeError):
        return "$0.00"


def get_status_badge_html(status):
    """Return styled HTML badge for vehicle or service status."""
    status_lower = str(status).lower().replace(" ", "")
    badge_class = f"badge-{status_lower}"
    return f'<span class="badge {badge_class}">{status}</span>'

