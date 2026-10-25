import os
import sys
from datetime import date, timedelta

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import create_app  # noqa: E402
from db import connect  # noqa: E402


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test.db")


@pytest.fixture
def app(db_path):
    return create_app(db_path=db_path)


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def conn(app, db_path):
    c = connect(db_path)
    yield c
    c.close()


@pytest.fixture
def future_date():
    return (date.today() + timedelta(days=2)).isoformat()


def add_patient(conn, name="Test Patient"):
    return conn.execute("INSERT INTO patients (name) VALUES (?)", (name,)).lastrowid


def add_vaccine(conn, name="TestVax", stock=10):
    return conn.execute("INSERT INTO vaccines (name, stock) VALUES (?, ?)", (name, stock)).lastrowid


def stock_of(conn, vid):
    return conn.execute("SELECT stock FROM vaccines WHERE id = ?", (vid,)).fetchone()[0]
