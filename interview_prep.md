# Interview Prep — Non-Trivial Questions on the Billing Agent Eval Project

Questions an interviewer might use to probe depth, each with: what they're really testing, a strong answer, and (where relevant) the underlying concept explained from scratch. The **Scalability** section teaches the concepts, since that's the weakest area.

> **Meta-strategy:** for many of these, the strongest answer names *when NOT to do something* — the scalable version AND why this project doesn't need it. Over-engineering is a red flag; calibrated judgment is the signal.

---

## A. SCALABILITY & PERFORMANCE (concept-teaching section)

You said you don't know how scaling works. Here are the concepts you actually need, each tied to a question they'd ask.

### Concept 1: Time complexity (Big-O) — "how does cost grow with input size?"
Big-O describes how runtime/memory grows as input `n` grows, ignoring constants.
- **O(1)** — constant. A dict/hash lookup. Doesn't grow with n.
- **O(log n)** — halving each step. Binary search, balanced-tree operations.
- **O(n)** — linear. One pass over n items. A `SELECT` scanning n rows.
- **O(n log n)** — sorting.
- **O(n²)** — nested loops over the same data. The thing to avoid.

**Q: "Your evaluator compares two DB states. What's its time complexity?"**
> "It's O(n) in the number of rows: I read each table once, build a hash-multiset (`Counter`) of content-tuples per table — each insert is O(1) average — then compare with a single dict equality, also O(n). No nested loops, so it's linear. For a test fixture of hundreds of rows, it's effectively instant."

### Concept 2: Database indexes — "how does a query find rows without scanning everything?"
Without an index, `SELECT * WHERE cus_id = 5` **scans every row** (O(n)) — a "full table scan." An **index** on `cus_id` is a sorted structure (B-tree) the DB keeps alongside the table, letting it jump to matching rows in O(log n) instead of O(n). Cost: indexes use extra space and slightly slow writes (the index must update too).

**Q: "A B2B customer has 100,000 transactions. Your `get_total_paid_for_sub` does a `SUM ... WHERE cus_id=? AND sub_id=?`. Does that scale?"**
> "As written it's a full scan — O(n) per call — because there's no index. At my test scale (hundreds of rows) that's fine. For 100k rows per customer I'd add a composite index on `(cus_id, sub_id)`; the query then uses the index to find just that customer's rows in O(log n) + the number of matching rows, instead of scanning the whole table. One line: `CREATE INDEX idx_txn_cust_sub ON transactions(cus_id, sub_id)`. But I wouldn't add it preemptively — indexes cost write-speed and space, and my benchmark DB will never hit that scale."

### Concept 3: The N+1 query problem — "are you hitting the DB in a loop?"
If you fetch a list of N things, then loop and fire one query *per* thing, that's N+1 queries (1 for the list + N for the details). Slow because each query has round-trip overhead. Fix: fetch everything in one query (a `JOIN` or `WHERE id IN (...)`).

**Q: "Your evaluator loops over customers and queries each one's transactions separately. Is that a problem?"**
> "That's an N+1 pattern — one query per customer. At tens of customers it's negligible. At scale I'd pull all rows in a single ordered query and group them in memory, turning N+1 queries into 1. But again, for a bounded eval fixture the round-trip cost is irrelevant; I'd only refactor if profiling showed it mattered."

### Concept 4: Memory — in-memory vs streaming
Loading everything into memory (a full multiset) is fine for small data. For huge data you **stream**: process rows one at a time, keeping only an aggregate, so memory stays O(distinct values) not O(all rows).

**Q: "A multiset holds every element in memory. What if there are 100k events per user?"** (the exact question you got)
> "Wrong altitude for this project — the evaluator runs over a test fixture of hundreds of rows, so multiset memory is trivial. If I genuinely needed production-scale comparison, I wouldn't materialize full multisets; I'd stream each side into a hash of `(content-tuple → count)` in a single O(n) pass, giving O(distinct rows) memory. But building that for a benchmark that will never see 100k rows would be over-engineering."

### Concept 5: Vertical vs horizontal scaling (general literacy)
- **Vertical** = bigger machine (more RAM/CPU). Simple, has a ceiling.
- **Horizontal** = more machines, split the load (sharding data, load-balancing requests). Scales further, adds complexity (coordination, consistency).
You likely won't need to *design* this, but know the terms. For your eval, neither applies — it's a single-process offline script.

