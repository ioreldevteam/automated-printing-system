from __future__ import annotations

import json
import re
from pathlib import Path

MOCK_DIR = Path(__file__).resolve().parents[1] / "mock_api"
ITEM_CODE_REGEX = re.compile(r"^\d{3}-\d{4}$")


def test_product_data_json_structure():
    with open(MOCK_DIR / "product_data.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    assert isinstance(data, list)
    assert len(data) > 0
    for item in data:
        assert "item_code" in item
        assert ITEM_CODE_REGEX.match(item["item_code"])
        assert "item_name" in item
        assert "retail_barcode" in item
        assert "mrp_value" in item


def test_unit_box_json_structure():
    with open(MOCK_DIR / "unit_box.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    assert isinstance(data, list)
    assert len(data) > 0

    serials_per_item: dict[str, list[str]] = {}
    all_serials: list[str] = []

    for item in data:
        # User requested: item_code, item name, serial code, retail barcode, mrp_value, batch code
        assert "item_code" in item
        assert ITEM_CODE_REGEX.match(item["item_code"])
        assert "item_name" in item
        assert "serial_code" in item
        assert "retail_barcode" in item
        assert "mrp_value" in item
        assert "batch_code" in item

        code = item["item_code"]
        serial = item["serial_code"]
        serials_per_item.setdefault(code, []).append(serial)
        all_serials.append(serial)

    # Every serial code must be unique
    assert len(all_serials) == len(set(all_serials))

    # One item code needs to have at least 20 serial nos
    for code, serials in serials_per_item.items():
        assert len(serials) >= 20
        assert len(serials) == len(set(serials))


def test_b_box_json_structure():
    with open(MOCK_DIR / "b_box.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    assert isinstance(data, list)
    assert len(data) > 0
    b_serials = []
    for item in data:
        # User requested: serial code, no of quantity, batch no, barcode, item code, item name
        assert "serial_code" in item
        assert "no_of_quantity" in item
        assert "batch_no" in item
        assert "barcode" in item
        assert "item_code" in item
        assert ITEM_CODE_REGEX.match(item["item_code"])
        assert "item_name" in item
        b_serials.append(item["serial_code"])
    assert len(b_serials) == len(set(b_serials))


def test_m_box_json_structure():
    with open(MOCK_DIR / "m_box.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    assert isinstance(data, list)
    assert len(data) > 0
    m_serials = []
    for item in data:
        # User requested: serial code, no of quantity, barcode, item code, item name
        assert "serial_code" in item
        assert "no_of_quantity" in item
        assert "barcode" in item
        assert "item_code" in item
        assert ITEM_CODE_REGEX.match(item["item_code"])
        assert "item_name" in item
        m_serials.append(item["serial_code"])
    assert len(m_serials) == len(set(m_serials))


def test_combined_mock_api_json():
    with open(MOCK_DIR / "mock_api.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    assert "product_data" in data
    assert "unit_box" in data
    assert "b_box" in data
    assert "m_box" in data
