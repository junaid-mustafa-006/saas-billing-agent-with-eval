import sqlite3
import os

def reset_db(db_path="billing.db"):
    if os.path.exists(db_path):
        os.remove(db_path)
        
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    cursor = conn.cursor()
    
    conn.executescript("""
        DROP TABLE IF EXISTS transactions;
        DROP TABLE IF EXISTS subscriptions;
        DROP TABLE IF EXISTS payment_methods;
        DROP TABLE IF EXISTS catalog;
        DROP TABLE IF EXISTS users;
    """)

    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            cus_id INTEGER PRIMARY KEY,
            name TEXT,
            email TEXT,
            phone TEXT,
            active_sub_id INTEGER
        );

        CREATE TABLE IF NOT EXISTS payment_methods (
            pay_id INTEGER PRIMARY KEY,
            cus_id INTEGER,
            type TEXT,
            status TEXT,
            FOREIGN KEY(cus_id) REFERENCES users(cus_id)
        );

        CREATE TABLE IF NOT EXISTS catalog (
            plan_name TEXT PRIMARY KEY,
            price_per_seat REAL,
            seat_cap INTEGER,
            duration_days INTEGER
        );

        CREATE TABLE IF NOT EXISTS subscriptions (
            sub_id INTEGER PRIMARY KEY,
            cus_id INTEGER,
            plan_name TEXT,
            seats_used INTEGER,
            start_date TEXT,
            end_date TEXT,
            status TEXT,
            autopay INTEGER,
            FOREIGN KEY(cus_id) REFERENCES users(cus_id),
            FOREIGN KEY(plan_name) REFERENCES catalog(plan_name)
        );

        CREATE TABLE IF NOT EXISTS transactions (
            trans_id INTEGER PRIMARY KEY,
            cus_id INTEGER,
            sub_id INTEGER,
            amount_paid REAL,
            payment_date TEXT,
            type TEXT,
            FOREIGN KEY(cus_id) REFERENCES users(cus_id),
            FOREIGN KEY(sub_id) REFERENCES subscriptions(sub_id)
        );
    """)

    cursor.executescript("""
        INSERT OR IGNORE INTO catalog (plan_name, price_per_seat, seat_cap, duration_days) VALUES 
        ('Starter', 10.0, 5, 30),
        ('Pro', 25.0, 20, 30),
        ('Enterprise', 50.0, 100, 30);
    """)

    cursor.executescript("""
        INSERT OR IGNORE INTO users (cus_id, name, email, phone, active_sub_id) 
        VALUES (1, 'Alice', 'alice@example.com', '555-0101', NULL);
        
        INSERT OR IGNORE INTO payment_methods (pay_id, cus_id, type, status) 
        VALUES (1, 1, 'card', 'valid');
        
        INSERT OR IGNORE INTO subscriptions (sub_id, cus_id, plan_name, seats_used, start_date, end_date, status, autopay) 
        VALUES (1, 1, 'Pro', 10, '2026-06-15', '2026-07-15', 'active', 1);
        
        UPDATE users SET active_sub_id = 1 WHERE cus_id = 1;
        
        INSERT OR IGNORE INTO transactions (trans_id, cus_id, sub_id, amount_paid, payment_date, type) 
        VALUES (1, 1, 1, 250.0, '2026-06-15', 'new');
    """)

    cursor.executescript("""
        INSERT OR IGNORE INTO users (cus_id, name, email, phone, active_sub_id) 
        VALUES (2, 'Bob', 'bob@example.com', '555-0102', NULL);
        
        INSERT OR IGNORE INTO payment_methods (pay_id, cus_id, type, status) 
        VALUES (2, 2, 'upi', 'valid');
        
        INSERT OR IGNORE INTO subscriptions (sub_id, cus_id, plan_name, seats_used, start_date, end_date, status, autopay) 
        VALUES (2, 2, 'Starter', 2, '2026-06-02', '2026-07-02', 'active', 1);
        
        UPDATE users SET active_sub_id = 2 WHERE cus_id = 2;
        
        INSERT OR IGNORE INTO transactions (trans_id, cus_id, sub_id, amount_paid, payment_date, type) 
        VALUES (2, 2, 2, 20.0, '2026-06-02', 'new');
    """)

    cursor.executescript("""
        INSERT OR IGNORE INTO users (cus_id, name, email, phone, active_sub_id) 
        VALUES (3, 'Carl', 'carl@example.com', '555-0103', NULL);
        
        INSERT OR IGNORE INTO payment_methods (pay_id, cus_id, type, status) 
        VALUES (3, 3, 'card', 'expired');
        
        INSERT OR IGNORE INTO subscriptions (sub_id, cus_id, plan_name, seats_used, start_date, end_date, status, autopay) 
        VALUES (3, 3, 'Enterprise', 50, '2026-04-01', '2026-05-01', 'cancelled', 0);
        
        INSERT OR IGNORE INTO transactions (trans_id, cus_id, sub_id, amount_paid, payment_date, type) 
        VALUES (3, 3, 3, 2500.0, '2026-04-01', 'new');
    """)

    conn.commit()
    conn.close()