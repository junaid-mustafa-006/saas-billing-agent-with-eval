# SaaS Billing Agent — Design Decisions & Rationale

A running record of every significant decision, the problem that prompted it, the choice made, and the tradeoffs accepted. Written so a future contributor (or future you) can understand *why*, not just *what*.

---

## 0. Project Goal & Framing

**What we're building:** a τ-bench-style **evaluation benchmark** for a SaaS billing agent. An agent handles billing requests (add seats, upgrade, downgrade, cancel) against a sandboxed SQLite database; an evaluator scores each task automatically by comparing the final DB state to a ground-truth state.

**The core thesis:** the *evaluation harness* is the differentiator, not the agent. Anyone can wrap an LLM around tools. Few build a trustworthy, final-state-verified benchmark with a self-correction loop and real metrics.

**Why this domain (SaaS billing):** it clears three bars at once — (1) crisp, machine-checkable rules → verifiable ground truth; (2) enterprise signal (real work a company would assign); (3) not a published τ-bench domain (retail/airline/banking are taken), so it reads as an original system rather than a re-implementation.

**Why not quant/trading (despite domain expertise):** trading has no single correct final state ("should I buy X" isn't checkable), which fails the one non-negotiable requirement — verifiability.

---

## 1. Scope Decisions (In vs. Out)

The governing principle: **finish a deep, verified project over an ambitious half-built one.** Every "out of scope" below was cut to protect the timeline, and each is recorded in `future_work.md`.

| Feature | Decision | Rationale |
|---|---|---|
| Daily renewal engine (server sweep) | **OUT** | Not an agent action — it's a cron job. No tool triggers it. Tasks author their initial state directly instead of simulating time passing. |
| `paused` status | **OUT** | Only produced by failed renewals → a sweep concept. No agent action creates it. |
| Fine-tuning a specialist model | **OUT (stretch)** | Requires the eval to exist first (to prove it beat the base model). Big effort, small payoff on a bounded domain; high risk of an unfinished project. Dessert, not dinner. |
| Mock payment gateway | **OUT (stretch)** | A demo/UX layer for watching the agent act live — irrelevant to correctness (eval checks DB state). |
| Transaction status column (pending/failed/successful) | **OUT** | No real payment rail exists in the sandbox; we ARE the system of record, so refunds are instant and always succeed. Modeling pending/failed is cosplay. |
| Multi-model benchmarking | **OUT (stretch)** | Ranks vendors, not our engineering. Our story is one model measured twice (before/after self-correction). |
| LLM user-simulator | **OUT (stretch)** | τ-bench's flakiest part; unreliable proxy for real users. Only after core eval is trustworthy. |
| Blog write-up | **Planned (W6)** | "τ-bench-style billing eval: what broke, what self-correction bought." Worth more to the job hunt than a weak paper. |

**Explicitly NOT pursuing a research paper** — applying a known method (final-state eval) to a new domain isn't novel research. A sharp blog post is the right artifact.

---

## 2. The Central Architectural Principle

**Decision: tools ENFORCE what's legal; the agent ORCHESTRATES what to attempt and how to recover.**

**Problem it resolves:** the temptation to strip protections out of tools and let the agent decide everything ("otherwise it's just an NLP wrapper").

**Why the opposite is correct:**
- LLMs are non-deterministic. Letting the model be the last line of defense against overselling seats or mischarging = money-correctness at the mercy of a coin flip. No real billing system does this.
- Protections in tools don't *remove* the agent's job — they *create* it. Every rule a tool enforces is a situation the agent must navigate: check before acting, read the refusal, recover, retry. **The tool's refusal is what generates the agent's most valuable skill (recovery).**
- A "simple NLP model" can name-match a function. It cannot: refuse-then-recover, enforce user-attached conditionals ("only if under ₹500"), chain dependent actions reacting to each result, or decompose one vague sentence into ordered operations. That gap is the difference between a toy and an agent.

**Tool granularity:** each tool is *one meaningful, self-protecting business action* (`add_seats`, `cancel_subscription`), not too coarse (`handle_everything`) nor too fine (`write_one_row`). The agent composes them.

---

## 3. Schema Design

Five tables: `users`, `payment_methods`, `catalog`, `subscriptions`, `transactions`.

**Key decisions & the issues behind them:**

- **Separate `catalog` (template) from `subscriptions` (instance).** Plan price/cap/duration are catalog facts; a customer's plan/dates/seats are instance facts. Cramming them together causes drift.
- **`seat_cap` lives in `catalog`; `seats_used` lives on the `subscription`.** The cap is a per-plan constant (all Pro users share it); the live count is per-customer. Putting the cap on the subscription would copy it onto every row and risk divergence. *(This is the "single source of truth" principle, first instance.)*
- **`active_sub_id` on `users`** points to the one live subscription — resolves "which of a customer's many subs is current?" unambiguously. Nullable: `NULL` = no active subscription.
- **Circular FK** (`users` ↔ `subscriptions`): handled by insert order — insert user with `active_sub_id = NULL` → insert sub → `UPDATE` the user. NULL FKs are allowed.
- **FK enforcement requires `PRAGMA foreign_keys = ON` per connection.** SQLite ignores FK declarations otherwise — they're decorative without the pragma. (Discovered by inserting a ghost row that should have failed and didn't.)
- **Money stored as `REAL`, rounded to 2dp** at every calculation. Floats can drift (333.3300001); rounding at the boundary keeps ledger comparisons clean.
- **Auth fields cut** (password, CVV, full card numbers). Storing a CVV is illegal under PCI-DSS for real systems and adds zero eval value here. `payment_methods` reduced to `{type, status}` where `status ∈ {valid, expired}` — enough to satisfy "valid payment method on file."

