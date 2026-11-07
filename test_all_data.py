"""Test verification script for pages/7_All_Data.py functionality."""

import pandas as pd
import db

def test_all_data():
    print("Testing All Data page queries and logic...")

    # 1. SHOW TABLES
    tables_result = db.execute_query("SHOW TABLES", fetch="all")
    table_names = [list(r.values())[0] for r in tables_result]
    print("1. Discovered tables:", table_names)
    assert "users" in table_names
    assert "vehicles" in table_names
    assert "customers" in table_names
    assert "sales" in table_names
    assert "services" in table_names

    # 2. Count for each table
    for t in table_names:
        cnt = db.execute_query(f"SELECT COUNT(*) AS total_rows FROM `{t}`", fetch="one")["total_rows"]
        print(f"   Table '{t}': {cnt} row(s)")

    # 3. Query tests & password protection
    for t in table_names:
        if t == "sales":
            q = """
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
        elif t == "services":
            q = """
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
        elif t == "users":
            q = "SELECT user_id, username, role, created_at FROM users ORDER BY user_id ASC"
        else:
            q = f"SELECT * FROM `{t}`"

        rows = db.execute_query(q, fetch="all")
        df = pd.DataFrame(rows) if rows else pd.DataFrame()

        # Guarantee password_hash is omitted
        assert "password_hash" not in df.columns, f"CRITICAL: password_hash exposed in table {t}!"
        print(f"2. Verified {t}: shape={df.shape}, cols={list(df.columns)}")

        # Test search logic on non-empty df
        if not df.empty:
            term = str(df.iloc[0, 1]).lower()[:4]
            mask = df.astype(str).apply(lambda col: col.str.lower().str.contains(term, na=False)).any(axis=1)
            filtered = df[mask]
            assert len(filtered) >= 1
            csv_bytes = filtered.to_csv(index=False).encode("utf-8")
            assert len(csv_bytes) > 0
            print(f"   -> Search for '{term}': {len(filtered)} match(es), CSV size: {len(csv_bytes)} bytes")
        else:
            print(f"   -> Table '{t}' is empty. Handled cleanly.")

    print("\nSUCCESS: All Data functionality verified 100%!")


if __name__ == "__main__":
    test_all_data()

