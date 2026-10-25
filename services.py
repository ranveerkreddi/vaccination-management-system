"""Business logic. Booking and cancelling run inside explicit transactions so
stock and slot capacity stay consistent even with concurrent requests."""
from datetime import date, datetime

from db import SLOT_CAPACITY, SLOTS


class BookingError(Exception):
    """A user-facing validation or business-rule error."""


def _parse_date(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        raise BookingError("Enter a valid date (YYYY-MM-DD).")


def slot_availability(conn, appt_date):
    """Return {slot: remaining places} for one date."""
    rows = conn.execute(
        "SELECT slot, COUNT(*) AS n FROM appointments "
        "WHERE appt_date = ? AND status != 'cancelled' GROUP BY slot",
        (appt_date,),
    ).fetchall()
    used = {r["slot"]: r["n"] for r in rows}
    return {s: SLOT_CAPACITY - used.get(s, 0) for s in SLOTS}


def book_appointment(conn, patient_id, vaccine_id, appt_date, slot):
    """Book a slot and decrement stock atomically. Returns the new appointment id."""
    if _parse_date(appt_date) < date.today():
        raise BookingError("Appointment date cannot be in the past.")
    if slot not in SLOTS:
        raise BookingError("Choose a valid time slot.")

    conn.execute("BEGIN IMMEDIATE")  # take the write lock before checking anything
    try:
        if not conn.execute("SELECT 1 FROM patients WHERE id = ?", (patient_id,)).fetchone():
            raise BookingError("Patient not found.")
        if not conn.execute("SELECT 1 FROM vaccines WHERE id = ?", (vaccine_id,)).fetchone():
            raise BookingError("Vaccine not found.")

        taken = conn.execute(
            "SELECT COUNT(*) FROM appointments "
            "WHERE appt_date = ? AND slot = ? AND status != 'cancelled'",
            (appt_date, slot),
        ).fetchone()[0]
        if taken >= SLOT_CAPACITY:
            raise BookingError(f"{appt_date} {slot} is full. Choose another slot.")

        if conn.execute(
            "SELECT 1 FROM appointments WHERE patient_id = ? AND vaccine_id = ? AND status = 'booked'",
            (patient_id, vaccine_id),
        ).fetchone():
            raise BookingError("This patient already has a booked appointment for this vaccine.")

        updated = conn.execute(
            "UPDATE vaccines SET stock = stock - 1 WHERE id = ? AND stock > 0", (vaccine_id,)
        ).rowcount
        if updated == 0:
            raise BookingError("This vaccine is out of stock.")

        cur = conn.execute(
            "INSERT INTO appointments (patient_id, vaccine_id, appt_date, slot) VALUES (?, ?, ?, ?)",
            (patient_id, vaccine_id, appt_date, slot),
        )
        conn.execute("COMMIT")
        return cur.lastrowid
    except BaseException:
        conn.execute("ROLLBACK")
        raise


def cancel_appointment(conn, appt_id):
    """Cancel a booked appointment and return the dose to stock."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute("SELECT vaccine_id, status FROM appointments WHERE id = ?", (appt_id,)).fetchone()
        if row is None:
            raise BookingError("Appointment not found.")
        if row["status"] != "booked":
            raise BookingError("Only booked appointments can be cancelled.")
        conn.execute("UPDATE appointments SET status = 'cancelled' WHERE id = ?", (appt_id,))
        conn.execute("UPDATE vaccines SET stock = stock + 1 WHERE id = ?", (row["vaccine_id"],))
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise


def mark_administered(conn, appt_id):
    cur = conn.execute(
        "UPDATE appointments SET status = 'administered' WHERE id = ? AND status = 'booked'", (appt_id,)
    )
    if cur.rowcount == 0:
        raise BookingError("Only booked appointments can be marked as administered.")


def dashboard_stats(conn):
    today = date.today().isoformat()
    q = lambda sql, args=(): conn.execute(sql, args).fetchone()[0]
    return {
        "patients": q("SELECT COUNT(*) FROM patients"),
        "administered": q("SELECT COUNT(*) FROM appointments WHERE status = 'administered'"),
        "upcoming": q("SELECT COUNT(*) FROM appointments WHERE status = 'booked' AND appt_date >= ?", (today,)),
        "low_stock": conn.execute("SELECT name, stock FROM vaccines WHERE stock <= 10 ORDER BY stock").fetchall(),
    }


def report_by_vaccine(conn):
    return conn.execute(
        """
        SELECT v.name, v.stock,
               SUM(a.status = 'administered') AS administered,
               SUM(a.status = 'booked')       AS booked,
               SUM(a.status = 'cancelled')    AS cancelled
        FROM vaccines v
        LEFT JOIN appointments a ON a.vaccine_id = v.id
        GROUP BY v.id
        ORDER BY administered DESC, v.name
        """
    ).fetchall()


def report_by_day(conn, limit=14):
    return conn.execute(
        """
        SELECT appt_date, COUNT(*) AS total
        FROM appointments
        WHERE status != 'cancelled'
        GROUP BY appt_date
        ORDER BY appt_date DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()