---

## 4. The Money Model (the hardest, most-revised area)

### 4a. Proration
**Decision:** mid-cycle seat additions are **prorated** — charge only for remaining days: `seats × price_per_seat × (days_remaining / total_days)`.
**Rationale:** charging a full month for 12 days of use would overcharge.
**Consequence:** this decision ripples into refunds (see 4b) — you cannot recompute a prorated charge from current seats.

### 4b. Refund amount = SUM the ledger, NOT recompute
**Problem (the "325 vs 285/317.5" saga):** what's the refund when a customer cancels after paying for a subscription + prorated seat-adds?
**Wrong approach:** `current_seats × price_per_seat` — this charges all seats at *full* rate, ignoring that seat-adds were prorated. Gives 325 when the customer actually paid 317.5 → refunds MORE than they paid ("paying customers to cancel").
**Decision:** refund = `SUM(amount_paid) WHERE sub_id = ? AND type != 'refund'` — the actual total paid, read from the ledger.
**Rationale (recurring principle):** `amount_paid` is a **recorded fact** precisely because it can't be reliably recomputed — prices change, proration varies. The ledger is the only truth of what money moved. Recomputing from current state gives a different (wrong) number.

### 4c. Upgrade uses VIRTUAL CREDIT, not a refund
**Decision:** upgrade charge = `max(0, new_full_month_cost − old_prorated_credit)`. **No refund transaction row is ever written.**
**Rationale:** an upgrade isn't a cancellation — the customer isn't leaving, they're moving up mid-cycle. Credit the unused old-plan value against the new cost; charge only the gap. With current pricing (Starter 10 < Pro 25 < Enterprise 50), new cost always exceeds old credit, so charge > 0.
**Contrast with downgrade's immediate branch**, which DOES refund fully then recharge — because a downgrade-within-7-days is modeled as a *cancellation* (see 5b).
**Corrected value:** Alice (Pro, 10 seats, Jun 15) → Enterprise on Jun 25: credit = 25×10×(20/30) = 166.67; new_cost = 50×10 = 500; charge = **333.33**. (An earlier hand-computed "416.67" was wrong — used 10 remaining days instead of 20. Lesson: generate numbers by running the tool.)

