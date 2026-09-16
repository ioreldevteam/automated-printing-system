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
        # See flush_batch(): labels are buffered and sent to CUPS as one `lp`
        # job instead of one `lp` invocation per label, so a whole batch's
        # quantity prints together from a single submission.
        self._pending_documents: list[str] = []

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

    @staticmethod
    def _render_document(label: LabelData) -> str:
        return (
            f"PRODUCT: {label.product_name}\n"
            f"SERIAL: {label.serial_number}\n"
            f"BATCH: {label.batch_number}\n"
            f"DATE: {label.date}\n"
            "\f"  # form feed: force a page eject after this label. Without
                  # it, "-o raw" text jobs on many generic/text-only CUPS
                  # drivers never signal the printer to advance to a new
                  # page between labels concatenated into one `lp` job, so a
                  # whole batch of labels can land on a single physical
                  # page/strip instead of one page per label.
        )

    def _submit(self, document: str) -> None:
        executable = shutil.which("lp")
        if executable is None:
            raise PrinterError("CUPS lp command is not installed", error_code="PRINTER_001")
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

    def print_label(self, template: str, label: LabelData) -> None:
        """Buffer this label rather than submitting a separate `lp` job for
        it immediately. Call flush_batch() to submit everything buffered so
        far as one job (one page per label, via the form feed above)."""
        del template
        self._pending_documents.append(self._render_document(label))

    def supports_batch_printing(self) -> bool:
        return True

    def flush_batch(self) -> None:
        if not self._pending_documents:
            return
        document = "".join(self._pending_documents)
        try:
            self._submit(document)
        except PrinterError:
            # Keep what's buffered so the caller can retry the whole batch
            # rather than silently losing labels that never printed.
            raise
        self._pending_documents.clear()

    def test_print(self) -> bool:
        # Submitted immediately/standalone -- a test print shouldn't sit
        # behind whatever a real job has buffered.
        test_label = LabelData(product_name="TEST", serial_number="TEST0000", batch_number="TEST")
        try:
            self._submit(self._render_document(test_label))
            return True
        except PrinterError:
            return False