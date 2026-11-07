"""Vehicles Management Page.

Handles inventory browsing, full-text search, multi-attribute filtering,
and complete CRUD operations (Add, Edit, Delete) with rigorous input validation.
"""

from datetime import datetime
import streamlit as st
import pandas as pd
import db
import ui_common

st.set_page_config(page_title="Vehicles - AutoCore VMS", page_icon="🚙", layout="wide")
ui_common.require_auth()

st.title("🚙 Vehicle Inventory Management")
st.caption("Manage catalog, track stock availability, update pricing, and register new incoming models.")

# Available Select Options
VEHICLE_TYPES = ["Car", "Bike", "Truck", "Bus", "SUV"]
ENGINE_TYPES = ["Petrol", "Diesel", "CNG", "Electric", "Hybrid"]
STATUS_OPTIONS = ["Available", "Sold Out", "Under Service"]
CURRENT_YEAR = datetime.now().year

# Tab layout: Browse & Manage, Add New Vehicle
tab_view, tab_add = st.tabs(["📋 Inventory Catalog", "➕ Add New Vehicle"])

# ==============================================================================
# TAB 1: INVENTORY CATALOG (SEARCH, FILTER, EDIT, DELETE)
# ==============================================================================
with tab_view:
    # Filter Section
    with st.expander("🔍 Search & Filter Filters", expanded=True):
        f_col1, f_col2, f_col3, f_col4 = st.columns(4)
        with f_col1:
            search_query = st.text_input("Search", placeholder="Search VIN, Brand, Model...")
        with f_col2:
            try:
                available_brands = ["All"] + db.get_distinct_brands()
            except Exception:
                available_brands = ["All"]
            filter_brand = st.selectbox("Brand", available_brands)
        with f_col3:
            filter_engine = st.selectbox("Engine Type", ["All"] + ENGINE_TYPES)
        with f_col4:
            filter_type = st.selectbox("Vehicle Type", ["All"] + VEHICLE_TYPES)

        f_col5, f_col6 = st.columns([1, 3])
        with f_col5:
            filter_status = st.selectbox("Status", ["All"] + STATUS_OPTIONS)
        with f_col6:
            price_range = st.slider("Price Range ($)", min_value=0, max_value=200000, value=(0, 200000), step=1000)

    # Fetch Filtered Data
    try:
        vehicles_data = db.get_vehicles(
            search=search_query,
            brand=filter_brand,
            engine_type=filter_engine,
            vehicle_type=filter_type,
            status=filter_status,
            min_price=price_range[0],
            max_price=price_range[1],
        )
    except Exception as e:
        vehicles_data = []
        st.error(f"Failed to query vehicle inventory: {e}")

    st.write(f"Showing **{len(vehicles_data)}** vehicle record(s)")

    if vehicles_data:
        df_display = pd.DataFrame(vehicles_data)
        table_view = df_display[
            ["vehicle_id", "vin", "brand", "model", "year_made", "vehicle_type", "engine_type", "colour", "price", "quantity", "status"]
        ].copy()
        table_view.columns = ["ID", "VIN", "Brand", "Model", "Year", "Type", "Engine", "Colour", "Price ($)", "Stock Qty", "Status"]

        st.dataframe(
            table_view.style.map(
                lambda val: "color: #166534; font-weight: bold;" if val == "Available"
                else "color: #991b1b; font-weight: bold;" if val == "Sold Out"
                else "color: #92400e; font-weight: bold;" if val == "Under Service"
                else "",
                subset=["Status"]
            ),
            use_container_width=True,
            hide_index=True,
        )

        st.divider()

        # Action Selector: Edit or Delete
        act_col1, act_col2 = st.columns([1, 2])
        with act_col1:
            vehicle_options = {f"{v['brand']} {v['model']} ({v['vin']}) [ID: {v['vehicle_id']}]": v for v in vehicles_data}
            selected_label = st.selectbox("Select Vehicle to Edit or Delete:", list(vehicle_options.keys()))
            selected_vehicle = vehicle_options[selected_label]

        with act_col2:
            sub_tab_edit, sub_tab_delete = st.tabs(["✏️ Edit Vehicle", "🗑️ Delete Vehicle"])

            with sub_tab_edit:
                with st.form("edit_vehicle_form"):
                    st.write(f"**Editing Vehicle:** {selected_vehicle['brand']} {selected_vehicle['model']} (`{selected_vehicle['vin']}`)")
                    st.caption("VIN cannot be modified after registration to preserve transaction integrity.")

                    e1, e2 = st.columns(2)
                    with e1:
                        e_brand = st.text_input("Brand *", value=selected_vehicle["brand"])
                        e_model = st.text_input("Model *", value=selected_vehicle["model"])
                        e_year = st.number_input("Year Made *", min_value=1950, max_value=CURRENT_YEAR + 1, value=int(selected_vehicle["year_made"]))
                        e_type = st.selectbox("Vehicle Type *", VEHICLE_TYPES, index=VEHICLE_TYPES.index(selected_vehicle["vehicle_type"]))
                    with e2:
                        e_engine = st.selectbox("Engine Type *", ENGINE_TYPES, index=ENGINE_TYPES.index(selected_vehicle["engine_type"]))
                        e_colour = st.text_input("Colour *", value=selected_vehicle["colour"])
                        e_price = st.number_input("Price ($) *", min_value=1.0, value=float(selected_vehicle["price"]), step=100.0)
                        e_qty = st.number_input("Stock Quantity *", min_value=0, value=int(selected_vehicle["quantity"]), step=1)
                        e_status = st.selectbox("Status *", STATUS_OPTIONS, index=STATUS_OPTIONS.index(selected_vehicle["status"]))

                    edit_submitted = st.form_submit_button("Update Vehicle Details", type="primary")

                    if edit_submitted:
                        if not e_brand.strip() or not e_model.strip() or not e_colour.strip():
                            st.error("Brand, Model, and Colour fields cannot be empty.")
                        else:
                            try:
                                db.update_vehicle(
                                    vehicle_id=selected_vehicle["vehicle_id"],
                                    brand=e_brand,
                                    model=e_model,
                                    year_made=e_year,
                                    vehicle_type=e_type,
                                    engine_type=e_engine,
                                    colour=e_colour,
                                    price=e_price,
                                    quantity=e_qty,
                                    status=e_status,
                                )
                                st.success(f"Vehicle '{e_brand} {e_model}' updated successfully!")
                                st.rerun()
                            except Exception as ex:
                                st.error(f"Update failed: {ex}")

            with sub_tab_delete:
                st.warning(f"Are you sure you want to delete **{selected_vehicle['brand']} {selected_vehicle['model']}** (`{selected_vehicle['vin']}`)?")
                st.write("Vehicles with linked sales or service transactions cannot be deleted to maintain audit history.")
                confirm_delete = st.checkbox("I confirm that I want to permanently delete this vehicle record.")
                if st.button("Permanently Delete Vehicle", type="primary", disabled=not confirm_delete):
                    try:
                        db.delete_vehicle(selected_vehicle["vehicle_id"])
                        st.success("Vehicle deleted successfully from catalog.")
                        st.rerun()
                    except ValueError as ve:
                        st.error(str(ve))
                    except Exception as ex:
                        st.error(f"Delete failed: {ex}")
    else:
        st.info("No vehicles match the selected search criteria.")


