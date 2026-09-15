"""Simulation printer (Section 76/77). Stands in for either a Zebra or an
ANSER adapter during development and testing, without any physical hardware.
Supports injecting the failure modes Section 77 asks for so recovery logic
can be exercised deterministically (Section 79/101 test cases).
"""
from __future__ import annotations

import threading

from app.domain.models import LabelData, PrinterStatusInfo
from app.domain.states import PrinterStatus
from app.printers.base import BasePrinter, PrinterError

FailureMode = str  # "success" | "timeout" | "offline" | "media_out" | "unknown_result" | "busy"


class SimulationPrinter(BasePrinter):
    def __init__(self, name: str, role: str = "ZEBRA"):
        self.name = name
        self.role = role  # "ZEBRA" or "ANSER"
        self._connected = False
        self._lock = threading.Lock()
        self._print_count = 0
        self._consumed_count = 0
        self._fifo_pending = 0
        self._pending_failure: FailureMode | None = None
        self._fail_at_call: int | None = None
        self._call_counter = 0
        self._persistent_status = PrinterStatus.READY

    # --- test control -----------------------------------------------------
    def inject_failure(self, mode: FailureMode, at_call: int | None = None) -> None:
        """Arm a failure. If at_call is given, the failure fires only on that
        call number (1-based); otherwise it fires on the very next call and
        then clears (one-shot)."""
        with self._lock:
            self._pending_failure = mode
            self._fail_at_call = at_call

    def set_persistent_status(self, status: PrinterStatus) -> None:
        with self._lock:
            self._persistent_status = status

    def clear_failures(self) -> None:
        with self._lock:
            self._pending_failure = None
            self._fail_at_call = None
            self._persistent_status = PrinterStatus.READY

    def _next_failure(self) -> FailureMode | None:
        with self._lock:
            self._call_counter += 1
            if self._pending_failure is None:
                return None
            if self._fail_at_call is None:
                mode = self._pending_failure
                self._pending_failure = None
                return mode
            if self._call_counter == self._fail_at_call:
                return self._pending_failure
            return None

    # --- BasePrinter --------------------------------------------------------
    def connect(self) -> None:
        self._connected = True

    def disconnect(self) -> None:
        self._connected = False

    def get_status(self) -> PrinterStatusInfo:
        if not self._connected:
            return PrinterStatusInfo(status=PrinterStatus.OFFLINE, connected=False)
        return PrinterStatusInfo(status=self._persistent_status, connected=True)

    def test_print(self) -> bool:
        return self._connected and self._persistent_status == PrinterStatus.READY

    def _raise_for_mode(self, mode: FailureMode) -> None:
        if mode == "timeout":
            raise PrinterError(f"{self.name}: simulated timeout", error_code="PRINT_001")
        if mode == "offline":
            self._connected = False
            raise PrinterError(f"{self.name}: simulated offline", error_code="PRINTER_001")
        if mode == "media_out":
            self._persistent_status = PrinterStatus.MEDIA_OUT
            raise PrinterError(f"{self.name}: simulated media out", error_code="PRINTER_002")
        if mode == "busy":
            raise PrinterError(f"{self.name}: simulated busy", error_code="PRINT_001")
        if mode == "unknown_result":
            raise PrinterError(f"{self.name}: simulated unknown result", error_code="PRINT_002", uncertain=True)

    # Zebra-style interface
    def print_label(self, template: str, label: LabelData) -> None:
        if not self._connected:
            raise PrinterError(f"{self.name}: not connected", error_code="PRINTER_001")
        mode = self._next_failure()
        if mode and mode != "success":
            self._raise_for_mode(mode)
        self._print_count += 1

    # ANSER-style interface
    def push_serial(self, serial: str) -> None:
        if not self._connected:
            raise PrinterError(f"{self.name}: not connected", error_code="PRINTER_001")
        mode = self._next_failure()
        if mode and mode != "success":
            self._raise_for_mode(mode)
        with self._lock:
            self._fifo_pending += 1
            # The X1's photocell fires the physical print; the simulator
            # models that as an immediate consumption for determinism.
            self._consumed_count += 1
            self._fifo_pending -= 1

    def get_consumption_count(self) -> int:
        with self._lock:
            return self._consumed_count
