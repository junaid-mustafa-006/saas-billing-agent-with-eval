### 1. users
* **cus_id** (INTEGER PRIMARY KEY)
* **name** (TEXT)
* **email** (TEXT)
* **phone** (TEXT)
* **active_sub_id** (INTEGER) - *Foreign Key to subscriptions. NULL means no active plan. Unchanged for scheduled actions.*

---

### 2. payment_methods
* **pay_id** (INTEGER PRIMARY KEY)
* **cus_id** (INTEGER) - *Foreign Key to users.*
* **type** (TEXT) - *e.g., 'card', 'upi'*
* **status** (TEXT) - *e.g., 'valid', 'expired'*

---

### 3. catalog (The Template)
* **plan_name** (TEXT PRIMARY KEY) - *e.g., 'Starter', 'Pro', 'Enterprise'*
* **price_per_seat** (REAL) 
* **seat_cap** (INTEGER) - *Max seats allowed for this plan.*
* **duration_days** (INTEGER) - *e.g., 30 for monthly.*

---

### 4. subscriptions (The History & Active State)
* **sub_id** (INTEGER PRIMARY KEY)
* **cus_id** (INTEGER) - *Foreign Key to users.*
* **plan_name** (TEXT) - *Foreign Key to catalog.*
* **seats_used** (INTEGER) - *Live seat count.*
* **start_date** (TEXT) - *ISO format (YYYY-MM-DD).*
* **end_date** (TEXT) - *ISO format (YYYY-MM-DD).*
* **status** (TEXT) - *Must be: 'active', 'cancelled', 'scheduled_downgrade', 'scheduled_activation', 'scheduled_cancellation'.*
* **autopay** (INTEGER) - *'0' for NO, '1' for YES.*

---

### 5. transactions (The Ledger)
* **trans_id** (INTEGER PRIMARY KEY)
* **cus_id** (INTEGER) - *Foreign Key to users.*
* **sub_id** (INTEGER) - *Foreign Key to subscriptions.*
* **amount_paid** (REAL) - *Recorded Fact. Positive values only.*
* **payment_date** (TEXT) - *ISO format (YYYY-MM-DD).*
* **type** (TEXT) - *Must be: 'new', 'upgrade', 'refund', 'seat_add'.*