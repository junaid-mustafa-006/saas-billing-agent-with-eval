# Decision Log — The Struggle Behind the Design

A chronological record of the hard calls: the initial idea, why it seemed fine, the problem that surfaced, what changed, and the lesson. This is the *journey* (the reference doc `design_decisions.md` holds the *destination*). Each entry notes who proposed what — useful for interviews, where "walk me through a hard decision" is the real question.

**Legend:** 🔵 = my proposal/instinct · 🟢 = advisor pushback/advice · ✅ = final decision · 💡 = principle learned. Entries where I (the builder) was wrong and corrected are marked **[I was right]** where I held against pushback, or noted plainly where I conceded.

---

## PHASE 0 — Strategy & Scoping

### 0.1 Is a project even the lever for a 30 LPA fresher role?
- 🔵 My framing: "the right project gets me a 30 LPA AIE role."
- 🟢 Pushback: a project gets you the *interview*; interviews (DSA + ML system design) get you the *offer*. 30 LPA as a fresher is roughly top-1% (IIT/NIT→FAANG-India territory). A strong project realistically lands ~15-22 LPA at a product company, with 30 as upside.
- ✅ Reframed the target: project-heavy bet, aiming for the top of the fresher band with 30 as a stretch. Background (IIT KGP mech, off-cycle after a rescinded Straive offer) raises the ceiling but the interview bar is identical off-campus.
- 💡 A portfolio project is necessary but not sufficient; budget time honestly between project and interview prep.

### 0.2 Fine-tuning / research-paper / multi-model ambitions
- 🔵 My questions: should we benchmark many LLMs? Is this publishable? Should we fine-tune a billing-specialist model?
- 🟢 Advice: (a) one model measured twice (before/after self-correction), not a vendor bake-off; (b) blog post, not paper — applying a known method to a new domain isn't novel research; (c) fine-tuning is a *stretch* that requires the eval to exist first, high risk of an unfinished project.
- ✅ Core scope = the eval + agent + self-correction loop. Fine-tuning, multi-model, user-simulator → `future_work.md`.
- 💡 A finished verified project beats an ambitious half-built one. Scope discipline.

---

## PHASE 1 — Project & Domain Selection

### 1.1 Project category
- 🔵 Considered: RAG-over-PDFs chatbot; a course-generator ("an AI that generates a course on any topic").
- 🟢 Both rejected. RAG chatbot: saturated, signals *average candidate*. Course generator: **no verifiable core** — a generated "course" has no correct answer, so no real eval is possible, killing the one differentiator.
- ✅ Chose an **agentic workflow agent with a final-state eval gate** (τ-bench paradigm).
- 💡 A project has "good eval" only if its output is auto-checkable against ground truth. Verifiability is the gate.

### 1.2 Which agentic project
- 🔵 First landed on a **text-to-analytics (SQL) agent**.
- 🟢 Offered the **tool-use/workflow agent graded on end-state** (τ-bench/Sierra) as higher-differentiation — the frontier paradigm, mirrors real agent jobs, scarce in portfolios. User demanded proof of scarcity; I searched and substantiated (τ-bench is a recognized benchmark; final-state grading is the research frontier).
- ✅ Chose the **workflow agent** (project-heavy bet accepted the higher environment-build risk).
- 💡 Differentiation vs. finishability is a real tradeoff; the workflow agent wins on signal, costs more to build.

