import tools
from runner import (
    Task,
    generate_and_freeze_ground_truth,
    run_suite,
)

# ============================================================
# Database Configuration
# ============================================================

DB_PATH = "billing.db"
SEED_PATH = "seed_snapshot.db"

# ============================================================
# Add Seats Tests
# ============================================================

t_add_seats_happy = Task(
    id="add_seats_01",
    prompt="Add 2 seats to my plan.",
    seed_sql="",
    correct_sequence=lambda today: [
        tools.add_seats(
            cus_id=1,
            num_seats=2,
            today=today,
        )
    ],
    ground_truth_file="ground_truths/add_seats_01.json",
    cus_id=1,
)

t_add_seats_cap_refusal = Task(
    id="add_seats_02",
    prompt="Add 15 seats to my plan.",
    seed_sql="",
    correct_sequence=lambda today: [
        tools.add_seats(
            cus_id=1,
            num_seats=15,
            today=today,
        )
    ],
    ground_truth_file="ground_truths/add_seats_02.json",
    expect_success=False,
    cus_id=1,
)

t_add_seats_payment_refusal = Task(
    id="add_seats_03",
    prompt="I need 5 more seats.",
    seed_sql="""
        UPDATE payment_methods
        SET status='expired'
        WHERE cus_id=1;
    """,
    correct_sequence=lambda today: [
        tools.add_seats(
            cus_id=1,
            num_seats=5,
            today=today,
        )
    ],
    ground_truth_file="ground_truths/add_seats_03.json",
    expect_success=False,
    cus_id=1,
)

# ============================================================
# Cancellation Tests
# ============================================================

t_cancel_immediate = Task(
    id="cancel_01",
    prompt="Cancel my subscription immediately.",
    seed_sql="",
    correct_sequence=lambda today: [
        tools.cancel_subscription(
            cus_id=1,
            today=today,
        )
    ],
    ground_truth_file="ground_truths/cancel_01.json",
    cus_id=1,
)

t_cancel_delayed = Task(
    id="cancel_02",
    prompt="Cancel my Starter plan.",
    seed_sql="",
    correct_sequence=lambda today: [
        tools.cancel_subscription(
            cus_id=2,
            today=today,
        )
    ],
    ground_truth_file="ground_truths/cancel_02.json",
    cus_id=2,
)

t_cancel_anti_abuse = Task(
    id="cancel_03",
    prompt="Cancel my Pro plan and refund me.",
    seed_sql="""
        INSERT INTO transactions
        (cus_id, sub_id, amount_paid, payment_date, type)
        VALUES
        (1, 1, 100.0, '2026-05-01', 'refund');
    """,
    correct_sequence=lambda today: [
        tools.cancel_subscription(
            cus_id=1,
            today=today,
        )
    ],
    ground_truth_file="ground_truths/cancel_03.json",
    cus_id=1,
)

t_cancel_noop = Task(
    id="cancel_04",
    prompt="Cancel my plan.",
    seed_sql="",
    correct_sequence=lambda today: [
        tools.cancel_subscription(
            cus_id=3,
            today=today,
        )
    ],
    ground_truth_file="ground_truths/cancel_04.json",
    expect_success=False,
    cus_id=3,
)

# ============================================================
# Downgrade Tests
# ============================================================

t_downgrade_overlap = Task(
    id="downgrade_01",
    prompt="Downgrade me to the Starter plan, 5 seats.",
    seed_sql="""
        UPDATE subscriptions
        SET seats_used=13
        WHERE cus_id=1;

        INSERT INTO transactions
        (cus_id, sub_id, amount_paid, payment_date, type)
        VALUES
        (1, 1, 67.5, '2026-06-18', 'seat_add');
    """,
    correct_sequence=lambda today: [
        tools.downgrade_plan(
            cus_id=1,
            new_plan_name="Starter",
            today=today,
            seats=5,
        )
    ],
    ground_truth_file="ground_truths/downgrade_01.json",
    cus_id=1,
)

