"""Zebra printer adapter (Section 25/27). Raw TCP printing to the printer's
print service (commonly port 9100), plus best-effort status via the ZPL
Host Status command (~HS).

The ~HS response layout is standard across Zebra ZPL II printers but not
every field is populated identically on every model/firmware (the plan
explicitly warns: "Do not assume every Zebra model exposes exactly the same
status features" -- Section 27). Parsing here is defensive: any field it
cannot confidently interpret falls back to PrinterStatus.UNKNOWN rather than
guessing READY.
"""
from __future__ import annotations

import socket
import time

from app.domain.models import LabelData, PrinterStatusInfo
from app.domain.states import PrinterStatus
from app.printers.base import BasePrinter, PrinterError
from app.printers.template_engine import render_template


class ZebraPrinter(BasePrinter):
    def __init__(self, name: str, address: str, port: int = 9100, connect_timeout: float = 5.0):
        self.name = name
        self.address = address
        self.port = port
        self.connect_timeout = connect_timeout
        self._sock: socket.socket | None = None

    def connect(self) -> None:
        try:
            sock = socket.create_connection((self.address, self.port), timeout=self.connect_timeout)
        except OSError as exc:
            raise PrinterError(f"Cannot reach Zebra printer {self.name} at {self.address}:{self.port}: {exc}",
                                error_code="PRINTER_001") from exc
        self._sock = sock

    def disconnect(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            finally:
                self._sock = None

    def _ensure_connected(self) -> socket.socket:
        if self._sock is None:
            self.connect()
        assert self._sock is not None
        return self._sock

    def print_label(self, template: str, label: LabelData) -> None:
        """Send a fully rendered ZPL document. The caller is responsible for
        persisting a PrintAttempt row before/after this call (Section 19) --
        this adapter only talks to the socket."""
        zpl = render_template(template, label)
        sock = self._ensure_connected()
        try:
            sock.sendall(zpl.encode("utf-8"))
        except OSError as exc:
            # Connection may have dropped mid-send: we cannot be sure whether
            # the printer received a complete label (Section 39).
            self.disconnect()
            raise PrinterError(f"Zebra send failed for {self.name}: {exc}", error_code="PRINT_002",
                                uncertain=True) from exc

    def get_status(self) -> PrinterStatusInfo:
        try:
            sock = self._ensure_connected()
            sock.sendall(b"~HS")
            time.sleep(0.2)
            sock.settimeout(2.0)
            raw = b""
            try:
                while True:
                    chunk = sock.recv(1024)
                    if not chunk:
                        break
                    raw += chunk
                    if len(raw) > 4096:
                        break
            except socket.timeout:
                pass
        except (OSError, PrinterError) as exc:
            return PrinterStatusInfo(status=PrinterStatus.OFFLINE, connected=False, detail=str(exc))

        text = raw.decode("ascii", errors="ignore")
        return self._parse_host_status(text)

    @staticmethod
    def _parse_host_status(text: str) -> PrinterStatusInfo:
        lines = [ln.strip("\x02\x03\r\n ") for ln in text.split("\r\n") if ln.strip("\x02\x03\r\n ")]
        if not lines:
            return PrinterStatusInfo(status=PrinterStatus.UNKNOWN, connected=True, raw_state=text,
                                      detail="No response to ~HS")

        try:
            line1 = lines[0].split(",")
            paper_out = line1[1].strip() == "1" if len(line1) > 1 else False
            paused = line1[2].strip() == "1" if len(line1) > 2 else False
        except (IndexError, ValueError):
            paper_out = paused = False

        ribbon_out = False
        head_open = False
        if len(lines) >= 3:
            try:
                line3 = lines[2].split(",")
                head_open = line3[7].strip() == "1" if len(line3) > 7 else False
                ribbon_out = line3[8].strip() == "1" if len(line3) > 8 else False
            except (IndexError, ValueError):
                pass

        if head_open:
            return PrinterStatusInfo(status=PrinterStatus.HEAD_OPEN, connected=True, raw_state=text,
                                      fault_code="PRINTER_004")
        if ribbon_out:
            return PrinterStatusInfo(status=PrinterStatus.RIBBON_OUT, connected=True, raw_state=text,
                                      fault_code="PRINTER_003")
        if paper_out:
            return PrinterStatusInfo(status=PrinterStatus.MEDIA_OUT, connected=True, raw_state=text,
                                      fault_code="PRINTER_002")
        if paused:
            return PrinterStatusInfo(status=PrinterStatus.PAUSED, connected=True, raw_state=text)
        return PrinterStatusInfo(status=PrinterStatus.READY, connected=True, raw_state=text)

    def test_print(self) -> bool:
        test_label = LabelData(product_name="TEST", serial_number="TEST0000", batch_number="TEST")
        template = "^XA\n^FO50,50^A0N,30,30^FD{PRODUCT_NAME} TEST PRINT^FS\n^FO50,100^A0N,24,24^FD{SERIAL_NUMBER}^FS\n^XZ\n"
        try:
            self.print_label(template, test_label)
            return True
        except PrinterError:
            return False
