"""Printer manager (Section 32): owns every configured printer adapter and is
the only place that knows how to build one from config.
"""
from __future__ import annotations

from app.config.loader import PrinterConfig
from app.domain.models import PrinterStatusInfo
from app.printers.anser import AnserPrinter
from app.printers.base import BasePrinter
from app.printers.cups import CupsPrinter
from app.printers.discovery import DiscoveredPrinter
from app.printers.simulation import SimulationPrinter
from app.printers.zebra import ZebraPrinter


def build_printer(cfg: PrinterConfig) -> BasePrinter:
    if cfg.simulate or cfg.type == "SIMULATION":
        return SimulationPrinter(name=cfg.name, role="ANSER" if cfg.type == "ANSER" else "ZEBRA")
    if cfg.type == "ZEBRA":
        return ZebraPrinter(name=cfg.name, address=cfg.address, port=cfg.port,
                             connect_timeout=cfg.connect_timeout_seconds)
    if cfg.type == "CUPS":
        return CupsPrinter(name=cfg.name, uri=cfg.address, connect_timeout=cfg.connect_timeout_seconds)
    if cfg.type == "ANSER":
        return AnserPrinter(name=cfg.name, address=cfg.address, port=cfg.port,
                             modbus_config=cfg.anser_modbus, connect_timeout=cfg.connect_timeout_seconds)
    raise ValueError(f"Unknown printer type: {cfg.type}")


class PrinterManager:
    def __init__(self) -> None:
        self._printers: dict[str, BasePrinter] = {}
        self._configs: dict[str, PrinterConfig] = {}

    def load_from_config(self, printer_configs: list[PrinterConfig]) -> None:
        for cfg in printer_configs:
            if not cfg.enabled:
                continue
            self._printers[cfg.name] = build_printer(cfg)
            self._configs[cfg.name] = cfg

    def register_discovered(self, printers: list[DiscoveredPrinter]) -> None:
        for printer in printers:
            if printer.name in self._printers:
                continue
            cfg = PrinterConfig(name=printer.name, type="CUPS", model=printer.model,
                                address=printer.uri, enabled=True)
            self._printers[cfg.name] = build_printer(cfg)
            self._configs[cfg.name] = cfg

    def get(self, name: str) -> BasePrinter:
        if name not in self._printers:
            raise KeyError(f"Printer not configured: {name}")
        return self._printers[name]

    def config_for(self, name: str) -> PrinterConfig:
        return self._configs[name]

    def names(self) -> list[str]:
        return list(self._printers.keys())

    def connect_all(self) -> dict[str, Exception | None]:
        results: dict[str, Exception | None] = {}
        for name, printer in self._printers.items():
            try:
                printer.connect()
                results[name] = None
            except Exception as exc:  # noqa: BLE001 - surface per-printer connect failures
                results[name] = exc
        return results

    def status_all(self) -> dict[str, PrinterStatusInfo]:
        return {name: printer.get_status() for name, printer in self._printers.items()}

    def test_all(self) -> dict[str, bool]:
        return {name: printer.test_print() for name, printer in self._printers.items()}
