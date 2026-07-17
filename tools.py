import sqlite3
from datetime import date, timedelta

# Hardcoded tier rankings for hierarchy checks
PLAN_TIERS = {
    'Starter': 1,
    'Pro': 2,
    'Enterprise': 3
}


# ----------------------- Calculation Tools ------------------------------
def prorated_amount(price_per_seat, num_seats, today, start_date, end_date):
    d_today = date.fromisoformat(today)
    d_start = date.fromisoformat(start_date)
    d_end = date.fromisoformat(end_date)
    if d_today < d_start:
        raise ValueError(f"Date error: today ({today}) is before sub start_date ({start_date})")
    if d_today > d_end:
        raise ValueError(f"Date error: today ({today}) is past sub end_date ({end_date})")
    total_days = (d_end - d_start).days
    days_remaining = (d_end - d_today).days
    fraction = days_remaining / total_days
    charge = num_seats * price_per_seat * fraction
    return round(charge, 2)


# ----------------------- Read Tools ------------------------------
def get_connection():
    conn = sqlite3.connect("billing.db")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def get_customer(cus_id):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM users WHERE cus_id = ?",
        (cus_id,)
    ).fetchone()
    conn.close()
    if row is None:
        return None
    return dict(row)

def get_active_subscription(cus_id):
    customer = get_customer(cus_id)
    if customer is None or customer['active_sub_id'] is None:
        return None
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM subscriptions WHERE sub_id = ?",
        (customer['active_sub_id'],)
    ).fetchone()
    conn.close()
    return dict(row) if row else None

def get_valid_payment_method(cus_id):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM payment_methods WHERE cus_id = ? AND status = ?",
        (cus_id, 'valid')
    ).fetchone()
    conn.close()
    if row is None:
        return None
    return dict(row)

def get_plan(plan_name):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM catalog WHERE plan_name = ?",
        (plan_name,)
    ).fetchone()
    conn.close()
    if row is None:
        return None
    return dict(row)

def get_last_transaction(cus_id):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM transactions WHERE cus_id = ? ORDER BY payment_date DESC, trans_id DESC LIMIT 1",
        (cus_id,)
    ).fetchone()
    conn.close()
    if row is None:
        return None
    return dict(row)

def get_last_refund(cus_id):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM transactions WHERE cus_id = ? AND type = 'refund' ORDER BY payment_date DESC, trans_id DESC LIMIT 1",
        (cus_id,)
    ).fetchone()
    conn.close()
    if row is None:
        return None
    return dict(row)

def is_refund_applicable(cus_id, today):
    last_refund = get_last_refund(cus_id)
    # Never had a refund -> applicable
    if last_refund is None:
        return True
    d_today = date.fromisoformat(today)
    d_refund = date.fromisoformat(last_refund['payment_date'])
    days_since_refund = (d_today - d_refund).days
    # >= 90 makes it applicable (90th day is safe)
    return days_since_refund >= 90

def get_total_paid_for_sub(cus_id, sub_id):
    # Sums all actual money paid for a specific subscription (ignoring refunds).
    conn = get_connection()
    row = conn.execute(
        "SELECT COALESCE(SUM(amount_paid), 0.0) FROM transactions WHERE cus_id = ? AND sub_id = ? AND type != 'refund'",
        (cus_id, sub_id)
    ).fetchone()
    conn.close()
    return float(row[0])


# ----------------------- Write Tools ------------------------------
def add_seats(cus_id, num_seats, today):
    subscription = get_active_subscription(cus_id)
    if subscription is None:
        return {"success": False, "reason": "No active subscription"}
    payment_method = get_valid_payment_method(cus_id)
    if payment_method is None:
        return {"success": False, "reason": "No valid payment method"}
    plan = get_plan(subscription['plan_name'])
    if subscription['seats_used'] + num_seats > plan['seat_cap']:
        return {"success": False, "reason": f"Would exceed seat cap of {plan['seat_cap']} (currently {subscription['seats_used']}, adding {num_seats})"}

    charge = prorated_amount(
        price_per_seat=plan['price_per_seat'],
        num_seats=num_seats,
        today=today,
        start_date=subscription['start_date'],
        end_date=subscription['end_date']
    )
    try:
        conn = get_connection()
        conn.execute(
            "INSERT INTO transactions (cus_id, sub_id, amount_paid, payment_date, type) VALUES (?, ?, ?, ?, ?)",
            (cus_id, subscription['sub_id'], charge, today, 'seat_add')
        )
        conn.execute(
            "UPDATE subscriptions SET seats_used = seats_used + ? WHERE sub_id = ?",
            (num_seats, subscription['sub_id'])
        )
        conn.commit()
        return {
            "success": True,
            "new_seat_count": subscription['seats_used'] + num_seats,
            "amount_charged": charge
        }
    except Exception as e:
        if 'conn' in locals():
            conn.rollback()
        return {"success": False, "reason": f"Database transaction failed: {str(e)}"}
    finally:
        if 'conn' in locals():
            conn.close()


