#!/usr/bin/env python3
"""Automated Printing System - Main Entry Point.

Usage:
    python main.py
    or
    python -m app.main
"""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure workspace root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.main import main

if __name__ == "__main__":
    raise SystemExit(main())