---

## 5. Refund Policy

### 5a. 7-day window measured from `start_date` (usage), NOT payment date
**Problem:** does the "recent charge" refund window count from when money moved, or when the customer started using the plan?
**Decision:** from `start_date` (usage). Reasoning: the refund is a "tried it, changed my mind" window, so it counts from when access began.
**Assumption/limitation:** for all in-scope subscriptions, `start_date == payment_date` (signup pays and starts same day). They diverge only via scheduled activation (renewal engine, out of scope).
**Known future gap (in `future_work.md`):** when the renewal engine exists, the 7-day check must ALSO require a recent payment (a payment-date guard), or a renewal charge wrongly gets no refund window. Renewal refunds are intentionally human-handled, out of agent scope.

### 5b. Downgrade = two-step model (cancel + enroll)
**Decision:** a downgrade is conceptually "cancel the old + enroll the new," so the cancellation's refund eligibility governs which branch runs.
- **Immediate branch** (usage ≤ 7 days AND refund applicable): full refund of old sub (ledger sum) + fresh charge for new plan, both immediate.
- **Scheduled branch** (else): old sub → `scheduled_downgrade` (runs to term), new sub → `scheduled_activation` (starts at old sub's end_date). No transaction at scheduling.

### 5c. Anti-abuse: refunds capped once per 90 days
**Problem:** customers could exploit the 7-day refund repeatedly.
**Decision:** a refund is applicable only if the last refund was ≥ 90 days ago (or never). Shared window across ALL actions — "money leaves the bank at most once per 90 days regardless of label (cancel/downgrade)."
**Routing, not blocking:** a failed 90-day check doesn't refuse the action — it *routes* to the delayed/no-refund branch (`scheduled_cancellation` or `scheduled_downgrade`).
**Implementation:** flat **90 days**, not calendar months. Tradeoff: simpler and deterministic (no February ambiguity); "3 months" ≈ 90 days is close enough for a policy. `is_refund_applicable` checks days since the most recent `type='refund'` row's `payment_date`.

---

## 6. Status Lifecycle

**Five statuses**, each produced by an agent action (a state that no action produces doesn't earn its place):
- `active` — baseline
- `cancelled` — cancel-within-7d / upgrade (old sub) / downgrade-with-refund (old sub)
- `scheduled_downgrade` — downgrade-past-7d (old sub, still serving until term)
- `scheduled_activation` — the queued future sub from a scheduled downgrade
- `scheduled_cancellation` — cancel-past-7d (runs to term, no refund)

**Key decisions:**
- **`scheduled_downgrade` (current sub) vs `scheduled_activation` (future sub) are DISTINCT.** Resolved a contradiction where one name meant both the still-running current sub and the queued future one — two different things, two names.
- **`scheduled_cancellation` is separate from `active + autopay=0`.** A past-7-day cancel can't just be active-with-autopay-off, because `add_seats` (allowed only when `active`) would wrongly succeed on it. A distinct status blocks seat adds on a sub running out its term.
- **Seat-add eligibility simplifies to one rule:** allowed only if `status = 'active'`. This auto-blocks all four non-active states.
- **`cancelled` is terminal** (no outgoing transitions). Term-end flips (`scheduled_* → active/cancelled`) are the renewal engine's job (out of scope); the agent must not attempt them.
- **Plan hierarchy:** `Starter(1) < Pro(2) < Enterprise(3)`, hardcoded in `PLAN_TIERS`. Determines upgrade vs downgrade direction; same-plan = no-op.

---

## 7. Date Handling — `end_date` Stamping

**Problem:** after an abrupt stop (cancel/upgrade/downgrade-away), a cancelled sub's `end_date` still showed its original future date — stale data.
**Debate:** is `end_date` redundant (always `start_date + duration`, derivable from catalog)?
**Resolution:** it IS redundant *only if never updated*. Once we stamp `end_date = today` on abrupt stops, it diverges from `start + duration` and becomes a **non-derivable recorded fact** (the formula knows when the sub *would* have ended, not that it was cancelled early). The stamping is what makes the column necessary.
**Decision:**
- **Abrupt stops** (immediate cancel, immediate downgrade's old sub, upgrade's old sub): stamp `end_date = today`.
- **Natural-term subs** (`scheduled_cancellation`, `scheduled_downgrade`): keep their real `end_date` — they genuinely run to term.
- **New subs:** `end_date = start_date + duration_days`.
**Critical ordering rule:** any date *read* (proration) must happen BEFORE any date *write* (stamp) on the same row. Verified: all three abrupt-stop tools read-then-write. Break this later and proration would read a truncated date → zero fraction.

---

## 8. The Five Write-Tools (summary)

All follow: **check rules → compute money → write ledger + state atomically (one commit) → return structured outcome dict.** All take `today` as a parameter (never read the real clock — a fixed clock is required for deterministic ground truth), except `cancel_scheduled_downgrade` (no dates involved).

- **`add_seats(cus_id, num_seats, today)`** — checks active + valid payment + cap; prorated charge; increments `seats_used`.
- **`cancel_subscription(cus_id, today)`** — 7-day (usage) + 90-day routing; refund branch (ledger-sum refund, `end_date` stamped, `active_sub_id → NULL`) vs delayed branch (`scheduled_cancellation`).
- **`downgrade_plan(cus_id, new_plan, today, seats=None)`** — direction/no-op/overflow guards; immediate branch (refund + fresh sub) vs scheduled branch (`scheduled_downgrade` + `scheduled_activation`).
- **`upgrade_plan(cus_id, new_plan, today, seats=None)`** — always immediate; virtual-credit math; **no refund row**; old sub `cancelled` + stamped.
- **`cancel_scheduled_downgrade(cus_id)`** — reverts `scheduled_downgrade → active`, DELETEs the `scheduled_activation` row (chosen over marking cancelled — it never started, no history value). No money moves.

**Seat handling on plan change:** `seats` is an OPTIONAL parameter. If omitted, carry over; if carried/requested seats exceed the new cap, the **tool refuses** (naming the cap) and the agent recovers by asking the user. Rationale: keeps seat-cap knowledge in the tool, not the LLM — a mandatory seats param would force the agent to know caps to avoid an invalid call. The refusal is also the showcase recovery scenario.

**Robustness patterns:** `try/except/rollback/finally` on all writes; `lastrowid` to capture auto-assigned IDs (never hard-code `sub_id`); `sqlite3.Row` → dict returns for name-based access; parameterized `?` queries (SQL-injection-safe habit).

---

## 9. The Evaluator Design (W2 core)

**The problem:** `sub_id` and `trans_id` auto-increment, so they differ every run. Raw row-diffing fails even for correct agents. "Equivalent DB states" must be defined on *meaningful content*, ignoring volatile IDs.

**Decisions:**
- **Compare per table, IDs stripped:**
  - **Transactions:** multiset of `{amount_paid, payment_date, type, linked_sub}` — where `linked_sub` identifies the transaction's subscription **by content, not `sub_id`**. Linkage key = **`{plan_name, start_date, end_date}`** (see §10 — resolved).
  - **Subscriptions:** multiset of `{plan_name, seats_used, start_date, end_date, status, autopay}`.
  - **Users:** `{name, email, phone}` identical; `active_sub_id` verified by the *content* of the sub it points to (not the raw id).
  - **`catalog`, `payment_methods`:** asserted byte-identical (no in-scope tool writes them).
- **Multiset, NOT ordered array.** Problem with arrays: multiple transactions can share a `payment_date` (no finer resolution than a day), and SQLite guarantees no row order without `ORDER BY` — so a stable sort key doesn't exist (trans_id is volatile). A multiset is order-free, killing the same-day ambiguity. **It still catches redundancy** (e.g. a bogus `-300, +300` pair): the multiset has extra elements vs. ground truth. (A count+sum compression was rejected — `[100,-20]` and `[2500,-2420]` share count and sum but differ in truth.)
- **Transaction↔subscription linkage via `linked_sub` content** (not two independent multisets) — because independent checks could pass a state where the right transactions attach to the wrong subs. Bundling binds "this 250 charge belongs to a Pro sub" as one checkable fact.
- **BUT keep a standalone subscription-content check too** — because some subs have *zero* transactions (`scheduled_activation`, `scheduled_cancellation`, any status-only change). A transaction-bundled check alone would make transaction-less subs invisible.
- **"Unchanged" is a valid expected state.** No-op / past-7-day / status-only tasks correctly write no transaction; ground truth asserts the relevant multiset is *unchanged*, and matching that is a pass. The evaluator must not assume every task writes a transaction.

**Ground-truth authoring workflow (generate-then-verify):**
1. Hand-author the **seed state** + **user prompt** (the inputs).
2. Hand-author the **correct tool-call sequence** (the answer key).
3. **Run that sequence; dump the final DB → that IS the ground truth.** Never hand-compute amounts.
4. Sanity-check the dump by inspection.

This folds in the **proof-of-eval** step: the hand-written correct sequence, scored against its own generated ground truth, must yield 100%. If not, the evaluator's comparison logic is broken — caught before any AI is involved. (Demonstrated live: a hand-written ground truth had 35/285 where the tool produced 67.5/317.5 — it would have failed the correct tool.)

---

## 10. Open Questions / Known Limitations

- **Linkage key uniqueness (RESOLVED):** the `linked_sub` key is **`{plan_name, start_date, end_date}`**. Adding `end_date` guarantees uniqueness across a customer's full history in the realistic cases — even same-day churn produces subs distinguishable by `end_date` (a cancelled sub is stamped to today; the active one runs to term). "One active subscription at a time" was NOT sufficient (it constrains only active subs, not history) — this was surfaced by the same-day-churn interview question. **Residual pathological case** (two subs identical across all three fields, from heavy same-day churn) is *benign*: byte-identical rows are genuinely fungible, so a multiset is correct to treat them as interchangeable — attaching a transaction to one vs. the other is a distinction without a difference. Adding `status` to the key would not eliminate this residual case, so `{plan_name, start_date, end_date}` is the stopping point.
- **`active_sub_id` verification:** must check the *content* of the pointed-to sub, not just "an active Starter exists" (the weaker `expected_active_plan` shorthand loses the identity link).
- **Dead code (cosmetic):** `add_seats`/`upgrade_plan` had `isinstance(charge_result, dict)` guards that never fire (`prorated_amount` raises, never returns a dict). Removed in the cleaned `tools.py`. Note: a bad date to `add_seats` still raises uncaught (pre-existing) — acceptable since tasks use valid dates.
- **Bad-date handling:** `prorated_amount` raises `ValueError` outside the DB try-block in some tools, so a malformed date crashes the tool rather than returning a failure dict. Not fixed (out of scope for valid-input tasks); flagged if agent-supplied dates ever become a vector.

---

## 11. Recurring Principles (the through-lines)

1. **Single source of truth** — a stored fact modifiable by events (`amount_paid`, `end_date`) is NOT redundant with a formula, because the formula only knows original inputs, not the events that changed them. (Seat-cap location, refund amount, end_date stamping all invoke this.)
2. **Generate, don't guess** — ground-truth numbers come from running the tools, then inspection. Hand-computed amounts were wrong at least twice (285, 416.67).
3. **Tools enforce, agent orchestrates** — money-safety is never the LLM's job; navigating money-safety rules is.
4. **Scope discipline** — a finished verified project beats an ambitious half-built one. Every cut protected the timeline.
5. **State earns its place** — a status/field is only added if an agent action produces/needs it.
6. **Verify state, not return values** — a tool's return dict is its *claim*; the DB rows are the *truth*. Tests (and the evaluator) assert DB state.