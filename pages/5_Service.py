"""Service Management Page.

Handles logging vehicle maintenance, updating service status (Pending -> In Progress -> Completed),
tracking service costs, quick customer registration, and prominent pending queue monitoring.
"""

from datetime import date
import streamlit as st
import pandas as pd
import db
import ui_common

st.set_page_config(page_title="Service - AutoCore VMS", page_icon="🔧", layout="wide")
ui_common.require_auth()

st.title("🔧 Service & Maintenance Center")
st.caption("Schedule vehicle servicing, assign technician jobs, track maintenance costs, and manage status updates.")

SERVICE_STATUSES = ["Pending", "In Progress", "Completed"]

tab_queue, tab_new_service, tab_history = st.tabs(["⏳ Pending & Active Jobs", "➕ Log New Service", "📜 All Service Records"])

# ==============================================================================
# TAB 1: PENDING & ACTIVE QUEUE (PROMINENT VIEW + 1-CLICK STATUS UPDATES)
# ==============================================================================
with tab_queue:
    st.subheader("⏳ Maintenance Queue")
    st.caption("Active jobs requiring immediate attention or status advancement.")

    try:
        pending_jobs = db.get_pending_services()
    except Exception as e:
        pending_jobs = []
        st.error(f"Error loading maintenance queue: {e}")

    if pending_jobs:
        st.write(f"**{len(pending_jobs)}** active service job(s) in progress or awaiting service:")

        for job in pending_jobs:
            with st.container(border=True):
                q_c1, q_c2, q_c3 = st.columns([3, 2, 2])
                with q_c1:
                    status_badge = "badge-pending" if job["status"] == "Pending" else "badge-inprogress"
                    st.markdown(
                        f"""
                        <h4 style="margin: 0; color: #0f172a;">Job #{job['service_id']}: {job['brand']} {job['model']} 
                            <span class="badge {status_badge}">{job['status']}</span>
                        </h4>
                        <div style="color: #64748b; font-size: 0.85rem; margin-top: 4px;">
                            VIN: <code>{job['vin']}</code> | Scheduled: <b>{job['service_date']}</b>
                        </div>
                        <div style="margin-top: 8px; font-size: 0.95rem;">
                            <b>Description:</b> {job['description']}
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                with q_c2:
                    st.markdown(
                        f"""
                        <div style="font-size: 0.9rem;">
                            <b>Customer:</b> {job['customer_name']}<br>
                            <b>Mobile:</b> {job['customer_phone']}<br>
                            <b>Current Est. Cost:</b> {ui_common.format_currency(job['cost'])}
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                with q_c3:
                    st.write("**Quick Status Action:**")
                    if job["status"] == "Pending":
                        if st.button("▶️ Start Service (In Progress)", key=f"start_{job['service_id']}", use_container_width=True):
                            try:
                                db.update_service_status(job["service_id"], "In Progress")
                                st.success(f"Job #{job['service_id']} marked In Progress!")
                                st.rerun()
                            except Exception as ex:
                                st.error(f"Failed: {ex}")

                    if job["status"] in ("Pending", "In Progress"):
                        if st.button("✅ Mark Completed", key=f"comp_{job['service_id']}", type="primary", use_container_width=True):
                            try:
                                db.update_service_status(job["service_id"], "Completed", release_vehicle=True)
                                st.success(f"Job #{job['service_id']} marked as Completed!")
                                st.rerun()
                            except Exception as ex:
                                st.error(f"Failed: {ex}")
    else:
        st.success("🎉 No pending or active service requests! All maintenance jobs are up to date.")


# ==============================================================================
# TAB 2: LOG NEW SERVICE (WITH QUICK CUSTOMER REGISTRATION)
# ==============================================================================
with tab_new_service:
    st.subheader("➕ Create Service Ticket")

    # Load customers and vehicles
    try:
        customers_list = db.get_customers()
        vehicles_list = db.get_vehicles()
    except Exception as e:
        customers_list = []
        vehicles_list = []
        st.error(f"Error loading system records: {e}")

    # Customer Selection + Quick New Customer
    st.markdown("#### 1. Customer Information")
    sc_c1, sc_c2 = st.columns([3, 1])

    target_cust_id = st.session_state.get("service_selected_customer_id") or st.session_state.get("latest_customer_id")
    cust_map = {}
    default_c_idx = 0
    for idx, c in enumerate(customers_list):
        lbl = f"{c['name']} (Phone: {c['phone']}) [ID #{c['customer_id']}]"
        cust_map[lbl] = c
        if target_cust_id and c["customer_id"] == target_cust_id:
            default_c_idx = idx

    with sc_c1:
        if customers_list:
            selected_c_lbl = st.selectbox("Select Customer *", list(cust_map.keys()), index=default_c_idx)
            chosen_customer = cust_map[selected_c_lbl]
        else:
            chosen_customer = None
            st.warning("No customers registered yet.")

    with sc_c2:
        st.write("")
        st.write("")
        show_quick_cust_service = st.toggle("➕ New Customer", value=False, key="toggle_serv_cust")

    # Inline Quick Add Customer Form
    if show_quick_cust_service:
        with st.container(border=True):
            st.markdown("##### 👤 Quick Add Customer Profile")
            with st.form("service_quick_add_customer"):
                sn_name = st.text_input("Customer Name *", placeholder="e.g. Vikram Seth")
                sn_phone = st.text_input("10-Digit Phone *", placeholder="e.g. 9811223344")
                sn_email = st.text_input("Email Address", placeholder="e.g. vikram@example.com")
                sn_addr = st.text_input("Address", placeholder="e.g. Hyderabad")

                save_serv_cust = st.form_submit_button("Save & Auto-Select", type="primary")

                if save_serv_cust:
                    if not sn_name.strip():
                        st.error("Customer name is required.")
                    else:
                        try:
                            new_cid = db.add_customer(sn_name, sn_phone, sn_email, sn_addr)
                            st.session_state["service_selected_customer_id"] = new_cid
                            st.session_state["latest_customer_id"] = new_cid
                            st.success(f"Customer '{sn_name.strip()}' added and auto-selected!")
                            st.rerun()
                        except ValueError as ve:
                            st.error(str(ve))
                        except Exception as ex:
                            st.error(f"Error saving customer: {ex}")

    st.divider()

    # Vehicle and Job Details
    st.markdown("#### 2. Vehicle & Work Details")
    if not vehicles_list:
        st.error("No vehicles registered in catalog.")
    elif not chosen_customer:
        st.info("Please select or add a customer above.")
    else:
        v_map = {f"{v['brand']} {v['model']} ({v['vin']}) [Status: {v['status']}]": v for v in vehicles_list}
        selected_v_lbl = st.selectbox("Select Vehicle *", list(v_map.keys()))
        chosen_vehicle = v_map[selected_v_lbl]

        with st.form("log_service_form", clear_on_submit=True):
            f_col1, f_col2 = st.columns(2)
            with f_col1:
                serv_date = st.date_input("Service Date *", value=date.today())
                serv_cost = st.number_input("Estimated / Actual Cost ($) *", min_value=0.0, value=150.0, step=25.0)

            with f_col2:
                serv_status = st.selectbox("Initial Service Status *", SERVICE_STATUSES, index=0)
                mark_under_serv = st.checkbox("Mark vehicle status as 'Under Service'", value=True)

            serv_desc = st.text_area(
                "Maintenance Description / Issues Reported *",
                placeholder="e.g. 10,000 km standard periodic maintenance, engine oil and oil filter change, brake pad inspection.",
            )

            submit_service = st.form_submit_button("Register Service Ticket", type="primary", use_container_width=True)

            if submit_service:
                if not serv_desc.strip():
                    st.error("Please enter a description for the maintenance work.")
                elif serv_cost < 0:
                    st.error("Cost cannot be negative.")
                else:
                    try:
                        new_sid = db.add_service(
                            vehicle_id=chosen_vehicle["vehicle_id"],
                            customer_id=chosen_customer["customer_id"],
                            service_date=serv_date,
                            description=serv_desc,
                            cost=serv_cost,
                            status=serv_status,
                            mark_vehicle_service=mark_under_serv,
                        )
                        st.success(f"Service ticket #{new_sid} created successfully for {chosen_vehicle['brand']} {chosen_vehicle['model']}!")
                        st.session_state.pop("service_selected_customer_id", None)
                    except Exception as ex:
                        st.error(f"Failed to log service ticket: {ex}")


# ==============================================================================
# TAB 3: ALL SERVICE RECORDS & AUDIT
# ==============================================================================
with tab_history:
    st.subheader("📜 All Service Records")

    s_col1, s_col2 = st.columns([1, 2])
    with s_col1:
        hist_status_filter = st.selectbox("Filter by Status", ["All"] + SERVICE_STATUSES)
    with s_col2:
        hist_search = st.text_input("Search Service History", placeholder="Search by customer, phone, vehicle, or description...")

    try:
        all_services = db.get_services(status=hist_status_filter, search=hist_search)
    except Exception as e:
        all_services = []
        st.error(f"Error querying service records: {e}")

    st.write(f"Showing **{len(all_services)}** service ticket(s)")

    if all_services:
        df_all_serv = pd.DataFrame(all_services)
        disp_serv = df_all_serv[
            ["service_id", "service_date", "customer_name", "customer_phone", "brand", "model", "vin", "cost", "status", "description"]
        ].copy()
        disp_serv.columns = ["Ticket ID", "Date", "Customer", "Phone", "Brand", "Model", "VIN", "Cost ($)", "Status", "Description"]

        st.dataframe(disp_serv, use_container_width=True, hide_index=True)

        st.divider()

        # Update specific service record
        st.markdown("#### ✏️ Update Ticket Status or Cost")
        serv_dict = {f"Ticket #{s['service_id']} - {s['brand']} {s['model']} ({s['customer_name']})": s for s in all_services}
        target_ticket_lbl = st.selectbox("Select Ticket to Update:", list(serv_dict.keys()))
        target_ticket = serv_dict[target_ticket_lbl]

        with st.form("update_service_status_form"):
            u_c1, u_c2 = st.columns(2)
            with u_c1:
                cur_status_idx = SERVICE_STATUSES.index(target_ticket["status"]) if target_ticket["status"] in SERVICE_STATUSES else 0
                u_status = st.selectbox("Update Status", SERVICE_STATUSES, index=cur_status_idx)
            with u_c2:
                u_cost = st.number_input("Update Final Cost ($)", min_value=0.0, value=float(target_ticket["cost"]), step=10.0)

            release_box = st.checkbox("Restore vehicle status to 'Available' if completed", value=(u_status == "Completed"))
            update_sub = st.form_submit_button("Update Ticket", type="primary")

            if update_sub:
                try:
                    db.update_service_status(target_ticket["service_id"], u_status, u_cost, release_vehicle=release_box)
                    st.success(f"Ticket #{target_ticket['service_id']} updated successfully!")
                    st.rerun()
                except Exception as ex:
                    st.error(f"Error updating service ticket: {ex}")
    else:
        st.info("No service records found.")

