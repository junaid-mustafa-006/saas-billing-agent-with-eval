import tools
import master_tools

master_tools.reset_db()
print("=== DB STATE TEST: CANCELLABLE DOWNGRADE ===\n")

# TEST 1: Guard Check (Alice has no scheduled downgrade right now)
print("[TEST 1: Refusal on Normal Active Sub]")
res_guard = tools.cancel_scheduled_downgrade(cus_id=1)
print(res_guard)
print("-" * 40)

# TEST 2: Schedule a Downgrade, then Undo it
print("\n[TEST 2: Schedule and Undo]")

# A. Schedule the downgrade (Alice on Pro -> Starter on Day 10)
print("-> Action: Scheduling downgrade...")
tools.downgrade_plan(cus_id=1, new_plan_name='Starter', today='2026-06-25', seats=5)

# B. Call the Undo tool
print("-> Action: Undoing scheduled downgrade...")
res_undo = tools.cancel_scheduled_downgrade(cus_id=1)
print("Result:", res_undo)

# C. Verify DB State
print("\n[DB CHECK] Alice's Subscriptions:")
conn = tools.get_connection()
subs = conn.execute("SELECT sub_id, plan_name, status FROM subscriptions WHERE cus_id = 1").fetchall()
for s in subs: print(dict(s))
# EXPECTED: Only ONE row. sub 1 = active. The scheduled Starter row should be GONE.

print("\n[DB CHECK] Alice's Active Sub ID:")
user = conn.execute("SELECT active_sub_id FROM users WHERE cus_id = 1").fetchone()
print(dict(user))
# EXPECTED: Still points to sub 1.

conn.close()