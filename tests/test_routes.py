from conftest import add_patient, add_vaccine, stock_of


def test_all_pages_load(client):
    for path in ["/", "/patients", "/inventory", "/appointments", "/reports"]:
        assert client.get(path).status_code == 200


def test_patient_crud(client, conn):
    client.post("/patients", data={"name": "Ravi", "phone": "9999999999"})
    row = conn.execute("SELECT * FROM patients WHERE name = 'Ravi'").fetchone()
    assert row["phone"] == "9999999999"
    client.post(f"/patients/{row['id']}/edit", data={"name": "Ravi K", "phone": "", "dob": ""})
    assert conn.execute("SELECT name FROM patients WHERE id = ?", (row["id"],)).fetchone()[0] == "Ravi K"
    client.post(f"/patients/{row['id']}/delete")
    assert conn.execute("SELECT COUNT(*) FROM patients").fetchone()[0] == 0


def test_blank_patient_name_rejected(client, conn):
    client.post("/patients", data={"name": "   "})
    assert conn.execute("SELECT COUNT(*) FROM patients").fetchone()[0] == 0


def test_inventory_add_restock_and_validation(client, conn):
    client.post("/inventory", data={"name": "MMR", "stock": "5"})
    vid = conn.execute("SELECT id FROM vaccines WHERE name = 'MMR'").fetchone()[0]
    client.post(f"/inventory/{vid}/restock", data={"qty": "7"})
    assert stock_of(conn, vid) == 12
    client.post("/inventory", data={"name": "MMR", "stock": "5"})  # duplicate
    client.post("/inventory", data={"name": "Neg", "stock": "-3"})  # invalid
    assert conn.execute("SELECT COUNT(*) FROM vaccines").fetchone()[0] == 1


def test_cannot_delete_patient_with_appointments(client, conn, future_date):
    p, v = add_patient(conn), add_vaccine(conn)
    client.post("/appointments/book", data={"patient_id": p, "vaccine_id": v, "appt_date": future_date, "slot": "09:00"})
    client.post(f"/patients/{p}/delete")
    assert conn.execute("SELECT COUNT(*) FROM patients WHERE id = ?", (p,)).fetchone()[0] == 1


def test_booking_flow_and_administer(client, conn, future_date):
    p, v = add_patient(conn), add_vaccine(conn, stock=4)
    client.post("/appointments/book", data={"patient_id": p, "vaccine_id": v, "appt_date": future_date, "slot": "09:00"})
    aid = conn.execute("SELECT id FROM appointments").fetchone()[0]
    assert stock_of(conn, v) == 3
    client.post(f"/appointments/{aid}/administer")
    assert conn.execute("SELECT status FROM appointments").fetchone()[0] == "administered"
    client.post(f"/appointments/{aid}/cancel")  # cannot cancel administered
    assert stock_of(conn, v) == 3


def test_slots_api(client, conn, future_date):
    p, v = add_patient(conn), add_vaccine(conn)
    client.post("/appointments/book", data={"patient_id": p, "vaccine_id": v, "appt_date": future_date, "slot": "09:00"})
    data = client.get(f"/api/slots?date={future_date}").get_json()
    assert data["remaining"]["09:00"] == data["capacity"] - 1
    assert client.get("/api/slots?date=oops").status_code == 400


def test_user_input_is_escaped(client):
    client.post("/patients", data={"name": "<script>alert(1)</script>"})
    html = client.get("/patients").get_data(as_text=True)
    assert "<script>alert(1)</script>" not in html
