"""Seeds a couple of demo products so the app can be exercised end-to-end
with the simulated ANSER/Zebra printers (config.yaml has simulate: true by
default) without needing a real product catalog or hardware.

Usage:
    python -m scripts.seed_demo_data
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.application.auth_service import AuthService
from app.config.loader import load_config
from app.database.database import init_db, session_scope
from app.database.repositories import ProductRepository

DEMO_PRODUCTS = [
    ("DEMO-001", "Demo Widget 500g"),
    ("DEMO-002", "Demo Bottle 1L"),
]


def main() -> int:
    config = load_config()
    init_db(config.database.path)

    with session_scope() as session:
        AuthService(session, config.security.bcrypt_rounds).ensure_default_admin()

        products = ProductRepository(session)
        for code, name in DEMO_PRODUCTS:
            if products.get_by_code(code) is None:
                products.create(product_code=code, product_name=name)
                print(f"Created product {code} - {name}")
            else:
                print(f"Product {code} already exists, skipping")

    print("\nDone. Login with admin / admin, then create a job for DEMO-001 or DEMO-002.")
    print("Printers in config.yaml are set to simulate: true, so no real hardware is needed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