# ==============================================================================
# TAB 2: ADD NEW VEHICLE
# ==============================================================================
with tab_add:
    st.subheader("➕ Register New Vehicle to Catalog")
    st.caption("All fields marked with an asterisk (*) are mandatory. VIN must be globally unique.")

    with st.form("add_vehicle_form", clear_on_submit=True):
        col_v1, col_v2 = st.columns(2)

        with col_v1:
            new_vin = st.text_input("Vehicle Identification Number (VIN) *", placeholder="e.g. 1HGCR2F83HA001234").strip().upper()
            new_brand = st.text_input("Brand / Make *", placeholder="e.g. Toyota, Honda, Hyundai, Tata")
            new_model = st.text_input("Model Name *", placeholder="e.g. Camry, Civic, Harrier")
            new_year = st.number_input("Year of Manufacture *", min_value=1950, max_value=CURRENT_YEAR + 1, value=CURRENT_YEAR)
            new_type = st.selectbox("Vehicle Body Type *", VEHICLE_TYPES)

        with col_v2:
            new_engine = st.selectbox("Engine / Powertrain Type *", ENGINE_TYPES)
            new_colour = st.text_input("Exterior Colour *", placeholder="e.g. Midnight Blue, Pearl White")
            new_price = st.number_input("Unit Selling Price ($) *", min_value=1.0, value=25000.0, step=500.0)
            new_qty = st.number_input("Initial Inventory Quantity *", min_value=0, value=1, step=1)
            new_status = st.selectbox("Initial Status *", STATUS_OPTIONS, index=0)

        add_submitted = st.form_submit_button("Register Vehicle", type="primary", use_container_width=True)

        if add_submitted:
            if not new_vin:
                st.error("VIN cannot be empty.")
            elif not new_brand.strip():
                st.error("Brand name is required.")
            elif not new_model.strip():
                st.error("Model name is required.")
            elif not new_colour.strip():
                st.error("Colour is required.")
            elif new_price <= 0:
                st.error("Price must be strictly positive (greater than 0).")
            elif new_qty < 0:
                st.error("Quantity cannot be negative.")
            else:
                try:
                    new_vid = db.add_vehicle(
                        vin=new_vin,
                        brand=new_brand,
                        model=new_model,
                        year_made=new_year,
                        vehicle_type=new_type,
                        engine_type=new_engine,
                        colour=new_colour,
                        price=new_price,
                        quantity=new_qty,
                        status=new_status,
                    )
                    st.success(f"Vehicle '{new_brand} {new_model}' (VIN: {new_vin}) registered successfully with ID #{new_vid}!")
                except ValueError as ve:
                    st.error(str(ve))
                except Exception as ex:
                    st.error(f"Error registering vehicle: {ex}")

