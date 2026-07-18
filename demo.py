import sqlite3
import tasks
import master_tools
from runner import setup_db_for_task
import agent_gemini;

conn=sqlite3.connect('billing.db')
conn.row_factory=sqlite3.Row
res=conn.execute("SELECT seats_used FROM subscriptions WHERE cus_id=1 AND status='active'").fetchone()
if res:
    print(dict(res))
else:
    print("No active subscription found.")
conn.close()

setup_db_for_task(tasks.t_add_seats_happy, tasks.DB_PATH, tasks.SEED_PATH) 
print(agent_gemini.run_agent(tasks.t_add_seats_happy.prompt, tasks.t_add_seats_happy.cus_id, today=tasks.t_add_seats_happy.today))


conn=sqlite3.connect('billing.db')
conn.row_factory=sqlite3.Row
res=conn.execute("SELECT seats_used FROM subscriptions WHERE cus_id=1 AND status='active'").fetchone()
if res:
    print(dict(res))
else:
    print("No active subscription found.")
conn.close()

master_tools.reset_db()