### 1.3 Domain
- 🔵 Proposed: college registrar; then e-commerce; then fintech (leveraging quant background — WorldQuant, IMC Prosperity, IQC).
- 🟢 All rejected, each for a specific reason: **registrar** reads as a student project (bad for a mech→AI pivot); **e-commerce** is τ-bench's flagship domain (zero differentiation — you'd re-implement the benchmark); **quant/trading fintech** has *no single correct final state* ("should I buy X" isn't checkable) — fails verifiability. Deliberately steered *away* from the user's actual expertise here.
- ✅ Chose **SaaS subscription & billing** — crisp machine-checkable rules, enterprise signal, not a published τ-bench domain.
- 💡 The domain must clear three bars at once: verifiable rules, enterprise signal, and not-a-benchmark-domain. Domain expertise ≠ good eval domain.

---

## PHASE 2 — The Architecture Principle

### 2.1 "If the rules are in the tools, isn't the agent just a useless NLP wrapper?" (the scope crisis)
- 🔵 My proposal: strip protections out of the tools, give the agent raw read/write, let it decide everything — otherwise "a simple NLP model would do that."
- 🟢 Strong pushback: **do the opposite.** LLMs are non-deterministic; letting the model be the last line of defense against overselling/mischarging = coin-flip correctness. Protections in tools don't *remove* the agent's job — a tool's *refusal* creates the agent's hardest, most-valued skill (refuse → ask user → retry). A simple NLP model can name-match a function but cannot recover, enforce user conditionals, chain dependent actions, or decompose vague requests.
- ✅ **Tools enforce what's legal; the agent orchestrates what to attempt and how to recover.** (My "switches + operator" analogy: the electrician wires the switches safe; the operator flips them in smart sequences and never rewires.)
- 💡 Money-safety is never the LLM's job; *navigating* money-safety rules is. This is the load-bearing architectural decision.

### 2.2 "Are we training the agent?"
- 🔵 My phrasing: "we'll train the agent by throwing situations at it."
- 🟢 Correction: not training in the ML sense — no weights change. The LLM arrives smart; we build the *exam that measures* it. W2 is an exam, not a training loop.
- ✅ Job = measurement (eval), not teaching the model.

---

## PHASE 3 — Schema

### 3.1 Auth fields
- 🔵 First schema included `password (hashed)`, `cvv`, full card numbers.
- 🟢 Cut all of them — storing a CVV is illegal under PCI-DSS for real systems and adds zero eval value. `payment_methods` reduced to `{type, status}`.
- ✅ Minimal payment representation; `status ∈ {valid, expired}`.
- 💡 Don't model production-payment-rail cosplay in a sandbox.

### 3.2 Template vs instance (catalog vs subscription)
- 🟢 Flagged: plan price/cap/duration is catalog (template) info; a customer's plan/dates/seats is instance info. Don't merge.
- ✅ Separate `catalog` and `subscriptions`; **seat_cap in catalog, seats_used on the subscription** (cap is per-plan constant; count is per-customer).
- 💡 Single source of truth — copying the cap onto every sub risks drift.

### 3.3 Identifying the active subscription
- 🔵 First idea: derive active-ness by comparing today's date against each sub's date range on every lookup.
- 🔵→✅ Then realized (self-corrected) that's wasteful; added **`active_sub_id` FK on the user** — points directly to the one live sub.
- 💡 Explicit state beats recomputing-on-every-read; also directly gradeable.

### 3.4 The scheduled-downgrade status contradiction
- 🔵 Initial policy used one status, `scheduled_downgrade`, described as *both* the queued future sub (concurrency rule) and the still-running current sub (downgrade rule).
- 🟢 Flagged the contradiction: two people would encode ground truth differently — one puts the status on the future row, one on the current row.
- ✅ **Split into two statuses:** `scheduled_downgrade` (current sub, running to term) and `scheduled_activation` (queued future sub). [User then extended this pattern correctly on their own — see 3.5.]
- 💡 One name for two different things is a ground-truth ambiguity waiting to happen.

### 3.5 `scheduled_cancellation` (user-caught)
- 🟢 (User's own realization, mid-downgrade discussion) A past-7-day cancel can't be `active + autopay=0`, because `add_seats` (allowed only on `active`) would wrongly succeed on it. Needs a distinct status.
- ✅ Added `scheduled_cancellation`; renamed the downgrade-queue status to `scheduled_activation` to disambiguate.
- 💡 A status earns its place only if an agent action produces/needs it — and here one was genuinely needed to block seat-adds.

### 3.6 The renewal engine, `paused`, and same-day server sweep
- 🔵 Proposed a daily server sweep that renews/expires subs and a `paused` status for failed renewals.
- 🟢 Cut from scope — the sweep is a cron job, not an agent action; no tool triggers it, and the eval authors initial states directly rather than simulating time. `paused` only comes from failed renewals → goes with the sweep.
- ✅ Out of scope → `future_work.md`.
- 💡 Don't build machinery the agent never touches and the eval doesn't need.

### 3.7 Transaction status column (pending/failed/successful)
- 🔵 Proposed adding a status column to transactions to model refund states.
- 🟢 Cut — no real payment rail exists in the sandbox; we ARE the system of record, so refunds are instant and always succeed. `type='refund'` already distinguishes them.
- ✅ Ledger rows are immutable facts, no status column.
- 💡 Same "no payment-rail cosplay" principle as 3.1.

### 3.8 Foreign keys silently unenforced
- 🟢 Discovered by inserting a "ghost" subscription for a non-existent customer/plan — it succeeded. SQLite ignores FK declarations without `PRAGMA foreign_keys = ON` per connection.
- ✅ Added the pragma to every connection; re-ran the ghost test → correctly rejected.
- 💡 Verify assumptions by trying to break them (a row that *should* fail and doesn't is the tell).

---

## PHASE 4 — Money & Refund Model (the most-revised area)

### 4.1 Proration on seat-adds
- 🔵→✅ (User decided, correctly) Mid-cycle seat additions are prorated: `seats × price × days_remaining/total_days`. Full-month charge for partial use would overcharge.
- 💡 This decision ripples into refunds (4.2) — you can't recompute a prorated charge from current seats.

### 4.2 Refund amount: `seats × price` vs ledger sum (the 325 vs 317.5 saga)
- 🔵 Proposed refund = `current_seats × price_per_seat` (e.g. 13 × 25 = 325).
- 🟢 Rejected with numbers: she actually paid 250 + a *prorated* seat-add, not 13 seats at full rate. `13 × 25 = 325` refunds MORE than she paid → "paying customers to cancel."
- 🔵 (Mid-argument) conflated two uses — tried to "fix" the refund amount by changing the 7-day *branch* check to use seats. Separated: the 7-day check is a *date* question; the refund amount is a *money* question.
- ✅ **Refund = `SUM(amount_paid) WHERE sub_id=? AND type!='refund'`** — the actual total paid, read from the ledger. Added helper `get_total_paid_for_sub`.
- 💡 `amount_paid` is a recorded fact precisely because events (proration, price changes) make it non-recomputable. The ledger is the only truth of what money moved.

### 4.3 The refund *number* itself (my arithmetic error)
- 🔵 (My error) I repeatedly used seat-add = 35 (assuming ~14 remaining days) and refund = 285.
- 🟢→ Corrected by running the tool: seat-add on Jun 18 with period Jun 15→Jul 15 = 27 remaining days → 3 × 25 × (27/30) = **67.5**, so refund = 250 + 67.5 = **317.5**. My mental math was wrong; the tool (using real dates) was right.
- ✅ 67.5 / 317.5.
- 💡 **Generate, don't guess** — ground-truth numbers come from running the tools, never hand math.

### 4.4 Upgrade money model: refund vs virtual credit
- 🔵 (User decided, correctly) An upgrade shouldn't issue a real refund — new plan is costlier, so just reduce the amount owed.
- 🟢 Sharpened: upgrade = **virtual credit**, `charge = max(0, new_full_cost − old_prorated_credit)`, **no refund transaction row** (contrast with downgrade-within-7-days, which IS a cancellation → full refund + recharge). Deleted an "excess refund" branch from the policy that contradicted this.
- ✅ Virtual credit, no refund row, `type='upgrade'`.
- 💡 An upgrade isn't a cancellation; a downgrade-within-7-days is. Same-looking actions, different money models.

### 4.5 The upgrade *number* (my second arithmetic error)
- 🔵 (My error) Asserted the upgrade charge should be 416.67 for several turns, computing the credit over 10 remaining days.
- 🟢→ The tool produced 333.33. "Day 10" means 10 days *elapsed*, so **20 days remain**: credit = 25 × 10 × (20/30) = 166.67; charge = 500 − 166.67 = **333.33**. The user's code trusted the date arithmetic; I didn't. I was wrong; conceded cleanly.
- ✅ 333.33 (corrected in all docs).
- 💡 Same as 4.3 — the code beat my mental estimate. This is the *second* time; it's why generate-then-verify became a rule.

### 4.6 How to compute the refund — `get_active_subscription` + prorate?
- 🔵 Proposed reusing `get_active_subscription` + `prorated_amount`, or `seats × price`, to get the refund.
- 🟢 Rejected: `prorated_amount` computes a *forward charge*, not "give back what was paid"; and `get_active_subscription` gives a seat *count*, not money. Refund must sum the ledger.
- ✅ New helper `get_total_paid_for_sub` (SUM of non-refund rows for the sub).
- 💡 "Refund what was paid" ≠ "recompute a price from current state."

---

## PHASE 5 — Refund Policy Edges

### 5.1 7-day window: payment date vs `start_date` (usage) — the long fight
- 🔵 Insisted the window counts from *usage* (`start_date`), not payment date — "we're giving them 7 days to try it."
- 🟢 Repeatedly raised the **renewal case**: after a renewal charge, `start_date` still shows the *original* date, so a usage-based window would wrongly deny a refund to someone charged yesterday. Pushed payment-date.
- 🔵 **[User was right]** Countered that **renewal refunds are out of scope entirely** (human-handled), so the renewal case can't arise in v1 — and provided a genuine counter-scenario (paid Mar 1, sub starts Mar 5) where payment-date is *wrong* and usage is right.
- 🟢→ Conceded: I was over-weighting an out-of-scope case. For v1, `start_date == payment_date` for all in-scope subs anyway.
- ✅ **7-day check from `start_date`.** Payment-date guard noted in `future_work.md` for when renewals exist.
- 💡 Both were half-right: the rule genuinely has two date conditions (usage AND recent-charge); we were each holding a different half. For v1, usage suffices because renewals are out of scope. (Also: don't let an out-of-scope edge block an in-scope decision.)

### 5.2 90-day anti-abuse refund cap
- 🔵 (User proposed) Customers could exploit the 7-day refund repeatedly → cap it to once per 90 days.
- 🟢 Refined: **shared window across all actions** ("money leaves the bank ≤ once per 90 days regardless of label"); a failed check **routes** to the delayed/no-refund branch, it does not *refuse* the action; measured from the latest `type='refund'` row's `payment_date`.
- ✅ `is_refund_applicable(cus_id, today)` → `days_since_last_refund >= 90`. Flat 90 days, not calendar months (determinism; no February ambiguity).
- 💡 An anti-abuse rule should route, not block; and a flat day-count beats calendar months for a gradeable system.

### 5.3 Seats on plan change: mandatory vs optional parameter
- 🔵 Wanted `seats` to be a **mandatory** input on every plan change ("we get the input anyway").
- 🟢 Recommended **optional**: if omitted, carry over; if it exceeds the new cap, the *tool refuses* and the agent recovers. Reason: a mandatory param forces the *agent* to know seat caps (to avoid an invalid call) — which re-breaks the tools-enforce/agent-orchestrates line. "We get input anyway" is true but *what triggers the ask* differs (agent-knows-cap vs tool-refusal-tells-it).
- ✅ **Optional `seats`; tool refuses on overflow; agent recovers.** (Agent may still proactively ask for UX — a prompt choice, not a tool-signature requirement.)
- 💡 Keep business-rule knowledge (caps) in the tool, never in the LLM. The refusal is also the showcase recovery scenario.

### 5.4 Cancellable downgrade — core or stretch?
- 🟢 Suggested deferring it (a 5th tool).
- 🔵 **[User insisted]** Kept it as core (undo is a real user need). It reuses existing machinery (revert status, delete queued row), so low marginal complexity.
- ✅ `cancel_scheduled_downgrade` is a core tool. DELETE the queued row (never started → no history value) vs. marking it cancelled.

---

## PHASE 6 — `end_date`, Tools & Testing

### 6.1 The `end_date` redundancy debate (user's logic was right; my explanation muddied it)
- 🔵 Argued `end_date` is redundant — it's always `start_date + duration`, recomputable from catalog.
- 🟢 Initially pushed back badly, conflating two timelines (claiming proration "requires" the stored column) — user correctly called this out as mixing their proposed change with a separate issue.
- 🔵→✅ **[User was right on the logic]** Resolution: `end_date` **is** redundant *if never updated*, but **becomes non-derivable** once you stamp it on abrupt stops (a formula can't know a sub was cancelled early). So the stamping is what makes the column necessary.
- ✅ **Stamp `end_date = today` on abrupt stops** (immediate cancel/downgrade/upgrade); natural-term subs keep their real end_date. **Ordering rule:** date reads (proration) must precede date writes (stamp) on the same row.
- 💡 A stored fact that events can change is not redundant with a formula — the formula knows original inputs, not the events that changed them. (Same principle as `amount_paid`.)

### 6.2 Reset-per-test (I was wrong; user was right)
- 🟢 Pushed "reset the DB before every test" as a rule.
- 🔵 **[User was right]** Pushed back: the real eval runs on a *persistent* multi-customer DB where each task's ground truth is defined against accumulated state; resetting-per-test is a unit-testing reflex that doesn't fit an agent eval. Auto-append IDs (`lastrowid`) already prevent collisions.
- 🟢→ Conceded. Per-test reset is not required for eval correctness.
- 💡 Don't import a testing reflex that doesn't match the system's actual usage pattern.

### 6.3 Test ID collisions & the "pick a bigger number" hack
- Context: a test hard-coded `sub_id = 4` for a new customer, colliding with a row a *tool* had auto-created.
- 🔵 (via a pasted external-AI answer) Proposed dodging it by using `sub_id = 99` (a bigger number).
- 🟢 Rejected the hack: "pick an unused number" is the same disease (still assumes you know the IDs) — it just moves the collision. Also flagged that the pasted answer wasn't the user's own writing and that outsourcing the fix defeats the learning.
- ✅ **Never hard-code `sub_id` in test setup; let SQLite auto-assign and capture with `lastrowid`; wire linked rows with the captured ID.**
- 💡 Eliminate the shared state that caused the collision, don't guess an ID around it. (And: show your own attempt, don't launder another model's answer.)

### 6.4 Verify state, not return values
- 🟢 Flagged that early tests only printed the tool's *return dict*, not the DB state. A function can return `success` while committing wrong rows.
- 🔵→✅ (User adopted) Every tool test now queries the DB afterward and asserts the actual rows across all affected tables.
- 💡 A tool's return dict is its *claim*; the DB rows are the *truth*. This is the same skill the evaluator formalizes.

---

## PHASE 7 — The Evaluator

### 7.1 Database diffing rejected; scope-specific comparison
- 🟢 Raised the core problem: `sub_id`/`trans_id` auto-increment and differ every run, so raw row-diffing fails even for correct agents.
- 🔵 (User's solution) Don't generalize; go scope-specific — check two things a billing agent must protect: (1) money (full transaction history per user), (2) services (each user's subscriptions with correct dates), plus assert immutable tables (users-except-pointer, catalog, payment_methods) are unchanged and only affected users differ.
- ✅ Table-by-table comparison of *meaningful content*, IDs stripped.
- 💡 "Equivalent DB states" = same facts regardless of auto-assigned integers.

### 7.2 Array vs sum vs count+sum vs multiset (the comparison structure)
- 🔵 (User) Check the full transaction *array*, not just the sum — to catch redundancies (e.g. a bogus `-300/+300` pair nets to zero but is insane).
- 🟢 Confirmed array-not-sum is the key insight most people miss. But flagged **ordering**: `payment_date` is day-resolution and SQLite guarantees no row order without `ORDER BY`, and the only tiebreaker (`trans_id`) is volatile → no stable order exists. Pushed **multiset** (order-free) which *still* catches redundancy (extra elements).
- 🔵 (User) Proposed a **count+sum-per-day** compression — then *caught its own bug*: `[100,-20]` and `[2500,-2420]` share count and sum but differ in truth. Rejected it.
- ✅ **Multiset (`collections.Counter`) of content tuples**, IDs stripped.
- 💡 Order-independence via multiset sidesteps an unsolvable ordering problem while preserving redundancy detection. (And: stress-test your own compression — the user caught the count+sum flaw unprompted.)

### 7.3 Linking transactions to subscriptions (struct bundling)
- 🔵 (User) Proposed a multiset of **structs** bundling a transaction with its subscription — better than two independent multisets (which could pass a state where the right transactions attach to the wrong subs).
- 🟢 Sharpened: bind to the sub's **content, not `sub_id`** (or you re-introduce the volatile-ID problem). AND keep a **standalone subscription check** too — some subs have *zero* transactions (`scheduled_activation`, `scheduled_cancellation`), invisible to a transaction-only check.
- ✅ Transaction multiset uses `linked_sub` (content); plus a separate subscription-content multiset.
- 💡 Transactions↔subscriptions is many-to-one-with-zeros; the paired struct handles the "many," the standalone check handles the "zero."

### 7.4 Linkage key: `{plan_name, start_date}` → `{plan_name, start_date, end_date}`
- 🔵 (User) Argued `{plan_name, start_date}` is unique "because only one active sub at a time."
- 🟢 **[Advisor was right]** Rejected the reasoning: it constrains only *active* subs, not history. Same-day multi-churn produces two same-plan same-start subs (one cancelled/stamped-to-today, one active/running-to-term) → ambiguous. (This exact hole resurfaced as an interview question — "same-day churn".)
- ✅ **Linkage key = `{plan_name, start_date, end_date}`.** Residual (two subs identical in all three) is benign — byte-identical rows are genuinely fungible.
- 💡 Uniqueness must hold across a customer's *entire history*, not just active rows.

### 7.5 Evaluator bugs found by broken-case testing
- 🟢 Ran the evaluator against *deliberately broken* states (not just the correct solution). Found:
  - **Bug 1 (false pass):** `unchanged_tables` was silently skipped when `seed_db_path` was `None` → a corrupted catalog PASSED. Fix: **raise** if a seed is required but missing.
  - **Bug 3 (false fail waiting to happen):** float `==` on `amount_paid` → a proration like `166.66666…` vs `166.67` would mismatch. Fix: **round to 2dp on both sides** before comparing.
  - Bug 2 (awareness): `Counter` needs tuples, not raw `sqlite3.Row` objects (already converted).
  - Bug 4 (awareness, unfixed): a dangling `active_sub_id` LEFT-JOINs to NULL, identical to a legit NULL pointer.
- 🔵→✅ (User adopted) Fixed 1 and 3; also added **`(bool, reason)` return** (the debug-mode suggestion) so failures report which table diverged.
- 💡 **Prove the negative** — an evaluator must be tested on broken states (must return False), not only correct ones. A half-tested evaluator silently lies. (This is arguably the single most important eval lesson.)

---

## PHASE 8 — Ground Truth & Workflow

### 8.1 Generate-then-verify workflow
- Context: the user's first hand-written ground truth for the overlap task had wrong amounts (35/285 instead of 67.5/317.5), missing `end_date` fields, and a weaker `expected_active_plan` shorthand.
- 🟢 Established: **author seed + prompt + correct tool sequence by hand → RUN it → dump the DB = ground truth → sanity-check.** Never hand-compute amounts.
- ✅ This folds in the **proof-of-eval** step: the hand-written correct solution, scored against its own generated ground truth, must yield 100% — validating the evaluator before any LLM is involved.
- 💡 Hand-computed ground truth was wrong at least twice (mine and the user's). Generate it.

### 8.2 Ground-truth format refinements
- 🔵 First format used `expected_active_plan: "Starter"` (a plan name) and omitted `end_date` on subscriptions.
- 🟢 Changed to `active_sub_content: {plan, start, end}` (asserts the active sub's *identity* by content, not just "some Starter exists"); added `end_date` to every sub (including the stamped date on the dead sub); added explicit `unchanged_tables`.
- ✅ Locked the ground-truth JSON contract (see `design_decisions.md` §3).
- 💡 A shorthand that checks a *weaker* condition than the tool guarantees can hide a bug.

### 8.3 Seed snapshot timing (harness bug)
- 🔵 First harness passed a `seed_db_path` to the evaluator but never *created* the snapshot, and conceptually would have snapshotted at the wrong moment.
- 🟢 Flagged: the "unchanged tables" baseline must be the DB state **after seeding, before the solution runs** — a task may legitimately seed custom rows, and "unchanged" means unchanged *by the solution's actions*, not vs. the default reset state.
- ✅ Added `setup_db_for_task` (reset → seed → snapshot), a shared helper used by BOTH generation and evaluation so they can't diverge. Snapshot via `shutil.copy` after seed, before tools.
- 💡 The immutability baseline is post-seed/pre-solution, not the default seed state.

### 8.4 Frozen vs. live ground truth (regression-guard decision)
- 🟢 Raised: should ground truth be regenerated every run, or frozen to disk?
- ✅ **Frozen** — generated once at authoring, saved to `ground_truths/task_XX.json`, loaded by the runner.
- 💡 If GT were regenerated from the current tools every run, a tool that breaks would break its GT identically → the task still "passes" → regression undetected. Frozen GT makes the suite a regression guard: a behavior change now fails the frozen expectation.

### 8.5 Assert-success during generation
- 🔵 (User's addition) `correct_sequence` returns a list of result dicts; `generate_and_freeze_ground_truth` asserts every call's `success` and raises otherwise.
- ✅ A silently-failing correct-solution (e.g. a wrong date that gets refused) can no longer freeze a no-op state as "truth."
- 💡 A broken solution should fail loudly at authoring, not produce a self-consistent-but-wrong ground truth. (Note: `run_harness` does NOT assert success — correct in W3, where the agent is allowed to fail and the eval catches it via state mismatch.)

---

## PHASE 9 — The Task Suite & the Refusal-Task Discovery

### 9.1 Rich shared seed vs. minimal per-task seeds
- 🔵 Proposed one comprehensive seed state covering all cases, so no task needs its own starting node.
- 🟢 Rejected: (a) shared mutable state breaks task independence; (b) a rich seed makes ground truth HARDER — the evaluator checks the whole DB, so every task's GT must then assert the state of all bystander customers too. Minimal seeds keep GT small and focused.
- ✅ `reset_db` seeds a small stable baseline (Alice/Bob/Carl); each task adds only what it needs via `seed_sql`. Reusable seed *fragments* OK; one monolith not.
- 💡 Coverage lives in the tasks, not the seed. Small DB → small, verifiable ground truth.

### 9.2 File layout & naming
- ✅ `tools.py` (5 tools + helpers), `master_tools.py` (`reset_db(db_path)` — parameterized after a hardcoded-path mismatch risk was flagged), `evaluator.py` (grader: one state-pair → (bool, reason)), `runner.py` (proctor: Task class, setup, generation, run_suite), `tasks.py` (the Task objects), `ground_truths/*.json`.
- 💡 Evaluator vs runner split: the grader knows nothing about tasks/seeding; the runner orchestrates and *calls* the grader. In W3 only the runner changes (swap correct_sequence for agent.run) — the verified grading core is never touched.

### 9.3 First suite run — 9/15, and the refusal-task contradiction (CURRENT BLOCKER)
- Context: 15 tasks authored (happy paths, both cancel branches, anti-abuse cancel, overlap downgrade, scheduled downgrade, direction refusals, no-ops, undo, a multi-step chain). Generated GTs, ran the suite.
- **Result: 9/15 PASS. All 6 failures were refusal tasks, failing at GENERATION, not evaluation.**
- 🟢 Diagnosis: `generate_and_freeze_ground_truth` asserts every result `success=True` (added in 8.5 to catch broken solutions) — but a refusal task's *correct* outcome IS `success=False` with an unchanged DB. The 8.5 safety assertion and the existence of refusal tasks contradict each other. One assumption ("every correct solution mutates state") is false for a whole task class.
- 💡 A safety check built for one task class can silently outlaw another. "Correctly did nothing" is a legitimate, checkable ground truth (state == seed).
- **OPEN (my decision to make):** Option A — `expect_success` flag on Task; generator asserts refusal for refusal-tasks and freezes the unchanged state. Option B — additionally assert the refusal *reason*. And the hard sub-question: for ambiguous prompts ("Downgrade me to Enterprise"), is correct behavior refuse/clarify (GT = unchanged) or infer-and-upgrade (GT = upgraded)? This decides what the eval rewards in W3.
- **RESOLVED (9.6, 9.7):** Option A adopted for refusal semantics. Ambiguous-direction prompts resolved via smart recovery (agent routes by named plan, not verb), applied symmetrically to both `downgrade_plan` and `upgrade_plan`. Direction-guard code paths remain in `tools.py` but are now untested — off the correct-agent path, defense-in-depth only. Suite at 15/15.

### 9.4 What a single anti-abuse task can't prove
- 🟢 Flagged: one task landing in the delayed branch doesn't isolate the 90-day rule — the same outcome occurs when the charge is merely old. An anti-abuse task needs a *contrast twin* (identical except refund >90 days ago → immediate branch) so the outcome difference isolates the rule.
- ✅ Adopted for the coverage matrix: rules are proven by contrast pairs, not single tasks.
- 💡 A task tests a rule only if that rule is the only thing determining its outcome.

### 9.5 Prompt/sequence agreement
- Context: an early draft task had prompt "Cancel my plan" with a correct_sequence calling `downgrade_plan`.
- 🟢 Flagged: prompt and answer key must describe the same action — in W3 the agent reads the *prompt*, and doing the right thing for it would fail a mismatched GT.
- ✅ Fixed in the authored suite (cancel_03 now cancels). Rule: name, prompt, and sequence must all describe one scenario.
- 💡 A task where the question and the answer key disagree fails the correct student.

### 9.6 Resolving the refusal-task contradiction
- Context: 9/15 first run, all 6 failures were refusal tasks failing at generation (see 9.3).
- ✅ **Option A adopted.** Added `expect_success` (default `True`) to `Task`. `generate_and_freeze_ground_truth` now branches: `expect_success=True` + tool fails → raise (broken correct-solution, same as before); `expect_success=False` + tool succeeds → raise (a refusal task that unexpectedly mutated state is equally broken); otherwise freeze whatever state resulted. "Correctly did nothing" is now a legitimate, checkable ground truth.
- Option B (also assert the refusal's `reason` string) was considered and **not** taken — the DB-state check already proves the refusal happened and left no side effects; asserting exact reason text would couple the test suite to wording, not behavior. Reason strings stay a debugging aid, not a graded field.
- 💡 The fix was one flag, not new architecture — the generator's assumption was too narrow, not wrong in kind.

### 9.7 The ambiguous-direction question — smart recovery, not refuse/clarify
- Context: 9.3 also flagged the harder sub-question — for a wrong-tier prompt like "Downgrade me to Enterprise," is the correct end-state "refused, unchanged" or "agent inferred real intent and acted"?
- 🔵 **Decided: smart recovery.** The verb ("upgrade"/"downgrade") is treated as unreliable human phrasing; the agent routes off the named plan, not the word describing direction. A user saying "downgrade me to Enterprise" almost certainly means "put me on Enterprise," and refusing over word choice is punishing the customer for the eval's own pedantry, not for an actual error.
- 🟢 Pushback considered: doesn't this delete the tools' own direction-guard safety net? Countered — no. The guard in `tools.py` (`downgrade_plan` refuses if target tier is higher; `upgrade_plan` refuses if target tier is lower/equal) still exists in code and still fires if it's ever hit directly. It just isn't reachable by a *correctly-behaving* agent anymore, because the agent now checks tier itself before picking which tool to call and calls the right one. A future dev deleting that guard from `tools.py` would be removing a safety net with no test catching it — accepted as their mistake to own, the same way unprotected payment logic would be.
- ✅ Both `downgrade_plan` and `upgrade_plan` follow the same policy: agent resolves direction from the named plan, calls the correct tool, guard is defense-in-depth only.
- Applied consistently: `downgrade_03` ("Downgrade me to Enterprise") → agent calls `upgrade_plan`, `expect_success=True` (10 seats fits Enterprise's 100 cap, so recovery succeeds cleanly). `upgrade_02` ("Upgrade me to Starter") → agent calls `downgrade_plan`, `expect_success=False` (Alice's 10 seats exceed Starter's 5-seat cap — recovery is *attempted* correctly but the seat-cap guard, a separate and still-live rule, refuses it; DB stays untouched).
- **Caught a self-inconsistency mid-implementation:** an earlier pass changed `upgrade_02` to smart-recovery but left `downgrade_03` on the old direction-refusal expectation — same tools, same policy, opposite test verdicts, no stated reason. Fixed by reversing `downgrade_03` to match. Traced from a review question ("why does one tool refuse and the other recover for the same class of prompt?") rather than caught proactively.
- 💡 A policy applied to one tool and not its mirror-image sibling is a bug even if every individual test passes — check policy symmetry, not just per-task correctness.

### 9.8 Payment-refusal test was silently testing the wrong guard
- Context: `add_seats_03` was originally written against Carl (`prompt: "I need 5 more seats"`), intended to test the "no valid payment method" branch.
- 🟢 Flagged: `add_seats` checks for an active subscription *before* checking payment method, and Carl's `active_sub_id` is NULL — so the call actually fails on "No active subscription," identical to what `cancel_04` already tests. The payment-method guard had zero coverage, invisibly.
- 🔵 **[User's fix]** Reused Alice instead of adding a new seed customer: `seed_sql="UPDATE payment_methods SET status = 'expired' WHERE cus_id = 1;"` — active sub present, seat count (10→15) safely under Pro's cap of 20, so payment status is the sole thing that can fail the call.
- ✅ `add_seats_03` now on Alice, `expect_success=False`, isolates the payment guard for real.
- 💡 A duplicate-looking refusal task (same failure class as another task) is coverage theater — trace which `if` actually fired, don't assume the prompt's stated intent matches the code path it hits.

---

## PHASE 10 — W3: The Agent

### 10.1 Backend and architecture kickoff
- 🔵 Raw Anthropic Messages API with tool-use, no framework (LangGraph deferred) — deliberate choice to learn the tool-calling architecture firsthand before abstracting it away.
- 🔵 Agent gets the full toolset: all 5 write-tools **and** all read-tools initially considered, then narrowed (see 10.2).
- 🔵 System prompt: `policy.md` distilled into strict IF/THEN bullets, not pasted verbatim — shorter, less token cost, forces the policy into agent-actionable rules rather than prose.
- 🔵 Baseline defined as single conversational turn, full tool-loop within that turn: `while model_wants_to_call_tools: execute`. No self-correction (that's W4) — a refused write-tool is reported as final output, not negotiated.
- 🟢 Caught mid-definition: an initial phrasing ("agent calls a tool once") was self-contradictory — `chain_01` needs two sequential tool calls to reach its correct end state, so "once" would make that task structurally impossible regardless of agent quality. Corrected to "one turn, loop until the model stops requesting tools."
- ✅ Harness stays unified, no separate script: `run_suite` gained an `agent_mode` flag. `False` → existing `correct_sequence()` path (proof-of-eval, untouched). `True` → prompt goes to the agent; the agent's real tool calls hit the real DB; the same `evaluate_task` grades it either way.
- 💡 Same principle as 8.3 (evaluator/runner split) — the grading core doesn't change based on who produced the actions.

### 10.2 Read-tool exposure: encapsulation boundary and the seat/payment asymmetry
- 🔵 Full read-tool set considered (`get_customer`, `get_active_subscription`, `get_valid_payment_method`, `get_plan`, `get_last_transaction`, `get_last_refund`, `get_total_paid_for_sub`, `is_refund_applicable`).
- ✅ Narrowed to **`get_customer`, `get_active_subscription`, `get_plan`** only. Excluded: `get_total_paid_for_sub`, `is_refund_applicable`, `get_last_transaction`, `get_last_refund`, `get_valid_payment_method`.
- Reasoning: LLMs given financial/calculation helpers will "helpfully" attempt the math themselves (proration, refund totals) instead of trusting the tool — the exact failure mode `add_seats`/`cancel_subscription` were built to prevent by keeping money-math server-side (see 4.2, 4.6). State-checking tools (`get_active_subscription`, `get_plan`) are safe to expose because they only inform *routing* decisions (which tool to call, whether a cap will be hit), never *financial* ones.
- **Deliberate asymmetry:** `get_plan`'s `seat_cap` is exposed (agent can look ahead and negotiate seat counts — enables smart recovery), but `get_valid_payment_method` is hidden (agent must attempt the write and discover a payment failure via the tool's refusal, never pre-empt it). Justification: seat caps are a negotiable configuration the agent can route around; payment status is a binary hard-stop requiring human intervention (fix the card), not agent negotiation. Exposing payment status risked the agent inventing its own refusal wording instead of relying on the backend's exact enforcement.
- 💡 Not every guard needs the same visibility policy — the right question per guard is "can the agent productively act on this information," not "is more information always better."

### 10.3 `today` and `cus_id`: keeping simulated state out of the model's hands
- 🟢 Flagged: every write-tool takes `today` as a parameter (a W1 decision, 4.1/8.7 — never the real clock, for determinism). Naively exposing `today` as a tool-call parameter to the LLM would reintroduce exactly the non-determinism that design avoided — the model would have to guess or hallucinate a date.
- ✅ `today` stripped from every tool schema shown to Claude/Gemini. Injected at the dispatch site instead: `run_agent(prompt, cus_id, today=...)` takes it as a Python parameter, and the dispatcher adds it into the real function call only for the tools that need it (`TOOLS_NEEDING_DATE` set), invisible to the model.
- 🔵 An `inspect.signature()`-based auto-detection of which tools need `today` was proposed and rejected as needless indirection — which tools need a date is a known, fixed fact about the 5 write-tools, not something to discover generically at runtime.
- 🟢 Same reasoning applied to `cus_id`: an early draft hardcoded "only use customer ID 1 unless specified" into the system prompt as a workaround. Rejected — none of the task prompts state a customer ID (in a real product this comes from session/auth, not conversation text), so the hack would silently misroute any task against a customer other than 1. Fixed by making `cus_id` an explicit parameter to `run_agent`, mirroring `today`, sourced from `Task.cus_id` in the harness.
- 🟢 Caught a mutation bug: an early draft did `claude_args = tool_call.input` then mutated it in place to inject `today`, risking corruption of the API's own response object (which needs to be echoed back unmodified into conversation history on the next turn). Fixed to `claude_args = dict(tool_call.input)` — copy before mutate.
- 💡 Anything the eval needs to control deterministically (dates, identity) must be injected by the harness, never left for the model to infer or guess.

### 10.4 System prompt duplication — extracted to `policy_prompt.py`
- 🟢 Flagged twice: the full IF/THEN policy text was pasted inline into both `agent.py`/`agent_claude.py` and `agent_gemini.py`. Identical content, two copies, drift risk on any future policy wording change (same class of bug as the earlier `today` duplication, 9.x).
- 🔵 First fix attempt reverted accidentally in a later paste (regressed to inline duplication a second time) — caught by direct diff against the prior correct version, not by re-reading the whole file.
- ✅ `policy_prompt.py` holds one `get_system_prompt(cus_id, today)` function; both backend files import and call it. Single source of truth for policy wording across backends.
- 💡 Duplication bugs don't stay fixed by fixing them once — they need to be checked for on every subsequent paste, not assumed gone.

### 10.5 Dual backend: Claude blocked by billing, pivoted to Gemini
- Context: Claude Pro (chat subscription) does not grant API access — API billing is separate, pay-per-token, no free tier. Decided not to pay for API credit at this stage.
- 🔵 Pivoted to Gemini API (free tier available). Built `agent_gemini.py` as a parallel implementation, not a replacement — `agent_claude.py` kept intact for whenever API credit is added.
- Real architectural question resolved: **what actually needs duplicating for a second backend?** Only the API-calling logic (`agent_*.py`: schema format, client, request/response parsing, tool-loop mechanics) is backend-specific. `tasks.py` (prompts, seeds, expected outcomes) and the entire eval harness (`runner.py`, `evaluator.py`) are backend-agnostic and were correctly kept as single shared files — an earlier instinct to also duplicate `tasks.py` as `tasks_gemini.py` was rejected as pure drift risk with zero benefit.
- ✅ `run_suite` gained a `backend` parameter (`"anthropic"` | `"gemini"`), switching which `agent_*` module it imports. One harness, two interchangeable model backends.
- Format differences hit during the port: Gemini's function-calling schema uses lowercase JSON-Schema types (`"object"`, `"integer"`) rather than the initially-guessed uppercase (`"OBJECT"`, `"INTEGER"`); response parsing differs (`response.function_calls` / `finish_reason` vs. Anthropic's `stop_reason == "tool_use"` and content-block iteration); message history construction differs (`types.Content`/`types.Part` objects vs. plain dicts).
- 🟢 Caught a type-mixing bug: `messages = [prompt]` put a raw string as the first history entry while every subsequent append was a typed `types.Content` object — inconsistent types in one list consumed by the SDK. Fixed to `types.Content(role="user", parts=[types.Part.from_text(text=prompt)])` from the start.
- 💡 Switching LLM backends is cheap at the harness level (one parameter) and expensive at the SDK level (full schema/response/history format translation) — the architecture correctly isolated that cost to exactly two files.

### 10.6 Runaway-loop and error-handling hardening
- 🟢 Flagged: the tool-loop (`for _ in range(10)` in both backends) needed a hard iteration cap — an unbounded `while True` risks a stuck agent looping forever, unbounded API cost, and a hung suite run on one bad task instead of a clean fail-and-continue.
- ✅ Both backends cap at 10 iterations, returning `"AGENT ERROR: exceeded max tool-call iterations"` on exhaustion instead of looping forever.
- ✅ `run_suite`'s agent-mode branch wrapped in try/except — one API/network failure on one task no longer crashes the entire 15-task run; it's logged as a FAIL with the error and the suite continues.
- ✅ Agent's final text response captured and printed alongside any FAIL line — necessary for diagnosing *why* an agent-mode task produced the wrong DB state, since the return value was originally discarded.
- 💡 A harness meant to run unattended needs to survive a single bad call, not just handle the happy path.

### 10.7 First real agent-mode run: rate limits, then real findings
- Context: first full 15-task Gemini run hit `429 RESOURCE_EXHAUSTED` after 6 tasks — free tier capped at 15 requests/minute, and the tool-loop can burn multiple requests per task. 9 tasks failed on quota exhaustion, not correctness — confirmed by the identical error text repeating verbatim.
- ✅ Re-run after the quota window reset; all 15 tasks got a genuine attempt across two models (`gemini-3.1-flash-lite`, then `gemini-3.5-flash`).
- **Results: 13/15 on `gemini-3.5-flash`, 12/15 on `gemini-3.1-flash-lite`. Same two tasks failed on both models** — `downgrade_02` and `chain_01` — which points at a task-design flaw rather than model inconsistency (a real model bug would be expected to vary across models/runs, not repeat identically).
- **`downgrade_02` finding:** prompt is "Switch my plan to Starter" with no seat count stated. The agent correctly followed the system-prompt rule "do NOT preemptively adjust seat counts to avoid a cap" — it carried over Alice's 10 seats, hit the Starter seat-cap overflow, and correctly refused. But the frozen ground truth's `correct_sequence` hardcodes `seats=5`, an assumption the prompt never states and the system prompt explicitly forbids the agent from making on its own. **The task's ground truth contradicts the policy it's supposed to be testing.** OPEN — resolve by either rewriting the prompt to state the seat count (matching `downgrade_01`'s pattern) or flipping `expect_success=False` with unchanged-state ground truth (matching `upgrade_02`'s refusal precedent).
- **`chain_01` finding:** prompt is "I need 15 total seats, and upgrade me to Enterprise." Ground truth's `correct_sequence` does two calls (`add_seats(5)` then `upgrade_plan(seats=15)`), producing a `seat_add` transaction plus an `upgrade` transaction. The agent instead called `upgrade_plan(seats=15)` directly in one call — `upgrade_plan` already accepts and validates an explicit seat count on its own, so this is a shorter valid path to a state that *satisfies the stated user goal* ("15 total seats, Enterprise") but produces a **different transaction ledger and a different charge**, because the upgrade's prorated credit is computed against the *pre-add* seat count (10) instead of the *post-add* count (15) the two-step path would have reached. **Open design question, not a bug:** does "I need 15 total seats, and upgrade me" have one correct interpretation (the explicit two-step path) or two equally valid ones (any sequence reaching 15 seats on Enterprise, regardless of ledger shape)? OPEN — this is the sharpest test yet of the "final-state, not trace" principle (8.2/9.2): two genuinely different final states both plausibly satisfy the same prompt, and the evaluator is correctly distinguishing them as unequal. Needs a decision on which final state — or whether both — should count as correct.
- 💡 An agent surfacing a contradiction between your policy and your own ground truth is a **more valuable finding than a clean pass** — it means the eval caught an authoring bug before it could hide behind a false "correct" label. This is what proof-of-eval (8.1) is *for*, just discovered one layer later than expected — at agent-mode time instead of hand-sequence time, because a real LLM will exploit ambiguities in prompt/ground-truth alignment that a hand-written `correct_sequence` never surfaces (a human author only ever writes toward the ground truth they already have in mind, never against it).

### 10.8 Closing the two OPEN findings — a false lead, then the real fixes
- Context: attempted to debug `downgrade_02` and `chain_01` further using an ad-hoc `debug.py` script that printed ground truth against live `billing.db` state.
- 🟢 **False lead caught before acting on it:** the debug output appeared to show `downgrade_02`'s ground truth mismatching a completely different final state (Enterprise, 15 seats, `06-20`→`07-20`) — which is actually `chain_01`'s end state, not `downgrade_02`'s. Root cause: the debug script never called `setup_db_for_task` before inspecting, so it read `billing.db` as left over from whatever task last ran in the prior full-suite invocation — comparing `downgrade_02`'s GT against stale data from an unrelated task. A second script compounded this by comparing an unfiltered whole-table ground truth against a `WHERE cus_id=1`-filtered actual query, guaranteeing a spurious mismatch regardless of correctness.
- 🔵 A theory built on this bad data (external suggestion: "your `today` dates differ between GT-gen and agent-run, and `upgrade_plan` now internally absorbs seat-add costs the old GT didn't expect") was **rejected without testing** — traced the actual printed rows first and found they belonged to the wrong task before accepting any causal story built on them. Its prescribed fix (delete `ground_truths/` and blanket-regenerate everything from current code) was correctly not applied — that would have silently defeated the frozen-GT regression-guard property (8.4/9.4) by making every future tool bug regenerate its own "correct" answer instead of being caught by it.
- ✅ **`downgrade_02` fix:** prompt rewritten to state the seat count explicitly — `"Switch my plan to Starter, dropping to 5 seats."` — matching `downgrade_01`'s pattern. `correct_sequence` (`seats=5`) and the frozen ground truth were already correct; only the prompt was out of alignment with the system prompt's "don't preemptively adjust seats" rule. No regeneration needed.
- ✅ **`chain_01` fix:** kept the two-step ground truth (`add_seats` then `upgrade_plan`) as canonical rather than rewriting it to match the agent's single-call shortcut. Verified first that both paths charge an identical total (541.67) — confirming this was a ledger-*shape* disagreement, not a money bug, before deciding how to resolve it. Added an explicit `MULTI-STEP REQUESTS` rule to `policy_prompt.py`'s `EXECUTION RULES`: separate stated actions get separate, sequential tool calls, executed in the order the user stated them, with "total count" targets converted to a delta from current state before the corresponding call. This closes the sequencing gap a looser first draft of the rule left open (an agent could satisfy "don't consolidate" while still reordering the two calls, changing the proration math).
- ✅ Full 15-task suite re-run after both fixes, on Gemini: **15/15.**
- 💡 A debug script needs the same setup discipline as the real harness (`setup_db_for_task` before inspection) — skipping it doesn't just risk a wrong answer, it risks a *plausible-looking* wrong answer that leads straight into a destructive "fix."
- 💡 When an external diagnosis prescribes an action that would undo a previously-established safeguard (here: frozen GT as regression guard), that's a signal to re-verify the diagnosis from raw evidence before acting, not a signal to trust the confidence of the explanation.

---

## PHASE 11 — The Post-W3 Crisis: Is This Project Even Hard?

### 11.1 The 15/15 crisis
- Context: after closing the two OPEN findings (10.8), the full suite hit 15/15 on Gemini. Instead of feeling like a milestone, this triggered a genuine confidence crisis: if the agent passes everything, did the project pose no real difficulty? Is there any work left that demonstrates skill rather than luck?
- 🟢 Reframed: 15/15 on a well-constrained, tool-enforced, atomically-committed system is not evidence the *project* was easy — it's the expected outcome of the central architectural bet made all the way back in Phase 2 (tools enforce, agent orchestrates). A system engineered so the agent structurally cannot mischarge or overwrite money-critical state, passing cleanly, is the design working as intended, not a sign of low difficulty.
- 🔵 Countered: also flagged honestly (not talked out of it) that the suite itself had quietly gotten *easier* over the session — the one genuinely hard, underspecified task (original `downgrade_02`, no seat count stated) was resolved by making the prompt explicit rather than by making the agent smarter. That's a legitimate fix for a ground-truth/policy contradiction (10.8), but it also removed the only task in the suite that could have exposed a baseline agent's real limitation (inventing information vs. asking for it).
- ✅ Conclusion held: the eval harness, the money-correctness architecture, and the decision trail are the actual differentiator and don't depend on the agent struggling. But the 15-task suite, as it stood, contained nothing a modern tool-calling LLM finds difficult — so 15/15 was true but not informative about robustness. Fix is more/harder tasks, not doubt about the project's foundation.
- 💡 A passing eval and an *informative* eval are different properties. A suite can be 100% deterministic, 100% correct, and still tell you almost nothing if every task is easy for the thing being tested.

### 11.2 Rejected: "PendingAction" HITL proposal, taken at face value
- Context: an external suggestion proposed reviving the agent's ability to ask a clarifying question (the original, since-removed `downgrade_02` behavior) via a `PendingAction` response type returned by `downgrade_plan` instead of executing, framed as a simple, resume-once-validated HITL flow.
- 🟢 Rejected as understated, not as wrong in spirit. Two concrete problems the proposal didn't address:
  1. Every write-tool's contract is currently binary (`success: True/False`), and that binary is load-bearing in `generate_and_freeze_ground_truth`'s assertion logic and in `evaluate_task`'s DB-state grading. A third response type isn't a one-tool edit — it requires deciding how ground truth and grading handle a task that hasn't produced any DB delta yet, which is a second design layer, not a patch.
  2. "Resumes once validated" assumes a mechanism to receive a follow-up answer and continue the same conversation. `run_agent` is currently single-call, single-turn — no such resumption path exists. The proposal stated the desired *behavior* without acknowledging the *mechanism* doesn't exist yet.
- 🔵 Also rejected, separately, a suggestion in the same exchange to add "prevent a downgrade causing negative balance" as a difficulty axis — checked against the actual schema (`design_decisions.md` §2) and confirmed there is no balance/credit concept anywhere in the 5 tables; the suggestion wasn't grounded in the system as built.
- ✅ Scoped down instead: two real options were identified — (A) redefine "correct" for an ambiguous-input task as *asking and stopping*, single-turn, cheap to build now; (B) build genuine multi-turn resumption (a second call into the same history, answered by a scripted or simulated follow-up, graded after the second turn) — explicitly the existing `future_work.md` item #6 (user-simulator), not new scope. Chose (A) as fresher-appropriate; (B) deferred, not abandoned.
- 💡 A confident-sounding proposal that names the *desired outcome* isn't the same as one that names the *mechanism* — check for the second before agreeing the first is "just a small change."

### 11.3 Resume framing — rejected "audit-compliant" language
- 🟢 Flagged that phrases like "Audit-Compliant Transaction Chaining" invite a depth of interview questioning (formal audit-log guarantees, immutability proofs) the project doesn't actually implement — the real claim is narrower: sequential tool calls preserve per-event ledger rows (§8.5's "ledger is the record of what happened" principle), nothing more.
- ✅ Decided: describe the project in terms defensible from the actual `decision_log.md` — the refund bug found by running code (4.3), the linkage-key fix (7.4), the frozen-GT regression-guard reasoning (8.4), and the debug-script false lead caught before acting on it (10.8) — rather than marketing-style bullet phrasing.
- 💡 A resume bullet should never claim more precision than the interviewer's obvious follow-up question could survive. As a fresher, the honest story (what broke, how it was found, what was learned) is stronger than an inflated one.

### 11.4 Is checking Gemini's raw tool result "cheating," and is this "better than τ-bench"?
- 🔵 Asked whether reading the tool's raw `{"success": False, "reason": ...}` dict — captured server-side, before it's sent to Gemini — counts as giving the agent unfair help, similar to or better than τ-bench methodology.
- 🟢 Clarified: not cheating — the agent's decisions and information are unaffected either way; this is a pure evaluation-side observation. But it **is** a real methodological shift: the evaluator's whole design (§1.4, §9.2) is deliberately final-state / trace-independent, explicitly to avoid over-constraining valid alternate tool orderings. Using the captured tool-call log to gate pass/fail on refusal *category* reintroduces trace-sensitivity for that task class. Not an upgrade to τ-bench's approach — a deliberate, narrow departure from your own stated philosophy, worth logging as an explicit exception with its own rationale if implemented, not framed as "strictly better."
- 🔵 Pushed for genuine, non-buzzword differentiators from standard final-state eval methodology. 🟢 identified four defensible ones without hype: (1) refusal tasks treated as first-class, generated ground truth ("correctly did nothing" is graded, not skipped) — most task suites underweight this; (2) the false-positive refusal gap is *named and understood*, whether or not closed; (3) contrast pairs to isolate single-variable rules (90-day anti-abuse, §9.4) — deliberate experimental-design rigor; (4) proof-of-eval and prove-the-negative discipline (§7.5) — testing the grader on broken states before trusting it on any agent, which most benchmarks skip.
- 💡 "Better than a published benchmark" is rarely a claim a fresher project can make and defend. "Same paradigm, unusually careful about negative-case coverage, and honest about its own blind spots" is true, specific, and survives scrutiny.

### 11.5 Building the TP/FP/FN/TN classification for this evaluator
- 🟢 Laid out the four-quadrant framework (evaluator verdict vs. actual agent correctness) with concrete examples from the project's own history: TP (`add_seats_01`), TN (pre-fix `chain_01` consolidation, correctly caught), FN (pre-fix `downgrade_02` — policy-compliant agent wrongly failed by a bad ground truth), FP (wrong-reason refusal — agent hallucinates a refusal for a reason unrelated to the actual tool logic, DB still ends up unchanged, evaluator passes it anyway because final-state grading can't see reasoning).
- 🟢 Flagged the core asymmetry: FNs in this system get **discovered and fixed** (a failing task forces investigation — both real project FNs surfaced exactly this way), but FPs are **silent** — nothing prompts investigation of something that already passed. Refusal/no-op tasks are structurally the highest-FP-risk class.
- 🔵 **[User's own deduction, verified correct]** Reasoned through the framework independently and proposed a cleaner formulation: negatives always arise from a genuine DB difference (further split into TN — real bug — and FN — either the tools' own logic is wrong and fixable, or nothing was written but the choice was reasonable, both cases visible and fixable); positives mean *no* DB difference (TP — correct as predicted; FP — restricted to exactly one case, since any wrong DB mutation would necessarily be caught by the multiset diff unless the ground truth itself is broken, which is separately guarded against). Concluded FP can only occur when there's no DB transaction, and that a path/reason check is therefore justified precisely and only for that one case — not over-engineering, a correctly bounded exception.
- 🟢 Verified the claim before accepting it: checked whether a duplicated or malformed write could still net out to an FP with zero DB difference. Confirmed it can't, specifically *because* of the multiset (count-preserving, not sum-collapsing) design chosen back in 7.2/9.2 — a duplicate write shows up as an extra element, not a hidden one. The user's deduction holds, and holds *because of* an earlier, separate design decision — the two are linked, not coincidental.
- 💡 The FP-boundary proof is a direct payoff of the count-preserving multiset decision made in W2; a design choice made for one reason (catching redundant transactions) turned out to also be what makes a much later methodological claim (FP is fully bounded) provable rather than assumed.

### 11.6 The no-write case is not one bucket — it's two, and only one is checkable
- 🔵 Initially conflated "no DB write occurred" with "refusal" as a single case for path-checking purposes.
- 🟢 Split it: sub-case A is *the write-tool was called and refused* — a structured `{"success": False, "reason": ...}` object exists in `run_agent`'s own execution, captured for free, no NLP required (10.4's earlier finding, re-surfaced). Sub-case B is *no write-tool was called at all* — no structured artifact exists, only the agent's free-text response, which was already correctly ruled out as non-deterministic to parse.
- 🔵 **[User's second deduction, verified correct]** Re-examined sub-case B and observed it doesn't actually need prose-parsing at all: whether a write-tool appears anywhere in the captured `tool_log` is itself a fully deterministic, structural check (`any(call.name in WRITE_TOOLS for call in tool_log)`) — independent of what the agent said. If no write-tool was ever called, that's an automatic fail regardless of reasoning quality, since every task in the suite has a required write-tool as its target and the suite deliberately excludes pure-read tasks. Read-tool calls preceding a genuine attempt are correctly not penalized — only the total absence of the required write-tool call is disqualifying.
- ✅ Resolved three-way split for any task expected to write: (1) wrote to DB → existing multiset evaluator decides pass/fail, untouched; (2) write-tool called, refused → compare the raw `reason` string's category against an expected tag (deterministic, no NLP); (3) write-tool never called → automatic fail, no reason-check needed or possible. All three are fully deterministic; none require reading or trusting the agent's free-text output.
- **OPEN implementation question:** how "expected refusal category" is represented per task for case (2) — e.g. a keyword/substring tag (`"seat_cap_overflow"`) matched against the raw tool `reason` string — decided in principle, not yet coded.
- 💡 A case that looks like it needs natural-language understanding sometimes only needs a better structural question asked of data you already have. The instinct to reach for NLP was the wrong reflex, not because NLP is inherently non-deterministic in all forms, but because the actual question ("was tool X ever called") never required reading prose at all.

---

## PHASE 12 — Building the Refusal-Category Gate (Workstream A, Implemented)

### 12.1 `tool_log` capture — both backends
- ✅ Both `agent_claude.py` and `agent_gemini.py` now initialize `tool_log = []` outside the tool-loop, append `(tool_name, result)` for every executed tool call (success or caught exception, both logged as a real dict), and return `(final_text, tool_log)` instead of just text. Identical shape in both backends, matching the pattern already established for `today`/`cus_id` injection and system-prompt sharing — backend-specific mechanics, shared architecture.
- 💡 The raw tool-result dict was always available inside `run_agent` before this — it's what gets serialized and sent back to the model as a `tool_result`. Capturing it required no new capability, only remembering to keep a reference to something already being computed.

### 12.2 `runner.py`: the three-way gate, and two bugs found by actually running it
- ✅ `Task` gained `expected_refusal` (a keyword/substring tag, e.g. `"cap"`, per refusal task) alongside the existing `expect_success`.
- ✅ `run_suite` (agent-mode branch) implements the three-way split designed in 11.6: (1) a write-tool succeeded → existing `evaluate_task` multiset grading, untouched; (2) a write-tool was called and refused → compare each refusal `reason` string against `t.expected_refusal` via substring match, pass only on a real match, not on "any refusal happened"; (3) no write-tool call appears anywhere in `tool_log` → automatic fail.
- 🟢 **Bug 1 (regression, caught before merging):** the three-way gate was initially written to run unconditionally, but `tool_log` is only ever populated inside the `agent_mode` branch — `correct_sequence()` (used when `agent_mode=False`) calls `tools.py` functions directly, bypassing the dispatcher and the log entirely. Running the deterministic W2 baseline (`agent_mode=False`) would have silently failed every task with "Agent failed to attempt any required write-tool action" — breaking the regression-check pathway that's supposed to always pass as a sanity check on the eval logic itself. Fixed by wrapping the whole three-way gate in `if agent_mode: ... else: t.correct_sequence(t.today)`, restoring the old direct-execution path exactly as it worked pre-Workstream-A.
- 🟢 **Bug 2 (incomplete implementation, caught before merging):** the first working draft's Case 2 branch checked only `if refusal_reasons: passed += 1` — it detected *that* a write-tool refused, but never compared the reason against `t.expected_refusal`. This passed on any refusal, from any write-tool, for any reason — reopening the exact false-positive gap the whole mechanism was built to close (an agent refusing for a wrong or unrelated reason would still show as PASS). Fixed by adding the actual `t.expected_refusal.lower() in reason.lower()` match, with a fallback (unconditional pass) only for tasks that don't yet define `expected_refusal`.
- 🟢 **Bug 3 (rate-limit regression):** `time.sleep(2)` between agent-mode tasks was originally placed only at the very end of the loop body, reachable only via the Case 1 fall-through path. Every `continue` inside the three-way gate (Cases 2 and 3, both pass and fail sub-branches) skipped it entirely — reopening the `429 RESOURCE_EXHAUSTED` risk (10.7) specifically for refusal-heavy runs, which is the task class this whole mechanism targets most. Fixed by wrapping the per-task body in `try:`/`finally:`, guaranteeing the sleep fires on every exit path regardless of which case a task hits.
- 🟢 **Bug 4 (crash, found by running against a live model, not by review):** first live run crashed on `cancel_04` with `AttributeError: 'NoneType' object has no attribute 'get'`. Cause: the write/refusal filter comprehensions ran `res.get(...)` inside an `if` clause that executed before the `name in WRITE_TOOLS` check — so a logged read-tool call whose result was `None` (a documented, deliberate return value of `get_active_subscription` when no active sub exists, not a bug) crashed the filter before it ever got to check whether the entry was even a write-tool call. Fixed by moving `name in WRITE_TOOLS` and a `res is not None` guard to the front of each `and`-chained condition, short-circuiting before any `.get()` call. 💡 A structural design (raw tool_log, real dicts) surfaced an existing contract (`None` on empty reads) at a new layer for the first time — not a new bug in `tools.py`, a new *consumer* of an old, correct behavior that hadn't been exercised this way before.

### 12.3 The `cancel_04` finding — read-based self-determination is the same failure mode as the payment case, applied without noticing
- Context: after fixing bugs 1–4, full suite ran 14/15 — every task passed except `cancel_04` (Carl, no active subscription), which failed Case 3 ("never attempted a write") despite the agent reaching a correct real-world conclusion (nothing to cancel).
- Investigation: the agent called `get_active_subscription(cus_id=3)`, received `None`, and — reasonably, given the system prompt's instruction to inspect state before acting — concluded there was nothing to cancel and never called `cancel_subscription` at all. Correct outcome, but the new Case 3 check can't distinguish "gave up without trying" from "correctly determined via a read that the write would be pointless," because both produce zero write-tool calls in the log.
- 🟢 Initially framed as a genuine open design tension requiring a new decision — proposed two options: force the write always, or loosen Case 3 to accept a qualifying read-tool result as a pass condition.
- 🔵 **Corrected: this wasn't a new decision — it was already made, in a different place, and not recognized as applying here.** §11.4/12.4's `get_valid_payment_method` exclusion established the exact rule needed: payment validity is a hard, binary, non-negotiable precondition, so the agent is required to attempt the write and let the tool's refusal be authoritative, rather than pre-judging the outcome from a read and skipping the call. "No active subscription to cancel" is the same shape — binary, non-negotiable, nothing to propose or retry, readable in advance — and should have been governed by the same rule from the start. The gap wasn't a new problem; it was an old rule not yet generalized to a second case it always covered.
- ✅ **The actual reason forcing the write matters, and is worth stating precisely, not just as "consistency with an old rule":** the agent's read-based judgment could be wrong in ways the tool would catch and it wouldn't. `get_active_subscription` returning `None` happens to be a reliable signal in this specific case, but the whole point of "tools enforce, agent orchestrates" (Phase 2, the project's first architectural decision) is that business-rule correctness lives in the tool, not in the model's inference. Letting the agent self-determine "this will fail" based on a read starts eroding that boundary case-by-case — today it's a reliable read, but the pattern of trusting agent inference over tool enforcement is exactly the thing the whole architecture was built to avoid normalizing.
- ✅ Added a generalized rule to `policy_prompt.py`'s `EXECUTION RULES`, worded to preserve the seat-cap lookahead behavior (still fine — read informs *how* to call a write-tool) while forbidding read-based skipping of the call entirely: *"Read-tool results inform how you call a write-tool (e.g. choosing a valid seat count), but never whether you call it. Even if a read-tool suggests an action will fail, you must still attempt the corresponding write-tool call. The tool's refusal is the authoritative source of truth — do not skip a write based on your own inference."*
- ✅ Verified in isolation first (single-task test script, not the full suite) — confirmed the agent now reads, then still attempts `cancel_subscription`, and receives the structured refusal. Full 15-task suite re-run after: **15/15**, all refusal tasks now genuinely category-matched, not just DB-unchanged.
- 💡 A rule made for one case (payment) doesn't automatically get recognized as applying to a structurally identical second case (subscription existence) just because it's logically implied — it has to be actively checked against new failures as they appear, not assumed to already cover them.

---

## Meta-lessons (the through-lines, for the "what did you learn" question)
1. **Single source of truth** — a stored fact events can change is not redundant with a formula (`amount_paid`, `end_date`).
2. **Generate, don't guess** — running the tool beat mental math twice; the ledger remembers what you charged even when you don't.
3. **Tools enforce, agent orchestrates** — the refusal creates the agent's recovery skill.
4. **Scope discipline** — every cut (renewal engine, fine-tuning, payment gateway) protected the timeline.
5. **State earns its place** — five statuses, each produced by an agent action.
6. **Verify state, not return values** — the return dict is a claim; the rows are truth.
7. **Prove the negative** — test the evaluator on broken states, not just correct ones.
8. **Don't let an out-of-scope edge block an in-scope decision** — the renewal case nearly derailed the 7-day rule.
9. **Uniqueness must hold across all history, not just the active row** — the linkage-key fix.
10. **Fix the cause, not the symptom** — auto-assign IDs vs. guessing a bigger number.