t_downgrade_scheduled = Task(
    id="downgrade_02",
    prompt="Switch my plan to Starter, dropping to 5 seats.",
    seed_sql="""
        UPDATE subscriptions
        SET start_date='2026-06-01'
        WHERE cus_id=1;
    """,
    correct_sequence=lambda today: [
        tools.downgrade_plan(
            cus_id=1,
            new_plan_name="Starter",
            today=today,
            seats=5,
        )
    ],
    ground_truth_file="ground_truths/downgrade_02.json",
    cus_id=1,
)

t_downgrade_smart_recovery = Task(
    id="downgrade_03",
    prompt="Downgrade me to Enterprise.",
    seed_sql="",
    correct_sequence=lambda today: [
        tools.upgrade_plan(
            cus_id=1,
            new_plan_name="Enterprise",
            today=today,
        )
    ],
    ground_truth_file="ground_truths/downgrade_03.json",
    expect_success=True,
    cus_id=1,
)

# ============================================================
# Upgrade Tests
# ============================================================

t_upgrade_mid_cycle = Task(
    id="upgrade_01",
    prompt="Upgrade my plan to Enterprise with 50 seats.",
    seed_sql="",
    correct_sequence=lambda today: [
        tools.upgrade_plan(
            cus_id=1,
            new_plan_name="Enterprise",
            today=today,
            seats=50,
        )
    ],
    ground_truth_file="ground_truths/upgrade_01.json",
    cus_id=1,
)

t_upgrade_smart_recovery = Task(
    id="upgrade_02",
    prompt="Upgrade me to Starter.",
    seed_sql="",
    correct_sequence=lambda today: [
        tools.downgrade_plan(
            cus_id=1,
            new_plan_name="Starter",
            today=today,
        )
    ],
    ground_truth_file="ground_truths/upgrade_02.json",
    expect_success=False,
    cus_id=1,
)

# ============================================================
# Undo Downgrade Tests
# ============================================================

t_undo_happy = Task(
    id="undo_01",
    prompt="Nevermind, keep my current plan.",
    seed_sql="""
        UPDATE subscriptions
        SET status='scheduled_downgrade'
        WHERE cus_id=1;

        INSERT INTO subscriptions
        (
            cus_id,
            plan_name,
            seats_used,
            start_date,
            end_date,
            status,
            autopay
        )
        VALUES
        (
            1,
            'Starter',
            5,
            '2026-07-15',
            '2026-08-15',
            'scheduled_activation',
            1
        );
    """,
    correct_sequence=lambda today: [
        tools.cancel_scheduled_downgrade(
            cus_id=1,
        )
    ],
    ground_truth_file="ground_truths/undo_01.json",
    cus_id=1,
)

t_undo_noop = Task(
    id="undo_02",
    prompt="Undo my plan change.",
    seed_sql="",
    correct_sequence=lambda today: [
        tools.cancel_scheduled_downgrade(
            cus_id=1,
        )
    ],
    ground_truth_file="ground_truths/undo_02.json",
    expect_success=False,
    cus_id=1,
)

# ============================================================
# Multi-Step Tests
# ============================================================

t_multistep_chain = Task(
    id="chain_01",
    prompt="I need 15 total seats, and upgrade me to Enterprise.",
    seed_sql="",
    correct_sequence=lambda today: [
        tools.add_seats(
            cus_id=1,
            num_seats=5,
            today=today,
        ),
        tools.upgrade_plan(
            cus_id=1,
            new_plan_name="Enterprise",
            today=today,
            seats=15,
        ),
    ],
    ground_truth_file="ground_truths/chain_01.json",
    cus_id=1,
)

# ============================================================
# Test Suite
# ============================================================

ALL_TASKS = [
    t_add_seats_happy,
    t_add_seats_cap_refusal,
    t_add_seats_payment_refusal,
    t_cancel_immediate,
    t_cancel_delayed,
    t_cancel_anti_abuse,
    t_cancel_noop,
    t_downgrade_overlap,
    t_downgrade_scheduled,
    t_downgrade_smart_recovery,
    t_upgrade_mid_cycle,
    t_upgrade_smart_recovery,
    t_undo_happy,
    t_undo_noop,
    t_multistep_chain,
]

# ============================================================
# Runner
# ============================================================

if __name__ == "__main__":
    run_suite(
        ALL_TASKS,
        DB_PATH,
        SEED_PATH,
    )