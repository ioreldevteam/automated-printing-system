from app.database.backup import backup_database
from app.database.database import init_db, session_scope
from app.database.repositories import ProductRepository
from app.database import database as database_module


def test_backup_creates_consistent_copy(tmp_path):
    database_module._engine = None
    database_module._SessionFactory = None
    db_path = tmp_path / "production.db"
    init_db(str(db_path))
    with session_scope() as session:
        ProductRepository(session).create(product_code="PROD-A", product_name="Backup Test")

    backup_dir = tmp_path / "backups"
    destination = backup_database(db_path, backup_dir)

    assert destination.exists()
    assert destination.parent == backup_dir

    import sqlite3
    conn = sqlite3.connect(str(destination))
    try:
        rows = conn.execute("SELECT product_code FROM products").fetchall()
    finally:
        conn.close()
    assert rows == [("PROD-A",)]

    database_module._engine = None
    database_module._SessionFactory = None
