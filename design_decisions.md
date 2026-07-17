# SaaS Billing Agent Eval — Full Design Document (HLD + LLD)

A complete design record: high-level architecture, low-level design (schema DDL, every SQL query, every data structure), all key decisions with rationale and tradeoffs, and open questions. Written so a future contributor can rebuild or extend the system from this doc alone.

## Table of Contents
1. [High-Level Design (HLD)](#1-high-level-design-hld)
2. [Low-Level Design (LLD): Schema](#2-lld-schema)
3. [LLD: Data Structures](#3-lld-data-structures)
4. [LLD: Read/Calculation Functions (with SQL)](#4-lld-readcalculation-functions)
5. [LLD: Write Tools (with SQL, per branch)](#5-lld-write-tools)
6. [LLD: The Evaluator (with SQL)](#6-lld-the-evaluator)
7. [LLD: Reset Harness (DDL)](#7-lld-reset-harness)
8. [Design Decisions & Rationale](#8-design-decisions--rationale)
9. [Recurring Principles](#9-recurring-principles)
10. [Open Questions / Known Limitations](#10-open-questions--known-limitations)
11. [Future Work](#11-future-work)

---

## 1. High-Level Design (HLD)

### 1.1 Goal
A **τ-bench-style evaluation benchmark** for a SaaS billing agent. An LLM agent handles natural-language billing requests by calling tools against a sandboxed SQLite database; an **evaluator** scores each task automatically by comparing the final DB state to a pre-generated ground-truth state. The differentiator is the **evaluation harness**, not the agent.

### 1.2 Components
```
┌─────────────────────────────────────────────────────────────┐
│                        TASK SUITE                            │
│  each task = { seed_setup, user_prompt,                      │
│                correct_solution (tool calls), ground_truth } │
└───────────────┬─────────────────────────────────────────────┘
                │
     ┌──────────▼───────────┐        ┌────────────────────────┐
     │   AGENT (W3+)         │        │   POLICY (policy.md)   │
     │  reads prompt +       │◄───────│  rules the agent must  │
     │  policy, plans,       │        │  follow; also defines  │
     │  calls tools,         │        │  ground truth          │
     │  recovers on refusal  │        └────────────────────────┘
     └──────────┬───────────┘
                │ calls
     ┌──────────▼───────────────────────────────────────────┐
     │   TOOL LAYER (tools.py)                               │
     │  5 write-tools + read/calc helpers.                  │
     │  ENFORCE all rules; atomic (single commit).          │
     └──────────┬───────────────────────────────────────────┘
                │ reads/writes
     ┌──────────▼───────────┐        ┌────────────────────────┐
     │  SQLITE DB           │        │  RESET HARNESS         │
     │  (billing.db)        │◄───────│  (admin/master_tools)  │
     │  5 tables            │        │  DROP+CREATE+seed      │
     └──────────┬───────────┘        └────────────────────────┘
                │ final state
     ┌──────────▼───────────────────────────────────────────┐
     │  EVALUATOR (evaluator.py)                            │
     │  compares final DB vs ground_truth (IDs stripped,   │
     │  multiset per table) -> (pass: bool, reason: str)   │
     └──────────────────────────────────────────────────────┘
```

### 1.3 Data Flow (how one task runs)
1. **Reset** the DB to a clean seeded state (`reset_db()`).
2. **Apply the task's seed_setup** (extra rows / state specific to the task).
3. **Snapshot** the DB → this snapshot is the "seed" the evaluator uses to verify unchanged tables.
4. **Run the solution**: either the hand-written `correct_solution` (for proof-of-eval) or the agent's tool calls (W3+).
5. **Evaluate**: `evaluate_task(actual_db, ground_truth, seed_snapshot)` → `(bool, reason)`.
6. **Aggregate** over all tasks → task-success rate (e.g. 27/30).

### 1.4 Evaluation Philosophy
- **Final-state, not trace-based.** Multiple valid tool orderings reach the same end state; grading the path over-constrains. We verify *what is true at the end*, not *how it got there*.
- **Content equivalence, IDs stripped.** `sub_id`/`trans_id` auto-increment and differ every run, so two states are "equal" if they encode the same facts regardless of assigned integers.
- **Metric:** binary pass/fail per task (a 90%-correct billing action is still wrong); headline = the success-rate delta between a naive agent and one with a self-correction loop.

### 1.5 Scope
**In:** the 5 billing actions (add seats, upgrade, downgrade, cancel, cancel-scheduled-downgrade), the policy, the evaluator, the task suite, the agent + self-correction loop.
**Out (→ `future_work.md`):** renewal engine / server sweep, `paused` status, fine-tuning, mock payment gateway, transaction status column, multi-model benchmarking, LLM user-simulator.

---

## 2. LLD: Schema

Five tables. SQLite. Dates stored as ISO-8601 TEXT (`YYYY-MM-DD`). Money as `REAL`, rounded to 2dp at every write. FK enforcement requires `PRAGMA foreign_keys = ON` per connection (SQLite ignores FK declarations otherwise).

```sql
CREATE TABLE users (
    cus_id        INTEGER PRIMARY KEY,
    name          TEXT,
    email         TEXT,
    phone         TEXT,
    active_sub_id INTEGER          -- FK -> subscriptions.sub_id; NULL = no active plan
);

CREATE TABLE payment_methods (
    pay_id INTEGER PRIMARY KEY,
    cus_id INTEGER,
    type   TEXT,                   -- 'card' | 'upi'
    status TEXT,                   -- 'valid' | 'expired'
    FOREIGN KEY(cus_id) REFERENCES users(cus_id)
);

CREATE TABLE catalog (            -- the plan TEMPLATE (shared by all subscribers)
    plan_name      TEXT PRIMARY KEY,   -- 'Starter' | 'Pro' | 'Enterprise'
    price_per_seat REAL,
    seat_cap       INTEGER,
    duration_days  INTEGER             -- e.g. 30
);

CREATE TABLE subscriptions (      -- a plan INSTANCE for a customer (history + active)
    sub_id     INTEGER PRIMARY KEY,
    cus_id     INTEGER,
    plan_name  TEXT,
    seats_used INTEGER,                -- live seat count for THIS subscription
    start_date TEXT,                   -- ISO
    end_date   TEXT,                   -- ISO; stamped to 'today' on abrupt stop (see 8.7)
    status     TEXT,                   -- see status set below
    autopay    INTEGER,                -- 0 | 1
    FOREIGN KEY(cus_id)    REFERENCES users(cus_id),
    FOREIGN KEY(plan_name) REFERENCES catalog(plan_name)
);

CREATE TABLE transactions (       -- the immutable money LEDGER
    trans_id     INTEGER PRIMARY KEY,
    cus_id       INTEGER,
    sub_id       INTEGER,
    amount_paid  REAL,                 -- recorded fact; positive; refunds use type='refund'
    payment_date TEXT,                 -- ISO
    type         TEXT,                 -- 'new' | 'seat_add' | 'upgrade' | 'refund'
    FOREIGN KEY(cus_id) REFERENCES users(cus_id),
    FOREIGN KEY(sub_id) REFERENCES subscriptions(sub_id)
);
```

**Subscription status set (5 values):** `active`, `cancelled` (terminal), `scheduled_downgrade` (current sub, running to term), `scheduled_activation` (queued future sub), `scheduled_cancellation` (running to term, no renewal).

**Plan hierarchy (in code, not DB):** `PLAN_TIERS = {'Starter':1, 'Pro':2, 'Enterprise':3}`.

**Circular FK note:** `users.active_sub_id` → `subscriptions`, and `subscriptions.cus_id` → `users`. Handled at insert time by ordering: insert user with `active_sub_id = NULL` → insert subscription → `UPDATE` the user's `active_sub_id`. NULL FKs are permitted.

---

## 3. LLD: Data Structures

| Structure | Purpose | Notes |
|---|---|---|
| `sqlite3.Row` → `dict(row)` | Row access by column name | `conn.row_factory = sqlite3.Row`; converted to dict on return so callers use `row['email']` not `row[2]`. |
| Tool return: `dict` | Structured outcome | e.g. `{"success": True, "amount_charged": 67.5}` or `{"success": False, "reason": "..."}`. The agent reads `reason` to recover. |
| `PLAN_TIERS: dict[str,int]` | Plan ordering | Determines upgrade vs downgrade direction. |
| `collections.Counter` | **Multiset** for eval comparison | Hash-based (dict of `tuple → count`). O(1) avg insert, single `==` to compare. Order-independent → sidesteps volatile row order and same-day tie ambiguity. |
| Content **tuple** | The "identity" of a row for comparison | Built by stripping IDs and keeping semantic fields. E.g. a subscription tuple = `(plan_name, seats_used, start_date, end_date, status, autopay)`. |
| Ground-truth **nested dict/JSON** | Expected final state | Keys: `unchanged_tables`, `users`, `subscriptions`, `transactions`. See 6.2. |
| Evaluator return: `(bool, str)` | Verdict + reason | e.g. `(False, "Mismatch in subscriptions table")` — reason enables fast debugging. |

**Ground-truth schema (the contract between task author and evaluator):**
```jsonc
{
  "unchanged_tables": ["catalog", "payment_methods"],
  "users": [
    { "cus_id": 1, "name": "...", "email": "...", "phone": "...",
      "active_sub_content": { "plan_name": "...", "start_date": "...", "end_date": "..." }  // or null
    }
  ],
  "subscriptions": [
    { "plan_name": "...", "seats_used": N, "start_date": "...", "end_date": "...",
      "status": "...", "autopay": 0|1 }
  ],
  "transactions": [
    { "type": "...", "amount_paid": R, "payment_date": "...",
      "linked_sub": { "plan_name": "...", "start_date": "...", "end_date": "..." } }
  ]
}
```
**Linkage key** (transaction → its subscription, ID-free): `{plan_name, start_date, end_date}`. See 8.9 and 10.

---

## 4. LLD: Read/Calculation Functions

Connection helper (used by all):
```python
def get_connection():
    conn = sqlite3.connect("billing.db")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn
```

| Function | SQL / Logic | Returns |
|---|---|---|
| `get_customer(cus_id)` | `SELECT * FROM users WHERE cus_id = ?` | dict or None |
| `get_active_subscription(cus_id)` | get_customer → if `active_sub_id` is None → None; else `SELECT * FROM subscriptions WHERE sub_id = ?` | dict or None |
| `get_valid_payment_method(cus_id)` | `SELECT * FROM payment_methods WHERE cus_id = ? AND status = 'valid'` | dict or None |
| `get_plan(plan_name)` | `SELECT * FROM catalog WHERE plan_name = ?` | dict or None |
| `get_last_transaction(cus_id)` | `SELECT * FROM transactions WHERE cus_id = ? ORDER BY payment_date DESC, trans_id DESC LIMIT 1` | dict or None |
| `get_last_refund(cus_id)` | `SELECT * FROM transactions WHERE cus_id = ? AND type = 'refund' ORDER BY payment_date DESC, trans_id DESC LIMIT 1` | dict or None |
| `get_total_paid_for_sub(cus_id, sub_id)` | `SELECT COALESCE(SUM(amount_paid), 0.0) FROM transactions WHERE cus_id = ? AND sub_id = ? AND type != 'refund'` | float (0.0 if none) |
| `is_refund_applicable(cus_id, today)` | last_refund is None → True; else `(today − refund.payment_date).days >= 90` | bool |

**Proration (pure function, no DB):**
```python
def prorated_amount(price_per_seat, num_seats, today, start_date, end_date):
    # raises ValueError if today < start_date or today > end_date
    total_days     = (end_date  - start_date).days
    days_remaining = (end_date  - today).days
    fraction       = days_remaining / total_days
    return round(num_seats * price_per_seat * fraction, 2)
```
Design notes: **`today` is a parameter, never the real clock** (deterministic ground truth). Boundary validation *raises* rather than returning 0 (loud failure > silent wrong number). `total_days` is computed from the two dates, not passed in, to avoid a numerator/denominator ruler mismatch.

---

## 5. LLD: Write Tools

Common contract: **check rules → compute money → write ledger + state atomically (one `commit`) → return outcome dict.** All wrapped in `try/except → rollback / finally → close`. New rows omit their PK (auto-increment) and capture it via `cursor.lastrowid`. All take `today` except `cancel_scheduled_downgrade`.

### 5.1 `add_seats(cus_id, num_seats, today)`
Guards: active sub exists; valid payment method; `seats_used + num_seats <= seat_cap`.
```sql
INSERT INTO transactions (cus_id, sub_id, amount_paid, payment_date, type)
       VALUES (?, ?, ?, ?, 'seat_add');           -- amount = prorated_amount(...)
UPDATE subscriptions SET seats_used = seats_used + ? WHERE sub_id = ?;
```
Charge is **prorated** (mid-cycle addition → remaining days only).

### 5.2 `cancel_subscription(cus_id, today)`
Branch condition: `is_recent_charge = 0 <= (today − start_date).days <= 7` AND `is_refund_applicable(...)`.

**Refund branch** (both true):
```sql
INSERT INTO transactions (...) VALUES (?, ?, ?, ?, 'refund');  -- amount = get_total_paid_for_sub(...)
UPDATE subscriptions SET status='cancelled', autopay=0, end_date=? WHERE sub_id=?;  -- end_date = today (stamp)
UPDATE users SET active_sub_id = NULL WHERE cus_id = ?;
```
**Delayed branch** (else):
```sql
UPDATE subscriptions SET status='scheduled_cancellation', autopay=0 WHERE sub_id=?;
-- no transaction; active_sub_id unchanged; end_date left at real value (runs to term)
```

### 5.3 `downgrade_plan(cus_id, new_plan_name, today, seats=None)`
Guards: active sub; not same plan (no-op); `PLAN_TIERS[new] <= PLAN_TIERS[old]` (else "use upgrade"); `target_seats <= new_plan.seat_cap` (else refuse — agent recovers). `target_seats = seats or sub['seats_used']`.
Branch condition: same as cancel (`recent_charge AND refund_applicable`).

**Immediate/refund branch:**
```sql
INSERT INTO transactions (...) VALUES (?, ?, ?, ?, 'refund');   -- get_total_paid_for_sub(...)
UPDATE subscriptions SET status='cancelled', autopay=0, end_date=? WHERE sub_id=?;   -- stamp today
INSERT INTO subscriptions (cus_id, plan_name, seats_used, start_date, end_date, status, autopay)
       VALUES (?, ?, ?, ?, ?, 'active', 1);        -- start=today, end=today+duration
INSERT INTO transactions (...) VALUES (?, ?, ?, ?, 'new');      -- fresh full-month charge
UPDATE users SET active_sub_id = ? WHERE cus_id = ?;            -- repoint to new sub
```
**Scheduled branch:**
```sql
UPDATE subscriptions SET status='scheduled_downgrade' WHERE sub_id=?;   -- old runs to term
INSERT INTO subscriptions (...) VALUES (?, ?, ?, ?, ?, 'scheduled_activation', 1);
       -- start = old.end_date, end = old.end_date + duration; NO transaction; active_sub_id unchanged
```

### 5.4 `upgrade_plan(cus_id, new_plan_name, today, seats=None)`
Always immediate. Guards: active sub; not same plan; `PLAN_TIERS[new] > PLAN_TIERS[old]` (else "use downgrade"); seat cap.
Money model — **virtual credit, no refund row**:
```
old_credit = prorated_amount(old_price, old_seats, today, old_start, old_end)   # unused old value
new_cost   = target_seats * new_price                                            # full fresh month
charge     = max(0, new_cost - old_credit)
```
```sql
UPDATE subscriptions SET status='cancelled', autopay=0, end_date=? WHERE sub_id=?;   -- stamp today
INSERT INTO subscriptions (...) VALUES (?, ?, ?, ?, ?, 'active', 1);   -- start=today, end=today+duration
INSERT INTO transactions (...) VALUES (?, ?, ?, ?, 'upgrade');         -- amount = charge (NO refund row)
UPDATE users SET active_sub_id = ? WHERE cus_id = ?;
```

### 5.5 `cancel_scheduled_downgrade(cus_id)`
Simplest tool — no dates, no money.
```sql
SELECT sub_id FROM subscriptions WHERE cus_id = ? AND status = 'scheduled_downgrade';  -- if none -> refuse
UPDATE subscriptions SET status = 'active' WHERE sub_id = ?;                            -- revert current
DELETE FROM subscriptions WHERE cus_id = ? AND status = 'scheduled_activation';         -- drop queued
-- active_sub_id unchanged (already pointed at the reverted sub)
```
Chose DELETE over marking `cancelled`: the queued sub never started, so it has no history value.

---

## 6. LLD: The Evaluator

`evaluate_task(actual_db_path, ground_truth, seed_db_path=None) -> (bool, reason)`.

### 6.1 Comparison strategy
Each table is reduced to a `Counter` (multiset) of **content tuples** (IDs stripped), and compared with `==`. Multiset (not list) because: (a) row order is not guaranteed by SQLite without `ORDER BY`, (b) `payment_date` is day-resolution so same-day rows have no stable order, (c) the only tiebreaker (`trans_id`) is non-deterministic. Multiset still catches redundancy (a duplicate/bogus row appears as an extra element).

### 6.2 The four checks (in order; returns on first mismatch)

**(a) Unchanged tables** — hard requirement, cannot be silently skipped:
```python
if "unchanged_tables" in ground_truth:
    if not seed_db_path:
        raise ValueError("seed_db_path required")   # missing seed must RAISE, not pass
    for table in ground_truth["unchanged_tables"]:
        # SELECT * FROM {table}  on both actual and seed
        if Counter(actual_rows) != Counter(seed_rows):
            return False, f"Mismatch in unchanged table: {table}"
```

**(b) Users** — `name/email/phone` identical + `active_sub_id` resolved to the pointed-to sub's *content* via LEFT JOIN:
```sql
SELECT u.cus_id, u.name, u.email, u.phone, s.plan_name, s.start_date, s.end_date
FROM users u LEFT JOIN subscriptions s ON u.active_sub_id = s.sub_id;
```
Expected tuple uses `active_sub_content` (or None). Mismatch → `(False, "Mismatch in users table")`.

**(c) Subscriptions** — content multiset:
```sql
SELECT plan_name, seats_used, start_date, end_date, status, autopay FROM subscriptions;
```
Mismatch → `(False, "Mismatch in subscriptions table")`.

**(d) Transactions** — content + linked-sub via LEFT JOIN, `amount_paid` **rounded to 2dp on both sides** (float-noise safety):
```sql
SELECT t.type, t.amount_paid, t.payment_date, s.plan_name, s.start_date, s.end_date
FROM transactions t LEFT JOIN subscriptions s ON t.sub_id = s.sub_id;
```
Tuple = `(type, round(amount,2), payment_date, plan_name, start_date, end_date)`. Mismatch → `(False, "Mismatch in transactions table")`. All pass → `(True, "Pass")`.

### 6.3 Verified against broken cases
The evaluator was tested not just on the correct solution (→ True) but on deliberately broken states, each of which must return False/raise:
- Wrong refund amount (285 vs 317.5) → False ✅
- Corrupted catalog price → False ✅
- Duplicate/redundant transaction row → False ✅
- Missing `seed_db_path` with a corrupted catalog → **raises ValueError** (previously a silent True) ✅
- Float-noise `317.50000000001` → True (rounding) ✅

This "prove it returns False when wrong" step is the proof-of-eval: a known-correct solution scored against its own generated ground truth must yield True; known-broken states must yield False.

---

## 7. LLD: Reset Harness

`reset_db()` (in the admin/`master_tools` module, **separate from `tools.py`** so the agent cannot call it). Drops children before parents, recreates schema, seeds catalog + demo customers.
```sql
DROP TABLE IF EXISTS transactions;
DROP TABLE IF EXISTS subscriptions;
DROP TABLE IF EXISTS payment_methods;
DROP TABLE IF EXISTS catalog;
DROP TABLE IF EXISTS users;
-- (CREATE TABLE ... as in Section 2)
INSERT INTO catalog VALUES ('Starter',10.0,5,30),('Pro',25.0,20,30),('Enterprise',50.0,100,30);
-- seed customers via: insert user (active_sub_id NULL) -> insert sub -> UPDATE active_sub_id -> insert 'new' txn
```
Per-test reset is **not** required for eval correctness (the agent operates on a persistent multi-customer DB; each task's ground truth is defined against that accumulated state). New rows use auto-increment IDs, so append-don't-collide; test setup must never hard-code `sub_id`.

---

## 8. Design Decisions & Rationale

### 8.1 Central principle — tools enforce, agent orchestrates
Tools ENFORCE what's legal (deterministic, safe); the agent ORCHESTRATES what to attempt and how to recover. Rationale: LLMs are non-deterministic, so money-correctness can't rest on the model. Protections don't remove the agent's job — a tool's *refusal* creates the agent's most valuable skill (refuse → ask user → retry). A "simple NLP wrapper" can name-match a function but cannot recover, enforce conditionals, chain dependent actions, or decompose vague requests.

### 8.2 Tool granularity
Each tool = one meaningful, self-protecting business action. Too coarse (`handle_everything`) → agent has nothing to reason about; too fine (`write_one_row`) → business logic leaks into the LLM.

### 8.3 Catalog/subscription split
Template (catalog: price/cap/duration) vs instance (subscription: plan/dates/seats). Merging duplicates the plan definition onto every row and risks drift. → seat_cap in catalog, seats_used on the subscription.

### 8.4 Proration on seat-adds
Mid-cycle additions charge for remaining days only (`seats × price × days_remaining/total_days`). Full-month charge for partial use would overcharge.

### 8.5 Refund = SUM the ledger, not recompute
Refund = `SUM(amount_paid) WHERE sub_id=? AND type!='refund'`. Recomputing from current seats (`seats × price`) ignores that seat-adds were prorated → gives more than was paid ("paying customers to cancel"; the 325-vs-317.5 bug). `amount_paid` is a recorded fact precisely because events (proration, price changes) make it non-recomputable.

### 8.6 Upgrade = virtual credit, no refund row
`charge = max(0, new_full_cost − old_prorated_credit)`; no `refund` transaction. An upgrade isn't a cancellation — credit the unused old value against the new cost, charge the gap. Contrast: downgrade-within-7-days IS modeled as a cancellation (full refund + recharge). Corrected number: Pro(10 seats, Jun15)→Enterprise on Jun25 = **333.33** (credit 166.67 over 20 remaining days; an earlier hand-computed 416.67 used 10 days — wrong; lesson: generate numbers by running the tool).

### 8.7 `end_date` stamping on abrupt stops
On immediate cancel / immediate downgrade / upgrade, the old sub's `end_date` is stamped to `today` (access ended now, not at the fictional future date). Natural-term subs (`scheduled_cancellation`, `scheduled_downgrade`) keep their real end_date. This makes the column non-derivable (a formula `start+duration` can't know a sub was cancelled early), hence necessary. **Ordering rule:** any date *read* (proration) precedes any date *write* (stamp) on the same row.

### 8.8 Refund policy
- **7-day window from `start_date` (usage)**, not payment date — it's a "tried it, changed my mind" window. (In scope, start_date == payment_date; they diverge only via scheduled activation, out of scope.)
- **90-day anti-abuse cap**: a refund is applicable only if the last refund was ≥90 days ago. Shared across all actions ("money leaves the bank at most once per 90 days regardless of label"). A failed check **routes** to the delayed/no-refund branch, it does not refuse the action. Flat 90 days (not calendar months) for determinism.

### 8.9 Evaluator design
Content-multiset per table, IDs stripped; `linked_sub` binds a transaction to its subscription by content (`{plan_name, start_date, end_date}`), not `sub_id`. A standalone subscription check is also kept (some subs have zero transactions — `scheduled_activation`, `scheduled_cancellation` — and would be invisible to a transaction-only check). "Unchanged" is a valid expected state (no-op / status-only tasks). Missing seed → raise. Round money before comparing.

### 8.10 Status set earns its place
5 statuses, each produced by an agent action. `scheduled_cancellation` is distinct from `active + autopay=0` because `add_seats` is allowed only on `active` — a distinct status blocks seat-adds on a sub running out its term. `scheduled_downgrade` (current) and `scheduled_activation` (queued) are distinct (resolved a naming contradiction where one word meant both).

### 8.11 Cut for scope
Renewal engine, `paused`, transaction status column, fine-tuning, payment gateway, multi-model benchmarking, LLM user-simulator — all out, each recorded in `future_work.md`. Principle: a finished verified project beats an ambitious half-built one.

---

## 9. Recurring Principles
1. **Single source of truth** — a stored fact that events can change (`amount_paid`, `end_date`) is NOT redundant with a formula, because the formula only knows original inputs, not the events that changed them.
2. **Generate, don't guess** — ground-truth numbers come from running the tools, then inspection. Hand-computed amounts were wrong twice (285→317.5, 416.67→333.33).
3. **Tools enforce, agent orchestrates** — money-safety is never the LLM's job.
4. **Scope discipline** — every cut protected the timeline.
5. **State earns its place** — a status/field is added only if an agent action produces/needs it.
6. **Verify state, not return values** — a tool's return dict is its *claim*; the DB rows are the *truth*. Tests and the evaluator assert DB state.
7. **Prove the negative** — an evaluator must be tested on broken states (must return False), not only correct ones (must return True). Half-tested evaluators silently lie.

---

## 10. Open Questions / Known Limitations
- **Linkage key (RESOLVED):** `linked_sub = {plan_name, start_date, end_date}`. Adding `end_date` distinguishes same-day-churn subs (a cancelled sub stamped to today vs an active one running to term). "One active subscription" was insufficient (constrains only active subs, not history). Residual case (two subs identical across all three fields) is benign — byte-identical rows are genuinely fungible, so a multiset is correct to treat them as interchangeable; adding `status` would not remove this residual, so three fields is the stopping point.
- **Dangling `active_sub_id` (unfixed):** an `active_sub_id` pointing to a non-existent sub LEFT-JOINs to NULL, identical to a legitimately-NULL pointer — an adversarial task could exploit this. Acceptable for now; would need an explicit "pointer references an existing row" assertion to harden.
- **Bad-date input (unfixed):** `prorated_amount` raises `ValueError` outside the DB try-block in some tools, so a malformed agent-supplied date crashes the tool rather than returning a failure dict. Acceptable for valid-input tasks.
- **Evaluator reason granularity:** returns the first mismatching *table*, not the specific differing rows. Enough for debugging which table diverged; could be extended to diff the multisets and report the differing tuples.

---

## 11. Future Work
1. **Fine-tuning** a billing-specialist model, benchmarked against the base model on this eval (the eval is the prerequisite).
2. **Mock payment gateway** — live payment simulation to watch the agent act (demo/UX layer).
3. **Daily renewal engine** — server sweep: retries autopay, flips `scheduled_activation → active` and `scheduled_downgrade → cancelled` at term-end, sets `paused` on failed renewal. Reintroduces `paused`.
4. **`paused` state + failed-renewal handling** — depends on #3.
5. **Payment-date guard on the 7-day check** — required once renewals exist, so a renewal charge isn't wrongly denied a refund window. (Renewal refunds intentionally human-handled.)
6. **LLM user-simulator** — multi-turn eval; only after core eval is trustworthy.
7. **Multi-model benchmarking** — run the eval across several LLMs (blog extension).
8. **Blog write-up (W6)** — "τ-bench-style billing agent eval: what broke and what self-correction bought."
9. **Additional tools/scenarios** — plan pause/resume, promo codes, multi-currency.
10. **Refund-as-negative-amount ledger** refactor — if plain-sum net revenue is ever wanted.