"""Wires together the long-lived singletons the UI needs: config, printer
manager, event bus, production controller, and printer monitor. Built once in
main.py and handed to the UI so widgets don't each re-derive this wiring.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.config.loader import AppConfig
from app.database.database import session_scope
from app.database.models import User
from app.domain.events import EventBus
from app.monitoring.printer_monitor import PrinterMonitor
from app.application.printer_service import PrinterService
from app.application.production_service import ProductionController
from app.printers.printer_manager import PrinterManager
from app.printers.discovery import DiscoveredPrinter, discover_printers

ZEBRA_TEMPLATE_PATH = str(
    Path(__file__).resolve().parents[2] / "app" / "templates" / "zpl" / "sticker_label_v1.zpl"
)


@dataclass
class AppContext:
    config: AppConfig
    event_bus: EventBus
    printer_manager: PrinterManager
    production_controller: ProductionController
    printer_monitor: PrinterMonitor
    current_user: User | None = None
    discovered_printers: list[DiscoveredPrinter] | None = None


def build_app_context(config: AppConfig) -> AppContext:
    event_bus = EventBus()
    printer_manager = PrinterManager()
    printer_manager.load_from_config(config.printers)
    discovered_printers = discover_printers()
    printer_manager.register_discovered(discovered_printers)

    anser_cfg = next((p for p in config.printers if p.type == "ANSER"), None)
    zebra_cfg = next((p for p in config.printers if p.type == "ZEBRA"), None)

    production_controller = ProductionController(
        printer_manager=printer_manager,
        event_bus=event_bus,
        max_retries=config.printing.max_retries,
        anser_printer_name=anser_cfg.name if anser_cfg else "ANSER-01",
        zebra_printer_name=zebra_cfg.name if zebra_cfg else "ZEBRA-01",
        zebra_template_path=ZEBRA_TEMPLATE_PATH,
    )
    printer_monitor = PrinterMonitor(printer_manager, event_bus,
                                      poll_interval_seconds=config.monitoring.status_poll_interval_seconds)

    return AppContext(
        config=config, event_bus=event_bus, printer_manager=printer_manager,
        production_controller=production_controller, printer_monitor=printer_monitor,
        discovered_printers=discovered_printers,
    )


def rescan_discovered_printers(context: AppContext) -> list[str]:
    """Re-run host printer discovery (CUPS/USB/network) and hot-register any
    printer that has appeared since startup or the last rescan -- e.g. a USB
    label printer plugged in after the app was launched. Safe to call
    repeatedly (from a UI button or a background timer): printers already
    known, configured or previously discovered, are left untouched.

    Returns the names of newly added printers, if any.
    """
    discovered = discover_printers()
    context.discovered_printers = discovered
    newly_added = context.printer_manager.register_discovered(discovered)

    if newly_added:
        with session_scope() as session:
            PrinterService(context.printer_manager).sync_configured_printers(session)
        for name in newly_added:
            try:
                context.printer_manager.get(name).connect()
            except Exception:  # noqa: BLE001 - best effort; monitor will retry via polling
                pass

    return newly_added
