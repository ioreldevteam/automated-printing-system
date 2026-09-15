"""Independent network dependency tracking (Section 61). The external API and
the printer network are unrelated failure domains and must be evaluated
separately: the API being down should never by itself pause printing, and a
printer being unreachable should never depend on API connectivity.
"""
from __future__ import annotations

import socket
from dataclasses import dataclass

import httpx

from app.config.loader import ApiConfig, PrinterConfig


@dataclass
class NetworkStatus:
    api_reachable: bool
    printer_reachable: dict[str, bool]


def check_api_reachable(api_config: ApiConfig, timeout_seconds: float = 3.0) -> bool:
    if api_config.mode == "local":
        return True
    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            response = client.get(api_config.base_url)
        return response.status_code < 500
    except httpx.RequestError:
        return False


def check_printer_reachable(printer_config: PrinterConfig, timeout_seconds: float = 2.0) -> bool:
    if printer_config.simulate:
        return True
    try:
        with socket.create_connection((printer_config.address, printer_config.port), timeout=timeout_seconds):
            return True
    except OSError:
        return False


def check_network_status(api_config: ApiConfig, printer_configs: list[PrinterConfig]) -> NetworkStatus:
    return NetworkStatus(
        api_reachable=check_api_reachable(api_config),
        printer_reachable={p.name: check_printer_reachable(p) for p in printer_configs},
    )