### Concept 6: Connection handling
Opening a DB connection has overhead. Your tools open/close a connection per call — fine at low volume. High-throughput systems use a **connection pool** (reuse a fixed set of open connections). Worth *mentioning* you know it exists; not worth building for an eval.

**Q: "You open a new SQLite connection on every tool call. Concern?"**
> "At eval volume, no — SQLite connections are cheap and it keeps each tool self-contained. A high-throughput service would use a connection pool to avoid per-call setup cost, but that's a production concern my harness doesn't have."

---

## B. EVALUATION METHODOLOGY (the heart of the project — know these cold)

**Q: "Why compare final state instead of the sequence of actions the agent took?"**
> "Final-state evaluation, like τ-bench. Multiple valid tool-call orderings can reach the same correct end state, so grading the path would reject correct solutions. I verify *what's true at the end*, not *how it got there*. Order-independence is a feature, not a gap."

**Q: "Same-day multi-churn — how do you track the correct transitions?"** (the "rock")
> "Two separate things. **Transition order** I intentionally don't verify — it's final-state eval, and many valid paths reach one end state. **Final-state identity** I resolve by keying each subscription on content — `plan_name + start_date + end_date` — so even two same-day same-plan subs are distinguishable by end_date. IDs are stripped because they're non-deterministic across runs."

**Q: "Why a multiset and not a sorted list?"**
> "Transactions can share a `payment_date` (day resolution only), and SQLite guarantees no row order without ORDER BY, and the only tiebreaker (trans_id) is non-deterministic across runs. So no stable total order exists. A multiset is order-free, avoiding that entirely, and it *still* catches redundant transactions — a bogus `-300/+300` pair shows up as extra elements versus ground truth."

**Q: "How do you know your evaluator itself is correct?"**
> "Proof-of-eval: I hand-write the correct tool-call solution for each task, generate the ground truth by *running* that solution and dumping the DB, then score the same solution against it — it must yield 100%. If a known-correct solution doesn't pass, the evaluator's comparison logic is broken, and I catch that before any LLM is involved. I found a real bug this way — a hand-computed ground truth had the wrong refund amount and would have failed the correct tool."

**Q: "Isn't stripping IDs losing information?"**
> "The IDs carry no semantic meaning — `sub_id=4` vs `sub_id=7` is an auto-increment artifact, not a fact about the customer's state. Two DB states are *equivalent* if they represent the same facts regardless of which integers got assigned. Content is the identity; IDs are noise for comparison purposes."

**Q: "What's your metric, and what does 'success' mean per task?"**
> "Task-success rate: fraction of tasks where the final DB state exactly matches ground truth (all tables, IDs stripped). Binary per task — pass/fail, no partial credit — because a billing action that's 90% right is still wrong. My headline is the delta: baseline vs. after adding a self-correction loop."

---

## C. SYSTEM DESIGN / ARCHITECTURE

**Q: "Why put the business rules in the tools instead of the agent's prompt?"**
> "LLMs are non-deterministic — the same prompt can behave differently across runs. If the model is the last line of defense against overselling seats or mischarging, correctness is a coin flip. Tools enforce the invariants deterministically; the agent orchestrates — decides what to attempt, reads refusals, recovers. The tool's refusal is actually what creates the agent's most valuable skill: recovery."

**Q: "How did you decide tool granularity?"**
> "Each tool is one meaningful, self-protecting business action — `add_seats`, `cancel_subscription`. Too coarse (`handle_everything`) leaves the agent nothing to reason about; too fine (`write_one_row`) pushes business logic up into the LLM. The right grain gives the agent composable primitives while keeping money-logic in code."

**Q: "How does the agent handle a tool refusal — walk me through it."**
> "Say a downgrade would leave more seats than the new plan's cap. The tool refuses with a structured reason naming the cap. The agent reads that, asks the user how many seats to keep, then retries with an explicit count. That refuse → ask → retry loop is the core agentic behavior, and it only exists because the tool enforced the cap rather than silently truncating."

---

## D. CORRECTNESS & CONCURRENCY

