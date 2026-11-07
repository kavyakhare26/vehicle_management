"""Customer Management Page.

Handles customer registry, search by name or mobile, 10-digit phone validation,
duplicate prevention, profile editing, and safe deletion.
"""

import streamlit as st
import pandas as pd
import db
import ui_common

st.set_page_config(page_title="Customers - AutoCore VMS", page_icon="👥", layout="wide")
ui_common.require_auth()

st.title("👥 Customer Management")
st.caption("Manage client profiles, contact information, and track customer relationships.")

tab_view, tab_add = st.tabs(["📋 Customer Directory", "➕ Add New Customer"])

# ==============================================================================
# TAB 1: CUSTOMER DIRECTORY (SEARCH, EDIT, DELETE)
# ==============================================================================
with tab_view:
    search_query = st.text_input("🔍 Search Customers", placeholder="Search by customer name or 10-digit phone number...")

    try:
        customers_list = db.get_customers(search=search_query)
    except Exception as e:
        customers_list = []
        st.error(f"Error loading customers: {e}")

    st.write(f"Showing **{len(customers_list)}** customer(s)")

    if customers_list:
        df_cust = pd.DataFrame(customers_list)
        display_cols = ["customer_id", "name", "phone", "email", "address", "created_at"]
        clean_df = df_cust[display_cols].copy()
        clean_df.columns = ["Customer ID", "Full Name", "Phone", "Email", "Address", "Registered On"]

        st.dataframe(clean_df, use_container_width=True, hide_index=True)

        st.divider()

        # Action: Edit or Delete
        c_act1, c_act2 = st.columns([1, 2])
        with c_act1:
            customer_dict = {f"{c['name']} ({c['phone']}) [ID: {c['customer_id']}]": c for c in customers_list}
            selected_label = st.selectbox("Select Customer to Manage:", list(customer_dict.keys()))
            selected_customer = customer_dict[selected_label]

        with c_act2:
            sub_edit, sub_delete = st.tabs(["✏️ Edit Customer Profile", "🗑️ Delete Customer"])

            with sub_edit:
                with st.form("edit_customer_form"):
                    st.write(f"**Editing Profile:** {selected_customer['name']}")

                    e_name = st.text_input("Full Name *", value=selected_customer["name"])
                    e_phone = st.text_input("10-Digit Mobile Number *", value=selected_customer["phone"])
                    e_email = st.text_input("Email Address", value=selected_customer["email"] or "")
                    e_address = st.text_area("Address", value=selected_customer["address"] or "")

                    edit_btn = st.form_submit_button("Save Customer Changes", type="primary")

                    if edit_btn:
                        if not e_name.strip():
                            st.error("Name is required.")
                        else:
                            try:
                                db.update_customer(
                                    customer_id=selected_customer["customer_id"],
                                    name=e_name,
                                    phone=e_phone,
                                    email=e_email,
                                    address=e_address,
                                )
                                st.success("Customer profile updated successfully!")
                                st.rerun()
                            except ValueError as ve:
                                st.error(str(ve))
                            except Exception as ex:
                                st.error(f"Failed to update customer: {ex}")

            with sub_delete:
                st.warning(f"Are you sure you want to delete **{selected_customer['name']}** (Phone: `{selected_customer['phone']}`)?")
                st.write("Customers with past sales or service records cannot be deleted.")
                confirm_del = st.checkbox("I confirm that I want to delete this customer record.")
                if st.button("Delete Customer Record", type="primary", disabled=not confirm_del):
                    try:
                        db.delete_customer(selected_customer["customer_id"])
                        st.success("Customer record deleted successfully.")
                        st.rerun()
                    except ValueError as ve:
                        st.error(str(ve))
                    except Exception as ex:
                        st.error(f"Delete failed: {ex}")
    else:
        st.info("No customers found. Click 'Add New Customer' tab to register one.")


# ==============================================================================
# TAB 2: ADD NEW CUSTOMER
# ==============================================================================
with tab_add:
    st.subheader("➕ Register New Customer")
    st.caption("Mobile number must be a valid 10-digit number and unique in the database.")

    with st.form("add_customer_form", clear_on_submit=True):
        col_c1, col_c2 = st.columns(2)
        with col_c1:
            new_name = st.text_input("Full Name *", placeholder="e.g. Ramesh Kumar")
            new_phone = st.text_input("10-Digit Mobile Number *", placeholder="e.g. 9876543210")

        with col_c2:
            new_email = st.text_input("Email Address", placeholder="e.g. ramesh@example.com")
            new_address = st.text_area("Physical / Mailing Address", placeholder="e.g. 45 Green Park, New Delhi")

        add_cust_btn = st.form_submit_button("Create Customer Profile", type="primary", use_container_width=True)

        if add_cust_btn:
            if not new_name.strip():
                st.error("Customer name cannot be empty.")
            else:
                try:
                    new_cid = db.add_customer(
                        name=new_name,
                        phone=new_phone,
                        email=new_email,
                        address=new_address,
                    )
                    st.success(f"Customer '{new_name.strip()}' registered successfully! (Customer ID: #{new_cid})")
                    # Set session state so other pages can detect
                    st.session_state["latest_customer_id"] = new_cid
                    st.session_state["latest_customer_name"] = new_name.strip()
                except ValueError as ve:
                    st.error(str(ve))
                except Exception as ex:
                    st.error(f"Failed to register customer: {ex}")

