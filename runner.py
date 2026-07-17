import json
import sqlite3
import shutil
import os
import master_tools
from evaluator import evaluate_task

class Task:
    # Notice expect_success=True is added right here
    def __init__(self, id, prompt, seed_sql, correct_sequence, ground_truth_file, expect_success=True):
        self.id = id
        self.prompt = prompt
        self.seed_sql = seed_sql
        self.correct_sequence = correct_sequence 
        self.ground_truth_file = ground_truth_file
        self.expect_success = expect_success

def setup_db_for_task(task, db_path, seed_db_path):
    master_tools.reset_db(db_path)
    
    if task.seed_sql:
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(task.seed_sql)
        conn.commit()
        conn.close()
        
    shutil.copy(db_path, seed_db_path)

def generate_and_freeze_ground_truth(task, db_path, seed_db_path):
    setup_db_for_task(task, db_path, seed_db_path)
    
    results = task.correct_sequence()
    for res in results:
        # This handles the refusal logic
        if task.expect_success and not res.get("success"):
            raise RuntimeError(f"Tool failed unexpectedly during GT generation for Task {task.id}: {res}")
        elif not task.expect_success and res.get("success"):
            raise RuntimeError(f"Tool succeeded unexpectedly during GT generation for Refusal Task {task.id}: {res}")
            
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    gt = {"unchanged_tables": ["catalog", "payment_methods"], "users": [], "subscriptions": [], "transactions": []}
    
    cur.execute("SELECT u.cus_id, u.name, u.email, u.phone, s.plan_name, s.start_date, s.end_date FROM users u LEFT JOIN subscriptions s ON u.active_sub_id = s.sub_id")
    for r in cur.fetchall():
        u_dict = {"cus_id": r["cus_id"], "name": r["name"], "email": r["email"], "phone": r["phone"]}
        if r["plan_name"]:
            u_dict["active_sub_content"] = {"plan_name": r["plan_name"], "start_date": r["start_date"], "end_date": r["end_date"]}
        gt["users"].append(u_dict)
        
    cur.execute("SELECT plan_name, seats_used, start_date, end_date, status, autopay FROM subscriptions")
    gt["subscriptions"] = [dict(r) for r in cur.fetchall()]
    
    cur.execute("SELECT t.type, t.amount_paid, t.payment_date, s.plan_name, s.start_date, s.end_date FROM transactions t LEFT JOIN subscriptions s ON t.sub_id = s.sub_id")
    for r in cur.fetchall():
        gt["transactions"].append({
            "type": r["type"], 
            "amount_paid": round(float(r["amount_paid"]), 2), 
            "payment_date": r["payment_date"], 
            "linked_sub": {"plan_name": r["plan_name"], "start_date": r["start_date"], "end_date": r["end_date"]}
        })
    conn.close()
    
    os.makedirs(os.path.dirname(task.ground_truth_file), exist_ok=True)
    with open(task.ground_truth_file, 'w') as f:
        json.dump(gt, f, indent=2)
    print(f"Ground truth frozen for Task {task.id} at {task.ground_truth_file}")

def run_suite(tasks, db_path, seed_db_path):
    passed = 0
    for t in tasks:
        setup_db_for_task(t, db_path, seed_db_path)
        
        t.correct_sequence()
        
        try:
            with open(t.ground_truth_file, 'r') as f:
                ground_truth = json.load(f)
        except FileNotFoundError:
            print(f"Task {t.id}: FAIL - Ground truth JSON not found. Run generator first.")
            continue
            
        ok, reason = evaluate_task(db_path, ground_truth, seed_db_path)
        
        if ok:
            passed += 1
            print(f"Task {t.id}: PASS")
        else:
            print(f"Task {t.id}: FAIL - {reason}")
            
    print(f"\nFinal Score: {passed}/{len(tasks)}")