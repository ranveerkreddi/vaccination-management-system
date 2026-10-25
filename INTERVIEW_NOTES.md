# Interview notes: Vaccination Management System

Read the code in `services.py` until you can explain it without looking.

**What does the project do?**
A web app where staff register patients, track vaccine stock and book appointments. Booking checks slot capacity and
stock, then writes both changes in a single transaction.

**How do you prevent double booking or overselling?**
`BEGIN IMMEDIATE` takes SQLite's write lock before the checks, so concurrent requests run one at a time. I tested it
with 12 threads on a 3-place slot and confirmed exactly 3 succeed. When I removed the lock, the same test overbooked
(6 bookings), which shows the test catches the bug.

**Why SQLite? What would you change for production?**
Zero setup, ideal for a demo. For production I'd use PostgreSQL (row-level locking, `SELECT ... FOR UPDATE` or a
unique/exclusion constraint), add authentication, CSRF protection, and migrations.

**Why plain SQL and not an ORM?**
To show I understand the queries, joins and transactions directly. An ORM like SQLAlchemy is the next step.

**Which SQL concepts are used?**
Primary and foreign keys, `CHECK` and `UNIQUE` constraints, an index, `JOIN`, `LEFT JOIN`, `GROUP BY`, aggregates,
transactions (`BEGIN`/`COMMIT`/`ROLLBACK`), parameterised queries.

**What is SQL injection and how did you avoid it?**
Building SQL by string-concatenating user input. I always pass values as `?` parameters.

**What would you improve?**
Login and roles, multiple clinics, email/SMS reminders, PostgreSQL, a vaccination-record history per patient,
CSRF protection, pagination.
