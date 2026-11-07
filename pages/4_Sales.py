"""Sales Management Page.

Handles vehicle checkout, stock availability checks, atomic transactions (insert sale +
decrement inventory in one transaction with rollback on failure), automatic 'Sold Out' status,
seamless new-customer creation with auto-selection, and transaction history.
"""

from datetime import date, datetime
import streamlit as st
import pandas as pd
import db
import ui_common

st.set_page_config(page_title="Sales - AutoCore VMS", page_icon="💳", layout="wide")
ui_common.require_auth()

st.title("💳 Sales & Checkout Portal")
st.caption("Process vehicle sales with atomic transaction guarantees and live inventory reconciliation.")

PAYMENT_MODES = ["Cash", "UPI", "Card", "Loan"]

tab_new_sale, tab_history = st.tabs(["🛒 New Vehicle Sale", "📜 Sales History"])

# ==============================================================================
# TAB 1: NEW VEHICLE SALE (ATOMIC TRANSACTION)
# ==============================================================================
with tab_new_sale:
    st.subheader("🛒 Record New Sale")

    # Fetch active customers
    try:
        customers_list = db.get_customers()
    except Exception as e:
        customers_list = []
        st.error(f"Error loading customers: {e}")

    # Fetch available vehicles (quantity > 0)
    try:
        available_vehicles = db.get_vehicles(status="Available")
        # Filter only those with quantity > 0
        available_vehicles = [v for v in available_vehicles if v["quantity"] > 0]
    except Exception as e:
        available_vehicles = []
        st.error(f"Error loading vehicle stock: {e}")

    # Section 1: Customer Selection + Seamless "New Customer" option
    st.markdown("#### 1. Customer Information")
    cust_col1, cust_col2 = st.columns([3, 1])

    # Check if a newly created customer needs to be preselected
    target_cust_id = st.session_state.get("sales_selected_customer_id") or st.session_state.get("latest_customer_id")

    customer_map = {}
    default_cust_idx = 0
    for idx, c in enumerate(customers_list):
        label = f"{c['name']} (Phone: {c['phone']}) [ID #{c['customer_id']}]"
        customer_map[label] = c
        if target_cust_id and c["customer_id"] == target_cust_id:
            default_cust_idx = idx

    with cust_col1:
        if customers_list:
            selected_cust_label = st.selectbox(
                "Select Existing Customer *",
                options=list(customer_map.keys()),
                index=default_cust_idx,
                help="Choose an existing registered customer or add a new one on the right.",
            )
            selected_customer = customer_map[selected_cust_label]
        else:
            selected_customer = None
            st.warning("No customers registered yet. Please click '➕ New Customer' below.")

    with cust_col2:
        st.write("")  # Alignment spacer
        st.write("")
        show_quick_cust = st.toggle("➕ New Customer", value=False, help="Register a new customer and auto-select without losing entered data")

    # Seamless New Customer Quick-Form
    if show_quick_cust:
        with st.container(border=True):
            st.markdown("##### 👤 Quick Register New Customer")
            st.caption("Fill details and click 'Save & Auto-Select'. The customer will be immediately chosen for this sale.")
            with st.form("sales_inline_new_customer"):
                nc_name = st.text_input("Customer Full Name *", placeholder="e.g. Ananya Roy")
                nc_phone = st.text_input("10-Digit Phone *", placeholder="e.g. 9123456780")
                nc_col1, nc_col2 = st.columns(2)
                with nc_col1:
                    nc_email = st.text_input("Email", placeholder="ananya@example.com")
                with nc_col2:
                    nc_address = st.text_input("Address", placeholder="Kolkata, WB")

                save_cust_btn = st.form_submit_button("Save & Auto-Select Customer", type="primary")

                if save_cust_btn:
                    if not nc_name.strip():
                        st.error("Customer name is required.")
                    else:
                        try:
                            new_cid = db.add_customer(nc_name, nc_phone, nc_email, nc_address)
                            st.session_state["sales_selected_customer_id"] = new_cid
                            st.session_state["latest_customer_id"] = new_cid
                            st.success(f"Customer '{nc_name.strip()}' saved and auto-selected!")
                            st.rerun()
                        except ValueError as ve:
                            st.error(str(ve))
                        except Exception as ex:
                            st.error(f"Error saving customer: {ex}")

    st.divider()

    # Section 2: Vehicle Selection & Quantity
    st.markdown("#### 2. Vehicle Selection & Pricing")

    if not available_vehicles:
        st.error("⚠️ No vehicles are currently available in inventory with stock > 0. Please add stock in the Vehicles tab.")
    elif not selected_customer:
        st.info("Please select or add a customer above to proceed with the sale.")
    else:
        vehicle_map = {
            f"{v['brand']} {v['model']} ({v['vin']}) - Stock: {v['quantity']} unit(s) - ${float(v['price']):,.2f}": v
            for v in available_vehicles
        }

        v_col1, v_col2 = st.columns([3, 1])
        with v_col1:
            selected_v_label = st.selectbox("Select Vehicle *", list(vehicle_map.keys()))
            chosen_vehicle = vehicle_map[selected_v_label]

        with v_col2:
            max_qty = int(chosen_vehicle["quantity"])
            sale_qty = st.number_input(
                "Quantity *",
                min_value=1,
                max_value=max_qty,
                value=1,
                step=1,
                help=f"Available in stock: {max_qty}",
            )

        unit_price = float(chosen_vehicle["price"])
        total_price = unit_price * sale_qty

        # Price summary card
        st.markdown(
            f"""
            <div style="background-color: #f1f5f9; padding: 16px 20px; border-radius: 10px; margin: 12px 0 20px 0; border: 1px solid #cbd5e1;">
                <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap;">
                    <div>
                        <span style="color: #64748b; font-size: 0.9rem;">Vehicle:</span> <b>{chosen_vehicle['brand']} {chosen_vehicle['model']}</b> ({chosen_vehicle['colour']}, {chosen_vehicle['vehicle_type']})<br>
                        <span style="color: #64748b; font-size: 0.9rem;">VIN:</span> <code>{chosen_vehicle['vin']}</code> | 
                        <span style="color: #64748b; font-size: 0.9rem;">Available Stock:</span> <b>{chosen_vehicle['quantity']}</b> |
                        <span style="color: #64748b; font-size: 0.9rem;">Unit Price:</span> <b>{ui_common.format_currency(unit_price)}</b>
                    </div>
                    <div style="text-align: right; margin-top: 8px;">
                        <span style="color: #475569; font-size: 0.85rem; text-transform: uppercase; font-weight: 600;">Calculated Total Amount</span>
                        <div style="color: #1e3a8a; font-size: 1.9rem; font-weight: 800;">{ui_common.format_currency(total_price)}</div>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("#### 3. Payment & Finalization")
        pay_col1, pay_col2 = st.columns(2)
        with pay_col1:
            payment_mode = st.selectbox("Payment Mode *", PAYMENT_MODES)
        with pay_col2:
            sale_date = st.date_input("Sale Date *", value=date.today(), max_value=date.today())

        # Checkout confirmation
        st.caption("Submitting this order will record the sale and decrement vehicle inventory in a single atomic transaction. If stock reaches 0, the vehicle will be marked 'Sold Out'.")
        if st.button("🚀 Complete Vehicle Sale Transaction", type="primary", use_container_width=True):
            try:
                result = db.execute_sale_transaction(
                    customer_id=selected_customer["customer_id"],
                    vehicle_id=chosen_vehicle["vehicle_id"],
                    sale_date=sale_date,
                    quantity=sale_qty,
                    payment_mode=payment_mode,
                )
                st.balloons()
                st.success(
                    f"🎉 **Transaction Successful!** Sale ID #{result['sale_id']} recorded. "
                    f"Total: {ui_common.format_currency(result['total_price'])}. "
                    f"Remaining inventory for {result['vehicle_name']}: {result['remaining_qty']} unit(s)."
                )
                if result["remaining_qty"] == 0:
                    st.warning(f"📢 Vehicle '{result['vehicle_name']}' is now **Sold Out**.")

                # Reset selected customer in session state
                st.session_state.pop("sales_selected_customer_id", None)
            except ValueError as ve:
                st.error(f"❌ Transaction Rejected: {ve}")
            except Exception as ex:
                st.error(f"❌ Database Transaction Failed (Rolled Back): {ex}")


# ==============================================================================
# TAB 2: SALES HISTORY & FILTERS
# ==============================================================================
with tab_history:
    st.subheader("📜 Sales Transaction Ledger")

    # Filter controls
    f_c1, f_c2, f_c3 = st.columns(3)
    with f_c1:
        s_search = st.text_input("Filter by Customer, Vehicle, or VIN", placeholder="Search name, phone, VIN...")
    with f_c2:
        s_paymode = st.selectbox("Payment Mode", ["All"] + PAYMENT_MODES)
    with f_c3:
        date_filter = st.date_input("Date Range", value=(date(2023, 1, 1), date.today()))

    start_d = date_filter[0] if isinstance(date_filter, tuple) and len(date_filter) > 0 else None
    end_d = date_filter[1] if isinstance(date_filter, tuple) and len(date_filter) > 1 else None

    try:
        sales_data = db.get_sales(start_date=start_d, end_date=end_d, payment_mode=s_paymode, search=s_search)
    except Exception as e:
        sales_data = []
        st.error(f"Error loading sales records: {e}")

    # Summary metrics for filtered sales
    if sales_data:
        total_vol = sum(s["quantity"] for s in sales_data)
        total_rev = sum(float(s["total_price"]) for s in sales_data)

        m1, m2, m3 = st.columns(3)
        m1.metric("Transactions Count", len(sales_data))
        m2.metric("Total Vehicles Sold", f"{total_vol} units")
        m3.metric("Total Revenue ($)", ui_common.format_currency(total_rev))

        # Format dataframe
        df_sales = pd.DataFrame(sales_data)
        clean_sales = df_sales[
            ["sale_id", "sale_date", "customer_name", "customer_phone", "brand", "model", "vin", "quantity", "total_price", "payment_mode"]
        ].copy()
        clean_sales.columns = ["Sale ID", "Date", "Customer", "Phone", "Brand", "Model", "VIN", "Qty", "Total Price ($)", "Payment"]

        st.dataframe(clean_sales, use_container_width=True, hide_index=True)
    else:
        st.info("No sales transactions found for the specified filters.")

