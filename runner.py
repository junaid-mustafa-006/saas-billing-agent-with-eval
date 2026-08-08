import json
import sqlite3
import shutil
import os
import master_tools
import time
from evaluator import evaluate_task

class Task:
    def __init__(self, id, prompt, seed_sql, correct_sequence, ground_truth_file, expect_success=True, cus_id=1, today="2026-06-20", expected_refusal=None):
        self.id = id
        self.prompt = prompt
        self.seed_sql = seed_sql
        self.correct_sequence = correct_sequence
        self.ground_truth_file = ground_truth_file
        self.expect_success = expect_success
        self.cus_id = cus_id
        self.today = today
        self.expected_refusal = expected_refusal

def setup_db_for_task(task, db_path, seed_db_path):
    master_tools.reset_db(db_path)
    if task.seed_sql:
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA foreign_keys=ON")
        conn.executescript(task.seed_sql)
        conn.commit()
        conn.close()
    shutil.copy(db_path, seed_db_path)

def generate_and_freeze_ground_truth(task, db_path, seed_db_path):
    setup_db_for_task(task, db_path, seed_db_path)
    results = task.correct_sequence(task.today)
    for res in results:
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

WRITE_TOOLS = {"add_seats", "cancel_subscription", "downgrade_plan", "upgrade_plan", "cancel_scheduled_downgrade"}

def run_suite(tasks, db_path, seed_db_path, agent_mode=False, backend="anthropic"):
    if agent_mode:
        if backend == "anthropic":
            import agent_claude as agent
        elif backend == "gemini":
            import agent_gemini as agent
        else:
            raise ValueError(f"Unknown backend requested: {backend}")

    passed = 0
    for t in tasks:
        setup_db_for_task(t, db_path, seed_db_path)
        
        try:
            response_text = ""
            tool_log = []
            
            if agent_mode:
                try:
                    response_text, tool_log = agent.run_agent(t.prompt, t.cus_id, today=t.today)
                except Exception as e:
                    print(f"Task {t.id}: FAIL - API/Network Error: {str(e)}")
                    continue
                    
                # THREE-WAY EVALUATION GATE (Agent Mode)
                wrote_to_db = any(
                    name in WRITE_TOOLS and res is not None and res.get("success") is True
                    for name, res in tool_log
                )
                attempted_write = any(
                    name in WRITE_TOOLS and res is not None
                    for name, res in tool_log
                )

                if not attempted_write:
                    # Case 3: Never attempted a write
                    print(f"Task {t.id}: FAIL - Agent failed to attempt any required write-tool action.")
                    continue

                if not wrote_to_db and not t.expect_success:
                    # Case 2: Attempted write, but cleanly refused (Policy check with targeted reason matching)
                    refusal_reasons = [
                        res.get("reason", "") for name, res in tool_log
                        if name in WRITE_TOOLS and res is not None and res.get("success") is False
                    ]
                    
                    if not refusal_reasons:
                        print(f"Task {t.id}: FAIL - Expected refusal but found no structured failure reason.")
                        continue
                    
                    # If an expected refusal keyword was defined, validate it matches
                    if t.expected_refusal:
                        matched = any(t.expected_refusal.lower() in reason.lower() for reason in refusal_reasons)
                        if matched:
                            passed += 1
                            print(f"Task {t.id}: PASS (Resfulal Reason Matched: '{t.expected_refusal}')")
                            continue
                        else:
                            print(f"Task {t.id}: FAIL - Refused, but reason(s) {refusal_reasons} did not match expected pattern '{t.expected_refusal}'.")
                            continue
                    else:
                        # Fallback if no specific keyword string was provided
                        passed += 1
                        print(f"Task {t.id}: PASS (Refusal Handled Correctly)")
                        continue

            else:
                # Baseline Mode: direct execution of ground truth sequence
                t.correct_sequence(t.today)

            # Case 1: Standard DB Write Execution (or Baseline non-agent execution)
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
                if agent_mode:
                    print(f"Task {t.id}: FAIL - {reason}\nAgent Response: {response_text}")
                else:
                    print(f"Task {t.id}: FAIL - {reason}")
                    
        finally:
            if agent_mode:
                time.sleep(2)
                
    print(f"\nFinal Score: {passed}/{len(tasks)}")