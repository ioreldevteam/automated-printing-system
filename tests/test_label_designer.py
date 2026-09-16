from __future__ import annotations

import tempfile
from pathlib import Path

from app.domain.models import LabelData
from app.printers.template_engine import load_template, render_template
from app.templates.label_designer import (
    generate_zebra_zpl,
    render_label_qimage,
    save_label_monochrome_bmp,
    save_label_png,
)


def test_label_rendering_png_and_monochrome_bmp():
    data = {
        "item_code": "101-1001",
        "product_name": "1 Gang 1 Way Switch Indicator",
        "retail_barcode": "8901234567890",
        "batch_code": "BATCH-20260916-01",
        "mrp_value": "450.00",
        "rated_specs": "10 AX / 250 V~",
        "sls_code": "141",
        "serial_number": "SN1011001-0001",
    }

    qimage = render_label_qimage(data, width=600, height=240)
    assert qimage.width() == 600
    assert qimage.height() == 240

    with tempfile.TemporaryDirectory() as tmpdir:
        png_path = Path(tmpdir) / "test_label.png"
        bmp_path = Path(tmpdir) / "test_label.bmp"

        save_label_png(data, png_path)
        save_label_monochrome_bmp(data, bmp_path)

        assert png_path.exists() and png_path.stat().st_size > 0
        assert bmp_path.exists() and bmp_path.stat().st_size > 0


def test_zebra_zpl_template_substitution():
    label = LabelData(
        product_name="1 Gang 1 Way Switch Indicator",
        serial_number="SN1011001-0001",
        batch_number="BATCH-20260916-01",
        extra={
            "retail_barcode": "8901234567890",
            "mrp_value": "450.00",
            "item_code": "101-1001",
            "rated_specs": "10 AX / 250 V~",
            "sls_code": "141",
        },
    )

    template_path = Path(__file__).resolve().parents[1] / "app" / "templates" / "zpl" / "sticker_label_v1.zpl"
    template = load_template(template_path)
    rendered = render_template(template, label)

    assert "^XA" in rendered and "^XZ" in rendered
    assert "8901234567890" in rendered
    assert "BATCH-20260916-01" in rendered
    assert "450.00" in rendered
    assert "101-1001" in rendered
    assert "SN1011001-0001" in rendered
    assert "10 AX / 250 V~" in rendered
    # No un-substituted brackets left
    assert "{" not in rendered and "}" not in rendered
