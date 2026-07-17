# Billing Agent Core Policy

### Plan Hierarchy
* **Tier order (low → high):** `Starter` < `Pro` < `Enterprise`.
* A plan change to a **higher** tier is an **upgrade**; to a **lower** tier is a **downgrade**.
* A change to the **same** plan is a no-op and is refused.

### Status Lifecycle & Transitions
* **Valid Statuses:** `active`, `cancelled`, `scheduled_downgrade`, `scheduled_activation`, `scheduled_cancellation`.
* **active →** `cancelled` (immediate), `scheduled_downgrade` (delayed downgrade), or `scheduled_cancellation` (delayed cancel).
* **scheduled_downgrade →** `active` (via cancellable-downgrade tool).
* **scheduled_activation →** `cancelled` (via cancellable-downgrade tool).
* **scheduled_cancellation →** `cancelled` (at term-end, via renewal engine). No undo tool in scope; the agent must not attempt to reactivate it.
* **cancelled →** terminal. No outgoing transitions.
* **Note:** Seat additions modify an `active` row without changing its status (not a transition).
* **Out of Scope:** Term-end flips of scheduled states to `active`/`cancelled` are handled by a separate renewal engine.

### Concurrency Rules
* **Current subscription:** Exactly one "current" subscription per user (status `active`, `scheduled_downgrade`, or `scheduled_cancellation`).
* **Queue:** At most one `scheduled_activation` subscription queued for the future.

### Refund Frequency (Anti-Abuse) — Global Invariant
* **Core rule:** Money leaves the company to a customer **at most once per 90 days**, regardless of which action triggers it (cancellation or downgrade). Upgrades are exempt (no real money leaves — credit only reduces a charge).
* **Window basis:** 90 days is measured from the `payment_date` of the customer's **most recent `type='refund'` transaction**. If the customer has never had a refund, a refund is applicable.
* **`refund_applicable(cus_id, today)`** ⇔ (no prior refund) **OR** (today − most-recent-refund `payment_date` ≥ 90 days).
* **Effect is routing, not blocking:** A failed refund check never refuses the action. It routes the action from its immediate/refund branch to its delayed/no-refund branch (see Cancellations and Downgrades).
* **Shared window:** A refund from *any* action blocks a refund from *any* action for 90 days (a recent cancellation refund blocks a downgrade refund and vice versa).

### Global Tool Constraints
* **Optional Seats:** Across all plan-change tools, `seats` is an optional parameter.
* **Default:** If omitted, seats carry over from the current subscription.
* **Overflow → refuse:** If carried-over (or requested) seats exceed the target plan's `seat_cap`, the tool refuses with a reason naming the cap. The agent recovers by asking the user for a seat count and retrying. Seat-cap knowledge lives in the tool, never in the agent.
* **No-op / invalid:** Requests that don't change state (same-plan "change", cancelling an already-cancelled/scheduled_cancellation sub, acting on a user with no current sub) are refused with a reason.

### Seat Additions
* **Eligibility:** Permitted strictly if status is `active`. (Auto-blocks all scheduled/cancelled states.)
* **Payment:** Requires a `valid` payment method on file.
* **Constraint:** current + requested seats must not exceed the plan's `seat_cap`.
* **Billing:** `seats × price_per_seat × (days_remaining / total_days)`, rounded to 2 dp.
* **DB State:** new `transactions` row (`type='seat_add'`); `subscriptions.seats_used` increments.

### Upgrades (Immediate)
* **Execution:** Immediate. Old sub → `cancelled`.
* **New Subscription:** status `active`; `start_date` = today; `end_date` = today + `duration_days` (billing cycle resets); `seats_used` = old sub's seat count, or explicit `seats` if provided, validated against the new cap.
* **Billing (virtual credit, never a refund):** `charge = max(0, new_prorated_cost − old_prorated_credit)`, where each is `seats × price_per_seat × (days_remaining / total_days)` for the respective plan. The old-plan credit only *reduces* the charge; it never produces a refund row. (With current pricing, new cost always exceeds old credit, so charge > 0 in practice.)
* **DB State:** one `transactions` row (`type='upgrade'`, the computed charge). No refund row.
* **active_sub_id:** repoints immediately to the new sub.