**Q: "What happens if your tool crashes halfway through — say after the refund but before updating seats?"**
> "Each write-tool wraps its mutations in a single database transaction — all the `execute`s, then one `commit`. If anything raises before the commit, I roll back, so the DB is never left half-updated (charged-but-not-provisioned, or vice versa). It's atomic: all-or-nothing."

**Q: "Two requests for the same customer arrive at once. Race condition?"**
> "My eval is single-threaded and sequential, so no concurrent access occurs — out of scope by design. In a real system this is a genuine concern: two `add_seats` could both read seats=3 and both write 6, overselling. You'd handle it with row-level locking (`SELECT ... FOR UPDATE`) or optimistic concurrency (a version column checked on write). I'd note it as a production hardening step, not something the benchmark needs."

**Q: "Why store `amount_paid` when you could recompute it from seats and price?"**
> "Because it's a recorded fact that events can change. Seat-adds are prorated, prices can change — so recomputing from *current* state gives a different number than what was *actually charged*. The ledger is the only truth of what money moved. Recomputing a refund from current seats once gave me 325 when the customer actually paid 317.5 — it would have refunded more than they paid."

---

## E. DATA MODELING

**Q: "Why separate `catalog` from `subscriptions`?"**
> "Catalog is the template (a plan's price, cap, duration — shared by all subscribers); a subscription is an instance (this customer's plan, dates, seats). Merging them duplicates the plan definition onto every row and risks drift. It's the template/instance split."

**Q: "You said `end_date = start_date + duration`. So isn't the column redundant?"**
> "Only if it's never updated. I stamp `end_date = today` when a subscription is stopped early (cancel/upgrade/downgrade-away). Once that can happen, the stored value diverges from `start + duration` — the formula only knows when the sub *would* have ended, not that it was cancelled early. Storing it makes early-termination a recorded fact, which the evaluator checks."

**Q: "Why five statuses? Isn't that over-modeled?"**
> "Each status is produced by an agent action — I didn't add any that no action creates. I need `scheduled_cancellation` distinct from `active + autopay=0`, for instance, because seat-adds are allowed only on `active`; without the distinct status, a sub running out its term after cancellation would wrongly accept seat additions."

---

## F. THE AGENT ITSELF (W3+ — for when you've built it)

**Q: "How will you measure whether your self-correction loop actually helps?"**
> "Run the full task suite twice on the same model — once with a naive single-shot agent (baseline), once with the self-correction loop that feeds tool-refusal reasons back for a retry. The task-success-rate delta is the measurement. Same model, same tasks, only the orchestration differs, so the delta isolates the loop's contribution."

**Q: "What's a failure mode you expect from the agent, and how does your eval expose it?"**
> "Mis-reading a tool refusal and giving up instead of recovering — e.g. hitting a seat cap and cancelling instead of asking for a new count. The final DB state ends up wrong (or unchanged when it should have changed), so the task fails. The eval doesn't need to know *why* it failed — the state mismatch flags it, and I read the trace to diagnose."

**Q: "How would you turn per-task pass/fail into something actionable?"**
> "Bucket failures by task type — if downgrades fail more than upgrades, that points at either a tool bug or a prompt gap in that path. The eval gives me the *where*; the traces give me the *why*."

---

## G. TESTING / TRUSTWORTHINESS

**Q: "How do you know a passing task isn't passing by luck?"**
> "The comparison is exact across all tables with IDs stripped — every subscription's content, every transaction, every user's active pointer, and the untouched tables asserted byte-identical. A lucky partial match can't pass because I check the *whole* state, not just the active subscription. And the proof-of-eval step validated the comparator against known-correct solutions."

**Q: "Why assert the untouched tables are unchanged? Isn't checking the affected rows enough?"**
> "No — an agent could corrupt unrelated data (wrong customer's sub, a stray catalog edit) while getting the target right. Asserting `catalog` and `payment_methods` are byte-identical, and that only the affected customer's rows changed, catches collateral damage a target-only check would miss."

---

## Quick-reference: the "judgment" answers

When asked about scaling/hardening the project doesn't need, the template is:
> "At my scale [tens of customers, hundreds of rows], it's a non-issue. If I needed [production scale], I'd [the real technique: index / stream / pool / lock]. But building that here would be over-engineering a benchmark that will never see that load."

This shows you *know* the technique **and** know when not to reach for it — which is the actual signal.