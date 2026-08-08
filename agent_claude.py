import json
import anthropic
import tools
from policy_prompt import get_system_prompt

# ============================================================
# Tool Schemas
# ============================================================

add_seats_schema = {
    "name": "add_seats",
    "description": "Adds extra seats to a customer's active subscription.",
    "input_schema": {
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
    "input_schema": {
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
    "input_schema": {
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
    "input_schema": {
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
    "input_schema": {
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
    "input_schema": {
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
    "input_schema": {
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
    "input_schema": {
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

client = anthropic.Anthropic()

# ============================================================
# Agent
# ============================================================

def run_agent(prompt, cus_id, today="2026-06-20"):

    messages = [
        {
            "role": "user",
            "content": prompt,
        }
    ]

    system_prompt = get_system_prompt(cus_id, today)
    tool_log = []

    for _ in range(10):
        response = client.messages.create(
            model="claude-sonnet-5",
            max_tokens=1024,
            system=system_prompt,
            messages=messages,
            tools=tools_list,
        )

        messages.append(
            {
                "role": "assistant",
                "content": response.content,
            }
        )

        if response.stop_reason != "tool_use":
            break

        tool_results = []

        for block in response.content:

            if block.type != "tool_use":
                continue

            tool_name = block.name
            claude_args = dict(block.input)

            if tool_name in TOOLS_NEEDING_DATE:
                claude_args["today"] = today

            tool_func = dispatcher[tool_name]

            try:
                result = tool_func(**claude_args)
            except Exception as e:
                result = {
                    "success": False,
                    "reason": f"Tool Execution Error: {e}"
                }

            tool_log.append((tool_name, result))
            result_str = json.dumps(result)

            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result_str,
                }
            )

        if tool_results:
            messages.append(
                {
                    "role": "user",
                    "content": tool_results,
                }
            )
    else:
        return "AGENT ERROR: exceeded max tool-call iterations", tool_log

    final_text = [
        block.text
        for block in response.content
        if block.type == "text"
    ]

    return (final_text[0] if final_text else ""), tool_log