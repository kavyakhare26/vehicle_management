"""Reports & Analytics Page.

Generates custom-period financial audits, sales volume metrics, top-selling brand rankings,
interactive revenue visualizations, and complete CSV export capabilities across all modules.
"""

from datetime import date, timedelta
import streamlit as st
import pandas as pd
import plotly.express as px
import db
import ui_common

st.set_page_config(page_title="Reports - AutoCore VMS", page_icon="📈", layout="wide")
ui_common.require_auth()

st.title("📈 Reports & Business Intelligence")
st.caption("Generate revenue analytics, audit sales performance by date range, and export operational datasets to CSV.")

# Date Range Filter
st.markdown("#### 📅 Audit Period Selection")
r_col1, r_col2 = st.columns([2, 1])

with r_col1:
    today = date.today()
    default_start = today.replace(day=1) - timedelta(days=180)  # past ~6 months
    date_selection = st.date_input("Select Report Date Window:", value=(default_start, today))

start_date = date_selection[0] if isinstance(date_selection, tuple) and len(date_selection) > 0 else default_start
end_date = date_selection[1] if isinstance(date_selection, tuple) and len(date_selection) > 1 else today

st.write(f"Analyzing performance from **{start_date.strftime('%d %b %Y')}** to **{end_date.strftime('%d %b %Y')}**")

# Fetch Period Summary
try:
    summary = db.get_reports_summary(start_date, end_date)
except Exception as e:
    st.error(f"Error compiling reports: {e}")
    st.stop()

# 1. Executive Summary Metric Cards
m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Sales Orders", summary["total_transactions"])
m2.metric("Vehicles Sold", f"{summary['total_units_sold']} units")
m3.metric("Vehicle Revenue", ui_common.format_currency(summary["total_revenue"]))
m4.metric("Avg Order Value", ui_common.format_currency(summary["avg_order_value"]))
m5.metric("Service Revenue", ui_common.format_currency(summary["service_revenue"]))

st.divider()

# 2. Charts: Best-selling Brands and Monthly Revenue
c_left, c_right = st.columns(2)

with c_left:
    with st.container(border=True):
        st.markdown("#### 🏆 Best-Selling Brands (By Revenue)")
        brand_df = summary["brand_summary"]
        if not brand_df.empty:
            fig_brand = px.bar(
                brand_df,
                x="brand",
                y="brand_revenue",
                text_auto=".2s",
                labels={"brand": "Brand", "brand_revenue": "Revenue ($)"},
                color="brand_revenue",
                color_continuous_scale="Blues",
            )
            fig_brand.update_layout(margin=dict(l=10, r=10, t=20, b=20), xaxis_title=None, coloraxis_showscale=False)
            st.plotly_chart(fig_brand, use_container_width=True)
            st.dataframe(
                brand_df.rename(columns={"brand": "Brand", "sales_count": "Transactions", "units_sold": "Units Sold", "brand_revenue": "Total Revenue ($)"}),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("No vehicle sales found in the selected date range.")

with c_right:
    with st.container(border=True):
        st.markdown("#### 📈 Monthly Sales Revenue Trend")
        try:
            monthly_df = db.get_sales_by_month_data()
            if not monthly_df.empty:
                fig_trend = px.line(
                    monthly_df,
                    x="sale_month",
                    y="total_revenue",
                    markers=True,
                    labels={"sale_month": "Month", "total_revenue": "Revenue ($)"},
                )
                fig_trend.update_traces(line_color="#2563eb", line_width=3, marker_size=8)
                fig_trend.update_layout(margin=dict(l=10, r=10, t=20, b=20), xaxis_title=None)
                st.plotly_chart(fig_trend, use_container_width=True)
            else:
                st.info("No monthly revenue history available.")
        except Exception as e:
            st.error(f"Error rendering trend chart: {e}")

st.divider()

# 3. Detailed Filtered Sales Table
st.subheader("📋 Sales Records for Selected Window")
try:
    filtered_sales = db.get_sales(start_date=start_date, end_date=end_date)
    if filtered_sales:
        df_filtered = pd.DataFrame(filtered_sales)
        clean_filtered = df_filtered[
            ["sale_id", "sale_date", "customer_name", "customer_phone", "brand", "model", "vin", "quantity", "total_price", "payment_mode"]
        ].copy()
        clean_filtered.columns = ["Sale ID", "Date", "Customer", "Phone", "Brand", "Model", "VIN", "Qty", "Total Price ($)", "Payment Mode"]
        st.dataframe(clean_filtered, use_container_width=True, hide_index=True)
    else:
        st.info("No sales transactions recorded within this timeframe.")
except Exception as e:
    st.error(f"Error retrieving sales: {e}")

st.divider()

# 4. CSV Download Exports
st.subheader("📥 Export Datasets to CSV")
st.caption("Download full audit reports and current operational databases in standard comma-separated format.")

exp1, exp2, exp3, exp4 = st.columns(4)

with exp1:
    with st.container(border=True):
        st.markdown("**Sales Ledger**")
        st.caption("All historical sales orders")
        try:
            all_sales = db.get_sales()
            if all_sales:
                sales_csv = pd.DataFrame(all_sales).to_csv(index=False).encode("utf-8")
                st.download_button(
                    label="⬇️ Download Sales CSV",
                    data=sales_csv,
                    file_name=f"sales_report_{date.today()}.csv",
                    mime="text/csv",
                    use_container_width=True,
                )
            else:
                st.write("No sales data.")
        except Exception:
            st.write("Unavailable")

with exp2:
    with st.container(border=True):
        st.markdown("**Vehicle Inventory**")
        st.caption("Complete inventory catalog")
        try:
            all_veh = db.get_vehicles()
            if all_veh:
                veh_csv = pd.DataFrame(all_veh).to_csv(index=False).encode("utf-8")
                st.download_button(
                    label="⬇️ Download Inventory CSV",
                    data=veh_csv,
                    file_name=f"vehicle_inventory_{date.today()}.csv",
                    mime="text/csv",
                    use_container_width=True,
                )
            else:
                st.write("No vehicle data.")
        except Exception:
            st.write("Unavailable")

with exp3:
    with st.container(border=True):
        st.markdown("**Customer Directory**")
        st.caption("Registered client profiles")
        try:
            all_cust = db.get_customers()
            if all_cust:
                cust_csv = pd.DataFrame(all_cust).to_csv(index=False).encode("utf-8")
                st.download_button(
                    label="⬇️ Download Customers CSV",
                    data=cust_csv,
                    file_name=f"customers_directory_{date.today()}.csv",
                    mime="text/csv",
                    use_container_width=True,
                )
            else:
                st.write("No customer data.")
        except Exception:
            st.write("Unavailable")

with exp4:
    with st.container(border=True):
        st.markdown("**Service Maintenance**")
        st.caption("All past and pending service tickets")
        try:
            all_serv = db.get_services()
            if all_serv:
                serv_csv = pd.DataFrame(all_serv).to_csv(index=False).encode("utf-8")
                st.download_button(
                    label="⬇️ Download Service CSV",
                    data=serv_csv,
                    file_name=f"service_records_{date.today()}.csv",
                    mime="text/csv",
                    use_container_width=True,
                )
            else:
                st.write("No service data.")
        except Exception:
            st.write("Unavailable")

