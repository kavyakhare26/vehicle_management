"""Automated End-to-End Test Suite for Vehicle Management System.

Tests all CRUD operations, input validations, transaction atomicity,
bcrypt authentication, and reporting helpers.
"""

from datetime import date
import db


def run_tests():
    print("==================================================")
    print("STARTING COMPLETE END-TO-END AUTOMATED TEST SUITE")
    print("==================================================")

    # 1. Test Database Initialization & Connection
    print("\n[TEST 1] Testing Database Connection & Initialization...")
    init_ok, init_msg = db.init_database()
    assert init_ok, f"Init failed: {init_msg}"
    conn_ok, conn_msg = db.test_db_connection()
    assert conn_ok, f"Connection failed: {conn_msg}"
    print("  -> PASSED: Database connected and seeded.")

    # 2. Test Bcrypt Authentication
    print("\n[TEST 2] Testing Bcrypt Authentication...")
    admin_user = db.authenticate_user("admin", "admin123")
    assert admin_user is not None, "Admin authentication failed!"
    assert admin_user["role"] == "admin"
    print("  -> Admin authenticated successfully:", admin_user)

    staff_user = db.authenticate_user("staff", "staff123")
    assert staff_user is not None, "Staff authentication failed!"
    assert staff_user["role"] == "staff"
    print("  -> Staff authenticated successfully:", staff_user)

    invalid_auth = db.authenticate_user("admin", "wrong_password_999")
    assert invalid_auth is None, "Invalid password was unexpectedly accepted!"
    print("  -> PASSED: Invalid credentials correctly rejected.")

    # 3. Test Customer Validation & Duplicate Phone Prevention
    print("\n[TEST 3] Testing Customer 10-Digit Validation & Duplicate Checks...")
    # Invalid phone test
    try:
        db.add_customer("Invalid Phone User", "12345", "test@test.com")
        assert False, "Should have rejected 5-digit phone number!"
    except ValueError as ve:
        print("  -> Correctly rejected short phone:", ve)

    # Valid customer addition
    test_phone = "9988776655"
    # Clean up if existed from previous run
    existing_c = db.get_customer_by_phone(test_phone)
    if existing_c:
        db.execute_query("DELETE FROM customers WHERE phone = %s", (test_phone,))

    cust_id = db.add_customer("Amit Verma", test_phone, "amit@example.com", "Sector 18, Noida")
    assert cust_id > 0, "Customer addition returned invalid ID"
    print(f"  -> Added customer #{cust_id} successfully.")

    # Duplicate phone test
    try:
        db.add_customer("Duplicate Amit", test_phone, "dup@example.com")
        assert False, "Should have rejected duplicate phone number!"
    except ValueError as ve:
        print("  -> Correctly rejected duplicate phone:", ve)

    # 4. Test Vehicle Validation & Duplicate VIN Check
    print("\n[TEST 4] Testing Vehicle Validation & Unique VIN Check...")
    test_vin = "TESTVIN99990001A"
    existing_v = db.get_vehicle_by_vin(test_vin)
    if existing_v:
        db.execute_query("DELETE FROM vehicles WHERE vin = %s", (test_vin,))

    veh_id = db.add_vehicle(
        vin=test_vin,
        brand="Mahindra",
        model="XUV700",
        year_made=2024,
        vehicle_type="SUV",
        engine_type="Diesel",
        colour="Midnight Black",
        price=27000.0,
        quantity=2,
        status="Available",
    )
    assert veh_id > 0
    print(f"  -> Registered vehicle #{veh_id} ({test_vin}).")

    # Duplicate VIN test
    try:
        db.add_vehicle(
            vin=test_vin,
            brand="Mahindra",
            model="XUV700 Clone",
            year_made=2024,
            vehicle_type="SUV",
            engine_type="Diesel",
            colour="Red",
            price=27000.0,
            quantity=1,
        )
        assert False, "Should have rejected duplicate VIN!"
    except ValueError as ve:
        print("  -> Correctly rejected duplicate VIN:", ve)

    # 5. Test KPI Metrics & Low Stock Alert
    print("\n[TEST 5] Testing KPI Metrics & Low Stock Detection...")
    kpis = db.get_dashboard_kpis()
    assert kpis["total_stock"] > 0
    assert kpis["total_customers"] > 0
    print("  -> Live KPI indicators:", kpis)

    low_stock = db.get_low_stock_vehicles()
    assert len(low_stock) > 0, "Expected low stock vehicles (Mahindra has qty=2, Hyundai has qty=2)"
    print(f"  -> Found {len(low_stock)} low stock vehicle(s) (< 3 units). Correct.")

    # 6. Test Atomic Sale Transaction & Inventory Decrement
    print("\n[TEST 6] Testing Atomic Sale Transaction & Auto 'Sold Out' Logic...")
    # Attempt to buy 10 units when only 2 are available (Must fail & rollback)
    try:
        db.execute_sale_transaction(
            customer_id=cust_id,
            vehicle_id=veh_id,
            sale_date=date.today(),
            quantity=10,
            payment_mode="Cash",
        )
        assert False, "Should have failed due to insufficient stock!"
    except ValueError as ve:
        print("  -> Over-order correctly blocked:", ve)

    # Verify stock was untouched after rollback
    veh_check = db.get_vehicle_by_id(veh_id)
    assert veh_check["quantity"] == 2, f"Stock changed unexpectedly to {veh_check['quantity']}"

    # Now execute valid sale of 2 units (Entire remaining stock)
    sale_res = db.execute_sale_transaction(
        customer_id=cust_id,
        vehicle_id=veh_id,
        sale_date=date.today(),
        quantity=2,
        payment_mode="UPI",
    )
    assert sale_res["sale_id"] > 0
    assert sale_res["remaining_qty"] == 0
    print(f"  -> Completed sale #{sale_res['sale_id']}. Total: ${sale_res['total_price']:,.2f}")

    # Check that status automatically became 'Sold Out'
    veh_sold = db.get_vehicle_by_id(veh_id)
    assert veh_sold["quantity"] == 0, "Quantity should be 0"
    assert veh_sold["status"] == "Sold Out", f"Status should be 'Sold Out', but got '{veh_sold['status']}'"
    print("  -> PASSED: Vehicle stock is 0 and status is automatically 'Sold Out'.")

    # 7. Test Service Logging & Status Progression
    print("\n[TEST 7] Testing Service Logging & Status Update...")
    service_id = db.add_service(
        vehicle_id=veh_id,
        customer_id=cust_id,
        service_date=date.today(),
        description="First 1,000 km general inspection and wheel alignment",
        cost=180.0,
        status="Pending",
        mark_vehicle_service=True,
    )
    assert service_id > 0
    print(f"  -> Logged service ticket #{service_id}.")

    # Verify pending queue includes it
    pending = db.get_pending_services()
    assert any(p["service_id"] == service_id for p in pending), "New service not in pending list!"
    print("  -> Pending queue verified.")

    # Advance to In Progress then Completed
    db.update_service_status(service_id, "In Progress")
    serv_up = db.get_services(status="In Progress")
    assert any(s["service_id"] == service_id for s in serv_up)

    db.update_service_status(service_id, "Completed", new_cost=195.0, release_vehicle=True)
    print("  -> Service ticket updated to Completed with final cost $195.00.")

    # 8. Test Reports & Analytics Functions
    print("\n[TEST 8] Testing Reporting & Aggregation Queries...")
    rep = db.get_reports_summary(date(2020, 1, 1), date.today())
    assert rep["total_transactions"] >= 1
    assert rep["total_units_sold"] >= 2
    assert rep["total_revenue"] > 0
    print("  -> Reports summary retrieved successfully:", rep)

    monthly_df = db.get_sales_by_month_data()
    assert not monthly_df.empty
    print("  -> Monthly sales trend compiled:\n", monthly_df)

    # Clean up test records
    print("\n[CLEANUP] Removing test vehicle, customer, sales, services...")
    db.execute_query("DELETE FROM services WHERE service_id = %s", (service_id,))
    db.execute_query("DELETE FROM sales WHERE sale_id = %s", (sale_res["sale_id"],))
    db.execute_query("DELETE FROM vehicles WHERE vehicle_id = %s", (veh_id,))
    db.execute_query("DELETE FROM customers WHERE customer_id = %s", (cust_id,))
    print("  -> Cleaned up temporary test rows.")

    print("\n==================================================")
    print("ALL TESTS PASSED WITH 100% SUCCESS!")
    print("==================================================")


if __name__ == "__main__":
    run_tests()

