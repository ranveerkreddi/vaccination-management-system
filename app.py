"""Vaccination Management System: Flask + SQLite."""
import os
import sqlite3
from datetime import date

from flask import Flask, abort, flash, g, jsonify, redirect, render_template, request, url_for

import services
from db import SLOT_CAPACITY, SLOTS, connect, init_db
from services import BookingError


def create_app(db_path=None, seed=False):
    app = Flask(__name__)
    app.config["DB_PATH"] = db_path or os.environ.get("DB_PATH", "vaccination.db")
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-change-me")
    init_db(app.config["DB_PATH"])
    if seed or os.environ.get("SEED_DEMO") == "1":
        seed_demo(app.config["DB_PATH"])

    def db():
        if "conn" not in g:
            g.conn = connect(app.config["DB_PATH"])
        return g.conn

    @app.teardown_appcontext
    def close_db(_exc):
        conn = g.pop("conn", None)
        if conn is not None:
            conn.close()

    # ---------- dashboard ----------
    @app.route("/")
    def dashboard():
        return render_template("dashboard.html", stats=services.dashboard_stats(db()))

    # ---------- patients (CRUD) ----------
    @app.route("/patients", methods=["GET", "POST"])
    def patients():
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            if not name:
                flash("Patient name is required.", "error")
            else:
                db().execute(
                    "INSERT INTO patients (name, phone, dob) VALUES (?, ?, ?)",
                    (name, request.form.get("phone", "").strip() or None, request.form.get("dob") or None),
                )
                flash(f"Patient {name} added.", "ok")
            return redirect(url_for("patients"))
        rows = db().execute("SELECT * FROM patients ORDER BY name").fetchall()
        return render_template("patients.html", patients=rows)

    @app.route("/patients/<int:pid>/edit", methods=["GET", "POST"])
    def edit_patient(pid):
        row = db().execute("SELECT * FROM patients WHERE id = ?", (pid,)).fetchone()
        if row is None:
            abort(404)
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            if not name:
                flash("Patient name is required.", "error")
                return redirect(url_for("edit_patient", pid=pid))
            db().execute(
                "UPDATE patients SET name = ?, phone = ?, dob = ? WHERE id = ?",
                (name, request.form.get("phone", "").strip() or None, request.form.get("dob") or None, pid),
            )
            flash("Patient updated.", "ok")
            return redirect(url_for("patients"))
        return render_template("edit_patient.html", p=row)

    @app.post("/patients/<int:pid>/delete")
    def delete_patient(pid):
        try:
            db().execute("DELETE FROM patients WHERE id = ?", (pid,))
            flash("Patient deleted.", "ok")
        except sqlite3.IntegrityError:
            flash("Cannot delete a patient who has appointments.", "error")
        return redirect(url_for("patients"))

    # ---------- vaccine inventory (CRUD) ----------
    @app.route("/inventory", methods=["GET", "POST"])
    def inventory():
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            try:
                stock = int(request.form.get("stock", "0"))
                if stock < 0 or not name:
                    raise ValueError
                db().execute("INSERT INTO vaccines (name, stock) VALUES (?, ?)", (name, stock))
                flash(f"{name} added with {stock} doses.", "ok")
            except ValueError:
                flash("Enter a vaccine name and a non-negative dose count.", "error")
            except sqlite3.IntegrityError:
                flash("A vaccine with that name already exists.", "error")
            return redirect(url_for("inventory"))
        rows = db().execute("SELECT * FROM vaccines ORDER BY name").fetchall()
        return render_template("inventory.html", vaccines=rows)

    @app.post("/inventory/<int:vid>/restock")
    def restock(vid):
        try:
            qty = int(request.form.get("qty", "0"))
            if qty <= 0:
                raise ValueError
        except ValueError:
            flash("Enter a positive number of doses.", "error")
            return redirect(url_for("inventory"))
        db().execute("UPDATE vaccines SET stock = stock + ? WHERE id = ?", (qty, vid))
        flash(f"Added {qty} doses.", "ok")
        return redirect(url_for("inventory"))

    @app.post("/inventory/<int:vid>/delete")
    def delete_vaccine(vid):
        try:
            db().execute("DELETE FROM vaccines WHERE id = ?", (vid,))
            flash("Vaccine deleted.", "ok")
        except sqlite3.IntegrityError:
            flash("Cannot delete a vaccine that has appointments.", "error")
        return redirect(url_for("inventory"))

    # ---------- appointments ----------
    @app.route("/appointments")
    def appointments():
        rows = db().execute(
            """
            SELECT a.id, a.appt_date, a.slot, a.status, p.name AS patient, v.name AS vaccine
            FROM appointments a
            JOIN patients p ON p.id = a.patient_id
            JOIN vaccines v ON v.id = a.vaccine_id
            ORDER BY a.appt_date DESC, a.slot
            """
        ).fetchall()
        return render_template(
            "appointments.html",
            appointments=rows,
            patients=db().execute("SELECT id, name FROM patients ORDER BY name").fetchall(),
            vaccines=db().execute("SELECT id, name, stock FROM vaccines ORDER BY name").fetchall(),
            slots=SLOTS,
            capacity=SLOT_CAPACITY,
            today=date.today().isoformat(),
        )

    @app.post("/appointments/book")
    def book():
        try:
            services.book_appointment(
                db(),
                int(request.form.get("patient_id", 0)),
                int(request.form.get("vaccine_id", 0)),
                request.form.get("appt_date", ""),
                request.form.get("slot", ""),
            )
            flash("Appointment booked.", "ok")
        except (BookingError, ValueError) as e:
            flash(str(e) if isinstance(e, BookingError) else "Choose a patient and a vaccine.", "error")
        return redirect(url_for("appointments"))

    @app.post("/appointments/<int:aid>/cancel")
    def cancel(aid):
        try:
            services.cancel_appointment(db(), aid)
            flash("Appointment cancelled and dose returned to stock.", "ok")
        except BookingError as e:
            flash(str(e), "error")
        return redirect(url_for("appointments"))

    @app.post("/appointments/<int:aid>/administer")
    def administer(aid):
        try:
            services.mark_administered(db(), aid)
            flash("Marked as administered.", "ok")
        except BookingError as e:
            flash(str(e), "error")
        return redirect(url_for("appointments"))

    # ---------- reports + JSON API ----------
    @app.route("/reports")
    def reports():
        return render_template(
            "reports.html",
            by_vaccine=services.report_by_vaccine(db()),
            by_day=services.report_by_day(db()),
        )

    @app.get("/api/slots")
    def api_slots():
        d = request.args.get("date", "")
        try:
            services._parse_date(d)
        except BookingError as e:
            return jsonify(error=str(e)), 400
        return jsonify(date=d, capacity=SLOT_CAPACITY, remaining=services.slot_availability(db(), d))

    return app


def seed_demo(path):
    """Insert sample data once (only if the database is empty)."""
    conn = connect(path)
    if conn.execute("SELECT COUNT(*) FROM vaccines").fetchone()[0] == 0:
        conn.executemany(
            "INSERT INTO vaccines (name, stock) VALUES (?, ?)",
            [("Covishield", 40), ("Covaxin", 25), ("Hepatitis B", 8), ("MMR", 30)],
        )
        conn.executemany(
            "INSERT INTO patients (name, phone, dob) VALUES (?, ?, ?)",
            [("Asha Rao", "9000000001", "1998-04-12"), ("Vikram Singh", "9000000002", "1991-09-30"),
             ("Meera Nair", "9000000003", "2001-01-15")],
        )
    conn.close()


if __name__ == "__main__":
    create_app(seed=True).run(debug=True)
