"""Dashboard Page for Vehicle Management System.

Displays executive KPI cards, monthly revenue trends, inventory distribution by brand,
and immediate alerts for low-stock vehicles (quantity < 3).
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import db
import ui_common

# Page configuration
st.set_page_config(page_title="Dashboard - AutoCore VMS", page_icon="📊", layout="wide")

# Protect Page with Authentication
ui_common.require_auth()

st.title("📊 Executive Dashboard")
st.caption("Real-time automotive operations, inventory metrics, and financial performance overview.")

# Refresh button
top_col1, top_col2 = st.columns([6, 1])
with top_col2:
    if st.button("🔄 Refresh Data", use_container_width=True):
        st.rerun()

# 1. Fetch KPI metrics
try:
    kpis = db.get_dashboard_kpis()
except Exception as e:
    st.error(f"Error fetching dashboard indicators: {e}")
    st.stop()

# 2. Render Metric KPI Cards
c1, c2, c3, c4 = st.columns(4)

with c1:
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-title">📦 Total Vehicles in Stock</div>
            <div class="metric-value">{kpis['total_stock']}</div>
            <div class="metric-subtitle">Across all active models</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with c2:
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-title">👥 Registered Customers</div>
            <div class="metric-value">{kpis['total_customers']}</div>
            <div class="metric-subtitle">Verified phone accounts</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with c3:
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-title">🗓️ Monthly Sales Count</div>
            <div class="metric-value">{kpis['month_sales_count']}</div>
            <div class="metric-subtitle">Current calendar month</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with c4:
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-title">💰 Monthly Revenue</div>
            <div class="metric-value" style="color: #166534;">{ui_common.format_currency(kpis['month_revenue'])}</div>
            <div class="metric-subtitle">All-time: {ui_common.format_currency(kpis['total_revenue'])}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.write("")

# 3. Low Stock Alerts (quantity < 3)
try:
    low_stock = db.get_low_stock_vehicles()
except Exception as e:
    low_stock = []
    st.error(f"Error fetching low stock vehicles: {e}")

if low_stock:
    st.markdown(
        f"""
        <div style="background-color: #fffbeb; border: 1px solid #fde68a; border-left: 5px solid #f59e0b; padding: 14px 18px; border-radius: 8px; margin-bottom: 20px;">
            <div style="font-weight: 700; color: #92400e; font-size: 1rem;">⚠️ Low Stock Alert: {len(low_stock)} vehicle(s) have fewer than 3 units in stock!</div>
            <div style="color: #b45309; font-size: 0.85rem;">Restock recommended to prevent out-of-stock orders.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    with st.expander("🔻 View Low-Stock Inventory Details", expanded=True):
        low_df = pd.DataFrame(low_stock)
        low_display = low_df[["vin", "brand", "model", "vehicle_type", "quantity", "price", "status"]].copy()
        low_display.columns = ["VIN", "Brand", "Model", "Type", "Stock Qty", "Unit Price ($)", "Status"]
        st.dataframe(
            low_display.style.highlight_between(subset=["Stock Qty"], left=0, right=2, color="#fed7aa"),
            use_container_width=True,
            hide_index=True,
        )
else:
    st.success("✅ Healthy Stock Levels: All inventory models have 3 or more units available.")

# 4. Interactive Charts
st.subheader("📈 Trends & Inventory Distribution")

chart_col1, chart_col2 = st.columns(2)

with chart_col1:
    with st.container(border=True):
        st.markdown("#### 📅 Sales by Month")
        try:
            sales_by_month_df = db.get_sales_by_month_data()
            if not sales_by_month_df.empty:
                fig_sales = px.bar(
                    sales_by_month_df,
                    x="sale_month",
                    y="total_revenue",
                    text_auto=".2s",
                    labels={"sale_month": "Month", "total_revenue": "Revenue ($)"},
                    title="Monthly Revenue ($)",
                    color_discrete_sequence=["#2563eb"],
                )
                fig_sales.update_layout(margin=dict(l=20, r=20, t=40, b=20), xaxis_title=None)
                st.plotly_chart(fig_sales, use_container_width=True)
            else:
                st.info("No sales transactions recorded yet. Transactions will populate this monthly trend chart.")
        except Exception as e:
            st.error(f"Error loading sales chart: {e}")

with chart_col2:
    with st.container(border=True):
        st.markdown("#### 🏷️ Stock Distribution by Brand")
        try:
            stock_brand_df = db.get_stock_by_brand_data()
            if not stock_brand_df.empty:
                fig_brand = px.pie(
                    stock_brand_df,
                    names="brand",
                    values="total_stock",
                    hole=0.45,
                    title="Vehicle Inventory Share by Brand",
                    color_discrete_sequence=px.colors.qualitative.Prism,
                )
                fig_brand.update_traces(textposition="inside", textinfo="percent+label")
                fig_brand.update_layout(margin=dict(l=20, r=20, t=40, b=20))
                st.plotly_chart(fig_brand, use_container_width=True)
            else:
                st.info("No vehicle inventory available.")
        except Exception as e:
            st.error(f"Error loading inventory distribution chart: {e}")

# 5. Pending Services Quick Summary
try:
    pending_services = db.get_pending_services()
    if pending_services:
        st.write("")
        st.subheader(f"🔧 Maintenance Queue ({len(pending_services)} in queue)")
        pend_df = pd.DataFrame(pending_services)
        display_pend = pend_df[["service_id", "service_date", "customer_name", "customer_phone", "brand", "model", "status", "cost"]].copy()
        display_pend.columns = ["Service ID", "Date", "Customer", "Phone", "Brand", "Model", "Status", "Est. Cost ($)"]
        st.dataframe(display_pend, use_container_width=True, hide_index=True)
except Exception:
    pass

