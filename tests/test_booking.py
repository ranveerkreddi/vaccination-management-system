import threading
import time
from datetime import date, timedelta

import pytest

import services
from conftest import add_patient, add_vaccine, stock_of
from db import SLOT_CAPACITY, connect
from services import BookingError


def test_booking_decrements_stock(conn, future_date):
    p, v = add_patient(conn), add_vaccine(conn, stock=5)
    services.book_appointment(conn, p, v, future_date, "09:00")
    assert stock_of(conn, v) == 4


def test_slot_capacity_is_enforced(conn, future_date):
    v = add_vaccine(conn, stock=20)
    for i in range(SLOT_CAPACITY):
        services.book_appointment(conn, add_patient(conn, f"P{i}"), v, future_date, "10:00")
    with pytest.raises(BookingError, match="full"):
        services.book_appointment(conn, add_patient(conn, "Extra"), v, future_date, "10:00")
    assert stock_of(conn, v) == 20 - SLOT_CAPACITY  # failed booking did not consume stock


def test_out_of_stock_is_rejected(conn, future_date):
    p, v = add_patient(conn), add_vaccine(conn, stock=0)
    with pytest.raises(BookingError, match="out of stock"):
        services.book_appointment(conn, p, v, future_date, "09:00")


def test_cancel_returns_dose_to_stock(conn, future_date):
    p, v = add_patient(conn), add_vaccine(conn, stock=3)
    aid = services.book_appointment(conn, p, v, future_date, "09:00")
    services.cancel_appointment(conn, aid)
    assert stock_of(conn, v) == 3
    with pytest.raises(BookingError):
        services.cancel_appointment(conn, aid)  # cannot cancel twice


def test_cancelled_booking_frees_the_slot(conn, future_date):
    v = add_vaccine(conn, stock=20)
    ids = [services.book_appointment(conn, add_patient(conn, f"P{i}"), v, future_date, "11:00")
           for i in range(SLOT_CAPACITY)]
    services.cancel_appointment(conn, ids[0])
    services.book_appointment(conn, add_patient(conn, "New"), v, future_date, "11:00")


def test_same_patient_cannot_double_book_vaccine(conn, future_date):
    p, v = add_patient(conn), add_vaccine(conn)
    services.book_appointment(conn, p, v, future_date, "09:00")
    with pytest.raises(BookingError, match="already has"):
        services.book_appointment(conn, p, v, future_date, "10:00")


def test_past_date_and_bad_input_rejected(conn):
    p, v = add_patient(conn), add_vaccine(conn)
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    with pytest.raises(BookingError, match="past"):
        services.book_appointment(conn, p, v, yesterday, "09:00")
    with pytest.raises(BookingError, match="valid date"):
        services.book_appointment(conn, p, v, "not-a-date", "09:00")
    with pytest.raises(BookingError, match="slot"):
        services.book_appointment(conn, p, v, (date.today() + timedelta(days=1)).isoformat(), "03:33")


def _run_threads(db_path, jobs):
    """jobs: list of (patient_id, vaccine_id, date, slot). Returns (successes, failures)."""
    results, lock = [], threading.Lock()
    barrier = threading.Barrier(len(jobs))

    def worker(job):
        c = connect(db_path)
        # Widen the check-then-write window so a missing lock reliably shows up as overbooking
        c.set_trace_callback(lambda sql: time.sleep(0.02) if sql.startswith("SELECT COUNT(*)") else None)
        barrier.wait()  # start all threads at the same moment
        try:
            services.book_appointment(c, *job)
            outcome = "ok"
        except BookingError:
            outcome = "rejected"
        finally:
            c.close()
        with lock:
            results.append(outcome)

    threads = [threading.Thread(target=worker, args=(j,)) for j in jobs]
    [t.start() for t in threads]
    [t.join() for t in threads]
    return results.count("ok"), results.count("rejected")


def test_concurrent_requests_cannot_overbook_a_slot(conn, db_path, future_date):
    v = add_vaccine(conn, stock=50)
    jobs = [(add_patient(conn, f"P{i}"), v, future_date, "12:00") for i in range(12)]
    ok, rejected = _run_threads(db_path, jobs)
    assert ok == SLOT_CAPACITY and rejected == 12 - SLOT_CAPACITY
    booked = conn.execute("SELECT COUNT(*) FROM appointments WHERE slot = '12:00'").fetchone()[0]
    assert booked == SLOT_CAPACITY
    assert stock_of(conn, v) == 50 - SLOT_CAPACITY


def test_concurrent_requests_cannot_oversell_stock(conn, db_path, future_date):
    v = add_vaccine(conn, stock=2)
    slots = ["09:00", "10:00", "11:00", "12:00", "14:00", "15:00", "16:00"]
    jobs = [(add_patient(conn, f"P{i}"), v, future_date, slots[i % len(slots)]) for i in range(10)]
    ok, _ = _run_threads(db_path, jobs)
    assert ok == 2
    assert stock_of(conn, v) == 0