def cancel_subscription(cus_id, today):
    sub = get_active_subscription(cus_id)
    if sub is None:
        return {"success": False, "reason": "No active subscription found to cancel."}

    # --- WHICH BRANCH? (usage measured from start_date) ---
    d_today = date.fromisoformat(today)
    d_start = date.fromisoformat(sub['start_date'])
    days_since_start = (d_today - d_start).days

    is_recent_charge = (0 <= days_since_start <= 7)
    refund_ok = is_refund_applicable(cus_id, today)

    try:
        conn = get_connection()

        if is_recent_charge and refund_ok:
            # --- IMMEDIATE / REFUND BRANCH ---
            refund_amt = get_total_paid_for_sub(cus_id, sub['sub_id'])

            conn.execute(
                "INSERT INTO transactions (cus_id, sub_id, amount_paid, payment_date, type) VALUES (?, ?, ?, ?, ?)",
                (cus_id, sub['sub_id'], refund_amt, today, 'refund')
            )
            # end_date stamped to today: access ends now, not at the original future date
            conn.execute(
                "UPDATE subscriptions SET status = 'cancelled', autopay = 0, end_date = ? WHERE sub_id = ?",
                (today, sub['sub_id'])
            )
            conn.execute(
                "UPDATE users SET active_sub_id = NULL WHERE cus_id = ?",
                (cus_id,)
            )

            outcome_msg = "Immediate cancellation executed with full refund."
            returned_refund = refund_amt
            new_status = "cancelled"

        else:
            # --- DELAYED BRANCH (no refund; runs to its real end_date) ---
            conn.execute(
                "UPDATE subscriptions SET status = 'scheduled_cancellation', autopay = 0 WHERE sub_id = ?",
                (sub['sub_id'],)
            )
            outcome_msg = "Delayed cancellation scheduled. No refund issued."
            returned_refund = 0.0
            new_status = "scheduled_cancellation"

        conn.commit()
        return {
            "success": True,
            "outcome": outcome_msg,
            "refund_amount": returned_refund,
            "new_status": new_status
        }

    except Exception as e:
        if 'conn' in locals():
            conn.rollback()
        return {"success": False, "reason": f"Database transaction failed: {str(e)}"}
    finally:
        if 'conn' in locals():
            conn.close()


def downgrade_plan(cus_id, new_plan_name, today, seats=None):
    sub = get_active_subscription(cus_id)
    if sub is None:
        return {"success": False, "reason": "No active subscription found to downgrade."}

    old_plan_name = sub['plan_name']
    if old_plan_name == new_plan_name:
        return {"success": False, "reason": "No-op: User is already on this plan."}

    if PLAN_TIERS.get(new_plan_name, 0) > PLAN_TIERS.get(old_plan_name, 0):
        return {"success": False, "reason": "Direction Error: Target plan is higher tier. Use upgrade_plan instead."}

    new_plan = get_plan(new_plan_name)
    target_seats = seats if seats is not None else sub['seats_used']

    if target_seats > new_plan['seat_cap']:
        return {"success": False, "reason": f"Overflow: {target_seats} seats exceed {new_plan_name}'s cap of {new_plan['seat_cap']}. Please specify a new seat count."}

    d_today = date.fromisoformat(today)
    d_start = date.fromisoformat(sub['start_date'])
    days_since_start = (d_today - d_start).days

    is_recent_charge = (0 <= days_since_start <= 7)
    refund_ok = is_refund_applicable(cus_id, today)

    duration_delta = timedelta(days=new_plan['duration_days'])

    try:
        conn = get_connection()
        cursor = conn.cursor()

        if is_recent_charge and refund_ok:
            # --- IMMEDIATE / REFUND BRANCH (cancel old + enroll new now) ---
            refund_amt = get_total_paid_for_sub(cus_id, sub['sub_id'])

            cursor.execute(
                "INSERT INTO transactions (cus_id, sub_id, amount_paid, payment_date, type) VALUES (?, ?, ?, ?, ?)",
                (cus_id, sub['sub_id'], refund_amt, today, 'refund')
            )
            # end_date stamped to today (abrupt stop)
            cursor.execute(
                "UPDATE subscriptions SET status = 'cancelled', autopay = 0, end_date = ? WHERE sub_id = ?",
                (today, sub['sub_id'])
            )

            new_end = (d_today + duration_delta).isoformat()
            cursor.execute(
                "INSERT INTO subscriptions (cus_id, plan_name, seats_used, start_date, end_date, status, autopay) VALUES (?, ?, ?, ?, ?, 'active', 1)",
                (cus_id, new_plan_name, target_seats, today, new_end)
            )
            new_sub_id = cursor.lastrowid

            fresh_charge = round(target_seats * new_plan['price_per_seat'], 2)
            cursor.execute(
                "INSERT INTO transactions (cus_id, sub_id, amount_paid, payment_date, type) VALUES (?, ?, ?, ?, ?)",
                (cus_id, new_sub_id, fresh_charge, today, 'new')
            )

            cursor.execute("UPDATE users SET active_sub_id = ? WHERE cus_id = ?", (new_sub_id, cus_id))

            outcome_msg = f"Immediate downgrade to {new_plan_name} executed. Refunded {refund_amt}, charged {fresh_charge}."

        else:
            # --- SCHEDULED BRANCH (old sub runs to its real end_date) ---
            cursor.execute(
                "UPDATE subscriptions SET status = 'scheduled_downgrade' WHERE sub_id = ?",
                (sub['sub_id'],)
            )

            d_old_end = date.fromisoformat(sub['end_date'])
            new_end = (d_old_end + duration_delta).isoformat()

            cursor.execute(
                "INSERT INTO subscriptions (cus_id, plan_name, seats_used, start_date, end_date, status, autopay) VALUES (?, ?, ?, ?, ?, 'scheduled_activation', 1)",
                (cus_id, new_plan_name, target_seats, sub['end_date'], new_end)
            )
            # No transaction created. active_sub_id unchanged.
            outcome_msg = f"Downgrade to {new_plan_name} scheduled for {sub['end_date']}."

        conn.commit()
        return {"success": True, "outcome": outcome_msg}

    except Exception as e:
        if 'conn' in locals():
            conn.rollback()
        return {"success": False, "reason": f"Database transaction failed: {str(e)}"}
    finally:
        if 'conn' in locals():
            conn.close()


