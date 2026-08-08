import json
import os
from dotenv import load_dotenv
from google import genai
from google.genai import types
import tools
from policy_prompt import get_system_prompt

load_dotenv()

# ============================================================
# Tool Schemas
# ============================================================

add_seats_schema = {
    "name": "add_seats",
    "description": "Adds extra seats to a customer's active subscription.",
    "parameters": {
        "type": "object",
        "properties": {
            "cus_id": {
                "type": "integer",
                "description": "The customer's ID."
            },
            "num_seats": {
                "type": "integer",
                "description": "Number of seats to add."
            }
        },
        "required": ["cus_id", "num_seats"]
    }
}

cancel_subscription_schema = {
    "name": "cancel_subscription",
    "description": (
        "Cancels a customer's subscription. "
        "If mid-cycle, schedules cancellation for the end of the term. "
        "If within refund window, cancels immediately."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "cus_id": {
                "type": "integer",
                "description": "The customer's ID."
            }
        },
        "required": ["cus_id"]
    }
}

downgrade_plan_schema = {
    "name": "downgrade_plan",
    "description": (
        "Downgrades a customer to a lower-tier plan. "
        "Will refuse if current seats exceed the new plan's cap."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "cus_id": {
                "type": "integer",
                "description": "The customer's ID."
            },
            "new_plan_name": {
                "type": "string",
                "description": (
                    "The name of the plan to downgrade to "
                    "(e.g., 'Starter')."
                )
            },
            "seats": {
                "type": "integer",
                "description": (
                    "Optional. The target number of seats for the new plan."
                )
            }
        },
        "required": ["cus_id", "new_plan_name"]
    }
}

upgrade_plan_schema = {
    "name": "upgrade_plan",
    "description": "Upgrades a customer to a higher-tier plan immediately.",
    "parameters": {
        "type": "object",
        "properties": {
            "cus_id": {
                "type": "integer",
                "description": "The customer's ID."
            },
            "new_plan_name": {
                "type": "string",
                "description": (
                    "The name of the plan to upgrade to "
                    "(e.g., 'Pro', 'Enterprise')."
                )
            },
            "seats": {
                "type": "integer",
                "description": (
                    "Optional. The total number of seats to have "
                    "on the new plan."
                )
            }
        },
        "required": ["cus_id", "new_plan_name"]
    }
}

cancel_scheduled_downgrade_schema = {
    "name": "cancel_scheduled_downgrade",
    "description": (
        "Reverts a scheduled downgrade, keeping the customer "
        "on their current active plan."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "cus_id": {
                "type": "integer",
                "description": "The customer's ID."
            }
        },
        "required": ["cus_id"]
    }
}

get_customer_schema = {
    "name": "get_customer",
    "description": (
        "Retrieves basic customer details "
        "(name, email, phone)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "cus_id": {
                "type": "integer",
                "description": "The customer's ID."
            }
        },
        "required": ["cus_id"]
    }
}

get_active_subscription_schema = {
    "name": "get_active_subscription",
    "description": (
        "Retrieves details of the customer's currently active "
        "subscription, including plan name and seat count."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "cus_id": {
                "type": "integer",
                "description": "The customer's ID."
            }
        },
        "required": ["cus_id"]
    }
}

get_plan_schema = {
    "name": "get_plan",
    "description": (
        "Retrieves the configuration for a subscription plan, "
        "including price_per_seat, seat_cap, and duration_days."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "plan_name": {
                "type": "string",
                "description": (
                    "The name of the plan "
                    "(e.g., 'Starter', 'Pro', 'Enterprise')."
                )
            }
        },
        "required": ["plan_name"]
    }
}

# ============================================================
# Tool Registry
# ============================================================

tools_list = [
    add_seats_schema,
    cancel_subscription_schema,
    downgrade_plan_schema,
    upgrade_plan_schema,
    cancel_scheduled_downgrade_schema,
    get_customer_schema,
    get_active_subscription_schema,
    get_plan_schema,
]

dispatcher = {
    "add_seats": tools.add_seats,
    "cancel_subscription": tools.cancel_subscription,
    "downgrade_plan": tools.downgrade_plan,
    "upgrade_plan": tools.upgrade_plan,
    "cancel_scheduled_downgrade": tools.cancel_scheduled_downgrade,
    "get_customer": tools.get_customer,
    "get_active_subscription": tools.get_active_subscription,
    "get_plan": tools.get_plan,
}

TOOLS_NEEDING_DATE = {
    "add_seats",
    "cancel_subscription",
    "downgrade_plan",
    "upgrade_plan",
}

client = genai.Client()

# ============================================================
# Agent
# ============================================================

def run_agent(prompt, cus_id, today="2026-06-20"):

    messages = [types.Content(role="user", parts=[types.Part.from_text(text=prompt)])]

    system_prompt = get_system_prompt(cus_id, today)
    tool_log = []

    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        tools=[types.Tool(function_declarations=tools_list)],
        temperature=0.0
    )

    for _ in range(10):
        response = client.models.generate_content(
            model="gemini-3.5-flash",
            config=config,
            contents=messages,
        )

        if response.candidates and response.candidates[0].content:
            messages.append(response.candidates[0].content)

        if not response.function_calls:
            break

        tool_results = []

        for call in response.function_calls:
            tool_name = call.name
            tool_args = dict(call.args) if call.args else {}

            if tool_name in TOOLS_NEEDING_DATE:
                tool_args["today"] = today

            tool_func = dispatcher[tool_name]

            try:
                result = tool_func(**tool_args)
            except Exception as e:
                result = {
                    "success": False,
                    "reason": f"Tool Execution Error: {e}"
                }

            tool_log.append((tool_name, result))
            result_str = json.dumps(result)

            tool_results.append(
                types.Part.from_function_response(
                    name=tool_name,
                    response={"result": result_str}
                )
            )

        if tool_results:
            messages.append(
                types.Content(
                    role="user",
                    parts=tool_results
                )
            )
    else:
        return "AGENT ERROR: exceeded max tool-call iterations", tool_log

    return (response.text if response.text else ""), tool_log