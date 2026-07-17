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

### 9.4 What a single anti-abuse task can't prove
- 🟢 Flagged: one task landing in the delayed branch doesn't isolate the 90-day rule — the same outcome occurs when the charge is merely old. An anti-abuse task needs a *contrast twin* (identical except refund >90 days ago → immediate branch) so the outcome difference isolates the rule.
- ✅ Adopted for the coverage matrix: rules are proven by contrast pairs, not single tasks.
- 💡 A task tests a rule only if that rule is the only thing determining its outcome.

### 9.5 Prompt/sequence agreement
- Context: an early draft task had prompt "Cancel my plan" with a correct_sequence calling `downgrade_plan`.
- 🟢 Flagged: prompt and answer key must describe the same action — in W3 the agent reads the *prompt*, and doing the right thing for it would fail a mismatched GT.
- ✅ Fixed in the authored suite (cancel_03 now cancels). Rule: name, prompt, and sequence must all describe one scenario.
- 💡 A task where the question and the answer key disagree fails the correct student.

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