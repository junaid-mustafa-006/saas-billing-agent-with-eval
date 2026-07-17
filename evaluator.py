import sqlite3
from collections import Counter

def evaluate_task(actual_db_path, ground_truth, seed_db_path=None):
    conn = sqlite3.connect(actual_db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    try:
        if "unchanged_tables" in ground_truth:
            if not seed_db_path:
                raise ValueError("seed_db_path required")
            seed_conn = sqlite3.connect(seed_db_path)
            seed_conn.row_factory = sqlite3.Row
            try:
                for table in ground_truth["unchanged_tables"]:
                    cur.execute(f"SELECT * FROM {table}")
                    actual = [tuple(r) for r in cur.fetchall()]
                    seed_cur = seed_conn.cursor()
                    seed_cur.execute(f"SELECT * FROM {table}")
                    expected = [tuple(r) for r in seed_cur.fetchall()]
                    if Counter(actual) != Counter(expected):
                        return False, f"Mismatch in unchanged table: {table}"
            finally:
                seed_conn.close()
            
        cur.execute("SELECT u.cus_id, u.name, u.email, u.phone, s.plan_name, s.start_date, s.end_date FROM users u LEFT JOIN subscriptions s ON u.active_sub_id=s.sub_id")
        actual_users = Counter([(r['cus_id'], r['name'], r['email'], r['phone'], r['plan_name'], r['start_date'], r['end_date']) for r in cur.fetchall()])
        expected_users = Counter()
        
        for u in ground_truth["users"]:
            plan = u["active_sub_content"]["plan_name"] if u.get("active_sub_content") else None
            start = u["active_sub_content"]["start_date"] if u.get("active_sub_content") else None
            end = u["active_sub_content"]["end_date"] if u.get("active_sub_content") else None
            expected_users.update([(u['cus_id'], u['name'], u['email'], u['phone'], plan, start, end)])
            
        if actual_users != expected_users:
            return False, "Mismatch in users table"
            
        cur.execute("SELECT plan_name, seats_used, start_date, end_date, status, autopay FROM subscriptions")
        actual_subs = Counter([tuple(r) for r in cur.fetchall()])
        expected_subs = Counter([(s['plan_name'], s['seats_used'], s['start_date'], s['end_date'], s['status'], s['autopay']) for s in ground_truth["subscriptions"]])
        
        if actual_subs != expected_subs:
            return False, "Mismatch in subscriptions table"
            
        cur.execute("SELECT t.type, t.amount_paid, t.payment_date, s.plan_name, s.start_date, s.end_date FROM transactions t LEFT JOIN subscriptions s ON t.sub_id=s.sub_id")
        actual_txs = Counter([(r['type'], round(float(r['amount_paid']), 2), r['payment_date'], r['plan_name'], r['start_date'], r['end_date']) for r in cur.fetchall()])
        expected_txs = Counter([(t['type'], round(float(t['amount_paid']), 2), t['payment_date'], t['linked_sub']['plan_name'], t['linked_sub']['start_date'], t['linked_sub']['end_date']) for t in ground_truth["transactions"]])
        
        if actual_txs != expected_txs:
            return False, "Mismatch in transactions table"
            
        return True, "Pass"
        
    finally:
        # This is the magic line that stops the Windows crash
        conn.close()