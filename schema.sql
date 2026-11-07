-- Vehicle Management System Database Schema
-- Database: vehicle_mgmt

CREATE DATABASE IF NOT EXISTS vehicle_mgmt;
USE vehicle_mgmt;

-- 1. Users Table
CREATE TABLE IF NOT EXISTS users (
    user_id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role ENUM('admin', 'staff') NOT NULL DEFAULT 'staff',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 2. Vehicles Table
CREATE TABLE IF NOT EXISTS vehicles (
    vehicle_id INT AUTO_INCREMENT PRIMARY KEY,
    vin VARCHAR(50) NOT NULL UNIQUE,
    brand VARCHAR(50) NOT NULL,
    model VARCHAR(50) NOT NULL,
    year_made INT NOT NULL,
    vehicle_type ENUM('Car', 'Bike', 'Truck', 'Bus', 'SUV') NOT NULL,
    engine_type ENUM('Petrol', 'Diesel', 'CNG', 'Electric', 'Hybrid') NOT NULL,
    colour VARCHAR(30) NOT NULL,
    price DECIMAL(12, 2) NOT NULL CHECK (price > 0),
    quantity INT NOT NULL CHECK (quantity >= 0),
    status ENUM('Available', 'Sold Out', 'Under Service') NOT NULL DEFAULT 'Available',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 3. Customers Table
CREATE TABLE IF NOT EXISTS customers (
    customer_id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    phone VARCHAR(15) NOT NULL UNIQUE,
    email VARCHAR(100) NULL,
    address TEXT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 4. Sales Table
CREATE TABLE IF NOT EXISTS sales (
    sale_id INT AUTO_INCREMENT PRIMARY KEY,
    customer_id INT NOT NULL,
    vehicle_id INT NOT NULL,
    sale_date DATE NOT NULL,
    quantity INT NOT NULL CHECK (quantity > 0),
    total_price DECIMAL(12, 2) NOT NULL,
    payment_mode ENUM('Cash', 'UPI', 'Card', 'Loan') NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_sales_customer FOREIGN KEY (customer_id) REFERENCES customers(customer_id) ON DELETE RESTRICT,
    CONSTRAINT fk_sales_vehicle FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 5. Services Table
CREATE TABLE IF NOT EXISTS services (
    service_id INT AUTO_INCREMENT PRIMARY KEY,
    vehicle_id INT NOT NULL,
    customer_id INT NOT NULL,
    service_date DATE NOT NULL,
    description TEXT NOT NULL,
    cost DECIMAL(10, 2) NOT NULL DEFAULT 0.00,
    status ENUM('Pending', 'In Progress', 'Completed') NOT NULL DEFAULT 'Pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_services_vehicle FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id) ON DELETE RESTRICT,
    CONSTRAINT fk_services_customer FOREIGN KEY (customer_id) REFERENCES customers(customer_id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- SAMPLE SEED DATA
-- Default Admin User (Password: admin123) and Staff User (Password: staff123)
INSERT INTO users (username, password_hash, role)
VALUES 
    ('admin', '$2b$12$Fk9q5xu4vUq6Z8VsT8IrN.iS/0npJr0iitMD6nNy2MTBl3A1eQN3K', 'admin'),
    ('staff', '$2b$12$cBrFAV5Hp1oT7lm7RAqsvORwilZjYdhMAjn4.FXKmnitJKuqVj77a', 'staff')
ON DUPLICATE KEY UPDATE role = VALUES(role);

-- Sample Vehicles (3 vehicles with distinct types and stock)
INSERT INTO vehicles (vin, brand, model, year_made, vehicle_type, engine_type, colour, price, quantity, status)
VALUES
    ('1HGCR2F83HA001234', 'Honda', 'Civic Sedan', 2024, 'Car', 'Petrol', 'Crystal Black', 28500.00, 5, 'Available'),
    ('5NMS3CAD1LH556789', 'Hyundai', 'Tucson AWD', 2023, 'SUV', 'Hybrid', 'Polar White', 34000.00, 2, 'Available'),
    ('1FTFW1ED4NFC99881', 'Tata', 'Nexon EV Max', 2024, 'SUV', 'Electric', 'Teal Blue', 22000.00, 4, 'Available')
ON DUPLICATE KEY UPDATE quantity = VALUES(quantity);

-- Sample Customer (1 customer)
INSERT INTO customers (name, phone, email, address)
VALUES
    ('Rahul Sharma', '9876543210', 'rahul.sharma@example.com', '124 MG Road, Indiranagar, Bengaluru, Karnataka')
ON DUPLICATE KEY UPDATE name = VALUES(name);