def upgrade_plan(cus_id, new_plan_name, today, seats=None):
    sub = get_active_subscription(cus_id)
    if sub is None:
        return {"success": False, "reason": "No active subscription found to upgrade."}

    old_plan_name = sub['plan_name']
    if old_plan_name == new_plan_name:
        return {"success": False, "reason": "No-op: User is already on this plan."}

    if PLAN_TIERS.get(new_plan_name, 0) <= PLAN_TIERS.get(old_plan_name, 0):
        return {"success": False, "reason": "Direction Error: Target plan is lower or equal tier. Use downgrade_plan instead."}

    new_plan = get_plan(new_plan_name)
    old_plan = get_plan(old_plan_name)
    target_seats = seats if seats is not None else sub['seats_used']

    if target_seats > new_plan['seat_cap']:
        return {"success": False, "reason": f"Overflow: {target_seats} seats exceed {new_plan_name}'s cap of {new_plan['seat_cap']}. Please specify a new seat count."}

    # Virtual credit: unused value of the old plan, subtracted from the new full-month cost.
    old_credit = prorated_amount(
        price_per_seat=old_plan['price_per_seat'],
        num_seats=sub['seats_used'],
        today=today,
        start_date=sub['start_date'],
        end_date=sub['end_date']
    )

    new_cost = target_seats * new_plan['price_per_seat']
    charge = round(max(0.0, new_cost - old_credit), 2)

    d_today = date.fromisoformat(today)
    new_end = (d_today + timedelta(days=new_plan['duration_days'])).isoformat()

    try:
        conn = get_connection()
        cursor = conn.cursor()

        # end_date stamped to today (abrupt stop). No refund row: credit is applied in the math.
        cursor.execute(
            "UPDATE subscriptions SET status = 'cancelled', autopay = 0, end_date = ? WHERE sub_id = ?",
            (today, sub['sub_id'])
        )

        cursor.execute(
            "INSERT INTO subscriptions (cus_id, plan_name, seats_used, start_date, end_date, status, autopay) VALUES (?, ?, ?, ?, ?, 'active', 1)",
            (cus_id, new_plan_name, target_seats, today, new_end)
        )
        new_sub_id = cursor.lastrowid

        cursor.execute(
            "INSERT INTO transactions (cus_id, sub_id, amount_paid, payment_date, type) VALUES (?, ?, ?, ?, ?)",
            (cus_id, new_sub_id, charge, today, 'upgrade')
        )

        cursor.execute("UPDATE users SET active_sub_id = ? WHERE cus_id = ?", (new_sub_id, cus_id))

        conn.commit()
        return {"success": True, "outcome": f"Immediate upgrade to {new_plan_name} executed. Net charge: {charge}."}

    except Exception as e:
        if 'conn' in locals():
            conn.rollback()
        return {"success": False, "reason": f"Database transaction failed: {str(e)}"}
    finally:
        if 'conn' in locals():
            conn.close()


def cancel_scheduled_downgrade(cus_id):
    conn = get_connection()
    downgrade_sub = conn.execute(
        "SELECT sub_id FROM subscriptions WHERE cus_id = ? AND status = 'scheduled_downgrade'",
        (cus_id,)
    ).fetchone()
    if not downgrade_sub:
        conn.close()
        return {"success": False, "reason": "No scheduled downgrade found to cancel."}
    try:
        conn.execute("UPDATE subscriptions SET status = 'active' WHERE sub_id = ?", (downgrade_sub['sub_id'],))
        conn.execute("DELETE FROM subscriptions WHERE cus_id = ? AND status = 'scheduled_activation'", (cus_id,))
        conn.commit()
        return {"success": True, "outcome": "Scheduled downgrade cancelled. Original subscription is active again."}
    except Exception as e:
        conn.rollback()
        return {"success": False, "reason": f"Database transaction failed: {str(e)}"}
    finally:
        conn.close()