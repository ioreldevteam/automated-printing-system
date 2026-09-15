"""CUPS printer adapter for locally installed printers such as Epson LQ-310."""
from __future__ import annotations

import shutil
import subprocess

from app.domain.models import LabelData, PrinterStatusInfo
from app.domain.states import PrinterStatus
from app.printers.base import BasePrinter, PrinterError


class CupsPrinter(BasePrinter):
    def __init__(self, name: str, uri: str = "", connect_timeout: float = 5.0):
        self.name = name
        self.uri = uri
        self.connect_timeout = connect_timeout

    def _lpstat(self, *args: str) -> subprocess.CompletedProcess[str]:
        executable = shutil.which("lpstat")
        if executable is None:
            raise PrinterError("CUPS lpstat command is not installed", error_code="PRINTER_001")
        try:
            return subprocess.run(
                [executable, *args], check=False, capture_output=True, text=True,
                timeout=self.connect_timeout,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise PrinterError(f"CUPS status failed for {self.name}: {exc}", error_code="PRINTER_001") from exc

    def connect(self) -> None:
        result = self._lpstat("-p", self.name)
        if result.returncode != 0:
            raise PrinterError(result.stderr.strip() or f"CUPS printer {self.name} is unavailable",
                               error_code="PRINTER_001")

    def disconnect(self) -> None:
        pass

    def get_status(self) -> PrinterStatusInfo:
        try:
            result = self._lpstat("-p", self.name)
        except PrinterError as exc:
            return PrinterStatusInfo(status=PrinterStatus.OFFLINE, connected=False, detail=str(exc))
        if result.returncode != 0:
            return PrinterStatusInfo(status=PrinterStatus.OFFLINE, connected=False,
                                     detail=result.stderr.strip() or "CUPS printer unavailable")
        text = result.stdout.strip()
        lowered = text.lower()
        if "disabled" in lowered:
            status = PrinterStatus.PAUSED
        elif "printing" in lowered:
            status = PrinterStatus.BUSY
        else:
            status = PrinterStatus.READY
        return PrinterStatusInfo(status=status, connected=True, raw_state=text, detail=text)

    def print_label(self, template: str, label: LabelData) -> None:
        del template
        executable = shutil.which("lp")
        if executable is None:
            raise PrinterError("CUPS lp command is not installed", error_code="PRINTER_001")
        document = (
            f"PRODUCT: {label.product_name}\n"
            f"SERIAL: {label.serial_number}\n"
            f"BATCH: {label.batch_number}\n"
            f"DATE: {label.date}\n"
        )
        try:
            result = subprocess.run(
                [executable, "-d", self.name, "-o", "raw"], input=document,
                check=False, capture_output=True, text=True, timeout=self.connect_timeout,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise PrinterError(f"CUPS print failed for {self.name}: {exc}", error_code="PRINT_002",
                               uncertain=True) from exc
        if result.returncode != 0:
            raise PrinterError(result.stderr.strip() or f"CUPS rejected print for {self.name}",
                               error_code="PRINT_002")

    def test_print(self) -> bool:
        test_label = LabelData(product_name="TEST", serial_number="TEST0000", batch_number="TEST")
        try:
            self.print_label("", test_label)
            return True
        except PrinterError:
            return False