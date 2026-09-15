from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from app.database import database as database_module
from app.database.database import init_db, session_scope
from app.database.repositories import PrinterRepository, ProductRepository


@pytest.fixture()
def db(tmp_path):
    database_module._engine = None
    database_module._SessionFactory = None
    init_db(str(tmp_path / "test.db"))
    yield
    database_module._engine = None
    database_module._SessionFactory = None


@pytest.fixture()
def seeded_product(db):
    with session_scope() as session:
        product = ProductRepository(session).create(product_code="PROD-A", product_name="Test Product")
        product_id = product.id
    return product_id


@pytest.fixture()
def seeded_printers(db):
    with session_scope() as session:
        repo = PrinterRepository(session)
        anser = repo.upsert(name="ANSER-01", type_="ANSER", model="X1", ip_address="127.0.0.1", port=502)
        zebra = repo.upsert(name="ZEBRA-01", type_="ZEBRA", model="ZT230", ip_address="127.0.0.1", port=9100)
        return anser.id, zebra.id
