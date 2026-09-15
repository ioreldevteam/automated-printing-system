"""Minimal template substitution for ZPL/label templates (Section 26).

Templates are raw text files with `{FIELD_NAME}` placeholders. No image
library or manual barcode placement is needed -- the printer firmware (ZPL
^BC/^BQ, or the ANSER X1's Barcode object) renders the barcode/QR natively
from the substituted text.
"""
from __future__ import annotations

from pathlib import Path

from app.domain.models import LabelData


def load_template(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8")


def render_template(template: str, label: LabelData) -> str:
    values = label.as_substitution_map()
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace("{" + key + "}", str(value))
    return rendered
