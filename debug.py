import json
import sqlite3

def check_mismatch(gt_file, db_table):
    with open(gt_file, 'r') as f:
        gt = json.load(f)
    
    conn = sqlite3.connect('billing.db')
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(f"SELECT * FROM {db_table} WHERE cus_id=1")
    actuals = [dict(r) for r in cur.fetchall()]
    
    print(f"--- Mismatch Analysis for {gt_file} ---")
    print("Expected (GT):", gt[db_table])
    print("Actual (DB):", actuals)

check_mismatch('ground_truths/downgrade_02.json', 'subscriptions')
check_mismatch('ground_truths/chain_01.json', 'transactions')