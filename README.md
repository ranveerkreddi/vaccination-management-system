# Vaccination Management System

A Flask + SQLite web app for managing patients, vaccine inventory and appointment booking.
Built to demonstrate relational design, transactional booking logic and automated tests.

**Live demo:** _add your Render URL here_ &nbsp;|&nbsp; **Stack:** Python, Flask, SQLite (plain SQL), Jinja2, JavaScript, pytest, gunicorn

## Features
- **Patients:** create, edit, delete (blocked if the patient has appointments).
- **Inventory:** add vaccines, restock doses, delete (blocked if referenced). Low-stock alerts on the dashboard.
- **Appointments:** book by patient, vaccine, date and time slot; mark as administered; cancel.
- **Booking rules (enforced in one SQL transaction):**
  - each date + time slot holds at most 3 active appointments
  - booking atomically decrements vaccine stock; cancelling returns the dose
  - out-of-stock vaccines, past dates, invalid slots and duplicate bookings are rejected
- **Reports:** doses by vaccine (administered / booked / cancelled) and appointments per day, using `JOIN` and `GROUP BY`.
- **JSON API:** `GET /api/slots?date=YYYY-MM-DD` returns remaining places per slot; the booking form uses it.

## Run locally
```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
python app.py                                          # http://127.0.0.1:5000 (seeds sample data)
```

## Run the tests
```bash
python -m pytest -q        # 17 tests
```
Includes concurrency tests that fire 12 simultaneous bookings at one slot and check that exactly 3 succeed
and stock is exact.

## Deploy on Render (free)
1. Push this folder to a GitHub repo.
2. On render.com choose **New > Blueprint** and select the repo (it reads `render.yaml`), or create a Web Service with
   build command `pip install -r requirements.txt` and start command `gunicorn wsgi:app`.
3. Set `SEED_DEMO=1` to load sample data on startup.

Note: Render's free tier has an ephemeral disk and the app sleeps after inactivity, so data resets on restart.
That is fine for a demo; use PostgreSQL for real persistence.

## Design notes
- **Schema:** `patients`, `vaccines`, `appointments` with foreign keys (`ON DELETE RESTRICT`), `CHECK` constraints
  (stock >= 0, valid status) and an index on `(appt_date, slot, status)`.
- **Concurrency:** booking runs `BEGIN IMMEDIATE`, which takes SQLite's write lock before the capacity check, so two
  requests cannot both see "one place left". The stock update (`UPDATE ... WHERE stock > 0`) is atomic on its own.
- **Security basics:** parameterised queries everywhere (no SQL injection), Jinja auto-escaping (tested), POST for all
  state changes.

## Limitations (honest list)
No authentication or roles, no CSRF tokens, single clinic, SQLite only. Not for real patient data.
