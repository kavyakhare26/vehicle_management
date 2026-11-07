"""All Data - Unified Database Explorer Page.

Dynamically inspects every table in the database using SHOW TABLES,
displays live record count metric cards, renders full datasets across dedicated tabs,
enriches sales and service relations with JOINs, guarantees password hashes are hidden,
and provides multi-column filtering and CSV exports for every table.
"""

from datetime import datetime
from decimal import Decimal
import streamlit as st
import pandas as pd
import db
import ui_common

# Configure Page
st.set_page_config(page_title="All Data - AutoCore VMS", page_icon="🗄️", layout="wide")

# Enforce existing session-based authentication guard
ui_common.require_auth()

# Top Header & Refresh Control
top_col1, top_col2 = st.columns([6, 1])
with top_col1:
    st.title("🗄️ Database Explorer & Master Records")
    st.caption("Live, dynamic view of all relational tables in the database with instant search and CSV export.")

with top_col2:
    st.write("")  # Vertical spacing
    if st.button("🔄 Refresh Data", key="refresh_all_data", use_container_width=True, type="primary"):
        st.rerun()

# 1. Dynamically retrieve all database tables using SHOW TABLES
try:
    tables_result = db.execute_query("SHOW TABLES", fetch="all")
    if not tables_result:
        st.warning("No tables found in current database.")
        st.stop()
    table_names = [list(row.values())[0] for row in tables_result]
except Exception as e:
    st.error(f"Error querying database tables: {e}")
    st.stop()

# 2. Compute record count for each table
table_counts = {}
for table in table_names:
    try:
        cnt_row = db.execute_query(f"SELECT COUNT(*) AS total_rows FROM `{table}`", fetch="one")
        table_counts[table] = int(cnt_row["total_rows"]) if cnt_row else 0
    except Exception as ex:
        table_counts[table] = 0
        st.error(f"Error reading row count for table '{table}': {ex}")

# 3. Render Metric Count Cards for every table
st.subheader("📊 Live Record Counts")
cols = st.columns(min(len(table_names), 5))
for idx, table in enumerate(table_names):
    col = cols[idx % len(cols)]
    formatted_name = table.replace("_", " ").title()
    count = table_counts.get(table, 0)
    with col:
        st.markdown(
            f"""
            <div class="metric-card" style="margin-bottom: 12px; padding: 16px;">
                <div class="metric-title">📋 {formatted_name}</div>
                <div class="metric-value" style="font-size: 1.6rem;">{count}</div>
                <div class="metric-subtitle">Table: <code>{table}</code></div>
            </div>
            """,
            unsafe_allow_html=True,
        )

st.divider()

# 4. Render one Tab per Table with enriched JOINs and column protection
st.subheader("📁 Table Records")
tab_labels = [f"📄 {t.replace('_', ' ').title()} ({table_counts.get(t, 0)})" for t in table_names]
tabs = st.tabs(tab_labels)


def fetch_table_dataframe(table_name):
    """Retrieve full records for a given table with appropriate JOINs or column filters."""
    # Custom query for sales: Join customers and vehicles for human-readable details
    if table_name == "sales":
        query = """
            SELECT s.sale_id, s.sale_date,
                   c.customer_id, c.name AS customer_name, c.phone AS customer_phone,
                   v.vehicle_id, v.brand AS vehicle_brand, v.model AS vehicle_model,
                   v.vin AS vehicle_vin, v.vehicle_type,
                   s.quantity, s.total_price, s.payment_mode, s.created_at
            FROM sales s
            LEFT JOIN customers c ON s.customer_id = c.customer_id
            LEFT JOIN vehicles v ON s.vehicle_id = v.vehicle_id
            ORDER BY s.sale_id DESC
        """
        rows = db.execute_query(query, fetch="all")

    # Custom query for services: Join customers and vehicles
    elif table_name == "services":
        query = """
            SELECT s.service_id, s.service_date,
                   c.customer_id, c.name AS customer_name, c.phone AS customer_phone,
                   v.vehicle_id, v.brand AS vehicle_brand, v.model AS vehicle_model,
                   v.vin AS vehicle_vin,
                   s.description, s.cost, s.status, s.created_at
            FROM services s
            LEFT JOIN customers c ON s.customer_id = c.customer_id
            LEFT JOIN vehicles v ON s.vehicle_id = v.vehicle_id
            ORDER BY s.service_id DESC
        """
        rows = db.execute_query(query, fetch="all")

    # Query for users: Strictly hide password_hash
    elif table_name == "users":
        query = """
            SELECT user_id, username, role, created_at
            FROM users
            ORDER BY user_id ASC
        """
        rows = db.execute_query(query, fetch="all")

    # Generic query for all other current and future tables
    else:
        query = f"SELECT * FROM `{table_name}`"
        rows = db.execute_query(query, fetch="all")

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)

    # Strictly guarantee password_hash is never exposed if present
    if "password_hash" in df.columns:
        df = df.drop(columns=["password_hash"])

    return df


for idx, table in enumerate(table_names):
    with tabs[idx]:
        st.markdown(f"#### Table: `vehicle_mgmt.{table}`")

        try:
            df = fetch_table_dataframe(table)
        except Exception as e:
            st.error(f"Failed to load records for table '{table}': {e}")
            df = pd.DataFrame()

        # Handle empty table state gracefully
        if df.empty:
            st.info(f"ℹ️ No records yet in '{table}'.")
        else:
            # Search Box across all columns & Download CSV controls
            search_col, dl_col = st.columns([3, 1])

            with search_col:
                search_term = st.text_input(
                    f"🔍 Search within {table.title()}",
                    placeholder=f"Filter across all columns in {table}...",
                    key=f"search_box_{table}",
                )

            # Apply multi-column filtering if search term provided
            if search_term.strip():
                # Case-insensitive substring match across every column
                term = search_term.strip().lower()
                mask = df.astype(str).apply(
                    lambda col: col.str.lower().str.contains(term, na=False)
                ).any(axis=1)
                filtered_df = df[mask]
            else:
                filtered_df = df

            with dl_col:
                st.write("")  # Alignment spacing
                st.write("")
                csv_bytes = filtered_df.to_csv(index=False).encode("utf-8")
                timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
                st.download_button(
                    label=f"⬇️ Download CSV ({len(filtered_df)})",
                    data=csv_bytes,
                    file_name=f"{table}_export_{timestamp_str}.csv",
                    mime="text/csv",
                    key=f"download_btn_{table}",
                    use_container_width=True,
                )

            st.caption(f"Displaying **{len(filtered_df)}** of **{len(df)}** total record(s)")

            # Render Table using st.dataframe
            st.dataframe(
                filtered_df,
                use_container_width=True,
                hide_index=True,
            )