### Downgrades — Two-Step Model
A downgrade is conceptually **cancel-the-old + enroll-the-new**; the cancellation's refund eligibility therefore governs which branch runs. The **immediate/refund branch runs only if BOTH** conditions hold: usage ≤ 7 days (today − `start_date` ≤ 7) **AND** `refund_applicable(cus_id, today)` is true. If **either** fails, the **standard (delayed) branch** runs.

**Standard branch — runs when usage > 7 days, OR a refund is not currently applicable:** delayed.
* Old sub → `scheduled_downgrade`; autopay stays `1`. No transaction created at scheduling.
* New sub created: status `scheduled_activation`; `start_date` = old sub's `end_date`; `end_date` = that + `duration_days`; `seats_used` = carried over (or `seats` param), validated against the new cap (overflow → refuse).
* **active_sub_id:** unchanged (still the current, now `scheduled_downgrade`, sub).

**Immediate/refund branch — runs only when usage ≤ 7 days (today − `start_date` ≤ 7) AND refund is applicable:** immediate.
* Old sub → `cancelled`. Full refund = SUM of all non-refund `amount_paid` for the old `sub_id` (one `refund` row). Same total-paid basis as cancellation.
* New sub created: status `active`; `start_date` = today; `end_date` = today + `duration_days`; `seats_used` = carried over (or `seats` param), validated against the new cap (overflow → refuse). Fresh charge for the new plan (one `new` row).
* **active_sub_id:** repoints immediately to the new sub.

### Cancellable Downgrade (Undo)
* **Execution:** Reverts `scheduled_downgrade` → `active`.
* **State:** the queued `scheduled_activation` sub is removed/cancelled.
* **Billing:** none (nothing was billed at scheduling).
* **active_sub_id:** unchanged (was already pointing at the reverted sub).

### Cancellations
The **refund branch runs only if BOTH** hold: sub used ≤ 7 days (today − `start_date` ≤ 7) **AND** `refund_applicable(cus_id, today)`. If **either** fails, the **delayed (no-refund)** branch runs — the cancellation still happens, just without a refund.
* **7-day basis = usage, not payment:** measured from the subscription's `start_date` (when the customer began using it), not the payment date. (For v1 these are identical for every in-scope sub, since signup pays and starts the same day. They diverge only via scheduled-activation, which the out-of-scope renewal engine handles.)
* **Refund amount = total actually paid for this subscription** = SUM of all non-refund `transactions.amount_paid` for this `sub_id` (e.g. original charge + any prorated seat-adds). NOT recomputed from current seats × price — the ledger is the source of truth for what was paid.
* **Refund branch (usage ≤ 7 days AND refund applicable):** immediate. Full refund of total paid (one `refund` row). Status → `cancelled`. Autopay → `0`. `active_sub_id` → NULL.
* **Delayed branch (usage > 7 days, OR refund not applicable):** No refund. Status → `scheduled_cancellation`. Autopay → `0`. Sub runs to `end_date`. `active_sub_id` unchanged.
* **Renewals never refund** (out of scope; human-handled).

### Refund & Ledger Conventions
* A refund is a new, immutable `transactions` row, `type='refund'`, positive `amount_paid`; net-revenue math subtracts this type.
* Refund amount, where applicable, = the SUM of all non-refund `amount_paid` for that `sub_id` (total actually paid: original charge + any prorated seat-adds). Read from the ledger, never recomputed from current seat count.
* No pending/failed/successful states. If it's in the ledger, it happened.

### Payment Method
* `payment_methods.status` ∈ { `valid`, `expired` }.