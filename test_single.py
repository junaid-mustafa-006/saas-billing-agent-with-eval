import tasks
from runner import setup_db_for_task
import agent_gemini

# Find cancel_04 from the list
task = next(t for t in tasks.ALL_TASKS if t.id == "cancel_04")

print(f"Testing isolated run for: {task.id}")
setup_db_for_task(task, tasks.DB_PATH, tasks.SEED_PATH)

response_text, tool_log = agent_gemini.run_agent(task.prompt, task.cus_id, today=task.today)
print("\n--- Tool Log ---")
for name, res in tool_log:
    print(f"Tool: {name} | Result: {res}")

print("\n--- Agent Response ---")
print(response_text)